from __future__ import annotations

import os


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QWidget
from qfluentwidgets import Theme, isDarkTheme, setTheme

from Database.DatabaseManager import DatabaseManager
from Database.SettingsManager import SettingsManager
from GUI_Qt.i18n import translate
from GUI_Qt.routes import ROUTE_REGISTRY
from GUI_Qt.screens.DescriptionsScreen import DescriptionsScreen


class _I18n:
    @staticmethod
    def tr(key, **values):
        return translate("en", key, **values)


def test_descriptions_route_constructs_and_can_be_shown():
    app = QApplication.instance() or QApplication([])
    db = DatabaseManager(":memory:")
    settings = SettingsManager(db)
    main = QWidget()
    main.db = db
    main.settings = settings
    main.i18n = _I18n()
    main.descriptions_screen = None

    try:
        screen = ROUTE_REGISTRY["descriptions"].screen_factory(main)
        screen.resize(1000, 720)
        screen.show()
        app.processEvents()

        assert isinstance(screen, DescriptionsScreen)
        assert screen.isVisible()
        assert screen.tabs.count() == 3
        assert main.descriptions_screen is screen

        # Regression: label normalization must not re-enter Qt's StyleChange
        # event handling while the screen is being re-themed. That previously
        # caused a native QtCore access violation in the real application.
        original_theme = Theme.DARK if isDarkTheme() else Theme.LIGHT
        try:
            for theme in (Theme.DARK, Theme.LIGHT, Theme.DARK, Theme.LIGHT):
                setTheme(theme)
                app.processEvents()
                screen._on_theme_changed()
                app.processEvents()
                assert screen.isVisible()
        finally:
            setTheme(original_theme)
            app.processEvents()
    finally:
        if main.descriptions_screen is not None:
            main.descriptions_screen.close()
            main.descriptions_screen.deleteLater()
        main.deleteLater()
        app.processEvents()
        db.close()
