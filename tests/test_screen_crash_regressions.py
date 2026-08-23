from __future__ import annotations

import os


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication
from qfluentwidgets import Theme, isDarkTheme, setTheme

from GUI_Qt.MainWindow import MainWindow


def _pump(app: QApplication, cycles: int = 4) -> None:
    for _ in range(cycles):
        app.processEvents()


def test_batch_resize_and_info_retheme_do_not_reenter_qt(tmp_path, monkeypatch) -> None:
    """Exercise the two native access-violation paths found in the UI audit."""
    monkeypatch.setenv("ULTRABIKE_DATA_DIR", str(tmp_path))
    app = QApplication.instance() or QApplication([])
    original_theme = Theme.DARK if isDarkTheme() else Theme.LIGHT
    window = MainWindow()

    try:
        window.resize(1280, 820)
        window.show()
        _pump(app)
        window.current_user = "lifecycle-test"
        window.show_main()
        window.cancel_screen_preload()
        _pump(app)

        assert window.open_route("batch")
        _pump(app)
        for width, height in ((920, 700), (1440, 960), (760, 680), (1280, 820)):
            window.resize(width, height)
            _pump(app)
            assert window.content_stack.currentWidget() is window.unified_batch_screen

        assert window.open_route("info")
        _pump(app)
        for theme in (Theme.DARK, Theme.LIGHT, Theme.DARK, Theme.LIGHT):
            setTheme(theme)
            _pump(app)
            window.info_screen._on_theme_changed()
            _pump(app)
            assert window.content_stack.currentWidget() is window.info_screen
    finally:
        setTheme(original_theme)
        window.cancel_screen_preload()
        try:
            if window.spotify_screen is not None:
                window.spotify_screen.shutdown(wait_ms=100)
        except Exception:
            pass
        window.hide()
        try:
            window.db.close()
        except Exception:
            pass
        window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        _pump(app)
