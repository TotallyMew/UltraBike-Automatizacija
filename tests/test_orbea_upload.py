from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from PIL import Image

from Managers.PimboProductEditor import PimAiStepResult, PimPreparationResult, PimPreparationStatus
from tools.orbea_automation.upload import OrbeaUploadService, OrbeaWorkflowOptions
from tools.orbea_automation.specifications import build_orbea_specification_plan
from tools.orbea_automation.website import parse_website_product, read_component_dialog
from tools.orbea_automation.website import SPECIFICATIONS_CAPTURE_VERSION

SKU = "U10707SV"
URL = "https://www.orbea.com/en-be/orca-m30i"
PIMBO_URL = "https://pim.bo.ultrabike.lt/dashboard/products/p1"


def package(root, sku=SKU):
    folder = root / "products" / sku
    folder.mkdir(parents=True)
    stages = {}
    for stage, filename, content in (
        ("description", "description.html", "<h2>Orca</h2><p>Full feature description.</p>"),
        ("specifications", "specifications.txt", "Frame: Orbea carbon\nFork: Orbea carbon fork\nBrakes: Shimano disc\nWheels: Oquo RP35PRO"),
    ):
        (folder / filename).write_text(content, encoding="utf-8")
        stages[stage] = {"status": "downloaded", "files": [str(Path("products") / sku / filename)]}
        if stage == "specifications":
            stages[stage]["capture_version"] = SPECIFICATIONS_CAPTURE_VERSION
    for subfolder, filenames in (("photos", ("side.png", "thumbnail.png")), ("tables", ("geometry.png", "geometry-xs.png", "size-guide-cm.png"))):
        (folder / subfolder).mkdir()
        for filename in filenames:
            Image.new("RGB", (100, 100) if filename == "thumbnail.png" else (500, 400)).save(folder / subfolder / filename)
    metadata = {"schema_version": 1, "sku": sku, "pimbo_product_id": "p1", "pimbo_url": PIMBO_URL,
                "pimbo_product_name": "ORBEA ORCA M30i Black (Gloss)", "orbea_url": URL,
                "orbea_product_name": "ORCA M30i", "status": "collected", "stages": stages}
    (folder / "orbea-product.json").write_text(json.dumps(metadata), encoding="utf-8")
    return folder


class Editor:
    def __init__(self):
        self.calls = []
        self.values = {}
        self.non_draft = False

    def begin(self, code):
        self.calls.append("begin")
        return PimPreparationResult(code, "p1", final_url=PIMBO_URL, status=PimPreparationStatus.BLOCKED_NON_DRAFT if self.non_draft else PimPreparationStatus.FAILED)

    def is_dirty(self):
        return False

    def collect_variant_sizes(self):
        self.calls.append("variants")
        return ("L", "S", "M")

    def set_specifications(self, values, **kwargs):
        assert kwargs["overwrite"] is True
        self.values.update(values)
        self.calls.append("prefill")
        return dict.fromkeys(dict(values), True)

    def upload_product_images(self, paths, **kwargs):
        paths = tuple(paths)
        assert len(paths) == 1 and paths[0].parent.name == "photos"
        self.calls.append("photos")
        return 1

    def upload_geometry_images(self, paths, **kwargs):
        assert {path.name for path in paths} == {"geometry.png", "geometry-xs.png"}
        self.calls.append("geometry")
        return 2

    def upload_size_table_images(self, paths, **kwargs):
        assert [path.name for path in paths] == ["size-guide-cm.png"]
        self.calls.append("size")
        return 1

    def set_description_html(self, value):
        assert "Full feature description" in value
        self.calls.append("description")
        return True

    def generate_description(self):
        self.calls.append("description_ai")
        return PimAiStepResult("description", True, True)

    def ensure_product_family(self, value):
        assert value == "Dviračiai"
        self.calls.append("family")
        return True

    def product_family(self):
        return "Dviračiai"

    def set_brand(self, value):
        assert value == "Orbea"
        self.calls.append("brand")
        return True

    def suggest_category(self, value):
        self.calls.append("category")
        return PimAiStepResult("category", True, True)

    def ensure_lithuanian_name_from_english(self):
        self.calls.append("name")
        return True

    def translate_lt_to_all(self, *, overwrite):
        assert overwrite is True
        self.calls.append("translations")
        return PimAiStepResult("translations", True, True)

    def switch_locale(self, locale):
        assert locale == "lt"

    def fill_empty_specifications_with_ai(self, source, *, excluded_fields=()):
        assert "Oquo RP35PRO" in source and "Orbea carbon fork" in source
        self.ai_source = source
        self.ai_exclusions = tuple(excluded_fields)
        self.calls.append("specifications_ai")
        return PimAiStepResult("specifications", True, True)

    def finish(self, result, **kwargs):
        return replace(result, status=PimPreparationStatus.READY_FOR_REVIEW, **{key: tuple(value) for key, value in kwargs.items()})

    def save_and_verify(self, result):
        self.calls.append("save")
        return replace(result, status=PimPreparationStatus.SAVED_AUTOMATICALLY)


