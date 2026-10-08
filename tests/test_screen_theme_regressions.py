from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget
from qfluentwidgets import Theme, isDarkTheme, setTheme

from GUI_Qt.styles.screen_theme import apply_screen_theme
from GUI_Qt.styles.theme_config import get_surface_color, get_text_color


class _I18n:
    @staticmethod
    def tr(key, **_values):
        return key


class _Main(QWidget):
    def __init__(self):
        super().__init__()
        self.i18n = _I18n()


def test_screen_theme_sets_native_text_roles_and_keeps_labels_transparent() -> None:
    app = QApplication.instance() or QApplication([])
    original_theme = Theme.DARK if isDarkTheme() else Theme.LIGHT
    root = QWidget()
    content = QWidget(root)
    label = QLabel("Readable text", content)
    layout = QVBoxLayout(content)
    layout.addWidget(label)

    try:
        setTheme(Theme.DARK)
        apply_screen_theme(root, "QWidget", content=content)
        app.processEvents()

        expected = get_text_color(True, "primary").lower()
        palette = root.palette()
        assert palette.color(QPalette.ColorRole.WindowText).name().lower() == expected
        assert palette.color(QPalette.ColorRole.Text).name().lower() == expected
        assert palette.color(QPalette.ColorRole.ButtonText).name().lower() == expected
        assert label.palette().color(QPalette.ColorRole.WindowText).name().lower() == expected
        assert not label.testAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        assert not label.autoFillBackground()
        assert "background-color: transparent" in label.styleSheet()
    finally:
        root.close()
        root.deleteLater()
        setTheme(original_theme)
        app.processEvents()
