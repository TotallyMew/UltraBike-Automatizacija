from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication
from qfluentwidgets import Theme, isDarkTheme, setTheme

from GUI_Qt.styles.theme_config import get_surface_color, get_text_color
from GUI_Qt.widgets.LoadingWidget import LoadingWidget


def _translate(key, **_values):
    return {
        "loading.default": "Loading...",
        "loading.subtitle": "Product automation workspace",
        "loading.title": "UltraBike",
    }.get(key, key)


def test_loading_widget_rethemes_canvas_and_content_for_dark_mode() -> None:
    app = QApplication.instance() or QApplication([])
    original_theme = Theme.DARK if isDarkTheme() else Theme.LIGHT
    widget = None
    try:
        setTheme(Theme.LIGHT)
        widget = LoadingWidget("Connecting...", tr=_translate)
        setTheme(Theme.DARK)
        widget._apply_theme()
        app.processEvents()

        styles = widget.styleSheet().lower()
        assert get_surface_color(True, "canvas").lower() in styles
        assert get_surface_color(True).lower() in styles
        assert get_text_color(True, "primary").lower() in styles
        assert (
            widget.palette().color(QPalette.ColorRole.Window).name().lower()
            == get_surface_color(True, "canvas").lower()
        )
        assert widget.title_label.text() == "UltraBike"
        assert widget.subtitle_label.text() == "Product automation workspace"
        assert widget.message_label.text() == "Connecting..."
    finally:
        if widget is not None:
            widget.close()
            widget.deleteLater()
        setTheme(original_theme)
        app.processEvents()


def test_loading_widget_updates_and_hides_an_empty_status() -> None:
    app = QApplication.instance() or QApplication([])
    widget = LoadingWidget(tr=_translate)
    try:
        widget.set_message("Downloading update...")
        assert widget.message_label.text() == "Downloading update..."
        assert not widget.status_panel.isHidden()

        widget.set_message("")
        assert widget.message_label.text() == ""
        assert widget.status_panel.isHidden()
        assert widget.accessibleDescription() == "Loading..."
    finally:
        widget.close()
        widget.deleteLater()
        app.processEvents()
