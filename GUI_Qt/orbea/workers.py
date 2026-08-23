"""Thread workers for the integrated Orbea workflow."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QThread, Signal

class OrbeaFilterWorker(QThread):
    loaded = Signal(object)
    failed = Signal(str)

    def __init__(self, driver, make_service: Callable[[Any], Any]):
        super().__init__()
        self.driver = driver
        self.make_service = make_service
        self._stopped = False
        self._service = None

    def request_stop(self):
        self._stopped = True
        self.requestInterruption()
        service = self._service
        if service is not None and hasattr(service, "cancel"):
            try:
                service.cancel()
            except Exception:
                pass

    def run(self):
        try:
            self._service = self.make_service(self.driver)
            options = self._service.discover_filter_options()
            if not self._stopped:
                self.loaded.emit(options)
        except Exception as exc:
            if not self._stopped:
                self.failed.emit(str(exc))


class OrbeaRunWorker(QThread):
    progress_changed = Signal(object)
    log_message = Signal(str)
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        driver,
        make_service: Callable[[Any], Any],
        config,
        *,
        resume: bool,
        retry_failed: bool,
    ):
        super().__init__()
        self.driver = driver
        self.make_service = make_service
        self.config = config
        self.resume = resume
        self.retry_failed = retry_failed
        self._service = None
        self._token: Any = threading.Event()

    def request_stop(self):
        token = self._token
        for method_name in ("cancel", "set"):
            method = getattr(token, method_name, None)
            if callable(method):
                try:
                    method()
                    break
                except Exception:
                    pass
        service = self._service
        if service is not None and hasattr(service, "cancel"):
            try:
                service.cancel()
            except Exception:
                pass

    def run(self):
        try:
            self._service = self.make_service(self.driver)
            try:
                from tools.orbea_automation import CancellationToken

                self._token = CancellationToken()
            except Exception:
                self._token = threading.Event()

            result = self._service.run(
                self.config,
                progress=self.progress_changed.emit,
                log=self.log_message.emit,
                cancellation=self._token,
                resume=self.resume,
                retry_failed=self.retry_failed,
            )
            self.succeeded.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


class OrbeaDescriptionWorker(QThread):
    """Run description extraction without touching the authenticated Pimbo browser."""

    progress_changed = Signal(object)
    log_message = Signal(str)
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, make_service: Callable[[], Any], config):
        super().__init__()
        self.make_service = make_service
        self.config = config
        self._service = None
        self._token: Any = threading.Event()
        self._stop_requested = False

    def request_stop(self):
        self._stop_requested = True
        token = self._token
        for method_name in ("cancel", "set"):
            method = getattr(token, method_name, None)
            if callable(method):
                try:
                    method()
                    break
                except Exception:
                    pass
        service = self._service
        if service is not None and hasattr(service, "cancel"):
            try:
                service.cancel()
            except Exception:
                pass

    def run(self):
        try:
            self._service = self.make_service()
            try:
                from tools.orbea_automation import CancellationToken

                self._token = CancellationToken()
            except Exception:
                self._token = threading.Event()

            if self._stop_requested:
                token = self._token
                for method_name in ("cancel", "set"):
                    method = getattr(token, method_name, None)
                    if callable(method):
                        method()
                        break
                if hasattr(self._service, "cancel"):
                    self._service.cancel()

            result = self._service.run(
                self.config,
                progress=self.progress_changed.emit,
                log=self.log_message.emit,
                cancellation=self._token,
            )
            self.succeeded.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


class OrbeaPhotoWorker(QThread):
    """Download public Orbea configurator photos away from the UI thread."""

    progress_changed = Signal(object)
    log_message = Signal(str)
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        make_service: Callable[[], Any],
        urls: tuple[str, ...],
        output_dir: Path,
    ):
        super().__init__()
        self.make_service = make_service
        self.urls = urls
        self.output_dir = output_dir
        self._service = None
        self._token: Any = threading.Event()
        self._stop_requested = False

    def request_stop(self):
        self._stop_requested = True
        token = self._token
        for method_name in ("cancel", "set"):
            method = getattr(token, method_name, None)
            if callable(method):
                try:
                    method()
                    break
                except Exception:
                    pass
        service = self._service
        if service is not None and hasattr(service, "cancel"):
            try:
                service.cancel()
            except Exception:
                pass

    def run(self):
        try:
            self._service = self.make_service()
            try:
                from tools.orbea_automation import CancellationToken

                self._token = CancellationToken()
            except Exception:
                self._token = threading.Event()
            if self._stop_requested:
                self.request_stop()
            run_many = getattr(self._service, "run_many", None)
            if callable(run_many):
                result = run_many(
                    self.urls,
                    self.output_dir,
                    progress=self.progress_changed.emit,
                    log=self.log_message.emit,
                    cancellation=self._token,
                )
            elif len(self.urls) == 1:
                result = self._service.run(
                    self.urls[0],
                    self.output_dir,
                    progress=self.progress_changed.emit,
                    log=self.log_message.emit,
                    cancellation=self._token,
                )
            else:
                raise RuntimeError("The photo service does not support multiple product URLs")
            self.succeeded.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


class OrbeaTableImageWorker(QThread):
    """Download selected Orbea images without running Pimbo."""

    progress_changed = Signal(object)
    log_message = Signal(str)
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        make_service: Callable[[], Any],
        urls: tuple[str, ...],
        output_dir: Path,
        *,
        download_geometry: bool = True,
        download_size_guide: bool = True,
        download_product_photos: bool = False,
    ):
        super().__init__()
        self.make_service = make_service
        self.urls = urls
        self.output_dir = output_dir
        self.download_geometry = bool(download_geometry)
        self.download_size_guide = bool(download_size_guide)
        self.download_product_photos = bool(download_product_photos)
        self._service = None
        self._token: Any = threading.Event()
        self._stop_requested = False

    def request_stop(self):
        self._stop_requested = True
        token = self._token
        for method_name in ("cancel", "set"):
            method = getattr(token, method_name, None)
            if callable(method):
                try:
                    method()
                    break
                except Exception:
                    pass
        service = self._service
        if service is not None and hasattr(service, "cancel"):
            try:
                service.cancel()
            except Exception:
                pass

    def run(self):
        try:
            self._service = self.make_service()
            try:
                from tools.orbea_automation import CancellationToken

                self._token = CancellationToken()
            except Exception:
                self._token = threading.Event()
            if self._stop_requested:
                self.request_stop()
            result = self._service.run_many(
                self.urls,
                self.output_dir,
                progress=self.progress_changed.emit,
                log=self.log_message.emit,
                cancellation=self._token,
                download_geometry=self.download_geometry,
                download_size_guide=self.download_size_guide,
                download_product_photos=self.download_product_photos,
            )
            self.succeeded.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


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