def service(editor, product_id="p1", name="ORBEA ORCA M30i Black (Gloss)"):
    driver = SimpleNamespace(current_url=PIMBO_URL)
    target = SimpleNamespace(status="pimbo_found", pimbo_product_id=product_id,
                             pimbo_product_name=name, pimbo_product_url=PIMBO_URL)
    return OrbeaUploadService(driver, editor_factory=lambda _: editor,
                             pimbo_client_factory=lambda _: SimpleNamespace(find_by_variant_sku=lambda sku: target))


def test_collected_package_full_upload_uses_correct_assets_and_two_saves(tmp_path):
    folder = package(tmp_path)
    matches = OrbeaUploadService.load_local_packages(tmp_path)
    assert len(matches) == 1 and matches[0].variant_skus == (SKU,)
    editor = Editor()
    with patch("tools.supplier_upload.time.sleep"):
        result = service(editor).upload_and_save(matches[0])
    assert result.succeeded and set(result.completed_stages) == set(OrbeaWorkflowOptions.STAGES)
    assert editor.calls == ["begin", "variants", "photos", "size", "geometry", "description", "description_ai",
                            "family", "brand", "category", "name", "translations", "save", "begin", "prefill", "specifications_ai", "save"]
    assert editor.values["Modelis"] == "Orbea ORCA M30i"
    assert editor.values["Spalva"] == "Black"
    assert "Lako užbaigimas" not in editor.values
    assert set(editor.ai_exclusions) == {"Ratų dydis", "Lako užbaigimas"}
    assert editor.values["Galimi rėmo dydžiai"] == "S, M, L"
    assert set(editor.values) == {"Modelis", "Spalva", "Galimi rėmo dydžiai"}
    assert "Fork: Orbea carbon fork" in editor.ai_source
    assert "Ratų dydis" not in editor.values
    saved = json.loads((folder / "orbea-upload-result.json").read_text())
    assert saved["preparation"]["status"] == "saved_automatically"


def test_fresh_sku_verification_cannot_redirect_package_to_another_product(tmp_path):
    package(tmp_path)
    editor = Editor()
    result = service(editor, "other-product").upload_and_save(OrbeaUploadService.load_local_packages(tmp_path)[0])
    assert not result.succeeded and "different PIMBO product" in result.preparation.error
    assert editor.calls == []


def test_non_draft_blocks_all_edits(tmp_path):
    package(tmp_path)
    editor = Editor()
    editor.non_draft = True
    result = service(editor).upload_and_save(OrbeaUploadService.load_local_packages(tmp_path)[0])
    assert result.preparation.status == PimPreparationStatus.BLOCKED_NON_DRAFT
    assert editor.calls == ["begin"]


def test_missing_source_specs_fail_without_feeding_name_only_data_to_ai(tmp_path):
    folder = package(tmp_path)
    (folder / "specifications.txt").unlink()
    editor = Editor()
    result = service(editor).upload_and_save(OrbeaUploadService.load_local_packages(tmp_path)[0],
        options=OrbeaWorkflowOptions.only("specifications_prefill", "specifications_magic_ai"))
    assert "prefill" not in editor.calls and "specifications_ai" not in editor.calls
    assert "save" not in editor.calls and not result.succeeded
    assert result.preparation.status == PimPreparationStatus.FAILED
    assert any("No saved Orbea component specifications" in warning for warning in result.preparation.warnings)
    assert result.completed_stages == ()


def test_missing_description_blocks_description_ai_and_automatic_save(tmp_path):
    folder = package(tmp_path)
    (folder / "description.html").unlink()
    editor = Editor()
    result = service(editor).upload_and_save(OrbeaUploadService.load_local_packages(tmp_path)[0],
        options=OrbeaWorkflowOptions.only("description_source", "description_magic_ai", "save"))
    assert not result.succeeded and "save" not in editor.calls and "description_ai" not in editor.calls
    assert result.preparation.warnings


