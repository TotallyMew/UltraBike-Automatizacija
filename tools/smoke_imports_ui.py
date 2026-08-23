"""Small import smoke-test script.

This is used during refactors to quickly validate there are no syntax/import errors
in UI modules without launching the full application.
"""

from __future__ import annotations

import sys
import importlib
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


import py_compile


def main() -> None:
    # Importing GUI modules (or even some style modules) can pull in Qt/QFluentWidgets
    # and execute import-time side effects. Keep this script compile-only.
    to_compile = [
        PROJECT_ROOT / "Managers" / "PimboProductEditor.py",
        PROJECT_ROOT / "Managers" / "EarningsManager.py",
        PROJECT_ROOT / "Managers" / "AnalyticsManager.py",
        PROJECT_ROOT / "Managers" / "SpotifyManager.py",
        PROJECT_ROOT / "Utilities" / "ProductNavigationHandler.py",
        PROJECT_ROOT / "Uploaders" / "BaseUploader.py",
        PROJECT_ROOT / "GUI_Qt" / "workers" / "batch_workers.py",
        PROJECT_ROOT / "GUI_Qt" / "workers" / "login_workers.py",
        PROJECT_ROOT / "GUI_Qt" / "workers" / "spotify_workers.py",
        PROJECT_ROOT / "GUI_Qt" / "styles" / "global_styles.py",
        PROJECT_ROOT / "GUI_Qt" / "styles" / "theme_config.py",
        PROJECT_ROOT / "GUI_Qt" / "screens" / "UnifiedBatchScreen.py",
        PROJECT_ROOT / "GUI_Qt" / "screens" / "UploadScreen.py",
        PROJECT_ROOT / "GUI_Qt" / "screens" / "SpecCheckerScreen.py",
        PROJECT_ROOT / "GUI_Qt" / "screens" / "NameGetterScreen.py",
        PROJECT_ROOT / "GUI_Qt" / "screens" / "EarningsScreen.py",
        PROJECT_ROOT / "GUI_Qt" / "screens" / "AnalyticsScreen.py",
        PROJECT_ROOT / "GUI_Qt" / "screens" / "ActivityScreen.py",
        PROJECT_ROOT / "GUI_Qt" / "screens" / "SpotifyScreen.py",
        PROJECT_ROOT / "GUI_Qt" / "routes.py",
        PROJECT_ROOT / "GUI_Qt" / "services" / "navigation.py",
        PROJECT_ROOT / "GUI_Qt" / "services" / "updates.py",
        PROJECT_ROOT / "GUI_Qt" / "services" / "errors.py",
        PROJECT_ROOT / "GUI_Qt" / "services" / "shutdown.py",
        PROJECT_ROOT / "GUI_Qt" / "batch" / "table.py",
        PROJECT_ROOT / "GUI_Qt" / "batch" / "workbook.py",
        PROJECT_ROOT / "GUI_Qt" / "batch" / "execution.py",
        PROJECT_ROOT / "GUI_Qt" / "earnings" / "dialogs.py",
        PROJECT_ROOT / "GUI_Qt" / "earnings" / "widgets.py",
        PROJECT_ROOT / "GUI_Qt" / "earnings" / "presentation.py",
        PROJECT_ROOT / "GUI_Qt" / "orbea" / "controller.py",
        PROJECT_ROOT / "GUI_Qt" / "orbea" / "workers.py",
        PROJECT_ROOT / "GUI_Qt" / "orbea" / "tabs.py",
        PROJECT_ROOT / "GUI_Qt" / "MainWindow.py",
    ]
    for path in to_compile:
        py_compile.compile(str(path), doraise=True)
    modules = [
        "Managers.PimboProductEditor",
        "Managers.EarningsManager",
        "Managers.AnalyticsManager",
        "Managers.SpotifyManager",
        "Utilities.ProductNavigationHandler",
        "Uploaders.BaseUploader",
        "GUI_Qt.workers.batch_workers",
        "GUI_Qt.workers.login_workers",
        "GUI_Qt.workers.spotify_workers",
        "GUI_Qt.screens.UnifiedBatchScreen",
        "GUI_Qt.screens.UploadScreen",
        "GUI_Qt.screens.SpecCheckerScreen",
        "GUI_Qt.screens.NameGetterScreen",
        "GUI_Qt.screens.EarningsScreen",
        "GUI_Qt.screens.AnalyticsScreen",
        "GUI_Qt.screens.ActivityScreen",
        "GUI_Qt.screens.SpotifyScreen",
        "GUI_Qt.routes",
        "GUI_Qt.services.navigation",
        "GUI_Qt.services.updates",
        "GUI_Qt.services.errors",
        "GUI_Qt.services.shutdown",
        "GUI_Qt.batch.table",
        "GUI_Qt.batch.workbook",
        "GUI_Qt.batch.execution",
        "GUI_Qt.earnings.dialogs",
        "GUI_Qt.earnings.widgets",
        "GUI_Qt.earnings.presentation",
        "GUI_Qt.orbea.controller",
        "GUI_Qt.orbea.workers",
        "GUI_Qt.orbea.tabs",
        "GUI_Qt.MainWindow",
    ]
    for module_name in modules:
        importlib.import_module(module_name)
    print("compile-and-import-ok")


if __name__ == "__main__":
    main()
