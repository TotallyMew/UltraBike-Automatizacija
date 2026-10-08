"""Upload collected Orbea packages through the shared Draft-only PIMBO workflow."""
from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path

from Managers.PimboProductEditor import PimAutomationError, PimPreparationResult, PimPreparationStatus, PimboProductEditor
from tools.kross_automation.service import KrossPimboClient, KrossWorkflowOptions
from tools.supplier_upload import IMAGE_SUFFIXES, SupplierUploadWorkflow, normalize_sku
from .checkpoint import atomic_write_json, utc_now
from .component_values import normalize_component_specifications
from .photos import normalize_orbea_product_url
from .specifications import MANUAL_SPECIFICATION_FIELDS, build_orbea_specification_plan, parse_orbea_name
from .website import SPECIFICATIONS_CAPTURE_VERSION

METADATA_NAME = "orbea-product.json"


@dataclass(frozen=True)
class OrbeaWorkflowOptions(KrossWorkflowOptions):
    @classmethod
    def only(cls, *stages):
        unknown = set(stages) - set(cls.STAGES)
        if unknown:
            raise ValueError(f"Unknown Orbea workflow stages: {', '.join(sorted(unknown))}")
        return cls(**{name: name in stages for name in cls.STAGES})


@dataclass(frozen=True)
class OrbeaUploadMatch:
    sku: str
    status: str
    pimbo_product_id: str = ""
    pimbo_product_name: str = ""
    pimbo_product_url: str = ""
    orbea_product_name: str = ""
    orbea_url: str = ""
    local_folder: str = ""
    note: str = ""
    variant_skus: tuple[str, ...] = ()

    @property
    def ready(self):
        return bool(self.sku and self.local_folder and self.status in {"local_ready", "collected", "collected_with_warnings", "partial"})


@dataclass(frozen=True)
class OrbeaProductData:
    url: str
    name: str
    description_html: str
    specification_text: str
    image_urls: tuple[str, ...] = ()
    variant_skus: tuple[str, ...] = ()
    description_unavailable: bool = False
    specifications_capture_version: int = SPECIFICATIONS_CAPTURE_VERSION
    geometry_unavailable: bool = False
    size_tables_unavailable: bool = False


@dataclass(frozen=True)
class OrbeaUploadResult:
    match: OrbeaUploadMatch
    preparation: PimPreparationResult
    downloaded_images: tuple[Path, ...] = ()
    product: OrbeaProductData | None = None
    dimensions_image: Path | None = None
    size_chart_image: Path | None = None
    options: OrbeaWorkflowOptions = field(default_factory=OrbeaWorkflowOptions)
    completed_stages: tuple[str, ...] = ()

    @property
    def succeeded(self):
        return self.preparation.status in {PimPreparationStatus.NO_CHANGES, PimPreparationStatus.READY_FOR_REVIEW, PimPreparationStatus.SAVED_AUTOMATICALLY}


class _CollectedSources:
    def capture_dimensions(self, *args, **kwargs):
        raise RuntimeError("Collect the missing Orbea tables first, then reload the saved products")