def test_confirmed_unpublished_description_skips_description_steps_without_blocking_save(tmp_path):
    folder = package(tmp_path)
    path = folder / "orbea-product.json"
    metadata = json.loads(path.read_text())
    metadata["stages"]["description"] = {"status": "not_available", "files": [], "source": "not_available"}
    path.write_text(json.dumps(metadata))
    editor = Editor()
    result = service(editor).upload_and_save(OrbeaUploadService.load_local_packages(tmp_path)[0],
        options=OrbeaWorkflowOptions.only("description_source", "description_magic_ai", "save"))
    assert result.succeeded and not result.preparation.warnings
    assert "description" not in editor.calls and "description_ai" not in editor.calls
    assert result.completed_stages == ("description_source", "description_magic_ai", "save")


@pytest.mark.parametrize("stages", [("specifications_magic_ai",)])
def test_old_incomplete_specification_packages_are_blocked_before_editing(tmp_path, stages):
    folder = package(tmp_path)
    path = folder / "orbea-product.json"
    metadata = json.loads(path.read_text())
    metadata["stages"]["specifications"]["capture_version"] = 1
    path.write_text(json.dumps(metadata))
    editor = Editor()
    result = service(editor).upload_and_save(OrbeaUploadService.load_local_packages(tmp_path)[0],
        options=OrbeaWorkflowOptions.only(*stages))
    assert not result.succeeded and "recollect specifications" in result.preparation.error
    assert editor.calls == []


def test_description_source_failure_blocks_save_even_without_description_ai(tmp_path):
    folder = package(tmp_path)
    (folder / "description.html").unlink()
    editor = Editor()
    result = service(editor).upload_and_save(OrbeaUploadService.load_local_packages(tmp_path)[0],
        options=OrbeaWorkflowOptions.only("description_source", "save"))
    assert result.preparation.status == PimPreparationStatus.FAILED
    assert "save" not in editor.calls


def test_failed_ai_result_blocks_supplier_save(tmp_path):
    package(tmp_path)
    editor = Editor()
    editor.generate_description = lambda: PimAiStepResult("description", False, detail="Failed generation")
    result = service(editor).upload_and_save(OrbeaUploadService.load_local_packages(tmp_path)[0],
        options=OrbeaWorkflowOptions.only("description_source", "description_magic_ai", "save"))
    assert result.preparation.status == PimPreparationStatus.FAILED
    assert "save" not in editor.calls
    assert "Failed generation" in result.preparation.error


def test_missing_prefill_field_blocks_completion_and_second_save(tmp_path):
    package(tmp_path)
    editor = Editor()
    editor.set_specifications = lambda values, **kwargs: {key: None if key == "Modelis" else True for key, value in values}
    result = service(editor).upload_and_save(OrbeaUploadService.load_local_packages(tmp_path)[0],
        options=OrbeaWorkflowOptions.only("specifications_prefill", "save"))
    assert result.preparation.status == PimPreparationStatus.FAILED
    assert editor.calls.count("save") == 1
    assert "Modelis" in " ".join(result.preparation.warnings)


def test_invalid_package_is_visible_but_cannot_be_selected(tmp_path):
    folder = tmp_path / "broken"
    folder.mkdir()
    (folder / "orbea-product.json").write_text("not-json")
    matches = OrbeaUploadService.load_local_packages(tmp_path)
    assert len(matches) == 1 and matches[0].status == "invalid" and not matches[0].ready


def test_same_sku_for_distinct_pimbo_owners_is_not_silently_combined(tmp_path):
    one = package(tmp_path / "one")
    two = package(tmp_path / "two")
    data = json.loads((two / "orbea-product.json").read_text())
    data["pimbo_product_id"] = "p2"
    (two / "orbea-product.json").write_text(json.dumps(data))
    assert len(OrbeaUploadService.load_local_packages(tmp_path)) == 2


def test_specification_plan_retains_unmapped_source_rows_and_never_guesses_wheel_size():
    product = SimpleNamespace(name="ALMA CARBON")
    plan = build_orbea_specification_plan("ORBEA ALMA CARBON Galactic Rainbow-Sunset C.View (Gloss)",
        ("XL", "M", "S", "M"), "Cuadro: Orbea Alma Carbon\nHorquilla: Fox 32\nWheels: Oquo", product=product)
    values = dict(plan.values)
    assert values["Spalva"] == "Galactic Rainbow - Sunset C.View"
    assert "Šakė" not in values and values["Galimi rėmo dydžiai"] == "S, M, XL"
    assert "Horquilla: Fox 32" in plan.magic_ai_source
    assert "Wheels: Oquo" in plan.magic_ai_source and "Ratų dydis" not in values


