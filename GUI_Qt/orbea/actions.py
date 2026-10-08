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
        return bool(getattr(self.worker, "_stop_requested", False))


def current_activity(screen) -> OrbeaActivity:
    if screen._upload_panel.is_running():
        return OrbeaActivity("upload", screen._upload_panel.worker)
    # Keep ownership until the finished callback runs on the UI thread.
    # A completed thread may still have queued result and cleanup signals.
    for name, attribute in (
        ("sort", "_excel_sort_worker"),
        ("collection", "_worker"),
        ("filters", "_filter_worker"),
        ("description", "_description_worker"),
        ("photos", "_photo_worker"),
        ("tables", "_table_image_worker"),
    ):
        worker = getattr(screen, attribute)
        if worker is not None:
            return OrbeaActivity(name, worker)
    return OrbeaActivity("idle")


def set_controls_locked(screen, locked: bool, *, active_button=None, stopping=False, upload_active=False):
    """Lock all job inputs together while retaining the active job's Stop button."""
    screen._upload_panel.setEnabled(not locked or upload_active)
    for group in (
        screen._config_widgets, screen._description_config_widgets,
        screen._photo_config_widgets, screen._table_image_config_widgets,
    ):
        for widget in group:
            widget.setEnabled(not locked)
    for button in (
        screen._start_btn, screen._resume_btn, screen._retry_btn,
        screen._retry_matched_btn, screen._load_collection_btn,
        screen._download_missing_btn, screen._description_start_btn,
        screen._photo_start_btn, screen._table_image_start_btn,
    ):
        button.setEnabled(not locked)
    if active_button is not None:
        active_button.setEnabled(not stopping)