class OrbeaUploadService(SupplierUploadWorkflow):
    supplier_label = "Orbea"
    metadata_name = METADATA_NAME
    geometry_name = "tables/geometry.png"
    size_table_name = "tables/size-guide-cm.png"
    required_specification_fields = ("Modelis",)
    specification_value_migrations = ()
    workflow_options_type = OrbeaWorkflowOptions
    upload_result_type = OrbeaUploadResult
    product_data_type = OrbeaProductData
    build_specification_plan = staticmethod(build_orbea_specification_plan)

    def __init__(self, pimbo_driver, *, pimbo_client_factory=KrossPimboClient, editor_factory=PimboProductEditor, db_manager=None):
        self.pimbo_driver = pimbo_driver
        self.pimbo_client_factory = pimbo_client_factory
        self.editor_factory = editor_factory
        self.public_catalog = _CollectedSources()
        self.translation_handler = None

    def specification_ai_exclusions(self, match, product):
        _model, color = parse_orbea_name(match.pimbo_product_name, source_model=getattr(product, "name", ""))
        return MANUAL_SPECIFICATION_FIELDS + (("Spalva",) if color.casefold() == "custom" else ())

    def validate_product_sources(self, product, selected):
        if product and selected.specifications_magic_ai and (
            product.specifications_capture_version < SPECIFICATIONS_CAPTURE_VERSION
        ):
            raise PimAutomationError("Saved Orbea specifications came from the old incomplete scraper; recollect specifications before uploading")

    @staticmethod
    def source_url(match):
        return match.orbea_url

    @staticmethod
    def source_name(match):
        return match.orbea_product_name

    @staticmethod
    def _description_html(product):
        return product.description_html

    @staticmethod
    def _read_package(folder):
        folder = Path(folder).resolve()
        data = json.loads((folder / METADATA_NAME).read_text(encoding="utf-8-sig"))
        sku = normalize_sku(data.get("sku"))
        if not sku or not data.get("orbea_product_name"):
            raise ValueError("The package has no verified SKU or Orbea product name")
        url = normalize_orbea_product_url(data.get("orbea_url") or "")
        stages = data.get("stages") or {}
        tables = stages.get("tables", {})
        table_names = {Path(path).name for path in tables.get("files", [])}
        tables_confirmed = tables.get("status") in {"downloaded", "not_available"}
        for filename in ("tables/geometry.png", "tables/size-guide-cm.png"):
            if not (folder / filename).resolve().is_relative_to(folder):
                raise ValueError("A table file is outside this product folder")
        def text_file(stage, filename):
            if stages.get(stage, {}).get("status") != "downloaded":
                return ""
            path = (folder / filename).resolve()
            if not path.is_relative_to(folder):
                raise ValueError("Source file is outside this product folder")
            return path.read_text(encoding="utf-8-sig") if path.is_file() else ""
        match = OrbeaUploadMatch(
            sku, data.get("status") or "local_ready", str(data.get("pimbo_product_id") or ""),
            str(data.get("pimbo_product_name") or ""), str(data.get("pimbo_url") or ""),
            str(data["orbea_product_name"]), url, str(folder),
            " | ".join(map(str, [*(data.get("warnings") or []), *(data.get("errors") or [])])), (sku,),
        )
        product = OrbeaProductData(url, match.orbea_product_name, text_file("description", "description.html"),
                                   normalize_component_specifications(text_file("specifications", "specifications.txt")), variant_skus=(sku,),
                                   description_unavailable=stages.get("description", {}).get("status") == "not_available",
                                   specifications_capture_version=int(stages.get("specifications", {}).get("capture_version") or 0),
                                   geometry_unavailable=tables_confirmed and "geometry.png" not in table_names,
                                   size_tables_unavailable=tables_confirmed and "size-guide-cm.png" not in table_names)
        return match, product

    @staticmethod
    def read_upload_result(match):
        path = Path(match.local_folder) / "orbea-upload-result.json"
        try:
            record = json.loads(path.read_text(encoding="utf-8-sig"))
            preparation = record["preparation"]
            if any(not isinstance(record.get(key, []), list) or not all(isinstance(stage, str) for stage in record.get(key, []))
                   for key in ("selected_stages", "completed_stages")):
                return None
            if normalize_sku(preparation.get("product_code")) != normalize_sku(match.sku):
                return None
            if match.pimbo_product_id and preparation.get("product_id") != match.pimbo_product_id:
                return None
            return record
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            return None

    @classmethod
    def upload_finished(cls, match):
        record = cls.read_upload_result(match)
        if record is None:
            return False
        status = record["preparation"].get("status")
        completed = set(record.get("completed_stages", []))
        if status == PimPreparationStatus.NO_CHANGES.value:
            completed.add("save")
        return status in {PimPreparationStatus.SAVED_AUTOMATICALLY.value, PimPreparationStatus.NO_CHANGES.value} and set(record.get("selected_stages", [])) <= completed

    @classmethod
    def saved_upload_stages(cls, match):
        record = cls.read_upload_result(match)
        if not record or not record["preparation"].get("product_id"):
            return ()
        completed = set(record.get("completed_stages", []))
        if "save" not in completed:
            return ()
        # The first save precedes component AI. A failed second phase can have
        # completed pre-fill/AI in memory without saving those changes.
        completed -= {"save", "specifications_prefill", "specifications_magic_ai"}
        return tuple(stage for stage in OrbeaWorkflowOptions.STAGES if stage in completed)

    @classmethod
    def specifications_need_recollection(cls, match):
        _saved, product = cls._read_package(match.local_folder)
        return product.specifications_capture_version < SPECIFICATIONS_CAPTURE_VERSION

    @classmethod
    def load_local_packages(cls, root):
        root = Path(root).resolve()
        paths = [root / METADATA_NAME] if (root / METADATA_NAME).is_file() else sorted(root.rglob(METADATA_NAME))
        matches = []
        latest = {}
        for path in paths:
            try:
                match, _ = cls._read_package(path.parent)
                key = (match.sku, match.pimbo_product_id)
                stamp = path.stat().st_mtime
                if key not in latest or stamp > latest[key][0]:
                    latest[key] = (stamp, match)
            except Exception as error:
                matches.append(OrbeaUploadMatch(path.parent.name, "invalid", local_folder=str(path.parent), note=str(error)))
        matches.extend(value[1] for value in latest.values())
        return tuple(sorted(matches, key=lambda match: (match.sku, match.local_folder)))

    def validate_package_target(self, saved_match, resolved_match):
        resume_id = getattr(self, "_resume_product_id", "")
        if resume_id and resume_id != resolved_match.pimbo_product_id:
            raise PimAutomationError("The saved upload progress belongs to a different PIMBO product")
        if saved_match.pimbo_product_id and saved_match.pimbo_product_id != resolved_match.pimbo_product_id:
            raise PimAutomationError("The saved package belongs to a different PIMBO product; collect it again before uploading")

    @staticmethod
    def local_photo_candidates(folder):
        folder = Path(folder).resolve()
        photos = folder / "photos"
        metadata = folder / METADATA_NAME
        if metadata.is_file():
            data = json.loads(metadata.read_text(encoding="utf-8-sig"))
            stage = (data.get("stages") or {}).get("photos", {})
            if stage.get("status") in {"downloaded", "error", "pending", "not_available"}:
                from .photo_packages import PHOTOS_CAPTURE_VERSION
                if stage.get("capture_version") != PHOTOS_CAPTURE_VERSION or stage.get("status") != "downloaded":
                    return ()
                paths = [(folder / path).resolve() for path in stage.get("package_files", [])]
                if any(not path.is_relative_to(photos.resolve()) or not path.is_file() for path in paths):
                    raise PimAutomationError("A matched-colour photo is missing or outside this product's photos folder")
                return tuple(sorted(paths))
        return tuple(path for path in sorted(photos.rglob("*")) if path.is_file()
                     and path.suffix.casefold() in IMAGE_SUFFIXES and path.resolve().is_relative_to(folder))

    @staticmethod
    def _local_product_photo_is_uploadable(path):
        from PIL import Image
        try:
            with Image.open(path) as image:
                return max(image.size) >= 400
        except (OSError, ValueError):
            return False

    @staticmethod
    def geometry_upload_paths(path):
        if path is None:
            return ()
        folder = path.parent.resolve()
        return (path, *tuple(item for item in sorted(folder.glob("geometry-*.png"))
                            if item.is_file() and item.resolve().is_relative_to(folder)))

    def upload_and_save(self, match, output_root=None, *, options=None, progress=None, resume_completed=False):
        folder = Path(match.local_folder).resolve()
        if not folder.is_dir() or not (folder / METADATA_NAME).is_file():
            raise ValueError("Load a collected Orbea product folder first")
        self._upload_target = match
        requested = options or OrbeaWorkflowOptions()
        completed_before = self.saved_upload_stages(match) if resume_completed else ()
        previous = self.read_upload_result(match) if completed_before else None
        self._resume_product_id = previous["preparation"]["product_id"] if previous else ""
        effective = OrbeaWorkflowOptions.only(*(stage for stage in requested.selected_stages if stage not in completed_before))
        if completed_before and progress:
            progress(f"{match.sku}: keeping already saved stages; running {', '.join(effective.selected_stages)}")
        try:
            result = super().upload_and_save(match, output_root, options=effective, progress=progress)
        except Exception as error:
            target = self._upload_target
            result = OrbeaUploadResult(target, PimPreparationResult(target.sku, target.pimbo_product_id,
                status=PimPreparationStatus.FAILED, final_url=target.pimbo_product_url, error=str(error)),
                options=effective)
        if previous and "product_photos" in completed_before and not result.preparation.photo_upload:
            result = replace(result, preparation=replace(result.preparation,
                photo_upload=dict(previous["preparation"].get("photo_upload") or {})))
        completed = set(completed_before) | set(result.completed_stages)
        if completed_before:
            completed.add("save")  # Retain the earlier verified first-phase save.
        result = replace(result, options=requested,
                         completed_stages=tuple(stage for stage in requested.STAGES if stage in completed))
        record = {"finished_at": utc_now(), "preparation": result.preparation.to_dict(),
                  "selected_stages": list(result.options.selected_stages), "completed_stages": list(result.completed_stages)}
        try:
            atomic_write_json(folder / "orbea-upload-result.json", record)
        except OSError as error:
            if progress:
                progress(f"Could not write the local upload result: {error}")
        return result
