"""Orbea model adaptation and workflow service construction."""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any, Mapping
from PySide6.QtCore import QObject, Slot

def _read(obj: Any, *names: str, default: Any = None) -> Any:
    """Read the first available mapping key or object attribute."""
    for name in names:
        if isinstance(obj, Mapping) and name in obj:
            return obj[name]
        if hasattr(obj, name):
            return getattr(obj, name)
    return default


def _plain(value: Any) -> Any:
    if hasattr(value, "value"):
        value = value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, tuple):
        return list(value)
    return value


def _create_model(model_type, values: dict[str, Any], aliases: dict[str, str]):
    """Construct a typed service model while tolerating API-compatible aliases."""
    parameters = inspect.signature(model_type).parameters
    kwargs: dict[str, Any] = {}
    for name, parameter in parameters.items():
        if name in ("self", "args", "kwargs"):
            continue
        canonical = aliases.get(name, name)
        if canonical in values:
            kwargs[name] = values[canonical]
        elif parameter.default is inspect.Parameter.empty:
            raise TypeError(f"{model_type.__name__} requires unsupported field '{name}'")
    return model_type(**kwargs)


def _service_factory(
    driver, image_driver_factory=None, photo_service_factory=None
):
    # Local import keeps the rest of the app importable in a partially-updated
    # installation and gives PyInstaller a normal Python module to collect.
    from tools.orbea_automation import OrbeaAutomationService

    return OrbeaAutomationService(
        driver,
        image_driver_factory=image_driver_factory,
        photo_service_factory=photo_service_factory,
    )


