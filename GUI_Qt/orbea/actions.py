"""Shared Orbea activity and control locking rules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class OrbeaActivity:
    name: str
    worker: Any = None

    @property
    def stopping(self) -> bool:
        return bool(getattr(self.worker, "_stop_requested", False) or
                    (self.worker and self.worker.isInterruptionRequested()
                     if hasattr(self.worker, "isInterruptionRequested") else False))


def current_activity(screen) -> OrbeaActivity:
    return screen.workflow_controller.activity()


def set_controls_locked(screen, locked: bool, *, active_button=None, stopping=False, upload_active=False):
    """Lock all job inputs together while retaining the active job's Stop button."""
    # The table remains scrollable; lock its selection and action controls, not
    # the containing QWidget (which can belong to another workspace column).
    screen._upload_panel.setEnabled(True)
    if locked:
        screen._upload_panel.set_locked(True)
    else:
        screen._upload_panel.update_state()
    for group in (
        screen._config_widgets, screen._description_config_widgets,
        screen._photo_config_widgets, screen._table_image_config_widgets,
    ):
        for widget in group:
            widget.setEnabled(not locked)
    for button in (
        screen._start_btn, screen._resume_btn, screen._download_btn, screen._description_start_btn,
        screen._photo_start_btn, screen._table_image_start_btn,
    ):
        button.setEnabled(not locked)
    if active_button is not None:
        active_button.setEnabled(not stopping)