@pytest.mark.parametrize("color, expected", [
    ("Caramel C. View (Matt)- Titan Gold (Gloss)", "Caramel C. View - Titan Gold"),
    ("Desert Rose (Matt) - Carbon Raw (Gloss)", "Desert Rose - Carbon Raw"),
    ("Black (Matte)", "Black"),
    ("White (Glossy)", "White"),
    ("Custom", None),
    ("custom (Matt)", None),
])
def test_orbea_full_pimbo_model_and_clean_color(color, expected):
    plan = build_orbea_specification_plan(
        f"Orbea RISE LT M30 420W 2027 {color}", ("L", "S", "M"),
        "Fork: Fox 36\nWheel size: 29\nRatų dydis: 29\nLako užbaigimas: Matt\nPaint finish: Gloss",
        product=SimpleNamespace(name="RISE LT M30"),
    )
    values = dict(plan.values)
    assert values["Modelis"] == "Orbea RISE LT M30 420W 2027"
    assert values.get("Spalva") == expected
    assert values["Galimi rėmo dydžiai"] == "S, M, L"
    assert "Lako užbaigimas" not in values and "Ratų dydis" not in values
    assert "Lako užbaigimas" not in plan.magic_ai_source and "Wheel size" not in plan.magic_ai_source
    assert "(Matt)" not in plan.magic_ai_source and "(Gloss)" not in plan.magic_ai_source


@pytest.mark.parametrize("sizes, expected", [
    (("XL", "M", "XS", "L", "S", "M"), "XS, S, M, L, XL"),
    (("63", "51", "45", "49", "51", "57"), "45, 49, 51, 57, 63"),
    (("55.5", "45", "51"), "45, 51, 55.5"),
])
def test_orbea_variant_sizes_sort_smallest_to_biggest(sizes, expected):
    plan = build_orbea_specification_plan("Orbea ORCA M30i 2027 Black (Gloss)", sizes,
        "Fork: Carbon", product=SimpleNamespace(name="ORCA M30i"))
    assert dict(plan.values)["Galimi rėmo dydžiai"] == expected


@pytest.mark.parametrize("stages", [
    ("specifications_prefill", "specifications_magic_ai"),
    ("specifications_prefill", "specifications_magic_ai", "save"),
    ("specifications_magic_ai",),
    ("specifications_magic_ai", "save"),
])
def test_custom_orbea_keeps_color_wheels_and_finish_manual_in_every_ai_path(tmp_path, stages):
    package(tmp_path)
    editor = Editor()
    match = OrbeaUploadService.load_local_packages(tmp_path)[0]
    with patch("tools.supplier_upload.time.sleep"):
        result = service(editor, name="Orbea ORCA M30i 2027 Custom").upload_and_save(
            match, options=OrbeaWorkflowOptions.only(*stages))
    assert result.succeeded
    assert set(editor.ai_exclusions) == {"Spalva", "Ratų dydis", "Lako užbaigimas"}
    assert not {"Spalva", "Ratų dydis", "Lako užbaigimas"}.intersection(editor.values)
    if "specifications_prefill" in stages:
        assert editor.values["Modelis"] == "Orbea ORCA M30i 2027"


def test_local_package_sku_change_is_rejected_before_edits(tmp_path):
    package(tmp_path)
    match = OrbeaUploadService.load_local_packages(tmp_path)[0]
    editor = Editor()
    result = service(editor).upload_and_save(replace(match, sku="U99999XX"))
    assert not result.succeeded and "not U99999XX" in result.preparation.error
    assert not editor.calls


def test_failed_preparation_retains_freshly_verified_target_for_batch_recovery(tmp_path):
    folder = package(tmp_path)
    metadata_path = folder / "orbea-product.json"
    metadata = json.loads(metadata_path.read_text())
    metadata.update(pimbo_product_id="", pimbo_url="")
    metadata_path.write_text(json.dumps(metadata))
    (folder / "specifications.txt").write_text("Fork: Carbon\nFork: Suspension")
    match = OrbeaUploadService.load_local_packages(tmp_path)[0]
    assert not match.pimbo_product_id and not match.pimbo_product_url
    editor = Editor()
    editor.collect_variant_sizes = lambda: (_ for _ in ()).throw(RuntimeError("Variants did not become ready"))
    uploader = service(editor)
    visited = []
    def navigate(url):
        visited.append(url)
        uploader.pimbo_driver.current_url = url
    uploader.pimbo_driver.get = navigate
    result = uploader.upload_and_save(match, options=OrbeaWorkflowOptions.only("specifications_prefill", "save"))
    assert not result.succeeded and "Variants did not become ready" in result.preparation.error
    assert result.match.pimbo_product_id == result.preparation.product_id == "p1"
    assert result.match.pimbo_product_url == result.preparation.final_url == PIMBO_URL
    assert uploader.recover_after_failed_upload(result.match)
    assert visited == ["https://pim.bo.ultrabike.lt/dashboard/products"]