class OrbeaWorkflowController(QObject):
    """Own the displayed source, job lifetime and authenticated-browser lease."""

    def __init__(
        self,
        screen,
        *,
        service_factory=None,
        image_driver_factory=None,
        description_service_factory=None,
        photo_service_factory=None,
        table_image_service_factory=None,
    ):
        super().__init__(screen if isinstance(screen, QObject) else None)
        self.screen = screen
        self.main = screen.main
        self.service_factory = service_factory
        self.image_driver_factory = image_driver_factory
        self.description_service_factory = description_service_factory
        self.photo_service_factory = photo_service_factory
        self.table_image_service_factory = table_image_service_factory
        self.owns_browser_lease = False
        self.active_collection = None
        self.source_root = None
        self.selection = {}
        self._selection_rows = None
        self._row_identities = ()
        self._job = None

    def set_source(self, root):
        self.source_root = Path(root).resolve()
        self.active_collection = self.source_root if (self.source_root / "run_checkpoint.json").is_file() else None

    def remember_selection(self, panel):
        from tools.orbea_automation.selected_downloads import product_identity
        if self._selection_rows is not panel.matches:
            self._selection_rows = panel.matches
            self._row_identities = tuple(product_identity(match) for match in panel.matches)
        self.selection = {identity: panel.table.item(row, 0).checkState()
                          for row, identity in enumerate(self._row_identities)}
        return dict(self.selection)

    def selected_products(self, panel, *, ready_only=False):
        from PySide6.QtCore import Qt
        self.remember_selection(panel)
        return tuple(match for row, match in panel._visible_rows()
                     if match.sku and match.status != "invalid" and (not ready_only or match.ready)
                     and self.selection.get(self._row_identities[row]) == Qt.CheckState.Checked)

    def select_visible(self, panel, *, checked=True, status=None):
        from PySide6.QtCore import Qt
        from tools.orbea_automation.photo_scan import PHOTO_STATUSES
        if self.activity().name != "idle":
            return
        panel.table.blockSignals(True)
        try:
            for row, match in panel._visible_rows():
                state = panel._row_statuses.get(match.local_folder, {})
                matches_status = (panel._photo_statuses.get(match.local_folder, {}).get("status", "not_checked") == status
                                  if status in PHOTO_STATUSES else state.get("warnings") if status == "warnings"
                                  else state.get("status") == status)
                if match.sku and match.status != "invalid" and (status is None or matches_status):
                    panel.table.item(row, 0).setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        finally:
            panel.table.blockSignals(False)
        self.remember_selection(panel)
        panel.update_state()

    def activity(self):
        from .actions import OrbeaActivity
        if self._job is not None:
            return OrbeaActivity(self._job["name"], self._job["worker"])
        # Compatibility for screen entry points and injected workers.
        panel = getattr(self.screen, "_upload_panel", None)
        if panel is not None and panel.is_running():
            return OrbeaActivity("upload", panel.worker)
        for name, attribute in (("sort", "_excel_sort_worker"), ("collection", "_worker"),
                                ("filters", "_filter_worker"), ("description", "_description_worker"),
                                ("photos", "_photo_worker"), ("tables", "_table_image_worker")):
            worker = getattr(self.screen, attribute, None)
            if worker is not None:
                return OrbeaActivity(name, worker)
        return OrbeaActivity("idle")

    def start_job(self, name, factory, *, owner, attribute, signals, finished, failed,
                  operation_attribute=None, kind="orbea", details=None):
        """Own construction, registration and start failures just like completion."""
        job = dict(name=name, worker=None, owner=owner, attribute=attribute, finished=finished,
                   failed=failed, operation_id=None, lease=self.owns_browser_lease)
        self._job = job
        if operation_attribute:
            setattr(owner, operation_attribute, None)
        try:
            worker = job["worker"] = factory()
            setattr(owner, attribute, worker)
            for signal, callback in signals.items():
                getattr(worker, signal).connect(callback)
            worker.finished.connect(self._job_finished)
            if hasattr(self.main, "track_worker"):
                record = self.main.track_worker(worker, kind, "orbea", **(details or {}))
                job["operation_id"] = getattr(record, "id", None)
                if operation_attribute:
                    setattr(owner, operation_attribute, job["operation_id"])
            self.screen._closing = False
            self.screen._update_action_states()
            worker.start()
            return worker
        except Exception as error:
            # No finished signal is guaranteed for a worker that did not start.
            job["operation_id"] = job["operation_id"] or getattr(job["worker"], "_operation_record_id", None)
            setattr(owner, attribute, None)
            if hasattr(owner, "_busy"):
                owner._busy = False
            tracker = getattr(self.main, "operation_tracker", None)
            try:
                if tracker and job["operation_id"]:
                    try:
                        tracker.finish(job["operation_id"], "failed", error_summary=str(error))
                    except Exception as tracker_error:
                        self.screen._append_log(f"Could not finish activity: {tracker_error}")
                    if operation_attribute:
                        setattr(owner, operation_attribute, None)
                failed(str(error))
            finally:
                self._finish_job(job, startup_failed=True)
            return None

    @Slot()
    def _job_finished(self):
        job = self._job
        if job is not None and self.sender() is job["worker"]:
            self._finish_job(job)

    def _finish_job(self, job, *, startup_failed=False):
        try:
            if not startup_failed:
                job["finished"]()
        except Exception as error:
            job["failed"](str(error))
        finally:
            if job["attribute"] != "worker" or startup_failed:
                setattr(job["owner"], job["attribute"], None)
            if hasattr(job["owner"], "_busy"):
                job["owner"]._busy = False
            if job["lease"]:
                self.release_browser()
            self._job = None
            self.screen._update_action_states()

    def request_stop(self):
        activity = self.activity()
        if activity.worker is not None and not activity.stopping:
            activity.worker.request_stop()
            self.screen._update_action_states()

    def make_service(self, driver):
        factory = self.service_factory
        if factory is None:
            return _service_factory(
                driver, self.image_driver_factory, self.make_photo_service
            )
        if (
            not inspect.isclass(factory)
            and hasattr(factory, "run")
            and hasattr(factory, "discover_filter_options")
        ):
            return factory
        return factory(driver)

    def make_description_service(self):
        factory = self.description_service_factory
        if factory is None:
            from tools.orbea_automation import OrbeaDescriptionService

            return OrbeaDescriptionService()
        if not inspect.isclass(factory) and hasattr(factory, "run"):
            return factory
        return factory()

    def make_photo_service(self):
        factory = self.photo_service_factory
        if factory is None:
            from tools.orbea_automation import OrbeaPhotoService

            return OrbeaPhotoService()
        if not inspect.isclass(factory) and any(
            callable(getattr(factory, method, None))
            for method in ("run", "run_many", "run_from_html")
        ):
            return factory
        return factory()

    def make_table_image_service(self):
        factory = self.table_image_service_factory
        if factory is None:
            from tools.orbea_automation import OrbeaTableImageService

            settings = getattr(self.screen, "settings", None)
            browser_name = "chrome"
            if settings is not None:
                try:
                    browser_name = str(
                        settings.get("browser_choice", "Chrome") or "Chrome"
                    ).strip().casefold()
                except Exception:
                    pass
            return OrbeaTableImageService(
                self.image_driver_factory,
                browser_name=browser_name,
                photo_service_factory=self.make_photo_service,
            )
        if not inspect.isclass(factory) and hasattr(factory, "run_many"):
            return factory
        return factory()

    def acquire_browser(self) -> bool:
        acquire = getattr(self.main, "try_acquire_browser_lease", None)
        if callable(acquire) and not acquire(self.screen):
            return False
        self.owns_browser_lease = True
        return True

    def release_browser(self) -> None:
        if not self.owns_browser_lease:
            return
        release = getattr(self.main, "release_browser_lease", None)
        if callable(release):
            try:
                release(self.screen)
            except Exception:
                pass
        self.owns_browser_lease = False
        self.screen._owns_browser_lease = False
