"""Validate a product selection and resolve it to explicitly scoped saved jobs."""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, replace
from pathlib import Path

from .checkpoint import CHECKPOINT_NAME, atomic_write_json, saved_run_config
from .models import OrbeaRunConfig

DOWNLOAD_MODES = ("missing", "refresh", "pimbo_photos")
DOWNLOAD_STAGES = ("photos", "description", "specifications", "tables")


class NoDownloadsNeeded(ValueError):
    """The checked rows already have every chosen stage."""


def product_identity(match):
    """A scan can discover a new product ID; its checkpoint row stays the same."""
    if getattr(match, "checkpoint_path", "") and getattr(match, "row_key", ""):
        return (str(Path(match.checkpoint_path).resolve()), match.row_key)
    return (str(Path(match.local_folder).resolve()), match.sku)


@dataclass(frozen=True)
class DownloadJob:
    config: OrbeaRunConfig
    row_keys: tuple[str, ...]
    resume: bool = False


@dataclass(frozen=True)
class DownloadRequest:
    mode: str
    stages: tuple[str, ...]
    jobs: tuple[DownloadJob, ...]
    batch_path: Path | None = None
    source_root: Path | None = None

    @property
    def count(self):
        return sum(len(job.row_keys) for job in self.jobs)


def begin_download_batch(request):
    """Persist the entire queue before running its first collection."""
    if request.batch_path:
        return request.batch_path, json.loads(request.batch_path.read_text(encoding="utf-8"))
    path = request.jobs[0].config.resume_run_dir / "selected-downloads.json"
    data = {"version": 1, "id": uuid.uuid4().hex, "mode": request.mode, "stages": list(request.stages),
            "source_root": str(request.source_root or request.jobs[0].config.resume_run_dir),
            "jobs": [{"run_dir": str(job.config.resume_run_dir), "row_keys": list(job.row_keys), "completed": False}
                     for job in request.jobs]}
    atomic_write_json(path, data)
    for job in request.jobs:
        checkpoint_path = job.config.resume_run_dir / CHECKPOINT_NAME
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8-sig"))
        checkpoint["selected_download_batch"] = str(path)
        atomic_write_json(checkpoint_path, checkpoint)
    return path, data


def pending_download_request(run_dir, *, browser_name="chrome"):
    checkpoint = json.loads((Path(run_dir) / CHECKPOINT_NAME).read_text(encoding="utf-8-sig"))
    reference = checkpoint.get("selected_download_batch")
    if not reference:
        return None
    path = Path(reference)
    if not path.is_file():
        raise ValueError("The saved download queue is missing; load the collection and select products again")
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("version") != 1 or data.get("mode") not in DOWNLOAD_MODES:
        raise ValueError("Unsupported saved download queue")
    stages = tuple(data["stages"])
    if not stages or not set(stages) <= set(DOWNLOAD_STAGES):
        raise ValueError("Invalid saved download stages")
    jobs = []
    for item in data["jobs"]:
        if item["completed"]:
            continue
        root = Path(item["run_dir"])
        config = replace(saved_run_config(root, browser_name=browser_name),
            collect_product_data=True, downloads_only=True, download_product_photos="photos" in stages,
            download_images="tables" in stages, download_description="description" in stages,
            download_specifications="specifications" in stages)
        saved = json.loads((root / CHECKPOINT_NAME).read_text(encoding="utf-8-sig"))
        keys = tuple(item["row_keys"])
        rows = {row.get("row_key"): row for row in saved.get("results", [])}
        if not keys or not set(keys) <= rows.keys():
            raise ValueError("The saved download selection no longer belongs to its collection")
        for key in keys:
            row = rows[key]
            eligible = (row.get("pimbo_photo_scan", {}).get("status") == "no_photos" and row.get("product_id")
                        if data["mode"] == "pimbo_photos" else row.get("status") == "code_match" and row.get("catalogue_url"))
            if not eligible:
                raise ValueError(f"{row.get('sku', key)}: the saved download selection is no longer eligible")
        resume = saved.get("selected_download_operation", {}).get("batch_id") == data["id"]
        jobs.append(DownloadJob(config, keys, resume=resume))
    return DownloadRequest(data["mode"], stages, tuple(jobs), path, Path(data["source_root"])) if jobs else None


