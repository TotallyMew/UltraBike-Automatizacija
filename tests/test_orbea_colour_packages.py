from __future__ import annotations

import html
import json
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image
from openpyxl import load_workbook

from tests.test_orbea_photo_downloader import _Session, _image_bytes, ASSET_HASH, ASSET_ROOT
from tools.orbea_automation.catalogue import CatalogueEntry, MatchResult
from tools.orbea_automation.models import OrbeaRunConfig
from tools.orbea_automation.photos import OrbeaPhotoService, parse_orbea_photo_product
from tools.orbea_automation.photo_packages import match_photo_colour
from tools.orbea_automation.service import OrbeaAutomationService
from tools.orbea_automation.upload import OrbeaUploadService
from tools.orbea_automation.website import parse_website_product

URL = "https://www.orbea.com/en-be/alma-h20"
MODEL = "ALMA H20"
COLOURS = {
    "R6": ("Frozen Concrete - Titanium", (150, 150, 150, 255)),
    "R8": ("Diamond Black - Titan Black", (5, 5, 5, 255)),
    "R7": ("Aloha Green - Acid Gum", (0, 180, 80, 255)),
    "R9": ("Unused Red", (255, 0, 0, 255)),
}
PRODUCTS = (
    ("U21005R6", "Orbea ALMA H20 Frozen Concrete - Titanium (Gloss)"),
    ("U21007R8", "Orbea ALMA H20 Diamond Black (Matt) - Titan Black (Gloss)"),
    ("U21009R7", "Orbea ALMA H20 Aloha Green - Acid Gum (Gloss)"),
)


def page():
    template = {"name": MODEL, "code": "U210TTCC", "hash": ASSET_HASH,
        "views": [{"type": view, "status": "published"} for view in ("side", "front")],
        "zones": [{"identifier": "C1", "type": "frame", "default_color": "R6",
                   "colors": [{"color": {"code": code, "name": {"en": name}, "status": "published"}}
                              for code, (name, _) in COLOURS.items()]}]}
    initializer = "currentTemplate = JSON.parse('" + json.dumps(template) + "');"
    return '<main><h1>ALMA H20</h1><div id="product-bike-detail" x-init="' + html.escape(initializer, quote=True) + '"></div></main>'


class Website:
    def __init__(self):
        self.product = replace(parse_website_product(page(), URL),
            description_html="<p>Verified Alma description.</p>", specifications_text="Frame: Aluminium")
        self.fetches = []
        self.lookups = []

    def fetch(self, url):
        self.fetches.append(url)
        return self.product

    def lookup(self, sku, title):
        self.lookups.append(sku)
        return MatchResult("code_match", "Orbea TTCC", CatalogueEntry("U210", "U210TTCC", MODEL, product_link=URL))

    def close(self):
        pass

    cancel = close


class Photos(OrbeaPhotoService):
    def __init__(self, session):
        super().__init__(session)
        self.calls = []

    def run_from_html(self, *args, **kwargs):
        self.calls.append(tuple(kwargs.get("variant_codes") or ()))
        return super().run_from_html(*args, **kwargs)


def photo_session():
    manifest = {"hash": ASSET_HASH, "base": {view: ["base"] for view in ("side", "front")},
                "zones": {"C1": {"views": {"side": list(COLOURS)}}}, "components": []}
    responses = {f"{ASSET_ROOT}/manifest.json": json.dumps(manifest).encode(),
                 **{f"{ASSET_ROOT}/{view}/base/XL/base.webp": _image_bytes((255, 255, 255, 255)) for view in ("side", "front")},
                 **{f"{ASSET_ROOT}/side/C1/XL/C1-{code}.webp": _image_bytes(pixel) for code, (_, pixel) in COLOURS.items()}}
    return _Session(responses)


def run(root, products=PRODUCTS, *, settings=None, website=None, photos=None, **kwargs):
    website = website or Website()
    photos = photos or Photos(photo_session())
    settings = settings or OrbeaRunConfig(None, root / "runs", collect_product_data=True,
        download_images=False, download_product_photos=True, download_description=False, download_specifications=False)
    def scan(client, catalogue, checkpoint, config, **unused):
        for index, (sku, title) in enumerate(products):
            checkpoint.upsert_result({"row_key": f"p{index}", "product_id": f"p{index}", "sku": sku,
                "title": title, "status": "unmatched", "product_url": f"https://pim.bo.ultrabike.lt/dashboard/products/p{index}"})
        checkpoint.data["scan_completed"] = True
        checkpoint.save()
    service = OrbeaAutomationService(object(), website_client_factory=lambda *args: website, photo_service_factory=lambda: photos)
    with patch("tools.orbea_automation.service.PimboBrowserClient.collect", scan):
        result = service.run(settings, **kwargs)
    return result, website, photos


def records(result):
    return json.loads(result.checkpoint_path.read_text(encoding="utf-8"))["results"]


