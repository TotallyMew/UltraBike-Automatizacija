"""Share one model's download pass and assign only its verified colour to each SKU."""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path

from .catalogue import normalize_code
from .checkpoint import utc_now, atomic_write_json
from .image_store import link_image
from .models import RunCancelled
from .photos import OrbeaPhotoService, OrbeaPhotoVariant, parse_orbea_photo_product
from .specifications import parse_orbea_name
from .utils import canonicalize_url, relative_or_absolute
from .website import template_code, product_matches

PHOTOS_CAPTURE_VERSION = 2


def _colour_key(value):
    value = re.sub(r"\(\s*(?:Glossy?|Matte?)\s*\)", "", str(value or ""), flags=re.I)
    return "".join(char for char in unicodedata.normalize("NFKD", value).casefold() if char.isalnum())


def pimbo_photo_colours(row, *, source_model="", photo_title=""):
    models = (source_model, row.get("catalogue_model", ""), photo_title,
              re.sub(r"\s+(?:19|20)\d{2}\s*$", "", photo_title))
    colours = []
    for model in models:
        if model:
            _, colour = parse_orbea_name(row.get("title", ""), source_model=model)
            if colour and colour not in colours:
                colours.append(colour)
    return colours


def match_photo_colour(photo_product, row, *, source_model=""):
    """Match names exactly after removing finishes, punctuation and spacing."""
    colours = pimbo_photo_colours(row, source_model=source_model, photo_title=photo_product.title)
    if any(_colour_key(colour) == "custom" for colour in colours):
        raise ValueError("Custom photos must come from the untouched Your Design gallery")
    candidates = {variant.code: variant for variant in photo_product.variants
                  if any(_colour_key(variant.name) == _colour_key(colour) for colour in colours)}
    if len(candidates) == 1:
        return next(iter(candidates.values()))
    available = "; ".join(variant.name for variant in photo_product.variants)
    detail = "ambiguous" if candidates else "not found"
    raise ValueError(f"Pimbo photo colour {detail}: {row.get('title', '')}. Published colours: {available}")


def package_folder(checkpoint, row):
    """Group sibling SKUs, retaining source files and upload results during a legacy move."""
    run_dir = checkpoint.run_dir.resolve()
    root = (run_dir / "products").resolve()
    if not root.is_relative_to(run_dir):
        raise ValueError("The products folder is outside the selected collection")
    sku = normalize_code(row.get("sku"))
    model = template_code(sku)
    url = canonicalize_url(row.get("catalogue_url", ""))
    siblings = [item for item in checkpoint.results if item.get("status") == "code_match"
                and template_code(item.get("sku", "")) == model
                and canonicalize_url(item.get("catalogue_url", "")) == url]
    grouped = bool(model and len({normalize_code(item.get("sku")) for item in siblings}) > 1)
    parent = root / model if grouped else root
    if grouped:
        urls = {canonicalize_url(item.get("catalogue_url", "")) for item in checkpoint.results
                if item.get("status") == "code_match" and template_code(item.get("sku", "")) == model}
        if len(urls) > 1:
            parent = root / (model + "-" + hashlib.sha256(url.encode()).hexdigest()[:8])
    destination = parent / sku

    def owns(folder):
        if not folder.resolve().is_relative_to(root):
            raise ValueError("The saved product folder is outside this collection's products folder")
        metadata = folder / "orbea-product.json"
        if not metadata.is_file():
            # Older interrupted collections can have verified checkpoint files but no metadata yet.
            owners = {item.get("product_id") for item in checkpoint.results if normalize_code(item.get("sku")) == sku}
            if owners != {row.get("product_id")}:
                return False
            return any((run_dir / filename).resolve().is_relative_to(folder.resolve())
                       and (run_dir / filename).is_file()
                       for stage in row.get("collection_stages", {}).values() for filename in stage.get("files", []))
        try:
            data = json.loads(metadata.read_text(encoding="utf-8-sig"))
            return normalize_code(data.get("sku")) == sku and data.get("pimbo_product_id") == row.get("product_id")
        except (OSError, ValueError, TypeError):
            return False

    source = None
    previous = (run_dir / row["local_folder"]).resolve() if row.get("local_folder") else root / sku
    for candidate in dict.fromkeys((previous, root / sku)):
        if candidate.is_dir() and owns(candidate):
            source = candidate
            break
    if source is not None and not grouped:
        destination = source  # A subset opened later keeps its existing grouped layout.
    if destination.exists() and not owns(destination):
        destination = destination.with_name(sku + "-" + hashlib.sha256(str(row.get("row_key")).encode()).hexdigest()[:8])
        if destination.exists() and not owns(destination):
            raise ValueError("Another product already owns the destination folder")
    if not destination.resolve().is_relative_to(root):
        raise ValueError("The product destination is outside this collection's products folder")
    if source is not None and source != destination:
        if destination.exists():
            raise ValueError("Both old and grouped product folders exist; check them before retrying")
        destination.parent.mkdir(parents=True, exist_ok=True)
        source.rename(destination)
    destination.mkdir(parents=True, exist_ok=True)
    if previous != destination:
        # This also repairs a checkpoint interrupted just after the directory move.
        old_prefix = relative_or_absolute(previous, run_dir).rstrip("/\\")
        new_prefix = relative_or_absolute(destination, run_dir).rstrip("/\\")
        for stage in row.get("collection_stages", {}).values():
            stage["files"] = [new_prefix + path[len(old_prefix):] if str(path).replace("\\", "/").startswith(old_prefix.replace("\\", "/") + "/") else path for path in stage.get("files", [])]
    row["local_folder"] = relative_or_absolute(destination, run_dir)
    metadata = destination / "orbea-product.json"
    data = json.loads(metadata.read_text(encoding="utf-8-sig")) if metadata.is_file() else {}
    data.update(schema_version=1, sku=row["sku"], pimbo_product_id=row.get("product_id"),
                pimbo_url=row.get("product_url"), pimbo_product_name=row.get("title"),
                orbea_url=row.get("catalogue_url"), orbea_product_name=row.get("catalogue_model"),
                stages=row.get("collection_stages", {}))
    data.setdefault("status", "partial")
    data.setdefault("collected_at", utc_now())
    atomic_write_json(metadata, data)
    checkpoint.save()
    return destination