@pytest.mark.parametrize("stages", [("specifications_prefill",), ("specifications_magic_ai",)])
def test_existing_packages_clean_configurator_text_on_load(tmp_path, stages):
    folder = package(tmp_path)
    (folder / "specifications.txt").write_text(
        "Crankset: Shimano Cues 34x50T € 0 More information\nCrankset: Shimano Cues 34x50T Incl.", encoding="utf-8")
    editor = Editor()
    sources = []
    def generate(source, **kwargs):
        sources.append(source)
        return PimAiStepResult("specifications", True, True)
    editor.fill_empty_specifications_with_ai = generate
    result = service(editor).upload_and_save(OrbeaUploadService.load_local_packages(tmp_path)[0],
        options=OrbeaWorkflowOptions.only(*stages))
    assert result.succeeded
    assert result.product.specification_text == "Crankset: Shimano Cues 34x50T"
    if "specifications_prefill" in stages:
        assert set(editor.values) == {"Modelis", "Spalva", "Galimi rėmo dydžiai"}
        assert not sources
    else:
        assert sources == ["Crankset: Shimano Cues 34x50T"]


def test_partial_package_exposes_collection_errors(tmp_path):
    folder = package(tmp_path)
    data = json.loads((folder / "orbea-product.json").read_text())
    data.update(status="partial", errors=["photos: download failed"])
    (folder / "orbea-product.json").write_text(json.dumps(data))
    match = OrbeaUploadService.load_local_packages(tmp_path)[0]
    assert match.ready and "photos: download failed" in match.note


def test_component_labels_in_product_and_outside_main_dialog_are_collected():
    source = '''<nav><span>Fork</span><span>Unrelated navigation</span></nav>
    <main><h1>ORCA M30i</h1><div id="product-bike-detail">
      <div><p>Frame</p><p>Orbea carbon</p></div>
      <div><div><span>Fork</span></div><div>Orbea ICR carbon fork</div></div>
    </div></main><div id="components-dialog"><dl><dt>Rear derailleur</dt><dd>Shimano 105</dd></dl>
    <table><tr><td>Wheels</td><td>Oquo RP35</td></tr></table></div>'''
    product = parse_website_product(source, URL)
    assert product.specifications_text.splitlines() == ["Rear derailleur: Shimano 105", "Wheels: Oquo RP35", "Frame: Orbea carbon", "Fork: Orbea ICR carbon fork"]
    assert "Unrelated navigation" not in product.specifications_text


def test_component_dialog_is_opened_read_and_closed_when_loaded_on_demand():
    class Element:
        def __init__(self, driver, kind):
            self.driver, self.kind = driver, kind
        def is_displayed(self):
            return self.kind == "button" or self.driver.opened
        def is_enabled(self):
            return True
        def click(self):
            self.driver.opened = True
        def get_attribute(self, name):
            if name == "aria-controls":
                return "components-dialog"
            return '<div id="components-dialog"><p>Frame</p><p>Orbea OMX</p><h3>Fork</h3><p>Orbea carbon</p></div>'
        def send_keys(self, keys):
            self.driver.opened = False
    class Driver:
        opened = False
        def find_elements(self, by, selector):
            if selector.startswith("button[aria-controls"):
                return [Element(self, "button")]
            if selector == "#components-dialog":
                return [Element(self, "dialog")]
            return []
        def find_element(self, by, selector):
            return Element(self, "body")
        def execute_script(self, *args):
            pass
    driver = Driver()
    assert read_component_dialog(driver, timeout=0.1, check=lambda: None) == "Frame: Orbea OMX\nFork: Orbea carbon"
    assert not driver.opened


