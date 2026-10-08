from __future__ import annotations

import inspect
import json
import threading
import time
from pathlib import Path
from typing import Any, Callable

from .catalogue import CatalogueEntry, CatalogueIndex, MatchResult
from .checkpoint import (
    RunCheckpoint,
    atomic_write_json,
    open_or_create_checkpoint,
    utc_now,
)
from .models import (
    CancellationToken,
    OrbeaRunConfig,
    OrbeaRunFailure,
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
    """Scan Pimbo, resolve Orbea products, and collect local assets and reports.

    ``pimbo_driver`` remains owned by the application. Any browser returned by
    ``image_driver_factory`` is owned and closed by this service.
    """

    def __init__(
        self,
        pimbo_driver: Any,
        image_driver_factory: Callable[..., Any] | None = None,
        photo_service_factory: Callable[[], Any] | None = None,
        website_client_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.pimbo_driver = pimbo_driver
        self.image_driver_factory = image_driver_factory
        self.photo_service_factory = photo_service_factory
        self.website_client_factory = website_client_factory
        self._cancellation = CancellationToken()
        self._image_driver: Any = None
        self._photo_service: Any = None
        self._website_client: Any = None

    def cancel(self) -> None:
        self._cancellation.cancel()
        if self._website_client is not None:
            self._website_client.cancel()
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
            factory = self.image_driver_factory
            try:
                signature = inspect.signature(factory)
            except (TypeError, ValueError):
                return factory(config.browser_name)
            try:
                signature.bind(config.browser_name)
            except TypeError:
                # Resolve the supported call before constructing a browser.
                # An internal TypeError must propagate without a second call.
                signature.bind()
                return factory()
            return factory(config.browser_name)
        from tools.orbea_table_image_downloader import create_driver

        # A dedicated public-site browser keeps normal site cookies between runs
        # and makes any verification available to the user.
        profile_dir = config.output_root / ".orbea-browser" / config.browser_name.casefold()
        return create_driver(config.browser_name, True, config.navigation_timeout, profile_dir=profile_dir)

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
            if result.get("website_validation_error"):
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
        row_keys: set[str] | None = None,
        driver_factory: Callable[[], Any] | None = None,
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
        if row_keys is not None:
            jobs = [job for job in jobs if row_keys.intersection(job["row_keys"])]
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
            if config.collect_product_data:
                missing_files = False
                for status_key, path in (("geometry_status", geometry_path), ("size_guide_status", size_path)):
                    if record.get(status_key) == "downloaded" and not path.is_file():
                        record[status_key] = "pending"
                        missing_files = True
                if record.get("geometry_status") == "downloaded" and any(
                    not (folder / variant["filename"]).is_file()
                    for variant in record.get("geometry_variants", []) if variant.get("filename")
                ):
                    record["geometry_status"] = "pending"
                    missing_files = True
                if missing_files:
                    record["attempts"] = 0
                    record["probe_refresh_required"] = True
                    legacy_probe_refresh = True
            checkpoint.upsert_image(canonical, record)
            is_transient = "transient_error" in {
                record.get("geometry_status"),
                record.get("size_guide_status"),
            }
            if retry_failed:
                should_process = is_transient or legacy_probe_refresh or (config.collect_product_data and not prior)
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
        self._image_driver = driver_factory() if driver_factory else self._new_image_driver(config)
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
                        **({"after_navigation": self._website_client.wait_for_product}
                           if driver_factory is not None and callable(getattr(self._website_client, "wait_for_product", None)) else {}),
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
            if driver is not None and driver_factory is None:
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
                asset_root=checkpoint.run_dir.parent / ".orbea-assets",
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

    def _lookup_products(self, website, checkpoint, reporter, token, log) -> None:
        from .website import OrbeaAccessError, WEBSITE_LOOKUP_VERSION, template_code

        rows = [row for row in checkpoint.results if row.get("sku") and row.get("status") in {"code_match", "title_only", "ambiguous", "unmatched"}]
        matches = {}
        saved_queries = set()
        lookup_errors = {}
        regions_recorded = False
        for saved in rows:
            if saved.get("website_lookup_version") == WEBSITE_LOOKUP_VERSION and saved.get("website_lookup_status") == "done":
                query = template_code(saved["sku"])
                if not query:
                    continue
                if saved.get("status") == "code_match" and saved.get("catalogue_code") == query and saved.get("catalogue_url"):
                    matches[query] = MatchResult("code_match", "Orbea TTCC search", CatalogueEntry(
                        query[:-4], query, saved.get("catalogue_model", ""), product_link=saved["catalogue_url"]))
                    saved_queries.add(query)
                elif saved.get("status") == "unmatched":
                    # A completed regional search with no exact match is also
                    # a reusable result. Retryable errors are never seeded.
                    matches.setdefault(query, MatchResult("unmatched", "Orbea TTCC search", None, saved.get("note", "")))
                    saved_queries.add(query)
        for index, row in enumerate(rows, 1):
            self._check_cancelled(token)
            checkpoint.set_phase("website_lookup")
            if row.get("website_lookup_status") == "done" and row.get("website_lookup_version") == WEBSITE_LOOKUP_VERSION:
                continue
            previous_error = row.pop("website_validation_error", None)
            if previous_error and row.get("website_lookup_status") == "error":
                row["note"] = ""
            query = template_code(row["sku"])
            reused_result = bool(query and (query in matches or query in lookup_errors))
            row["website_lookup_query"] = query
            row["website_lookup_source"] = "saved_result" if query in saved_queries else "shared_result" if reused_result else "search"
            message = f"Reusing Orbea result: {query} for {row['sku']}" if reused_result else f"Finding Orbea URL: {query or row['sku']}"
            reporter.emit("website_lookup", index - 1, len(rows), message)
            try:
                if query in lookup_errors:
                    raise lookup_errors[query]
                match = matches.get(query)
                if match is None:
                    discover = getattr(website, "discover_regions", None)
                    if callable(discover) and not regions_recorded:
                        checkpoint.data["orbea_regions"] = list(discover())
                        checkpoint.save()
                        regions_recorded = True
                    match = website.lookup(row["sku"], row.get("title", ""))
                    if query:
                        matches[query] = match
                if row.get("catalogue_url") and (match.entry is None or row["catalogue_url"] != match.entry.product_link):
                    row.pop("collection_stages", None)
                    row.pop("collection_status", None)
                row.update(status=match.status, match_method=match.method, note=match.note, **match.catalogue_fields())
                row["website_lookup_status"] = "done"
                row["website_lookup_version"] = WEBSITE_LOOKUP_VERSION
                if getattr(website, "regions", None):
                    checkpoint.data["orbea_regions"] = list(website.regions)
            except RunCancelled:
                raise
            except OrbeaAccessError as error:
                row["website_validation_error"] = f"{type(error).__name__}: {error}"
                row["website_lookup_status"] = "error"
                row["note"] = str(error)
                if checkpoint.data.get("compatibility", {}).get("collect_product_data"):
                    row["collection_status"] = "partial"
                checkpoint.data["website_lookup_completed"] = False
                checkpoint.save()
                self._log(log, str(error))
                reporter.emit("website_lookup", index, len(rows), str(error))
                # The security check applies to the website, not just this SKU.
                # Stop once and expose the report instead of retrying every row.
                raise
            except ValueError as error:
                lookup_errors[query] = error
                row["status"] = "ambiguous"
                row["note"] = str(error)
                row["website_validation_error"] = str(error)
                row["website_lookup_status"] = "error"
            except Exception as error:
                lookup_errors[query] = error
                row["status"] = "ambiguous"
                row["website_validation_error"] = f"{type(error).__name__}: {error}"
                row["website_lookup_status"] = "error"
                row["note"] = row["website_validation_error"]
            checkpoint.save()
            if reused_result:
                self._log(log, f"Orbea website: {row['sku']} — Reused {query} result ({row['status']}); no new region searches")
                message = f"{row['sku']}: reused {query} result ({row['status']})"
            else:
                self._log(log, f"Orbea website: {row['sku']} ({query}) — {row.get('note') or row['status']}")
                message = f"{row['sku']}: {row['status']}"
            reporter.emit("website_lookup", index, len(rows), message)
        checkpoint.data["website_lookup_completed"] = not any(row.get("website_lookup_status") == "error" for row in rows)
        checkpoint.save()

    def _prepare_matched_retry(self, config, checkpoint):
        """Make selected downloads pending while retaining the saved matches."""
        rows = [row for row in checkpoint.results
                if row.get("status") == "code_match" and row.get("catalogue_url")]
        if not rows:
            raise ValueError("The saved run has no matched Orbea products to retry")
        selected = {stage for stage, enabled in (
            ("description", config.download_description),
            ("specifications", config.download_specifications),
            ("photos", config.download_product_photos),
            ("tables", config.download_images),
        ) if enabled}
        if not selected:
            raise ValueError("No downloads were selected for this saved Orbea run")
        for row in rows:
            stages = row.setdefault("collection_stages", {})
            for stage in selected:
                stages[stage] = {**stages.get(stage, {}), "status": "pending", "note": ""}
            row["collection_status"] = "partial"
            row["collection_errors"] = []
            # A stopped refresh must not expose the old text as a successful
            # current capture when packages are loaded for upload.
            if row.get("local_folder"):
                folder = (checkpoint.run_dir / row["local_folder"]).resolve()
                if folder.is_relative_to(checkpoint.run_dir.resolve()):
                    metadata = folder / "orbea-product.json"
                    if metadata.is_file():
                        data = json.loads(metadata.read_text(encoding="utf-8-sig"))
                        if data.get("pimbo_product_id") == row.get("product_id") and data.get("sku") == row.get("sku"):
                            data.update(status="partial", stages=stages, errors=[], warnings=[])
                            atomic_write_json(metadata, data)
        if "tables" in selected:
            urls = {canonicalize_url(row["catalogue_url"]) for row in rows}
            for url in urls:
                if url in checkpoint.images:
                    checkpoint.images[url].update(geometry_status="pending", size_guide_status="pending",
                        attempts=0, errors=[], retryable=True, probe_refresh_required=True)
            checkpoint.data["images_completed"] = False
        if "photos" in selected:
            checkpoint.data["product_photos_completed"] = False
        if config.collect_product_data:
            checkpoint.data["product_data_completed"] = False
        checkpoint.data["completed"] = False
        checkpoint.save()
        return len(rows)

    def _collect_website_products(self, website, config, checkpoint, reporter, token, log, *, retry_failed, retry_matched=False):
        """Gather all code-confirmed URLs, then collect their selected assets."""
        from .collection import collect_packages, missing_downloads, validate_product
        from .website import OrbeaAccessError
        pending_by_url = {}
        product_cache = {}
        photo_cache = {}

        def collect_product(row):
            self._check_cancelled(token)
            if row.get("status") == "code_match":
                pending = missing_downloads(row, config, checkpoint.run_dir)
                if config.downloads_only and not pending:
                    if config.download_product_photos:
                        from .photo_packages import package_folder
                        package_folder(checkpoint, row)
                    return
                source_needs = pending_by_url.get(canonicalize_url(row["catalogue_url"]), pending)
                website.collect_description = "description" in source_needs
                website.collect_specifications = "specifications" in source_needs
                if any((config.download_images, config.download_description, config.download_specifications, config.download_product_photos)):
                    checkpoint.set_phase("product_data")
                    try:
                        key = canonicalize_url(row["catalogue_url"])
                        if key not in product_cache:
                            product_cache[key] = website.fetch(row["catalogue_url"])
                        validate_product(product_cache[key], row)
                        row.pop("website_validation_error", None)
                    except (RunCancelled, OrbeaAccessError):
                        raise
                    except ValueError as error:
                        row.update(status="ambiguous", note=str(error), website_validation_error=str(error), collection_status="partial", website_lookup_status="error")
                        checkpoint.data["website_lookup_completed"] = False
                        checkpoint.save()
                        write_report(checkpoint)
                        return
                    except Exception as error:
                        row["website_validation_error"] = f"{type(error).__name__}: {error}"
                if config.download_images and (not config.downloads_only or "tables" in pending) and not row.get("website_validation_error"):
                    checkpoint.set_phase("images")
                    # Reuse the owned public-site browser, like KROSS collection.
                    factory = (lambda: website.driver) if getattr(website, "driver_factory", None) else None
                    self._download_images(config, checkpoint, reporter, token, log,
                        retry_failed=retry_failed, row_keys={row["row_key"]}, driver_factory=factory)
                checkpoint.set_phase("product_data")
                collect_packages(self, website, config, checkpoint, reporter, token, log, rows=[row],
                                 product_cache=product_cache, photo_cache=photo_cache)
            write_image_manifest(checkpoint)
            write_report(checkpoint)

        # Make the full scan report usable while collection is still running.
        write_image_manifest(checkpoint)
        write_report(checkpoint)
        if not retry_matched and not config.downloads_only:
            self._lookup_products(website, checkpoint, reporter, token, log)
        write_report(checkpoint)
        if not retry_matched and not config.downloads_only and not checkpoint.data.get("website_lookup_completed"):
            return
        rows = [row for row in checkpoint.results if row.get("status") == "code_match"]
        for row in rows:
            pending_by_url.setdefault(canonicalize_url(row.get("catalogue_url")), set()).update(
                missing_downloads(row, config, checkpoint.run_dir))
        for index, row in enumerate(rows, 1):
            collect_product(row)
            reporter.emit("product_data", index, len(rows), f"{row['sku']}: {row.get('collection_status', 'checked')}")
        checkpoint.data["images_completed"] = not config.download_images or not any(
            record.get(field) not in {"downloaded", "not_available"}
            for record in checkpoint.images.values() for field in ("geometry_status", "size_guide_status"))
        checkpoint.data["product_data_completed"] = all(not missing_downloads(row, config, checkpoint.run_dir)
            for row in checkpoint.results if row.get("status") == "code_match")
        checkpoint.data["product_photos_completed"] = not config.download_product_photos or not any(
            row.get("collection_stages", {}).get("photos", {}).get("status") == "error" for row in checkpoint.results)
        checkpoint.save()

    def _finalize_run(
        self, checkpoint: RunCheckpoint | None, log: LogCallback | None,
        failure: BaseException | None,
    ) -> BaseException | None:
        """Close owned resources and preserve reports even when cleanup fails."""
        website, self._website_client = self._website_client, None
        if website is not None:
            try:
                website.close()
            except Exception as error:
                self._log(log, f"Could not close the Orbea browser: {error}")
                if failure is None:
                    failure = error
        if checkpoint is not None:
            try:
                if failure is not None:
                    checkpoint.data["last_error"] = f"{type(failure).__name__}: {failure}"
                    checkpoint.data["completed"] = False
                    checkpoint.save()
                write_image_manifest(checkpoint)
                write_report(checkpoint)
            except Exception as error:
                if failure is None:
                    failure = error
                self._log(log, f"Could not refresh the partial report: {error}")
                checkpoint.data["completed"] = False
                checkpoint.data["last_error"] = f"{type(failure).__name__}: {failure}"
                try:
                    checkpoint.save()
                except Exception as save_error:
                    self._log(log, f"Could not save the final checkpoint: {save_error}")
        return failure

    def run(
        self,
        config: OrbeaRunConfig,
        *,
        progress: ProgressCallback | None = None,
        log: LogCallback | None = None,
        cancellation: Any = None,
        resume: bool = True,
        retry_failed: bool = False,
        retry_matched: bool = False,
        download_missing: bool = False,
    ) -> OrbeaRunResult:
        download_missing = download_missing or config.downloads_only
        if download_missing:
            from dataclasses import replace
            config = replace(config, collect_product_data=True, downloads_only=True)
            if not config.resume_run_dir:
                raise ValueError("Open a saved Orbea collection before downloading missing items")
            if not any((config.download_images, config.download_product_photos, config.download_description, config.download_specifications)):
                raise ValueError("Select the items to download from this saved collection")
        if config.resume_run_dir is None and not retry_matched and config.catalogue_path is not None and not config.catalogue_path.is_file():
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
                config, resume=resume, retry_failed=retry_failed, retry_matched=retry_matched, download_missing=download_missing
            )
            reporter = _ProgressReporter(progress, checkpoint)
            self._check_cancelled(token)
            if retry_matched:
                count = self._prepare_matched_retry(config, checkpoint)
                retry_failed = False
                self._log(log, f"Retrying saved downloads for all {count} matched Orbea products")
                reporter.emit("product_data", 0, count, f"Retrying all {count} matched products")
            if download_missing:
                if not any(row.get("status") == "code_match" and row.get("catalogue_url") for row in checkpoint.results):
                    raise ValueError("This saved collection has no matched Orbea product links")
                checkpoint.data["completed"] = False
                checkpoint.save()
                self._log(log, "Downloading only missing selected items using saved Orbea links")
            scan_pending = not checkpoint.data.get("scan_completed") and not retry_matched and not download_missing
            catalogue = CatalogueIndex.from_workbook(config.catalogue_path) if scan_pending and config.catalogue_path else CatalogueIndex((), allow_empty=True)
            if scan_pending and config.catalogue_path:
                self._log(log, f"Loaded Orbea catalogue: {config.catalogue_path.name}")
            elif not scan_pending:
                self._log(log, "Continuing the saved Pimbo scan; no Pimbo connection is needed for Orbea downloads")
            website = None
            from .website import OrbeaWebsiteClient
            factory = self.website_client_factory or OrbeaWebsiteClient
            website = factory(lambda: self._new_image_driver(config), token, config.navigation_timeout)
            website.collect_description = config.download_description
            website.collect_specifications = config.download_specifications
            self._website_client = website
            access_phase = None

            def access_progress(waiting: bool, message: str) -> None:
                nonlocal access_phase
                if waiting:
                    access_phase = checkpoint.data.get("phase", "website_lookup")
                    checkpoint.set_phase("website_access")
                    try:
                        write_image_manifest(checkpoint)
                        write_report(checkpoint)
                    except Exception as report_error:
                        self._log(log, f"Could not refresh the partial report: {report_error}")
                else:
                    checkpoint.set_phase(access_phase or "website_lookup")
                self._log(log, message)
                reporter.emit("website_access" if waiting else (access_phase or "website_lookup"), 0, None, message)

            website.access_progress = access_progress
            if not retry_failed and not retry_matched and not download_missing and not checkpoint.data.get("scan_completed"):
                if self.pimbo_driver is None:
                    raise RuntimeError("Log in to Pimbo to continue the unfinished product scan")
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
            if website is not None:
                checkpoint.set_phase("product_data" if retry_matched else "website_lookup")
                if config.collect_product_data:
                    self._collect_website_products(website, config, checkpoint, reporter, token, log, retry_failed=retry_failed, retry_matched=retry_matched)
                elif not retry_matched:
                    self._lookup_products(website, checkpoint, reporter, token, log)
            self._check_cancelled(token)
            if config.download_images and not config.collect_product_data and (retry_matched or checkpoint.data.get("website_lookup_completed")):
                checkpoint.set_phase("images")
                self._download_images(
                    config,
                    checkpoint,
                    reporter,
                    token,
                    log,
                    retry_failed=retry_failed,
                )
            elif not config.download_images:
                checkpoint.data["images_completed"] = True
                checkpoint.save()

            self._check_cancelled(token)
            if not config.collect_product_data and config.download_product_photos and (retry_matched or checkpoint.data.get("website_lookup_completed")):
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
            elif not config.collect_product_data:
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
                and (website is None or bool(checkpoint.data.get("website_lookup_completed")))
                and (not config.collect_product_data or bool(checkpoint.data.get("product_data_completed")))
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
            try:
                failure = self._finalize_run(checkpoint, log, failure)
            finally:
                PIMBO_AUTOMATION_LOCK.release()

        if failure is not None and checkpoint is None:
            raise failure
        assert checkpoint is not None
        result = OrbeaRunResult(
            run_dir=checkpoint.run_dir,
            workbook_path=checkpoint.workbook_path,
            checkpoint_path=checkpoint.path,
            manifest_path=checkpoint.manifest_path,
            completed=bool(checkpoint.data.get("completed")),
            cancelled=cancelled or bool(checkpoint.data.get("cancelled")),
            resumed=checkpoint.resumed,
            counts=checkpoint.counts(),
        )
        if failure is not None:
            from .website import OrbeaAccessError
            reason = "website_access" if isinstance(failure, OrbeaAccessError) else ""
            raise OrbeaRunFailure(str(failure), result, reason=reason) from failure
        return result


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
    retry_matched: bool = False,
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
        retry_matched=retry_matched,
    )
