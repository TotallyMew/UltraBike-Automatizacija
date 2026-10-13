"""Lifecycle shared by the independent Orbea download/extraction jobs."""

from __future__ import annotations

from PySide6.QtCore import QObject
from qfluentwidgets import FluentIcon

from .actions import set_controls_locked


class OrbeaDirectWorkflow(QObject):
    """Connect one worker to its view, and restore controls when it finishes."""

    prefix: str
    output_attribute: str
    translation_prefix: str
    start_key: str
    start_text: str
    starting_text: str
    start_icon = FluentIcon.DOWNLOAD

    def __init__(self, screen):
        super().__init__(screen)
        self.screen = screen

    def start_worker(self, worker, *, total=None):
        view = self.screen
        details = {"output_path": str(getattr(view, self.output_attribute))}
        if total is not None:
            details["total"] = total
        view.workflow_controller.start_job(
            {"photo": "photos", "table_image": "tables"}.get(self.prefix, self.prefix),
            worker if callable(worker) else lambda: worker,
            owner=view, attribute=f"_{self.prefix}_worker", details=details,
            signals={"progress_changed": self.on_progress,
                     "log_message": getattr(view, f"_append_{self.prefix}_log"),
                     "succeeded": self.on_result, "failed": self.on_error},
            finished=self.finished, failed=self.start_failed)

    def start_failed(self, message):
        self.set_busy(False)
        self.on_error(message)

    def finished(self):
        view = self.screen
        setattr(view, f"_{self.prefix}_worker", None)
        self.set_busy(False)
        output_dir = getattr(view, self.output_attribute)
        getattr(view, f"_{self.prefix}_open_btn").setEnabled(
            bool(output_dir and output_dir.exists())
        )
        view._update_action_states()

    def set_busy(self, busy: bool):
        view = self.screen
        button = getattr(view, f"_{self.prefix}_start_btn")
        set_controls_locked(view, busy, active_button=button)
        if busy:
            button.setText(view._t(f"{self.translation_prefix}.stop", "Stop"))
            button.setIcon(FluentIcon.CLOSE)
            getattr(view, f"_{self.prefix}_status_label").setText(
                view._t(f"{self.translation_prefix}.starting", self.starting_text)
            )
        else:
            button.setText(view._t(self.start_key, self.start_text))
            button.setIcon(self.start_icon)
