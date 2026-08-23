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


def test_settings_save_skips_redundant_global_refreshes(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ULTRABIKE_DATA_DIR", str(tmp_path))
    app = QApplication.instance() or QApplication([])
    original_theme = Theme.DARK if isDarkTheme() else Theme.LIGHT
    window = MainWindow()

    try:
        window.show()
        _pump(app)
        window.current_user = "settings-save-test"
        window.show_main()
        window.cancel_screen_preload()
        assert window.open_route("settings")
        _pump(app)
        screen = window.settings_screen

        writes: list[dict] = []
        original_set_many = window.settings.set_many

        def record_set_many(values: dict) -> None:
            writes.append(dict(values))
            original_set_many(values)

        language_calls: list[tuple[str, bool]] = []
        original_set_language = window.i18n.set_language

        def record_set_language(language: str, *, persist: bool = False) -> None:
            language_calls.append((language, persist))
            original_set_language(language, persist=persist)

        theme_calls: list[bool] = []
        original_apply_global_theme = screen._apply_global_theme

        def record_apply_global_theme(is_dark: bool) -> bool:
            theme_calls.append(bool(is_dark))
            return original_apply_global_theme(is_dark)

        monkeypatch.setattr(window.settings, "set_many", record_set_many)
        monkeypatch.setattr(window.i18n, "set_language", record_set_language)
        monkeypatch.setattr(screen, "_apply_global_theme", record_apply_global_theme)

        # Saving unchanged values should be one database transaction and no
        # application-wide theme or language refresh.
        screen._save_all_settings()
        _pump(app)
        assert len(writes) == 1
        assert theme_calls == []
        assert language_calls == []

        # Theme changes are already applied by the live preview. Language is
        # applied once after persistence and must not write to the DB again.
        target_dark = not isDarkTheme()
        screen.theme_switch.toggleChecked()
        _pump(app)
        assert screen.theme_switch.isChecked() == target_dark
        assert isDarkTheme() == target_dark
        target_language = "lt" if window.i18n.language.code == "en" else "en"
        target_index = screen.language_combo.findData(target_language)
        assert target_index >= 0
        screen.language_combo.setCurrentIndex(target_index)
        _pump(app)
        assert screen.theme_switch.isChecked() == target_dark
        assert isDarkTheme() == target_dark

        theme_calls.clear()
        language_calls.clear()
        screen._save_all_settings()
        _pump(app)

        assert len(writes) == 2
        assert theme_calls == []
        assert language_calls == [(target_language, False)]
        assert window.settings.get("language") in ("English", "Lithuanian")
        assert window.settings.get("theme") == ("dark" if target_dark else "light")
    finally:
        setTheme(original_theme, lazy=True)
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
