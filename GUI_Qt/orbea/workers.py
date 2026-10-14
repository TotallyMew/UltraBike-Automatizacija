"""Thread workers for the integrated Orbea workflow."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QThread, Signal

from tools.orbea_automation.models import CancellationToken


class _OrbeaServiceWorker(QThread):
    """Keep one cancellation token through construction, execution and stopping."""

    progress_changed = Signal(object)
    log_message = Signal(str)
    succeeded = Signal(object)
    failed = Signal(str)
    skip_cancelled = False

    def __init__(self, make_service: Callable[..., Any], *service_args):
        super().__init__()
        self.make_service = make_service
        self._service_args = service_args
        self._service = None
        self._token = CancellationToken()
        self._stop_requested = False
        self._cancel_lock = threading.Lock()
        self._service_cancelled = False

    @property
    def stop_requested(self) -> bool:
        return self._token.is_cancelled()

    def request_stop(self):
        self._stop_requested = True
        self._token.cancel()
        self.requestInterruption()
        self._cancel_service()

    def _cancel_service(self):
        # Stop can arrive while the factory is still constructing the service.
        # Either that stop or the construction handshake cancels it, once.
        with self._cancel_lock:
            service = self._service
            if service is None or self._service_cancelled:
                return
            self._service_cancelled = True
        cancel = getattr(service, "cancel", None)
        if callable(cancel):
            try:
                cancel()
            except Exception:
                # A cleanup error must not undo the already-cancelled token.
                pass

    def _callbacks(self) -> dict[str, Any]:
        return {
            "progress": self.progress_changed.emit,
            "log": self.log_message.emit,
            "cancellation": self._token,
        }

    def run(self):
        try:
            if self.skip_cancelled and self.stop_requested:
                return
            service = self.make_service(*self._service_args)
            with self._cancel_lock:
                self._service = service
            if self.stop_requested:
                self._cancel_service()
                if self.skip_cancelled:
                    return
            result = self._execute(service)
            self._emit_result(result)
        except Exception as exc:
            self._emit_error(exc)

    def _execute(self, service):
        raise NotImplementedError

    def _emit_result(self, result):
        self.succeeded.emit(result)

    def _emit_error(self, exc):
        self.failed.emit(str(exc))


class OrbeaModelCopyWorker(_OrbeaServiceWorker):
    item_finished = Signal(object)
    progress_ready = Signal(object, object)

    def __init__(self, factory, driver, workbook, mode, selected_ttcc=(), *,
                 browser_count=1, browser_pool_factory=None):
        super().__init__(factory, driver)
        self.workbook, self.mode, self.selected_ttcc = workbook, mode, selected_ttcc
        self.driver = driver
        self.browser_count = max(1, min(4, int(browser_count)))
        self.browser_pool_factory = browser_pool_factory
        self._progress_lock = threading.Lock()

    def _publish_item(self, item, snapshot):
        self.item_finished.emit(item)
        try:
            # Files and full snapshots are processed by a worker, never a GUI
            # slot. Serialize publication so parallel snapshots arrive in order.
            with self._progress_lock:
                state = snapshot()
                self.progress_ready.emit(item, state)
        except (OSError, ValueError, KeyError, TypeError) as error:
            self.log_message.emit(str(error))

    def _execute(self, service):
        if self.browser_count > 1 and len(self.selected_ttcc) > 1:
            return self._execute_parallel(service)
        from tools.orbea_automation.model_copy import OrbeaModelCopyService
        publish = lambda item: self._publish_item(item, lambda: OrbeaModelCopyService.load_checkpoint(self.workbook))
        if self.mode == "capture":
            return service.capture_templates(self.workbook, selected_ttcc=self.selected_ttcc,
                                             item_finished=publish, **self._callbacks())
        return service.run(self.workbook, selected_ttcc=self.selected_ttcc,
                           retry_failed=self.mode == "retry", item_finished=publish, **self._callbacks())

    def _execute_parallel(self, primary):
        from .browser_pool import BrowserTaskQueue
        from tools.orbea_automation.parallel_copy import ModelCopyCheckpoint
        if self.browser_pool_factory is None:
            raise RuntimeError("Parallel copying requires an authenticated browser pool")
        primary.prepare_upload_batch((None, None), progress=self.log_message.emit)
        checkpoint = ModelCopyCheckpoint(self.workbook, capture=self.mode == "capture",
                                         mapping_changed=primary._colour_mapping_changed)
        queue = BrowserTaskQueue(self.selected_ttcc, lambda: self.stop_requested)
        count = min(self.browser_count, len(self.selected_ttcc))
        with self.browser_pool_factory(count, self.log_message.emit, queue.is_cancelled) as pool:
            services = {id(pool.drivers[0]): primary}
            for driver in pool.drivers[1:]:
                service = self.make_service(driver)
                if any(service is old for old in services.values()):
                    raise RuntimeError("Each parallel browser must have its own copying service")
                try:
                    service.prepare_upload_batch((None, None), progress=self.log_message.emit)
                except Exception:
                    pool.preserve(driver)
                    raise
                services[id(driver)] = service

            def execute(number, driver, ttcc):
                service = services[id(driver)]
                service.configure_parallel(checkpoint, (ttcc,))
                callbacks = dict(progress=lambda message: self.progress_changed.emit(f"[Browser {number}] {message}"),
                                 log=lambda message: self.log_message.emit(f"[Browser {number}] {message}"),
                                 cancellation=queue, item_finished=lambda item: self._publish_item(item, checkpoint.snapshot),
                                 selected_ttcc=(ttcc,))
                try:
                    state = (service.capture_templates(self.workbook, **callbacks) if self.mode == "capture" else
                             service.run(self.workbook, retry_failed=self.mode == "retry", **callbacks))
                    if state.error:
                        raise RuntimeError(f"Browser {number}: {state.error}")
                except Exception:
                    pool.preserve(driver)
                    queue.fatal.set()
                    raise

            queue.run(pool.drivers, execute)
            for error in queue.errors:
                self.log_message.emit(error)
        state = checkpoint.snapshot()
        state.cancelled = self.stop_requested
        state.error = " | ".join(queue.errors)
        return state


class OrbeaFilterWorker(_OrbeaServiceWorker):
    loaded = Signal(object)
    skip_cancelled = True

    def __init__(self, driver, make_service: Callable[[Any], Any]):
        super().__init__(make_service, driver)
        self.driver = driver

    def _execute(self, service):
        return service.discover_filter_options()

    def _emit_result(self, result):
        if not self.stop_requested:
            self.loaded.emit(result)

    def _emit_error(self, exc):
        if not self.stop_requested:
            super()._emit_error(exc)


class OrbeaRunWorker(_OrbeaServiceWorker):
    partial_result = Signal(object)
    website_blocked = Signal(str)

    def __init__(
        self, driver, make_service: Callable[[Any], Any], config, *,
        resume: bool, retry_failed: bool, retry_matched: bool = False,
        download_missing: bool = False,
        selected_jobs=(),
        download_request=None,
    ):
        super().__init__(make_service, driver)
        self.driver = driver
        self.config = config
        self.resume = resume
        self.retry_failed = retry_failed
        self.retry_matched = retry_matched
        self.download_missing = download_missing
        self.selected_jobs = selected_jobs
        self.download_request = download_request

    def _execute(self, service):
        if self.selected_jobs or self.download_request:
            from dataclasses import replace
            from tools.orbea_automation.selected_downloads import begin_download_batch
            from tools.orbea_automation.checkpoint import atomic_write_json
            results = []
            jobs = (tuple((job.config, job.row_keys) for job in self.download_request.jobs)
                    if self.download_request else self.selected_jobs)
            batch_path, batch = begin_download_batch(self.download_request) if self.download_request else (None, None)
            for index, (config, keys) in enumerate(jobs):
                if self.stop_requested and results:
                    break
                config = replace(config, download_browser_count=self.config.download_browser_count)
                self.log_message.emit(f"Downloading data for {len(keys)} selected products in {config.resume_run_dir.name}")
                continuing = self.download_request and self.download_request.jobs[index].resume
                kwargs = ({"download_mode": self.download_request.mode, "download_batch_id": batch["id"]}
                          if self.download_request and not continuing else {})
                result = service.run(config, **self._callbacks(), resume=True, retry_failed=False,
                                     retry_matched=not bool(self.download_request),
                                     **({"selected_row_keys": keys} if not continuing else {}), **kwargs)
                results.append(result)
                if batch is not None:
                    for item in batch["jobs"]:
                        if Path(item["run_dir"]).resolve() == config.resume_run_dir.resolve():
                            item["completed"] = result.completed
                    atomic_write_json(batch_path, batch)
                if result.cancelled:
                    break
                if len(results) < len(jobs):
                    self.partial_result.emit(result)
            return replace(results[-1], completed=len(results) == len(jobs)
                           and all(result.completed for result in results),
                           cancelled=self.stop_requested or any(result.cancelled for result in results))
        return service.run(
            self.config,
            **self._callbacks(),
            resume=self.resume,
            retry_failed=self.retry_failed,
            **({"retry_matched": True} if self.retry_matched else {}),
            **({"download_missing": True} if self.download_missing else {}),
        )

    def _emit_error(self, exc):
        partial = getattr(exc, "partial_result", None)
        if partial is not None:
            self.partial_result.emit(partial)
        if getattr(exc, "reason", "") == "website_access":
            self.website_blocked.emit(str(exc))
        else:
            super()._emit_error(exc)


class OrbeaPimboPhotoScanWorker(_OrbeaServiceWorker):
    item_finished = Signal(object)
    skip_cancelled = True

    def __init__(self, make_service, run_dir=None, skus=(), *, jobs=()):
        super().__init__(make_service)
        self.run_dir, self.skus = run_dir, skus
        self.jobs = jobs or ((run_dir, skus),)

    def _execute(self, service):
        results = []
        for root, skus in self.jobs:
            if self.stop_requested:
                break
            results.extend(service.run(root, skus, **self._callbacks(), item_finished=self.item_finished.emit))
        return tuple(results)


class OrbeaPimboContentScanWorker(OrbeaPimboPhotoScanWorker):
    """Use the same saved-product queue and stop-after-current read semantics."""


class OrbeaMissingPhotosWorker(_OrbeaServiceWorker):
    skip_cancelled = True

    def __init__(self, make_service, config, keys):
        super().__init__(make_service)
        self.config, self.keys = config, keys

    def _execute(self, service):
        return service.run(self.config, **self._callbacks(), resume=True, download_missing=True,
                           lookup_missing=True, selected_row_keys=self.keys)


class OrbeaDescriptionWorker(_OrbeaServiceWorker):
    """Extract descriptions without touching the authenticated Pimbo browser."""

    def __init__(self, make_service: Callable[[], Any], config):
        super().__init__(make_service)
        self.config = config

    def _execute(self, service):
        return service.run(self.config, **self._callbacks())


class OrbeaPhotoWorker(_OrbeaServiceWorker):
    """Download public Orbea configurator photos away from the UI thread."""

    def __init__(self, make_service: Callable[[], Any], urls: tuple[str, ...], output_dir: Path):
        super().__init__(make_service)
        self.urls = urls
        self.output_dir = output_dir

    def _execute(self, service):
        run_many = getattr(service, "run_many", None)
        if callable(run_many):
            return run_many(self.urls, self.output_dir, **self._callbacks())
        if len(self.urls) == 1:
            return service.run(self.urls[0], self.output_dir, **self._callbacks())
        raise RuntimeError("The photo service does not support multiple product URLs")


class OrbeaTableImageWorker(_OrbeaServiceWorker):
    """Download selected Orbea images without running Pimbo."""

    def __init__(
        self, make_service: Callable[[], Any], urls: tuple[str, ...], output_dir: Path, *,
        download_geometry: bool = True, download_size_guide: bool = True,
        download_product_photos: bool = False,
    ):
        super().__init__(make_service)
        self.urls = urls
        self.output_dir = output_dir
        self.download_geometry = bool(download_geometry)
        self.download_size_guide = bool(download_size_guide)
        self.download_product_photos = bool(download_product_photos)

    def _execute(self, service):
        return service.run_many(
            self.urls, self.output_dir, **self._callbacks(),
            download_geometry=self.download_geometry,
            download_size_guide=self.download_size_guide,
            download_product_photos=self.download_product_photos,
        )


class OrbeaExcelSortWorker(QThread):
    """Sort an existing Orbea match workbook without blocking the app window."""

    succeeded = Signal(str)
    failed = Signal(str)

    def __init__(self, source_path: Path):
        super().__init__()
        self.source_path = source_path

    def request_stop(self):
        self.requestInterruption()

    def run(self):
        try:
            from tools.orbea_automation.report import sort_existing_match_workbook

            destination = sort_existing_match_workbook(self.source_path)
            if not self.isInterruptionRequested():
                self.succeeded.emit(str(destination))
        except Exception as exc:
            if not self.isInterruptionRequested():
                self.failed.emit(str(exc))