def test_charger_and_all_other_components_are_sent_to_ai_without_field_mapping(tmp_path):
    folder = package(tmp_path)
    with (folder / "specifications.txt").open("a", encoding="utf-8") as stream:
        stream.write("\nCharger: TQ Charger 4A\nMotor: TQ-HPR40\nBattery: TQ HPR 290Wh\nWeight: 16 kg")
    editor = Editor()
    original = editor.set_specifications
    def set_name_fields(values, **kwargs):
        assert kwargs["move_if_empty"] == ()
        assert set(dict(values)) == {"Modelis", "Spalva", "Galimi rėmo dydžiai"}
        return original(values, **kwargs)
    editor.set_specifications = set_name_fields
    with patch("tools.supplier_upload.time.sleep"):
        result = service(editor).upload_and_save(OrbeaUploadService.load_local_packages(tmp_path)[0])
    assert result.succeeded and not result.preparation.warnings
    assert "Charger: TQ Charger 4A" in editor.ai_source
    assert "Motor: TQ-HPR40" in editor.ai_source and "Battery: TQ HPR 290Wh" in editor.ai_source
    assert "Weight: 16 kg" in editor.ai_source
    assert "Įkroviklis" not in editor.ai_source and "Įkroviklis (įtampa / srovė)" not in editor.values


def test_name_colour_and_size_prefill_does_not_require_a_component_scrape(tmp_path):
    folder = package(tmp_path)
    (folder / "specifications.txt").unlink()
    editor = Editor()
    result = service(editor).upload_and_save(OrbeaUploadService.load_local_packages(tmp_path)[0],
        options=OrbeaWorkflowOptions.only("specifications_prefill"))
    assert result.succeeded and not result.preparation.warnings
    assert set(editor.values) == {"Modelis", "Spalva", "Galimi rėmo dydžiai"}
    assert "specifications_ai" not in editor.calls


def saved_failed_upload(folder, *, completed=None):
    options = OrbeaWorkflowOptions.only(*(stage for stage in OrbeaWorkflowOptions.STAGES if stage not in {"brand", "product_photos"}))
    record = {"preparation": {"product_code": SKU, "product_id": "p1", "status": "failed", "error": "Specification enrichment failed"},
              "selected_stages": list(options.selected_stages),
              "completed_stages": completed or ["size_tables", "geometry", "description_source", "description_magic_ai",
                  "product_family", "category_magic_ai", "translations", "save"]}
    (folder / "orbea-upload-result.json").write_text(json.dumps(record), encoding="utf-8")
    return options


class ResumeEditor(Editor):
    def finish(self, result, **kwargs):
        status = PimPreparationStatus.READY_FOR_REVIEW if kwargs.get("changed_fields") else PimPreparationStatus.NO_CHANGES
        return replace(result, status=status, **{key: tuple(value) for key, value in kwargs.items()})


def test_retry_saved_specification_failure_runs_only_unsaved_specification_steps(tmp_path):
    folder = package(tmp_path)
    options = saved_failed_upload(folder)
    editor = ResumeEditor()
    match = OrbeaUploadService.load_local_packages(tmp_path)[0]
    with patch("tools.supplier_upload.time.sleep"):
        result = service(editor).upload_and_save(match, options=options, resume_completed=True)
    assert result.succeeded and result.options == options
    assert editor.calls == ["begin", "variants", "begin", "prefill", "specifications_ai", "save"]
    assert set(result.completed_stages) == set(options.selected_stages)
    assert OrbeaUploadService.upload_finished(match)


def test_repeated_specification_retry_preserves_the_earlier_saved_progress(tmp_path):
    folder = package(tmp_path)
    options = saved_failed_upload(folder)
    match = OrbeaUploadService.load_local_packages(tmp_path)[0]
    failed = ResumeEditor()
    failed.fill_empty_specifications_with_ai = lambda *args, **kwargs: PimAiStepResult("specifications", False, detail="temporary AI failure")
    with patch("tools.supplier_upload.time.sleep"):
        result = service(failed).upload_and_save(match, options=options, resume_completed=True)
    assert not result.succeeded and not OrbeaUploadService.upload_finished(match)
    assert "description_source" in OrbeaUploadService.saved_upload_stages(match)
    assert "specifications_prefill" not in OrbeaUploadService.saved_upload_stages(match)
    editor = ResumeEditor()
    with patch("tools.supplier_upload.time.sleep"):
        result = service(editor).upload_and_save(match, options=options, resume_completed=True)
    assert result.succeeded and "description" not in editor.calls and editor.calls.count("save") == 1


