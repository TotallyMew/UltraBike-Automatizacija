"""Background workers for the KROSS automation screen."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Iterable

from PySide6.QtCore import QThread, Signal

from Managers.PimboProductEditor import PimPreparationResult, PimPreparationStatus
from tools.kross_automation import (
    KrossCollectionOptions,
    KrossMatch,
    KrossUploadResult,
    KrossWorkflowOptions,
)
from tools.orbea_automation import PimboFilterSpec


class KrossFilterWorker(QThread):
    loaded = Signal(object)
    failed = Signal(str)

    def __init__(self, service_factory: Callable[[], Any]) -> None:
        super().__init__()
        self.service_factory = service_factory

    def run(self) -> None:
        try:
            self.loaded.emit(self.service_factory().discover_filter_options())
        except Exception as error:
            self.failed.emit(str(error))


class KrossCollectionWorker(QThread):
    progress_changed = Signal(int, int, str)
    log_message = Signal(str)
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        service_factory: Callable[[], Any],
        filters: PimboFilterSpec,
        output_root: Path,
        options: KrossCollectionOptions,
    ) -> None:
        super().__init__()
        self.service_factory = service_factory
        self.filters = filters
        self.output_root = Path(output_root)
        self.options = options
        self._stop_requested = False

    def request_stop(self) -> None:
        self._stop_requested = True
        self.requestInterruption()

    def run(self) -> None:
        try:
            service = self.service_factory()

            def progress(current: int, total: int, message: str) -> None:
                if self._stop_requested:
                    raise RuntimeError("KROSS collection was stopped")
                self.progress_changed.emit(current, total, message)

            result = service.collect_filtered(
                self.filters,
                self.output_root,
                options=self.options,
                progress=progress,
                log=self.log_message.emit,
            )
            if not self._stop_requested:
                self.succeeded.emit(result)
        except Exception as error:
            if not self._stop_requested:
                self.failed.emit(str(error))


class KrossSkuCollectionWorker(QThread):
    """Collect local packages from pasted SKUs, URLs, or SKU/URL pairs."""

    progress_changed = Signal(int, int, str)
    log_message = Signal(str)
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        service_factory: Callable[[], Any],
        inputs: Iterable[Any],
        output_root: Path,
        options: KrossCollectionOptions,
    ) -> None:
        super().__init__()
        self.service_factory = service_factory
        self.inputs = tuple(inputs)
        self.skus = self.inputs  # Compatibility with the original SKU-only worker.
        self.output_root = Path(output_root)
        self.options = options
        self._stop_requested = False

    def request_stop(self) -> None:
        self._stop_requested = True
        self.requestInterruption()

    def run(self) -> None:
        try:
            service = self.service_factory()

            def progress(current: int, total: int, message: str) -> None:
                if self._stop_requested:
                    raise RuntimeError("KROSS collection was stopped")
                self.progress_changed.emit(current, total, message)

            result = service.collect_inputs(
                self.inputs,
                self.output_root,
                options=self.options,
                progress=progress,
                log=self.log_message.emit,
            )
            if not self._stop_requested:
                self.succeeded.emit(result)
        except Exception as error:
            if not self._stop_requested:
                self.failed.emit(str(error))


class KrossDiscoveryWorker(QThread):
    progress_changed = Signal(int, int, str)
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, service_factory: Callable[[], Any], skus: Iterable[str]):
        super().__init__()
        self.service_factory = service_factory
        self.skus = tuple(skus)
        self._stop_requested = False

    def request_stop(self) -> None:
        self._stop_requested = True
        self.requestInterruption()

    def run(self) -> None:
        try:
            service = self.service_factory()

            def progress(current: int, total: int, message: str) -> None:
                if self._stop_requested:
                    raise RuntimeError("KROSS discovery was stopped")
                self.progress_changed.emit(current, total, message)

            result = service.discover(self.skus, progress=progress)
            if not self._stop_requested:
                self.succeeded.emit(result)
        except Exception as error:
            if not self._stop_requested:
                self.failed.emit(str(error))


class KrossUploadWorker(QThread):
    progress_changed = Signal(str)
    item_finished = Signal(object)
    completed = Signal()
    failed = Signal(str)

    def __init__(
        self,
        service_factory: Callable[[], Any],
        matches: Iterable[KrossMatch],
        output_root: Path | None,
        options: KrossWorkflowOptions | None = None,
    ) -> None:
        super().__init__()
        self.service_factory = service_factory
        self.matches = tuple(matches)
        self.output_root = Path(output_root) if output_root is not None else None
        self.options = options or KrossWorkflowOptions()
        self._stop_requested = False

    def request_stop(self) -> None:
        self._stop_requested = True
        self.requestInterruption()

    def run(self) -> None:
        try:
            if len(self.matches) > 1 and not self.options.save:
                raise ValueError(
                    "A run without Save can target only one PIMBO product at a time"
                )
            service = self.service_factory()
            for index, match in enumerate(self.matches, start=1):
                if self._stop_requested:
                    break
                self.progress_changed.emit(
                    f"{index}/{len(self.matches)} — running selected stages for {match.sku}"
                )
                try:
                    result = service.upload_and_save(
                        match,
                        self.output_root,
                        options=self.options,
                        progress=self.progress_changed.emit,
                    )
                except Exception as error:
                    preparation = PimPreparationResult(
                        product_code=match.sku,
                        product_id=match.pimbo_product_id,
                        status=PimPreparationStatus.FAILED,
                        final_url=match.pimbo_product_url,
                        error=str(error),
                    )
                    result = KrossUploadResult(match, preparation)
                self.item_finished.emit(result)
                if (
                    not result.succeeded
                    and index < len(self.matches)
                    and not self._stop_requested
                ):
                    self.progress_changed.emit(
                        f"{result.match.sku} failed; resetting PIMBO before the next product"
                    )
                    try:
                        recovered = service.recover_after_failed_upload(
                            result.match,
                            progress=self.progress_changed.emit,
                        )
                    except Exception as recovery_error:
                        recovered = False
                        self.progress_changed.emit(
                            f"Recovery after {result.match.sku} failed: {recovery_error}"
                        )
                    if not recovered:
                        self.failed.emit(
                            f"Batch stopped after {result.match.sku} so its browser state "
                            "cannot cause false failures for the remaining products. "
                            "The unprocessed rows can be run again after checking this product."
                        )
                        break
        except Exception as error:
            if not self._stop_requested:
                self.failed.emit(str(error))
        finally:
            self.completed.emit()
