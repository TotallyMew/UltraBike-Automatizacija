from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication
from qfluentwidgets import Theme, isDarkTheme, setTheme

from GUI_Qt.components.dialogs.UnsavedChangesDialog import UnsavedChangesDialog
from GUI_Qt.styles.theme_config import (
    get_accent_colors,
    get_semantic_colors,
    get_surface_color,
    get_text_color,
)


@pytest.mark.parametrize(
    ("theme", "is_dark"),
    [(Theme.LIGHT, False), (Theme.DARK, True)],
)
def test_unsaved_changes_dialog_uses_one_theme_context(theme: Theme, is_dark: bool) -> None:
    app = QApplication.instance() or QApplication([])
    original_theme = Theme.DARK if isDarkTheme() else Theme.LIGHT
    dialog = None
    try:
        setTheme(theme)
        dialog = UnsavedChangesDialog(
            "Unsaved Changes",
            "You have unsaved changes.",
            tr_func=lambda key, **_: key,
        )
        app.processEvents()

        dialog_style = dialog.styleSheet()
        assert get_surface_color(is_dark) in dialog_style
        assert get_text_color(is_dark, "primary") in dialog_style

        accent = get_accent_colors(is_dark)
        save_style = dialog.save_button.styleSheet()
        assert accent["base"] in save_style
        assert accent["text"] in save_style

        error = get_semantic_colors("error", is_dark)
        discard_style = dialog.discard_button.styleSheet()
        assert error["text"] in discard_style
        assert error["background"] in discard_style

        cancel_style = dialog.cancel_button.styleSheet()
        assert get_surface_color(is_dark, "alternate") in cancel_style
        assert get_text_color(is_dark, "primary") in cancel_style
    finally:
        if dialog is not None:
            dialog.close()
        setTheme(original_theme)

