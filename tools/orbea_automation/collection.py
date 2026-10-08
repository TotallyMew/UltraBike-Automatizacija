"""Save one representative Orbea SKU and its selected source assets locally."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .catalogue import normalize_code
from .photo_packages import PHOTOS_CAPTURE_VERSION, collect_colour_photos, package_folder
from .checkpoint import atomic_write_json, utc_now
from .features import DESCRIPTION_CAPTURE_VERSION
from .image_store import link_image
from .models import RunCancelled
from .utils import canonicalize_url, relative_or_absolute
from .website import SPECIFICATIONS_CAPTURE_VERSION, product_matches


def validate_product(product: Any, row: dict[str, Any]) -> None:
    if product.codes and not product_matches(product, row["sku"], row.get("title", "")):
        raise ValueError("The website product code does not match the Pimbo SKU")


def selected_downloads(config):
    return {"description": config.download_description, "specifications": config.download_specifications,
            "photos": config.download_product_photos, "tables": config.download_images}


def stage_complete(stage, prior, run_dir):
    versions = {"description": DESCRIPTION_CAPTURE_VERSION, "specifications": SPECIFICATIONS_CAPTURE_VERSION, "photos": PHOTOS_CAPTURE_VERSION}
    if stage in versions and prior.get("capture_version") != versions[stage]:
        return False
    if prior.get("status") == "not_available":
        return True
    files = prior.get("files", [])
    return bool(prior.get("status") == "downloaded" and files and
                all((Path(run_dir) / path).is_file() for path in files))


def missing_downloads(row, config, run_dir):
    stages = row.get("collection_stages", {})
    return {stage for stage, enabled in selected_downloads(config).items()
            if enabled and not stage_complete(stage, stages.get(stage, {}), run_dir)}


def collect_packages(service, website, config, checkpoint, reporter, token, log, *, rows=None, product_cache=None, photo_cache=None) -> None:
    product_cache = {} if product_cache is None else product_cache
    photo_cache = {} if photo_cache is None else photo_cache
    def fetch(row):
        key = canonicalize_url(row["catalogue_url"])
        if key not in product_cache:
            product_cache[key] = website.fetch(row["catalogue_url"])
        product = product_cache[key]
        validate_product(product, row)
        return product
    rows = [row for row in (checkpoint.results if rows is None else rows) if row.get("status") == "code_match"]
    selected = selected_downloads(config)
    for index, row in enumerate(rows, 1):
        service._check_cancelled(token)
        sku = normalize_code(row.get("sku"))
        if not sku:
            continue
        folder = package_folder(checkpoint, row)
        metadata = folder / "orbea-product.json"
        stages = row.setdefault("collection_stages", {})
        errors: list[str] = []
        product = None
        page_error = ""
        try:
            if row.get("website_validation_error"):
                raise ValueError(row["website_validation_error"])
            if any(selected[key] and not stage_complete(key, stages.get(key, {}), checkpoint.run_dir) for key in ("description", "specifications", "photos")):
                product = fetch(row)
        except RunCancelled:
            raise
        except Exception as error:
            page_error = f"{type(error).__name__}: {error}"
            if row.get("website_validation_error"):
                errors.append(f"Product page: {page_error}")

        for stage, enabled in selected.items():
            service._check_cancelled(token)
            prior = stages.get(stage, {})
            if not enabled:
                stages.setdefault(stage, {"status": "skipped", "files": []})
                continue
            if stage_complete(stage, prior, checkpoint.run_dir):
                continue
            files: list[Path] = []
            status = "downloaded"
            note = ""
            photo_info = {}
            try:
                if row.get("website_validation_error"):
                    raise ValueError(row["website_validation_error"])
                if stage != "tables" and page_error:
                    raise RuntimeError(page_error)
                if stage in {"description", "specifications"}:
                    if product is None:
                        product = fetch(row)
                    if stage == "description" and getattr(product, "description_error", ""):
                        raise RuntimeError(product.description_error)
                    if stage == "specifications" and getattr(product, "specifications_error", ""):
                        raise RuntimeError(product.specifications_error)
                    content = product.description_html if stage == "description" else product.specifications_text
                    if content:
                        path = folder / ("description.html" if stage == "description" else "specifications.txt")
                        temporary = path.with_suffix(path.suffix + ".tmp")
                        temporary.write_text(content + "\n", encoding="utf-8")
                        temporary.replace(path)
                        files.append(path)
                    else:
                        status, note = "not_available", "No source content could be extracted from this product page"
                elif stage == "photos":
                    if product is None:
                        product = fetch(row)
                    photo_info = collect_colour_photos(service, product, row, config, checkpoint, token, log, photo_cache, folder, website=website)
                    files.extend(photo_info["files"])
                    if photo_info["failures"]:
                        raise RuntimeError(" | ".join(photo_info["failures"]))
                    if not files:
                        status = "not_available"
                    note = " | ".join(photo_info["unavailable"])
                else:
                    record = checkpoint.images.get(canonicalize_url(row["catalogue_url"]), {})
                    paths = []
                    for key, state in (("geometry_image", "geometry_status"), ("size_guide_image", "size_guide_status")):
                        if record.get(state) == "downloaded" and record.get(key):
                            paths.append(checkpoint.run_dir / record[key])
                    for variant in record.get("geometry_variants", []):
                        filename = variant.get("filename")
                        if filename:
                            paths.append(checkpoint.run_dir / record.get("folder", "") / filename)
                    for path in dict.fromkeys(paths):
                        if not path.is_file():
                            raise FileNotFoundError(f"A downloaded table is missing: {path.name}")
                        destination = folder / "tables" / path.name
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        if not link_image(path, destination):
                            service._log(log, "This output drive cannot share table storage; saved a separate copy")
                        files.append(destination)
                    states = {record.get("geometry_status"), record.get("size_guide_status")}
                    if not states.issubset({"downloaded", "not_available"}):
                        raise RuntimeError(" | ".join(record.get("errors", [])) or "Table downloads remain incomplete")
                    if "not_available" in states:
                        note = "One or more tables were not published"
                    if not files:
                        status = "not_available"
            except RunCancelled:
                checkpoint.save()
                raise
            except Exception as error:
                status, note = "error", f"{type(error).__name__}: {error}"
                errors.append(f"{stage}: {note}")
            stages[stage] = {"status": status, "files": [relative_or_absolute(path, checkpoint.run_dir) for path in files], "note": note}
            if stage == "photos":
                stages[stage].update(capture_version=PHOTOS_CAPTURE_VERSION,
                    package_files=[str(path.relative_to(folder)) for path in files],
                    **{key: photo_info[key] for key in ("colour", "colour_code", "pimbo_colour", "previous_photo_folder", "source") if key in photo_info})
            if stage == "description":
                stages[stage]["capture_version"] = DESCRIPTION_CAPTURE_VERSION
                stages[stage]["source"] = getattr(product, "description_source", "page")
            if stage == "specifications":
                stages[stage]["capture_version"] = SPECIFICATIONS_CAPTURE_VERSION
                stages[stage]["source"] = getattr(product, "specifications_source", "legacy_components")
            checkpoint.save()

        # Keep failures for previously requested, now unchecked items visible.
        errors = list(dict.fromkeys([*errors, *(f"{stage}: {state.get('note', 'Download failed')}"
            for stage, state in stages.items() if state.get("status") == "error")]))
        # Warnings remain visible even when all available files were collected.
        warnings = [f"{key}: {value.get('note')}" for key, value in stages.items() if value.get("status") == "not_available" or (value.get("note") and value.get("status") == "downloaded")]
        row["collection_status"] = "partial" if errors else ("collected_with_warnings" if warnings else "collected")
        row["collection_errors"] = errors
        atomic_write_json(metadata, {
            "schema_version": 1, "collected_at": utc_now(), "sku": row["sku"],
            "pimbo_product_id": row.get("product_id"), "pimbo_url": row.get("product_url"),
            "pimbo_product_name": row.get("title"), "orbea_url": row.get("catalogue_url"),
            "orbea_product_name": row.get("catalogue_model"), "match_method": row.get("match_method"),
            "status": row["collection_status"], "selected_stages": {
                stage: enabled or stages.get(stage, {}).get("status") != "skipped"
                for stage, enabled in selected.items()},
            "stages": stages, "warnings": warnings, "errors": errors,
        })
        checkpoint.save()
        service._log(log, f"{row['sku']}: {row['collection_status']} — {folder}")
        reporter.emit("product_data", index, len(rows), f"{row['sku']}: {row['collection_status']}")
    checkpoint.data["product_data_completed"] = all(row.get("collection_status") in {"collected", "collected_with_warnings"}
        for row in checkpoint.results if row.get("status") == "code_match")
    checkpoint.save()
