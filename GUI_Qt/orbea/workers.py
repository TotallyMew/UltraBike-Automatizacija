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
    ):
        super().__init__(make_service, driver)
        self.driver = driver
        self.config = config
        self.resume = resume
        self.retry_failed = retry_failed
        self.retry_matched = retry_matched
        self.download_missing = download_missing

    def _execute(self, service):
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
