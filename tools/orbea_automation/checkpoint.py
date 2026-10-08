from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .models import OrbeaRunConfig, PimboFilterSpec


CHECKPOINT_VERSION = 2
CHECKPOINT_NAME = "run_checkpoint.json"
WORKBOOK_NAME = "orbea_matches.xlsx"
MANIFEST_NAME = "image_manifest.csv"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    for attempt in range(8):
        try:
            os.replace(temporary, path)
            break
        except PermissionError:
            # Windows readers can briefly hold the checkpoint while the GUI
            # updates progress. Retry the atomic replacement without changing ACLs.
            if os.name != "nt" or attempt == 7:
                raise
            time.sleep(0.05 * (attempt + 1))


def compatibility_for(config: OrbeaRunConfig) -> dict[str, Any]:
    return config.compatibility_dict(file_sha256(config.catalogue_path) if config.catalogue_path else "")


def _compatibility_matches(actual: Any, expected: dict[str, Any]) -> bool:
    """Keep older runs resumable when newly added options are left empty."""

    if not isinstance(actual, dict):
        return False
    normalized = dict(actual)
    normalized.setdefault("download_product_photos", False)
    normalized.setdefault("product_code_prefix", "")
    normalized.setdefault("collect_product_data", False)
    normalized.setdefault("download_description", False)
    normalized.setdefault("download_specifications", False)
    return normalized == expected


def _run_folder_name(moment: datetime | None = None) -> str:
    value = moment or datetime.now()
    return value.strftime("%Y%m%d-%H%M%S")


def create_run_directory(
    output_root: Path, moment: datetime | None = None
) -> Path:
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    base = _run_folder_name(moment)
    candidate = output_root / base
    suffix = 2
    while candidate.exists():
        candidate = output_root / f"{base}-{suffix}"
        suffix += 1
    candidate.mkdir(parents=False)
    return candidate


def _has_retryable_images(data: dict[str, Any]) -> bool:
    from .features import DESCRIPTION_CAPTURE_VERSION
    from .website import SPECIFICATIONS_CAPTURE_VERSION

    if data.get("compatibility", {}).get("download_description") and any(
        row.get("status") == "code_match" and row.get("collection_stages", {}).get("description", {}).get("capture_version") != DESCRIPTION_CAPTURE_VERSION
        for row in data.get("results", [])
    ):
        return True
    if data.get("compatibility", {}).get("download_specifications") and any(
        row.get("status") == "code_match" and row.get("collection_stages", {}).get("specifications", {}).get("capture_version") != SPECIFICATIONS_CAPTURE_VERSION
        for row in data.get("results", [])
    ):
        return True
    return any(row.get("collection_status") == "partial" or row.get("website_lookup_status") == "error"
               for row in data.get("results", [])) or any(
        record.get("retryable")
        or record.get("geometry_status") == "transient_error"
        or record.get("size_guide_status") == "transient_error"
        for record in data.get("images", {}).values()
    )


def _has_matched_products(data: dict[str, Any]) -> bool:
    return any(row.get("status") == "code_match" and row.get("catalogue_url")
               for row in data.get("results", []))


def find_latest_compatible_run(
    config: OrbeaRunConfig, *, include_completed_errors: bool = False, matched_only: bool = False
) -> Path | None:
    """Find the newest compatible run without altering any checkpoint."""

    root = config.output_root
    if not root.exists():
        return None
    expected = compatibility_for(config)
    candidates: list[tuple[float, Path]] = []
    for checkpoint_path in root.glob(f"*/{CHECKPOINT_NAME}"):
        try:
            data = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            if data.get("version") != CHECKPOINT_VERSION:
                continue
            if not _compatibility_matches(data.get("compatibility"), expected):
                continue
            if matched_only and not _has_matched_products(data):
                continue
            if data.get("completed") and not matched_only and not (
                include_completed_errors and _has_retryable_images(data)
            ):
                continue
            candidates.append((checkpoint_path.stat().st_mtime, checkpoint_path.parent))
        except (OSError, json.JSONDecodeError):
            continue
    return max(candidates, default=(0.0, None), key=lambda item: item[0])[1]