def test_three_alma_colours_share_one_download_and_have_exact_sku_subfolders(tmp_path):
    result, website, photos = run(tmp_path, resume=False)
    assert result.completed
    assert website.fetches == [URL] and len(website.lookups) == 1
    assert photos.calls == [("R6", "R8", "R7")]
    assert photos._external_session.calls.count(f"{ASSET_ROOT}/manifest.json") == 1
    assert len(photos._external_session.calls) == 6  # One manifest, two shared bases, three colour layers.
    assert not any("R9" in url for url in photos._external_session.calls)
    parent = result.run_dir / "products" / "U210TTCC"
    assert {folder.name for folder in parent.iterdir()} == {sku for sku, _ in PRODUCTS}
    for row in records(result):
        folder = result.run_dir / row["local_folder"]
        stage = row["collection_stages"]["photos"]
        assert folder == parent / row["sku"]
        assert stage["colour"] == COLOURS[stage["colour_code"]][0]
        candidates = OrbeaUploadService.local_photo_candidates(folder)
        assert len(candidates) == 2
        assert {path.name for path in candidates} == {stage["colour_code"] + "_" + view + ".png" for view in ("side", "front")}
        with Image.open(folder / "photos" / (stage["colour_code"] + "_side.png")) as image:
            assert image.convert("RGBA").getpixel((0, 0)) == COLOURS[stage["colour_code"]][1]
    assert len(OrbeaUploadService.load_local_packages(parent)) == 3
    book = load_workbook(result.workbook_path, data_only=True)
    headers = [cell.value for cell in book["Collected Products"][1]]
    assert "Photo colour" in headers and "Photo colour code" in headers
    book.close()


def test_colour_names_override_any_guess_based_on_the_sku_suffix(tmp_path):
    products = ((PRODUCTS[0][0], PRODUCTS[1][1]), (PRODUCTS[1][0], PRODUCTS[0][1]))
    result, _, photos = run(tmp_path, products, resume=False)
    assert result.completed
    rows = records(result)
    assert [row["collection_stages"]["photos"]["colour_code"] for row in rows] == ["R8", "R6"]
    assert len(photos.calls) == 1


@pytest.mark.parametrize("colour", ["Unknown Purple"])
def test_unmatched_colour_is_flagged_without_receiving_other_colours(tmp_path, colour):
    products = (PRODUCTS[0], (PRODUCTS[1][0], "Orbea ALMA H20 " + colour))
    result, _, photos = run(tmp_path, products, resume=False)
    assert not result.completed and photos.calls == [("R6",)]
    rows = records(result)
    assert rows[0]["collection_stages"]["photos"]["status"] == "downloaded"
    bad = rows[1]
    assert bad["collection_stages"]["photos"]["status"] == "error"
    folder = result.run_dir / bad["local_folder"]
    assert OrbeaUploadService.local_photo_candidates(folder) == ()
    assert colour in " | ".join(bad["collection_errors"])


def test_ambiguous_official_colour_names_do_not_pick_the_first_one():
    product = parse_orbea_photo_product(page(), URL)
    variants = tuple(replace(variant, name="Frozen Concrete - Titanium") for variant in product.variants[:2])
    with pytest.raises(ValueError, match="ambiguous"):
        match_photo_colour(replace(product, variants=variants), {"title": PRODUCTS[0][1]}, source_model=MODEL)
    variant = match_photo_colour(product, {"title": "Orbea ALMA H20 2027 Frozen Concrete/Titanium (Gloss)"}, source_model=MODEL)
    assert variant.code == "R6"


def test_same_colour_at_different_sizes_is_downloaded_once(tmp_path):
    products = (("U21005R6", PRODUCTS[0][1]), ("U21009R6", PRODUCTS[0][1]))
    result, website, photos = run(tmp_path, products, resume=False)
    assert result.completed and website.fetches == [URL] and photos.calls == [("R6",)]
    assert len(photos._external_session.calls) == 4
    assert all(len(OrbeaUploadService.local_photo_candidates(result.run_dir / row["local_folder"])) == 2 for row in records(result))


def test_failure_of_one_colour_does_not_fail_the_other_colours(tmp_path):
    session = photo_session()
    del session.responses[f"{ASSET_ROOT}/side/C1/XL/C1-R6.webp"]
    result, _, photos = run(tmp_path, photos=Photos(session), resume=False)
    assert not result.completed and len(photos.calls) == 1
    assert [row["collection_stages"]["photos"]["status"] for row in records(result)] == ["error", "downloaded", "downloaded"]


def test_resume_skips_finished_models_and_missing_file_restores_only_its_colour(tmp_path):
    result, _, _ = run(tmp_path, resume=False)
    settings = OrbeaRunConfig(None, tmp_path / "runs", collect_product_data=True, download_images=False,
        download_product_photos=True, download_description=False, download_specifications=False, resume_run_dir=result.run_dir)
    resumed, website, photos = run(tmp_path, settings=settings, download_missing=True)
    assert resumed.completed and website.fetches == [] and photos.calls == []
    first = records(result)[0]
    missing = result.run_dir / first["collection_stages"]["photos"]["files"][0]
    missing.unlink()
    repaired, website, photos = run(tmp_path, settings=settings, download_missing=True)
    assert repaired.completed and website.fetches == [URL] and photos.calls == [("R6",)]
    assert photos._external_session.calls == [f"{ASSET_ROOT}/manifest.json"]
    assert missing.is_file()


