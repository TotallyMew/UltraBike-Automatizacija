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
        setattr(view, f"_{self.prefix}_worker", worker)
        worker.progress_changed.connect(self.on_progress)
        worker.log_message.connect(getattr(view, f"_append_{self.prefix}_log"))
        worker.succeeded.connect(self.on_result)
        worker.failed.connect(self.on_error)
        worker.finished.connect(self.finished)
        try:
            if hasattr(view.main, "track_worker"):
                details = {"output_path": str(getattr(view, self.output_attribute))}
                if total is not None:
                    details["total"] = total
                view.main.track_worker(worker, "orbea", "orbea", **details)
            worker.start()
        except Exception as error:
            self.on_error(str(error))
            self.finished()

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