def resolve_product_rows(matches):
    """Read only: reject stale, ambiguous or foreign owners before any job starts."""
    checkpoints = {}
    resolved = []
    seen = set()
    for match in matches:
        folder = Path(match.local_folder).resolve()
        explicit = getattr(match, "checkpoint_path", "")
        run_dir = Path(explicit).resolve().parent if explicit else next(
            (parent for parent in folder.parents if (parent / CHECKPOINT_NAME).is_file()), None)
        if run_dir is None or not folder.is_relative_to(run_dir):
            raise ValueError(f"{match.sku}: the saved collection checkpoint is missing")
        if run_dir not in checkpoints:
            data = json.loads((run_dir / CHECKPOINT_NAME).read_text(encoding="utf-8-sig"))
            checkpoints[run_dir] = (saved_run_config(run_dir), data.get("results", []))
        config, rows = checkpoints[run_dir]
        key = getattr(match, "row_key", "")
        owners = [row for row in rows if str(row.get("sku", "")).upper() == match.sku.upper()
                  and (not key or row.get("row_key") == key)
                  and str(row.get("product_id") or "") == match.pimbo_product_id
                  and (run_dir / row.get("local_folder", f"products/{row['sku']}")).resolve() == folder]
        if len(owners) != 1 or not owners[0].get("row_key"):
            raise ValueError(f"{match.sku}: no verified saved match owns this product folder")
        identity = (run_dir, owners[0]["row_key"])
        if identity not in seen:
            resolved.append((config, owners[0]))
            seen.add(identity)
    if not resolved:
        raise ValueError("Select at least one visible product")
    return tuple(resolved)


def resolve_download_request(matches, *, mode="missing", stages=DOWNLOAD_STAGES, browser_name="chrome"):
    if mode not in DOWNLOAD_MODES:
        raise ValueError("Unknown Orbea download mode")
    stages = ("photos",) if mode == "pimbo_photos" else tuple(dict.fromkeys(stages))
    if not stages or not set(stages) <= set(DOWNLOAD_STAGES):
        raise ValueError("Choose the data to download")
    jobs = {}
    for config, row in resolve_product_rows(matches):
        if mode == "pimbo_photos":
            if row.get("pimbo_photo_scan", {}).get("status") != "no_photos":
                continue
            if not row.get("product_id"):
                raise ValueError(f"{row['sku']}: scan Pimbo before downloading missing photos")
        elif row.get("status") != "code_match" or not row.get("catalogue_url"):
            raise ValueError(f"{row['sku']}: no verified saved Orbea link; scan Pimbo photos first for photo repair")
        root = config.resume_run_dir
        settings = replace(config, browser_name=browser_name, collect_product_data=True, downloads_only=True,
            download_product_photos="photos" in stages, download_description="description" in stages,
            download_specifications="specifications" in stages, download_images="tables" in stages)
        if mode == "missing":
            from .collection import missing_downloads
            if not missing_downloads(row, settings, root):
                continue
        if root not in jobs:
            jobs[root] = (settings, [])
        jobs[root][1].append(row["row_key"])
    if not jobs:
        if mode == "missing":
            raise NoDownloadsNeeded("0 products need downloads for the chosen stages")
        raise ValueError("Scan Pimbo first and select products marked No photos")
    return DownloadRequest(mode, stages, tuple(DownloadJob(config, tuple(keys)) for config, keys in jobs.values()))


def selected_photo_jobs(matches, *, browser_name="chrome"):
    """Compatibility adapter for callers requesting the original photo refresh."""
    request = resolve_download_request(matches, mode="refresh", stages=("photos",), browser_name=browser_name)
    return tuple((job.config, job.row_keys) for job in request.jobs)
