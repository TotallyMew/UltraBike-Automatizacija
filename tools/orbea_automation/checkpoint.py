from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .models import OrbeaRunConfig


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
    os.replace(temporary, path)


def compatibility_for(config: OrbeaRunConfig) -> dict[str, Any]:
    return config.compatibility_dict(file_sha256(config.catalogue_path))


def _compatibility_matches(actual: Any, expected: dict[str, Any]) -> bool:
    """Compare checkpoints while keeping pre-photo-option runs resumable."""

    if not isinstance(actual, dict):
        return False
    normalized = dict(actual)
    normalized.setdefault("download_product_photos", False)
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
    return any(
        record.get("retryable")
        or record.get("geometry_status") == "transient_error"
        or record.get("size_guide_status") == "transient_error"
        for record in data.get("images", {}).values()
    )


def find_latest_compatible_run(
    config: OrbeaRunConfig, *, include_completed_errors: bool = False
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
            if data.get("completed") and not (
                include_completed_errors and _has_retryable_images(data)
            ):
                continue
            candidates.append((checkpoint_path.stat().st_mtime, checkpoint_path.parent))
        except (OSError, json.JSONDecodeError):
            continue
    return max(candidates, default=(0.0, None), key=lambda item: item[0])[1]


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
    def load(cls, run_dir: Path, config: OrbeaRunConfig) -> "RunCheckpoint":
        path = Path(run_dir) / CHECKPOINT_NAME
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("version") != CHECKPOINT_VERSION:
            raise ValueError("The run checkpoint was created by an incompatible version")
        if not _compatibility_matches(
            data.get("compatibility"), compatibility_for(config)
        ):
            raise ValueError("The run uses a different catalogue or Pimbo filter set")
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
        counts["unavailable"] = counts.get("images_not_available", 0)
        counts["errors"] = counts.get("error", 0) + counts.get(
            "images_transient_error", 0
        ) + len(photo_summary.get("failures", ()) or ())
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
) -> RunCheckpoint:
    run_dir = None
    if resume:
        run_dir = find_latest_compatible_run(
            config, include_completed_errors=retry_failed
        )
    if run_dir is not None:
        return RunCheckpoint.load(run_dir, config)
    return RunCheckpoint.create(create_run_directory(config.output_root), config)