def collect_colour_photos(service, product, row, config, checkpoint, token, log, cache, folder, *, website):
    from .collection import stage_complete
    key = canonicalize_url(row["catalogue_url"])
    if key not in cache:
        entry = cache[key] = {"matches": {}, "errors": {}, "results": {}}
        pending = [item for item in checkpoint.results if item.get("status") == "code_match"
                   and canonicalize_url(item.get("catalogue_url", "")) == key
                   and not stage_complete("photos", item.get("collection_stages", {}).get("photos", {}), checkpoint.run_dir)]
        custom_rows, regular_rows = [], []
        for item in pending:
            if product.codes and not product_matches(product, item["sku"], item.get("title", "")):
                entry["errors"][item["row_key"]] = "The website product code does not match the Pimbo SKU"
            elif any(_colour_key(colour) == "custom" for colour in pimbo_photo_colours(item, source_model=product.name)):
                custom_rows.append(item)
                entry["matches"][item["row_key"]] = OrbeaPhotoVariant("Custom", "Your Design (default)", "")
            else:
                regular_rows.append(item)
        name = (template_code(row["sku"]) or "Orbea") + "-" + hashlib.sha256(key.encode()).hexdigest()[:8]
        shared_root = checkpoint.run_dir / "product-photos"
        model_folder = shared_root / name
        if regular_rows:
            try:
                photo_product = parse_orbea_photo_product(product.page_html, product.url)
                for item in regular_rows:
                    try:
                        entry["matches"][item["row_key"]] = match_photo_colour(photo_product, item, source_model=product.name)
                    except ValueError as error:
                        entry["errors"][item["row_key"]] = str(error)
                codes = tuple(dict.fromkeys(entry["matches"][item["row_key"]].code for item in regular_rows
                                            if item["row_key"] in entry["matches"]))
                if codes:
                    photo_service = service.photo_service_factory() if service.photo_service_factory else OrbeaPhotoService()
                    service._photo_service = photo_service
                    try:
                        result = photo_service.run_from_html(product.url, product.page_html, shared_root,
                            cancellation=token, log=log, product_folder=name,
                            asset_root=config.output_root / ".orbea-assets", variant_codes=codes)
                    finally:
                        service._photo_service = None
                    if result.cancelled:
                        raise RunCancelled("The Orbea photo download was stopped")
                    for code in codes:
                        entry["results"][code] = (result, model_folder, codes)
            except RunCancelled:
                raise
            except Exception as error:
                for item in regular_rows:
                    entry["errors"].setdefault(item["row_key"], f"{type(error).__name__}: {error}")
        if custom_rows:
            try:
                service._log(log, "Selecting Your Design and saving its untouched default photos")
                result = website.read_default_custom_photos(product.url, model_folder / "Custom",
                    asset_root=config.output_root / ".orbea-assets", log=log)
                if result.cancelled:
                    raise RunCancelled("The Custom Orbea photo download was stopped")
                entry["results"]["Custom"] = (result, model_folder / "Custom", ("Custom",))
            except RunCancelled:
                raise
            except Exception as error:
                for item in custom_rows:
                    entry["errors"][item["row_key"]] = f"Custom Your Design photos: {type(error).__name__}: {error}"
    entry = cache[key]
    if row["row_key"] in entry["errors"]:
        raise ValueError(entry["errors"][row["row_key"]])
    variant = entry["matches"][row["row_key"]]
    result, source_folder, codes = entry["results"][variant.code]
    by_colour = getattr(result, "variant_files", {})
    sources = by_colour.get(variant.code, ())
    if not sources and len(codes) == 1 and not by_colour:
        sources = result.files  # A one-colour request contains only that colour.
    files = []
    previous_photo_folder = row.get("collection_stages", {}).get("photos", {}).get("previous_photo_folder", "")
    photos = folder / "photos"
    old_files = list(photos.rglob("*")) if photos.is_dir() else []
    wanted = {Path(source).name for source in sources}
    old_stage = row.get("collection_stages", {}).get("photos", {})
    other_images = [path for path in old_files if path.is_file() and path.suffix.casefold() in {".png", ".jpg", ".jpeg", ".webp"}
                    and (path.parent != photos or path.name not in wanted)]
    if old_files and (old_stage.get("capture_version") != PHOTOS_CAPTURE_VERSION or other_images):
        archive = folder / "previous-photos"
        index = 2
        while archive.exists():
            archive = folder / f"previous-photos-{index}"
            index += 1
        if not photos.resolve().is_relative_to(folder.resolve()) or not archive.resolve().is_relative_to(folder.resolve()):
            raise ValueError("Existing photos or their backup are outside the verified product folder")
        old_prefix = relative_or_absolute(photos, checkpoint.run_dir)
        new_prefix = relative_or_absolute(archive, checkpoint.run_dir)
        photos.rename(archive)
        old_stage["files"] = [new_prefix + str(path)[len(old_prefix):] if str(path).replace("\\", "/").startswith(old_prefix.replace("\\", "/") + "/") else path for path in old_stage.get("files", [])]
        old_stage["previous_photo_folder"] = previous_photo_folder = new_prefix
        checkpoint.save()
    for source in sources:
        source = Path(source).resolve()
        if not source.is_relative_to(source_folder.resolve()) or not source.is_file():
            raise ValueError("A colour photo is missing or outside its shared model folder")
        destination = folder / "photos" / source.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not link_image(source, destination):
            service._log(log, "This output drive cannot share photo storage; saved a separate copy")
        files.append(destination)
    all_prefixes = tuple(code + " " for code in codes)
    def relevant(messages):
        return tuple(message for message in messages if message.startswith(variant.code + " ") or not message.startswith(all_prefixes))
    failures = relevant(result.failures)
    unavailable = relevant(result.unavailable)
    if not files and not failures and not unavailable:
        failures = (f"No downloaded photos could be assigned to {variant.name}",)
    _, pimbo_colour = parse_orbea_name(row.get("title", ""), source_model=product.name)
    return {"files": files, "colour": variant.name, "colour_code": variant.code,
            "source": "your_design_default" if variant.code == "Custom" else "published_colour",
            "pimbo_colour": pimbo_colour, "failures": failures, "unavailable": unavailable,
            "previous_photo_folder": previous_photo_folder}