def test_confirmed_unpublished_tables_are_skipped_but_missing_published_files_fail(tmp_path):
    folder = package(tmp_path)
    metadata = folder / "orbea-product.json"
    data = json.loads(metadata.read_text())
    data["stages"]["tables"] = {"status": "not_available", "files": []}
    metadata.write_text(json.dumps(data))
    match = OrbeaUploadService.load_local_packages(tmp_path)[0]
    editor = ResumeEditor()
    result = service(editor).upload_and_save(match, options=OrbeaWorkflowOptions.only("geometry", "size_tables", "save"))
    assert result.succeeded and not result.preparation.warnings
    assert "geometry" not in editor.calls and "size" not in editor.calls
    assert {"geometry", "size_tables"} <= set(result.completed_stages)
    data["stages"]["tables"] = {"status": "downloaded", "files": ["tables/geometry.png", "tables/size-guide-cm.png"]}
    metadata.write_text(json.dumps(data))
    (folder / "tables/geometry.png").unlink()
    result = service(ResumeEditor()).upload_and_save(match, options=OrbeaWorkflowOptions.only("geometry", "save"))
    assert not result.succeeded and any("Geometry" in warning for warning in result.preparation.warnings)


def test_unsaved_review_progress_is_not_treated_as_a_saved_checkpoint(tmp_path):
    folder = package(tmp_path)
    saved_failed_upload(folder, completed=["description_source", "description_magic_ai"])
    match = OrbeaUploadService.load_local_packages(tmp_path)[0]
    assert OrbeaUploadService.saved_upload_stages(match) == ()
    assert not OrbeaUploadService.upload_finished(match)



def test_row_opening_failure_retries_the_sku_search_instead_of_failing_immediately():
    from tools.kross_automation.service import KrossPimboClient, PIMBO_PRODUCTS_URL
    driver = SimpleNamespace(current_url=PIMBO_PRODUCTS_URL)
    driver.get = lambda url: setattr(driver, "current_url", url)
    class Client(KrossPimboClient):
        searches = 0
        opens = 0
        def _ensure_list(self):
            pass
        def _search_field(self):
            return None
        def _candidate_snapshots(self):
            return []
        def _set_search(self, sku):
            self.searches += 1
        def _wait_for_fresh_candidates(self, signature):
            return [(0, "", "Orbea", SKU)]
        def _open_product_row(self, *args):
            self.opens += 1
            if self.opens == 1:
                raise RuntimeError("The matching PIMBO product row disappeared")
            driver.current_url = PIMBO_URL
        def _variant_skus(self, expected_sku=""):
            return {SKU}
        def _wait(self, predicate, message, timeout=None):
            value = predicate()
            if not value:
                raise RuntimeError(message)
            return value
    editor = SimpleNamespace(open_section=lambda _: None, product_name=lambda: "Orbea")
    client = Client(driver)
    with patch("tools.kross_automation.service.PimboProductEditor", lambda _: editor):
        result = client.find_by_variant_sku(SKU)
    assert result.status == "pimbo_found" and result.pimbo_product_id == "p1"
    assert client.searches == client.opens == 2


def test_failed_upload_recovery_does_not_require_save_to_be_disabled_after_reload():
    editor = Editor()
    uploader = service(editor)
    calls = []
    editor.is_dirty = lambda: True
    editor.wait_ready = lambda: None
    def navigate(url):
        calls.append(url)
        uploader.pimbo_driver.current_url = url
    uploader.pimbo_driver.get = navigate
    match = SimpleNamespace(sku=SKU, pimbo_product_id="p1", pimbo_product_url=PIMBO_URL)
    assert uploader.recover_after_failed_upload(match)
    assert calls == [PIMBO_URL, "https://pim.bo.ultrabike.lt/dashboard/products"]


def test_failed_upload_recovery_stops_if_reload_changes_the_product():
    from Managers.PimboProductEditor import PimAutomationError
    editor = Editor()
    uploader = service(editor)
    calls = []
    editor.is_dirty = lambda: True
    editor.wait_ready = lambda: None
    def navigate(url):
        calls.append(url)
        uploader.pimbo_driver.current_url = PIMBO_URL.replace("p1", "another-product")
    uploader.pimbo_driver.get = navigate
    match = SimpleNamespace(sku=SKU, pimbo_product_id="p1", pimbo_product_url=PIMBO_URL)
    with pytest.raises(PimAutomationError, match="changed while resetting"):
        uploader.recover_after_failed_upload(match)
    assert calls == [PIMBO_URL]


def test_batch_preflight_names_unsaved_product_and_does_not_navigate():
    from Managers.PimboProductEditor import PimAutomationError
    editor = Editor()
    editor.wait_ready = lambda: None
    editor.product_name = lambda: "Orbea AVANT H50"
    editor.is_dirty = lambda: True
    uploader = service(editor)
    uploader.pimbo_driver.get = lambda _: pytest.fail("Existing edits must not be discarded")
    with pytest.raises(PimAutomationError, match="unsaved changes: Orbea AVANT H50"):
        uploader.prepare_upload_batch((object(), object()))
    editor.is_dirty = lambda: False
    uploader.prepare_upload_batch((object(), object()))