def legacy_collection(tmp_path):
    settings = OrbeaRunConfig(None, tmp_path / "runs", collect_product_data=True, download_images=False,
        download_product_photos=False, download_description=True, download_specifications=True)
    result, _, _ = run(tmp_path, settings=settings, resume=False)
    assert result.completed
    data = json.loads(result.checkpoint_path.read_text(encoding="utf-8"))
    originals = {}
    for row in data["results"]:
        grouped = result.run_dir / row["local_folder"]
        flat = result.run_dir / "products" / row["sku"]
        grouped.rename(flat)
        previous = row["local_folder"]
        row["local_folder"] = str(flat.relative_to(result.run_dir))
        for stage in row["collection_stages"].values():
            stage["files"] = [row["local_folder"] + filename[len(previous):] for filename in stage.get("files", [])]
        (flat / "photos").mkdir()
        stale = flat / "photos" / "old-all-colours.png"
        stale.write_bytes(_image_bytes((255, 0, 0, 255)))
        row["collection_stages"]["photos"] = {"status": "downloaded", "files": [str(stale.relative_to(result.run_dir))]}
        metadata = flat / "orbea-product.json"
        saved = json.loads(metadata.read_text())
        saved["stages"] = row["collection_stages"]
        metadata.write_text(json.dumps(saved))
        ledger = flat / "orbea-upload-result.json"
        ledger.write_bytes(b'{"preserve-upload-history":true}')
        originals[row["sku"]] = {name: ((flat / name).read_bytes(), (flat / name).stat().st_mtime_ns)
            for name in ("description.html", "specifications.txt", "orbea-upload-result.json", "photos/old-all-colours.png")}
        assert OrbeaUploadService.local_photo_candidates(flat) == ()  # Unassigned old colours are not uploadable.
    result.checkpoint_path.write_text(json.dumps(data), encoding="utf-8")
    return result, settings, originals


def test_saved_flat_packages_are_grouped_without_losing_sources_or_upload_history(tmp_path):
    first, settings, originals = legacy_collection(tmp_path)
    settings = replace(settings, resume_run_dir=first.run_dir, download_product_photos=True)
    result, website, photos = run(tmp_path, settings=settings, download_missing=True)
    assert result.completed and website.fetches == [URL] and len(photos.calls) == 1
    for row in records(result):
        folder = result.run_dir / row["local_folder"]
        assert folder.parent.name == "U210TTCC" and folder.name == row["sku"]
        assert not (result.run_dir / "products" / row["sku"]).exists()
        for name, (content, modified) in originals[row["sku"]].items():
            preserved = folder / name if not name.startswith("photos/") else folder / "previous-photos" / Path(name).name
            assert preserved.read_bytes() == content
            assert preserved.stat().st_mtime_ns == modified
        metadata = json.loads((folder / "orbea-product.json").read_text())
        assert all((result.run_dir / filename).is_file() for stage in metadata["stages"].values() for filename in stage.get("files", []))
        candidates = OrbeaUploadService.local_photo_candidates(folder)
        assert len(candidates) == 2 and all("old-all-colours" not in path.name for path in candidates)
        assert {path.name for path in (folder / "photos").iterdir()} == {path.name for path in candidates}
    from tools.orbea_automation.saved_collection import open_saved_collection
    loaded, checkpoint = open_saved_collection(result.workbook_path, tmp_path / "unused")
    assert checkpoint.run_dir == result.run_dir and loaded.resume_run_dir == result.run_dir


def test_resume_repairs_a_move_interrupted_before_the_checkpoint_path_update(tmp_path):
    first, settings, originals = legacy_collection(tmp_path)
    initial = records(first)[0]
    flat = first.run_dir / initial["local_folder"]
    grouped = first.run_dir / "products" / "U210TTCC" / initial["sku"]
    flat.rename(grouped)  # Simulate a stop immediately after the directory move.
    settings = replace(settings, resume_run_dir=first.run_dir, download_product_photos=True)
    result, _, photos = run(tmp_path, settings=settings, download_missing=True)
    assert result.completed and len(photos.calls) == 1
    first_row = records(result)[0]
    assert result.run_dir / first_row["local_folder"] == grouped
    assert (grouped / "orbea-upload-result.json").read_bytes() == originals[first_row["sku"]]["orbea-upload-result.json"][0]
    assert all((result.run_dir / filename).is_file() for state in first_row["collection_stages"].values() for filename in state.get("files", []))


def test_selected_photo_service_colours_do_not_download_unused_variants(tmp_path):
    session = photo_session()
    result = OrbeaPhotoService(session).run_from_html(URL, page(), tmp_path, variant_codes=("R8",))
    assert result.variants == 1 and set(result.variant_files) == {"R8"}
    assert len(result.files) == 2
    assert not any("C1-R6" in url or "C1-R7" in url or "C1-R9" in url for url in session.calls)
    session = photo_session()
    with pytest.raises(ValueError, match="not published"):
        OrbeaPhotoService(session).run_from_html(URL, page(), tmp_path, variant_codes=("UNKNOWN",))
    assert session.calls == []
