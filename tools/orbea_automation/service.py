from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any, Callable

from .catalogue import CatalogueIndex
from .checkpoint import (
    RunCheckpoint,
    open_or_create_checkpoint,
    utc_now,
)
from .models import (
    CancellationToken,
    OrbeaRunConfig,
    OrbeaRunResult,
    PimboFilterOptions,
    RunCancelled,
    RunProgress,
)
from .pimbo import PimboBrowserClient
from .report import write_image_manifest, write_report
from .utils import canonicalize_url, image_folder_name, relative_or_absolute


ProgressCallback = Callable[[RunProgress], None]
LogCallback = Callable[[str], None]
PIMBO_AUTOMATION_LOCK = threading.Lock()


class _ProgressReporter:
    def __init__(
        self,
        callback: ProgressCallback | None,
        checkpoint: RunCheckpoint,
    ) -> None:
        self.callback = callback
        self.checkpoint = checkpoint
        self.started = time.monotonic()
        self.stage_started: dict[str, float] = {}

    def emit(
        self,
        stage: str,
        current: int,
        total: int | None,
        message: str = "",
    ) -> None:
        if self.callback is None:
            return
        now = time.monotonic()
        stage_started = self.stage_started.setdefault(stage, now)
        stage_elapsed = max(now - stage_started, 0.0)
        eta = None
        if total and current > 0 and current < total:
            eta = stage_elapsed / current * (total - current)
        progress = RunProgress(
            stage=stage,
            current=current,
            total=total,
            message=message,
            counts=self.checkpoint.counts(),
            elapsed_seconds=now - self.started,
            eta_seconds=eta,
        )
        try:
            self.callback(progress)
        except Exception:
            # A presentation callback must never corrupt a resumable run.
            pass