def test_batch_preflight_preserves_single_product_review_behavior():
    uploader = service(Editor())
    uploader.editor_factory = lambda _: pytest.fail("Single-product review must not be blocked by batch preflight")
    uploader.prepare_upload_batch((object(),))


class PhotoGuardEditor(Editor):
    def __init__(self, sources):
        super().__init__()
        from tests.test_pimbo_photo_guard import GalleryEditor
        self.gallery = GalleryEditor(sources)
        self.photo_upload = {}

    def prepare_product_photo_upload(self, **kwargs):
        result = self.gallery.prepare_product_photo_upload(**kwargs)
        self.photo_upload = self.gallery.photo_upload
        return result

    def upload_product_images(self, paths, **kwargs):
        self.calls.append("photos")
        return self.gallery.upload_product_images(paths, **kwargs)


@pytest.mark.parametrize("local_photos", [True, False])
def test_real_pimbo_photos_skip_selected_photo_stage_even_without_local_photos(tmp_path, local_photos):
    folder = package(tmp_path)
    if not local_photos:
        (folder / "photos" / "side.png").unlink()
    editor = PhotoGuardEditor(["https://cdn.example.com/real.jpg"])
    result = service(editor).upload_and_save(OrbeaUploadService.load_local_packages(tmp_path)[0],
        options=OrbeaWorkflowOptions.only("product_photos", "save"))
    assert result.succeeded and "photos" not in editor.calls
    assert result.preparation.warnings == ()
    assert "product_photos" in result.completed_stages
    assert result.preparation.photo_upload["action"] == "skipped_existing"
    saved = json.loads((folder / "orbea-upload-result.json").read_text())
    assert saved["preparation"]["photo_upload"]["existing_photos"] == 1


def test_missing_local_photos_do_not_delete_only_placeholder(tmp_path):
    from tests.test_pimbo_photo_guard import PLACEHOLDER
    folder = package(tmp_path)
    (folder / "photos" / "side.png").unlink()
    editor = PhotoGuardEditor([PLACEHOLDER])
    result = service(editor).upload_and_save(OrbeaUploadService.load_local_packages(tmp_path)[0],
        options=OrbeaWorkflowOptions.only("product_photos", "save"))
    assert result.preparation.status == PimPreparationStatus.FAILED and "save" not in editor.calls
    assert editor.gallery.driver.clicked == []
    assert result.preparation.photo_upload["action"] == "failed"
    assert "No product photos" in result.preparation.photo_upload["error"]


def test_mixed_gallery_cleanup_is_saved_without_requiring_local_photos(tmp_path):
    from tests.test_pimbo_photo_guard import PLACEHOLDER
    folder = package(tmp_path)
    (folder / "photos" / "side.png").unlink()
    editor = PhotoGuardEditor([PLACEHOLDER, "https://cdn.example.com/real.jpg"])
    result = service(editor).upload_and_save(OrbeaUploadService.load_local_packages(tmp_path)[0],
        options=OrbeaWorkflowOptions.only("product_photos", "save"))
    assert result.succeeded and editor.calls == ["begin", "save"]
    assert "images" in result.preparation.changed_fields
    assert result.preparation.photo_upload["placeholders_removed"] == 1
    assert result.preparation.photo_upload["uploaded_photos"] == 0


def test_photo_result_survives_failed_specs_and_retry_of_only_unfinished_steps(tmp_path):
    from tests.test_pimbo_photo_guard import PLACEHOLDER
    folder = package(tmp_path)
    match = OrbeaUploadService.load_local_packages(tmp_path)[0]
    editor = PhotoGuardEditor([PLACEHOLDER])
    editor.set_specifications = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("Specs failed"))
    options = OrbeaWorkflowOptions.only("product_photos", "specifications_prefill", "save")
    failed = service(editor).upload_and_save(match, options=options)
    assert failed.preparation.status == PimPreparationStatus.FAILED and "save" in failed.completed_stages
    assert failed.preparation.photo_upload["uploaded_photos"] == 1
    retry = Editor()
    retry.prepare_product_photo_upload = lambda **kwargs: pytest.fail("Saved photos must not be retried")
    completed = service(retry).upload_and_save(match, options=options, resume_completed=True)
    assert completed.succeeded
    assert completed.preparation.photo_upload == failed.preparation.photo_upload
    assert json.loads((folder / "orbea-upload-result.json").read_text())["preparation"]["photo_upload"]["placeholders_removed"] == 1