def find_latest_saved_run(output_root: Path, *, include_completed_errors: bool = False, matched_only: bool = False) -> Path | None:
    """Find saved work independently of the current fresh-scan controls."""
    candidates = []
    for path in Path(output_root).glob(f"*/{CHECKPOINT_NAME}"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("version") != CHECKPOINT_VERSION or not isinstance(data.get("compatibility"), dict):
                continue
            if matched_only and not _has_matched_products(data):
                continue
            if data.get("completed") and not matched_only and not (include_completed_errors and _has_retryable_images(data)):
                continue
            candidates.append((path.stat().st_mtime, path.parent))
        except (OSError, ValueError, TypeError):
            continue
    return max(candidates, default=(0.0, None), key=lambda item: item[0])[1]


def saved_run_config(run_dir: Path, *, browser_name: str | None = None) -> OrbeaRunConfig:
    """Restore the selected run's settings and pin Resume to that checkpoint."""
    run_dir = Path(run_dir).resolve()
    data = json.loads((run_dir / CHECKPOINT_NAME).read_text(encoding="utf-8"))
    if data.get("version") != CHECKPOINT_VERSION:
        raise ValueError("The saved Orbea run was created by an incompatible version")
    saved = data["compatibility"]
    settings = data.get("settings", {})
    filters = saved.get("filters", {})
    filter_names = PimboFilterSpec.__dataclass_fields__
    options = {name: saved[name] for name in (
        "all_products", "download_images", "download_product_photos", "product_code_prefix",
        "collect_product_data", "download_description", "download_specifications",
    ) if name in saved}
    options.update({name: settings[name] for name in (
        "max_products", "navigation_timeout", "control_discovery_timeout", "table_render_timeout",
        "selector_timeout", "image_retry_limit",
    ) if name in settings})
    return OrbeaRunConfig(
        Path(saved["catalogue_path"]) if saved.get("catalogue_path") else None,
        run_dir.parent,
        filters=PimboFilterSpec(**{key: value for key, value in filters.items() if key in filter_names}),
        browser_name=browser_name or settings.get("browser_name", "chrome"),
        resume_run_dir=run_dir,
        downloads_only=bool(data.get("saved_downloads_only")),
        **options,
    )


class RunCheckpoint:
    """Atomic, row-level checkpoint shared by scan, image, and report stages."""

    def __init__(self, path: Path, data: dict[str, Any], *, resumed: bool) -> None:
        self.path = Path(path)
        self.data = data
        self.resumed = resumed

    @classmethod
    def create(cls, run_dir: Path, config: OrbeaRunConfig) -> "RunCheckpoint":
        run_dir = Path(run_dir)
        data: dict[str, Any] = {
            "version": CHECKPOINT_VERSION,
            "run_id": run_dir.name,
            "started_at": utc_now(),
            "updated_at": utc_now(),
            "completed": False,
            "cancelled": False,
            "phase": "initializing",
            "compatibility": compatibility_for(config),
            "settings": {
                "browser_name": config.browser_name,
                "max_products": config.max_products,
                "navigation_timeout": config.navigation_timeout,
                "control_discovery_timeout": config.control_discovery_timeout,
                "table_render_timeout": config.table_render_timeout,
                "selector_timeout": config.selector_timeout,
                "image_retry_limit": config.image_retry_limit,
            },
            "totals": {"products": None, "pages": None},
            "results": [],
            "images": {},
        }
        checkpoint = cls(run_dir / CHECKPOINT_NAME, data, resumed=False)
        checkpoint.save()
        return checkpoint

    @classmethod
    def load(cls, run_dir: Path, config: OrbeaRunConfig, *, matched_only: bool = False, download_missing: bool = False) -> "RunCheckpoint":
        path = Path(run_dir) / CHECKPOINT_NAME
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("version") != CHECKPOINT_VERSION:
            raise ValueError("The run checkpoint was created by an incompatible version")
        # A completed scan contains the resolved catalogue fields already. An
        # explicitly selected Resume does not re-read a moved/changed workbook.
        pinned_scan = matched_only or download_missing or (config.resume_run_dir == Path(run_dir).resolve() and data.get("scan_completed"))
        expected = config.compatibility_dict(data["compatibility"].get("catalogue_sha256", "")) if pinned_scan else compatibility_for(config)
        actual = data.get("compatibility", {})
        if download_missing:
            download_fields = {"download_images", "download_product_photos", "download_description",
                               "download_specifications", "collect_product_data"}
            actual = {**actual, **{key: expected[key] for key in download_fields}}
        if not _compatibility_matches(actual, expected):
            raise ValueError("The run uses a different catalogue or Pimbo filter set")
        if download_missing:
            data["compatibility"] = actual
            data["saved_downloads_only"] = True
        previous_error = data.pop("last_error", None)
        if previous_error:
            data["previous_error"] = previous_error
        data["resumed_at"] = utc_now()
        data["cancelled"] = False
        checkpoint = cls(path, data, resumed=True)
        checkpoint.save()
        return checkpoint

    @property
    def run_dir(self) -> Path:
        return self.path.parent

    @property
    def workbook_path(self) -> Path:
        return self.run_dir / WORKBOOK_NAME

    @property
    def manifest_path(self) -> Path:
        return self.run_dir / MANIFEST_NAME

    @property
    def results(self) -> list[dict[str, Any]]:
        return self.data.setdefault("results", [])

    @property
    def images(self) -> dict[str, dict[str, Any]]:
        return self.data.setdefault("images", {})

    def processed_row_keys(self, *, retry_failed: bool = False) -> set[str]:
        return {
            str(item["row_key"])
            for item in self.results
            if item.get("row_key")
            and not (retry_failed and item.get("status") == "error")
        }

    def known_product_ids(self) -> set[str]:
        return {
            str(item["product_id"])
            for item in self.results
            if item.get("product_id")
        }

    def upsert_result(self, result: dict[str, Any]) -> None:
        key = str(result.get("row_key") or "")
        if not key:
            raise ValueError("A checkpoint result requires row_key")
        self.data["results"] = [
            item for item in self.results if str(item.get("row_key")) != key
        ]
        self.results.append(result)
        self.save()

    def upsert_image(self, canonical_url: str, record: dict[str, Any]) -> None:
        if not canonical_url:
            raise ValueError("An image record requires canonical_url")
        self.images[canonical_url] = record
        self.save()

    def set_totals(self, *, products: int | None, pages: int | None) -> None:
        self.data["totals"] = {"products": products, "pages": pages}
        self.save()

    def set_phase(self, phase: str) -> None:
        self.data["phase"] = phase
        self.save()

    def mark_cancelled(self) -> None:
        self.data["cancelled"] = True
        self.data["completed"] = False
        self.data["cancelled_at"] = utc_now()
        self.save()

    def mark_completed(self) -> None:
        self.data["phase"] = "complete"
        self.data["completed"] = True
        self.data["cancelled"] = False
        self.data["completed_at"] = utc_now()
        self.save()

    def counts(self) -> dict[str, int]:
        counts: dict[str, int] = {"scanned": len(self.results)}
        for result in self.results:
            status = str(result.get("status") or "unknown")
            counts[status] = counts.get(status, 0) + 1
        counts["image_urls"] = len(self.images)
        for record in self.images.values():
            for field in ("geometry_status", "size_guide_status"):
                status = str(record.get(field) or "pending")
                key = f"images_{status}"
                counts[key] = counts.get(key, 0) + 1
        counts["matched"] = counts.get("code_match", 0)
        counts["review"] = sum(
            counts.get(status, 0)
            for status in (
                "title_only",
                "ambiguous",
                "unmatched",
                "no_variant",
                "duplicate",
                "error",
            )
        )
        counts["images"] = counts.get("images_downloaded", 0)
        photo_summary = self.data.get("product_photos", {})
        counts["product_photos"] = int(photo_summary.get("files", 0) or 0)
        if self.data.get("compatibility", {}).get("collect_product_data"):
            counts["product_photos"] = sum(len(row.get("collection_stages", {}).get("photos", {}).get("files", [])) for row in self.results)
            counts["collected"] = sum(row.get("collection_status") in {"collected", "collected_with_warnings"} for row in self.results)
        counts["unavailable"] = counts.get("images_not_available", 0)
        counts["errors"] = counts.get("error", 0) + counts.get(
            "images_transient_error", 0
        ) + len(photo_summary.get("failures", ()) or ())
        counts["errors"] += sum(len(row.get("collection_errors", [])) + int(row.get("website_lookup_status") == "error") for row in self.results)
        return counts

    def pending_retryable_images(self) -> Iterable[tuple[str, dict[str, Any]]]:
        for url, record in self.images.items():
            if record.get("retryable") or "transient_error" in {
                record.get("geometry_status"),
                record.get("size_guide_status"),
            }:
                yield url, record

    def save(self) -> None:
        self.data["updated_at"] = utc_now()
        atomic_write_json(self.path, self.data)


def open_or_create_checkpoint(
    config: OrbeaRunConfig,
    *,
    resume: bool,
    retry_failed: bool,
    retry_matched: bool = False,
    download_missing: bool = False,
) -> RunCheckpoint:
    run_dir = None
    if resume:
        run_dir = config.resume_run_dir or find_latest_compatible_run(config, include_completed_errors=retry_failed, matched_only=retry_matched)
    if run_dir is not None:
        return RunCheckpoint.load(run_dir, config, matched_only=retry_matched, download_missing=download_missing)
    if retry_matched or download_missing:
        raise ValueError("No saved matched Orbea products were found in this output folder")
    return RunCheckpoint.create(create_run_directory(config.output_root), config)