class OrbeaAutomationService:
    """Run the Pimbo → catalogue → image → Excel pipeline.

    ``pimbo_driver`` remains owned by the application. Any browser returned by
    ``image_driver_factory`` is owned and closed by this service.
    """

    def __init__(
        self,
        pimbo_driver: Any,
        image_driver_factory: Callable[..., Any] | None = None,
        photo_service_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.pimbo_driver = pimbo_driver
        self.image_driver_factory = image_driver_factory
        self.photo_service_factory = photo_service_factory
        self._cancellation = CancellationToken()
        self._image_driver: Any = None
        self._photo_service: Any = None

    def cancel(self) -> None:
        self._cancellation.cancel()
        driver = self._image_driver
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass
        photo_service = self._photo_service
        if photo_service is not None:
            try:
                photo_service.cancel()
            except Exception:
                pass

    @staticmethod
    def _token(cancellation: Any) -> Any:
        if cancellation is None:
            return CancellationToken()
        return cancellation

    @staticmethod
    def _is_cancelled(token: Any) -> bool:
        if hasattr(token, "is_cancelled"):
            return bool(token.is_cancelled())
        if hasattr(token, "is_set"):
            return bool(token.is_set())
        return False

    @classmethod
    def _check_cancelled(cls, token: Any) -> None:
        if cls._is_cancelled(token):
            raise RunCancelled("The Orbea run was stopped")

    @staticmethod
    def _log(callback: LogCallback | None, message: str) -> None:
        if callback is None:
            return
        try:
            callback(message)
        except Exception:
            pass

    def discover_filter_options(self) -> PimboFilterOptions:
        return PimboBrowserClient(
            self.pimbo_driver, cancellation=self._cancellation
        ).discover_filter_options()

    def find_resumable_run(self, config: OrbeaRunConfig) -> Path | None:
        from .checkpoint import find_latest_compatible_run

        return find_latest_compatible_run(config)

    def _new_image_driver(self, config: OrbeaRunConfig) -> Any:
        if self.image_driver_factory is not None:
            try:
                return self.image_driver_factory(config.browser_name)
            except TypeError:
                return self.image_driver_factory()
        from tools.orbea_table_image_downloader import create_driver

        return create_driver(config.browser_name, False)

    @staticmethod
    def _terminal_image_status(status: Any) -> bool:
        return status in {"downloaded", "not_available"}

    @staticmethod
    def _upgrade_probe_record(record: dict[str, Any], current_version: int) -> bool:
        """Make old negative probes run once under the fast availability logic."""

        if record.get("availability_probe_version") == current_version:
            return False
        refresh_required = False
        for key in ("geometry_status", "size_guide_status"):
            if record.get(key) != "downloaded":
                record[key] = "pending"
                refresh_required = True
        if all(
            record.get(key) == "downloaded"
            for key in ("geometry_status", "size_guide_status")
        ):
            record["availability_probe_version"] = current_version
        record["probe_refresh_required"] = refresh_required
        return refresh_required

    def _image_jobs(self, checkpoint: RunCheckpoint) -> list[dict[str, Any]]:
        grouped: dict[str, dict[str, Any]] = {}
        for result in checkpoint.results:
            if result.get("status") != "code_match":
                continue
            canonical_url = canonicalize_url(result.get("catalogue_url", ""))
            if not canonical_url:
                result["geometry_status"] = "not_available"
                result["size_guide_status"] = "not_available"
                result["image_note"] = "The catalogue match has no valid Orbea URL"
                continue
            job = grouped.setdefault(
                canonical_url,
                {
                    "url": result.get("catalogue_url", ""),
                    "canonical_url": canonical_url,
                    "model": result.get("catalogue_model") or result.get("title") or "Orbea bike",
                    "models": [],
                    "variant_skus": [],
                    "row_keys": [],
                },
            )
            for key, value in (
                ("models", result.get("catalogue_model", "")),
                ("variant_skus", result.get("sku", "")),
                ("row_keys", result.get("row_key", "")),
            ):
                if value and value not in job[key]:
                    job[key].append(value)
        return list(grouped.values())

    def _download_images(
        self,
        config: OrbeaRunConfig,
        checkpoint: RunCheckpoint,
        reporter: _ProgressReporter,
        token: Any,
        log: LogCallback | None,
        *,
        retry_failed: bool,
    ) -> None:
        from tools.orbea_table_image_downloader import (
            AVAILABILITY_PROBE_VERSION,
            GEOMETRY_CAPTURE_VERSION,
            CaptureTimeouts,
            apply_capture_result,
            capture_orbea_tables,
            record_needs_processing,
        )

        jobs = self._image_jobs(checkpoint)
        checkpoint.save()
        processable: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for job in jobs:
            canonical = job["canonical_url"]
            folder_name = image_folder_name(job["model"], canonical)
            folder = checkpoint.run_dir / "images" / folder_name
            geometry_path = folder / "geometry.png"
            size_path = folder / "size-guide-cm.png"
            prior = dict(checkpoint.images.get(canonical, {}))
            record = {
                **prior,
                **job,
                "folder": relative_or_absolute(folder, checkpoint.run_dir),
                "geometry_image": relative_or_absolute(
                    geometry_path, checkpoint.run_dir
                ),
                "size_guide_image": relative_or_absolute(
                    size_path, checkpoint.run_dir
                ),
                "geometry_status": prior.get("geometry_status", "pending"),
                "size_guide_status": prior.get("size_guide_status", "pending"),
                "attempts": int(prior.get("attempts", 0)),
                "errors": list(prior.get("errors", [])),
            }
            if (
                record.get("geometry_status") == "downloaded"
                and record.get("geometry_capture_version")
                != GEOMETRY_CAPTURE_VERSION
            ):
                record["geometry_status"] = "pending"
            legacy_probe_refresh = self._upgrade_probe_record(
                record, AVAILABILITY_PROBE_VERSION
            )
            checkpoint.upsert_image(canonical, record)
            is_transient = "transient_error" in {
                record.get("geometry_status"),
                record.get("size_guide_status"),
            }
            if retry_failed:
                should_process = is_transient or legacy_probe_refresh
            else:
                should_process = record_needs_processing(record)
            if should_process:
                processable.append((job, record))

        if not processable:
            checkpoint.data["images_completed"] = not any(
                "transient_error"
                in {record.get("geometry_status"), record.get("size_guide_status")}
                for record in checkpoint.images.values()
            )
            checkpoint.save()
            reporter.emit("images", len(jobs), len(jobs), "No image downloads are pending")
            return

        timeouts = CaptureTimeouts(
            page_load=config.navigation_timeout,
            control_discovery=config.control_discovery_timeout,
            table_render=config.table_render_timeout,
            selector=config.selector_timeout,
        )
        self._image_driver = self._new_image_driver(config)
        try:
            for job_index, (job, record) in enumerate(processable, start=1):
                self._check_cancelled(token)
                folder = checkpoint.run_dir / record["folder"]
                geometry_path = checkpoint.run_dir / record["geometry_image"]
                size_path = checkpoint.run_dir / record["size_guide_image"]
                folder.mkdir(parents=True, exist_ok=True)

                # A normal run gets one initial attempt plus the configured
                # automatic retry. The explicit Retry Failed action gets one
                # new attempt and never touches terminal missing-table results.
                attempt_budget = 1 if retry_failed else max(
                    1 + config.image_retry_limit - int(record.get("attempts", 0)), 0
                )
                if record.pop("probe_refresh_required", False):
                    attempt_budget = max(attempt_budget, 1)
                attempts_this_run = 0
                while attempts_this_run < attempt_budget:
                    self._check_cancelled(token)
                    need_geometry = not self._terminal_image_status(
                        record.get("geometry_status")
                    )
                    need_size = not self._terminal_image_status(
                        record.get("size_guide_status")
                    )
                    if not need_geometry and not need_size:
                        break
                    record["attempts"] = int(record.get("attempts", 0)) + 1
                    record["last_attempt_at"] = utc_now()
                    self._log(
                        log,
                        f"Tables {job_index}/{len(processable)}: {job['model']} "
                        f"(attempt {record['attempts']})",
                    )
                    result = capture_orbea_tables(
                        self._image_driver,
                        job["url"],
                        geometry_path,
                        size_path,
                        need_geometry=need_geometry,
                        need_size_guide=need_size,
                        geometry_position="low",
                        timeouts=timeouts,
                    )
                    apply_capture_result(record, result, "low")
                    record["retryable"] = bool(result.get("retryable"))
                    checkpoint.upsert_image(job["canonical_url"], record)
                    attempts_this_run += 1
                    if not record["retryable"]:
                        break
                    if attempts_this_run < attempt_budget:
                        self._log(log, f"Retrying transient table error for {job['model']}")

                reporter.emit(
                    "images",
                    job_index,
                    len(processable),
                    f"{job['model']}: {record.get('geometry_status')} / {record.get('size_guide_status')}",
                )
        finally:
            driver = self._image_driver
            self._image_driver = None
            if driver is not None:
                try:
                    driver.quit()
                except Exception:
                    pass

        checkpoint.data["images_completed"] = not any(
            "transient_error"
            in {record.get("geometry_status"), record.get("size_guide_status")}
            for record in checkpoint.images.values()
        )
        checkpoint.data["images_completed_at"] = utc_now()
        checkpoint.save()

    def _download_product_photos(
        self,
        checkpoint: RunCheckpoint,
        reporter: _ProgressReporter,
        token: Any,
        log: LogCallback | None,
    ) -> None:
        """Download every published colour for each unique matched Orbea URL."""

        urls = [
            str(job.get("url") or "").strip()
            for job in self._image_jobs(checkpoint)
            if str(job.get("url") or "").strip()
        ]
        output_dir = checkpoint.run_dir / "product-photos"
        if not urls:
            checkpoint.data["product_photos"] = {
                "completed": True,
                "products": 0,
                "variants": 0,
                "views": 0,
                "files": 0,
                "unavailable": 0,
                "failures": [],
                "output_dir": relative_or_absolute(output_dir, checkpoint.run_dir),
            }
            checkpoint.data["product_photos_completed"] = True
            checkpoint.save()
            reporter.emit(
                "product_photos", 0, 0, "No matched Orbea product links were found"
            )
            return

        if self.photo_service_factory is None:
            from .photos import OrbeaPhotoService

            service = OrbeaPhotoService()
        else:
            service = self.photo_service_factory()
        self._photo_service = service

        def photo_progress(update: Any) -> None:
            reporter.emit(
                "product_photos",
                int(getattr(update, "current", 0) or 0),
                int(getattr(update, "total", 0) or 0),
                str(getattr(update, "message", "") or "Downloading product photos"),
            )

        try:
            result = service.run_many(
                urls,
                output_dir,
                progress=photo_progress,
                log=lambda message: self._log(log, message),
                cancellation=token,
            )
        except Exception as error:
            message = f"{type(error).__name__}: {error}"
            checkpoint.data["product_photos"] = {
                "completed": False,
                "products": 0,
                "variants": 0,
                "views": 0,
                "files": 0,
                "unavailable": 0,
                "failures": [message],
                "output_dir": relative_or_absolute(output_dir, checkpoint.run_dir),
            }
            checkpoint.data["product_photos_completed"] = False
            checkpoint.save()
            self._log(log, f"Product photos could not be completed: {message}")
            reporter.emit("product_photos", len(urls), len(urls), message)
            self._check_cancelled(token)
            return
        finally:
            self._photo_service = None

        failures = [str(value) for value in getattr(result, "failures", ())]
        cancelled = bool(getattr(result, "cancelled", False))
        completed = not cancelled and not failures
        checkpoint.data["product_photos"] = {
            "completed": completed,
            "products": int(getattr(result, "products", 0) or 0),
            "variants": int(getattr(result, "variants", 0) or 0),
            "views": int(getattr(result, "views", 0) or 0),
            "files": len(getattr(result, "files", ()) or ()),
            "unavailable": len(getattr(result, "unavailable", ()) or ()),
            "failures": failures,
            "output_dir": relative_or_absolute(output_dir, checkpoint.run_dir),
            "completed_at": utc_now(),
        }
        checkpoint.data["product_photos_completed"] = completed
        checkpoint.save()
        self._log(
            log,
            "Product photos: "
            f"{checkpoint.data['product_photos']['files']} files from "
            f"{checkpoint.data['product_photos']['products']} products",
        )
        if cancelled:
            raise RunCancelled("The Orbea product photo download was stopped")

    def run(
        self,
        config: OrbeaRunConfig,
        *,
        progress: ProgressCallback | None = None,
        log: LogCallback | None = None,
        cancellation: Any = None,
        resume: bool = True,
        retry_failed: bool = False,
    ) -> OrbeaRunResult:
        if not config.catalogue_path.is_file():
            raise FileNotFoundError(f"Orbea catalogue not found: {config.catalogue_path}")
        token = self._token(cancellation)
        if isinstance(token, CancellationToken):
            self._cancellation = token
        elif hasattr(token, "set") and hasattr(token, "is_set"):
            self._cancellation = CancellationToken(token)
            token = self._cancellation
        else:
            self._cancellation = CancellationToken()
        if not PIMBO_AUTOMATION_LOCK.acquire(blocking=False):
            raise RuntimeError("Another Orbea Pimbo scan is already running")

        checkpoint: RunCheckpoint | None = None
        reporter: _ProgressReporter | None = None
        cancelled = False
        failure: BaseException | None = None
        try:
            checkpoint = open_or_create_checkpoint(
                config, resume=resume, retry_failed=retry_failed
            )
            reporter = _ProgressReporter(progress, checkpoint)
            self._check_cancelled(token)
            catalogue = CatalogueIndex.from_workbook(config.catalogue_path)
            self._log(log, f"Loaded Orbea catalogue: {config.catalogue_path.name}")

            if not retry_failed and not checkpoint.data.get("scan_completed"):
                checkpoint.set_phase("pimbo_scan")
                client = PimboBrowserClient(
                    self.pimbo_driver, cancellation=token
                )

                def row_progress(current: int, total: int | None, message: str) -> None:
                    reporter.emit("pimbo_scan", current, total, message)

                client.collect(
                    catalogue,
                    checkpoint,
                    config,
                    retry_failed=False,
                    row_progress=row_progress,
                    log=lambda message: self._log(log, message),
                )

            self._check_cancelled(token)
            if config.download_images:
                checkpoint.set_phase("images")
                self._download_images(
                    config,
                    checkpoint,
                    reporter,
                    token,
                    log,
                    retry_failed=retry_failed,
                )
            else:
                checkpoint.data["images_completed"] = True
                checkpoint.save()

            self._check_cancelled(token)
            if config.download_product_photos:
                checkpoint.set_phase("product_photos")
                if checkpoint.data.get("product_photos_completed"):
                    summary = checkpoint.data.get("product_photos", {})
                    completed_files = int(summary.get("files", 0) or 0)
                    reporter.emit(
                        "product_photos",
                        completed_files,
                        completed_files,
                        "Product photos are already complete",
                    )
                else:
                    self._download_product_photos(checkpoint, reporter, token, log)
            else:
                checkpoint.data["product_photos_completed"] = True
                checkpoint.save()

            self._check_cancelled(token)
            checkpoint.set_phase("report")
            write_image_manifest(checkpoint)
            write_report(checkpoint)
            reporter.emit("report", 1, 1, "Excel report is ready")

            complete = (
                bool(checkpoint.data.get("scan_completed"))
                and bool(checkpoint.data.get("images_completed"))
                and bool(checkpoint.data.get("product_photos_completed"))
            )
            if complete:
                checkpoint.mark_completed()
            else:
                checkpoint.data["completed"] = False
                checkpoint.save()
        except RunCancelled:
            cancelled = True
            if checkpoint is not None:
                checkpoint.mark_cancelled()
        except BaseException as error:
            failure = error
            if checkpoint is not None:
                checkpoint.data["last_error"] = f"{type(error).__name__}: {error}"
                checkpoint.data["completed"] = False
                checkpoint.save()
        finally:
            if checkpoint is not None:
                # Stop and browser exceptions still yield a usable partial file.
                try:
                    write_image_manifest(checkpoint)
                    write_report(checkpoint)
                except Exception as report_error:
                    if failure is None:
                        failure = report_error
            PIMBO_AUTOMATION_LOCK.release()

        if failure is not None:
            raise failure
        assert checkpoint is not None
        return OrbeaRunResult(
            run_dir=checkpoint.run_dir,
            workbook_path=checkpoint.workbook_path,
            checkpoint_path=checkpoint.path,
            manifest_path=checkpoint.manifest_path,
            completed=bool(checkpoint.data.get("completed")),
            cancelled=cancelled or bool(checkpoint.data.get("cancelled")),
            resumed=checkpoint.resumed,
            counts=checkpoint.counts(),
        )


def run_pipeline(
    pimbo_driver: Any,
    config: OrbeaRunConfig,
    *,
    image_driver_factory: Callable[..., Any] | None = None,
    photo_service_factory: Callable[[], Any] | None = None,
    progress: ProgressCallback | None = None,
    log: LogCallback | None = None,
    cancellation: Any = None,
    resume: bool = True,
    retry_failed: bool = False,
) -> OrbeaRunResult:
    """Convenience entry point used by the Qt worker and standalone callers."""

    return OrbeaAutomationService(
        pimbo_driver,
        image_driver_factory=image_driver_factory,
        photo_service_factory=photo_service_factory,
    ).run(
        config,
        progress=progress,
        log=log,
        cancellation=cancellation,
        resume=resume,
        retry_failed=retry_failed,
    )
