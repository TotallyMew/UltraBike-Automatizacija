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
        PROJECT_ROOT / "Utilities" / "ProductNavigationHandler.py",
        PROJECT_ROOT / "Uploaders" / "BaseUploader.py",
        PROJECT_ROOT / "GUI_Qt" / "workers" / "batch_workers.py",
        PROJECT_ROOT / "GUI_Qt" / "styles" / "global_styles.py",
        PROJECT_ROOT / "GUI_Qt" / "styles" / "theme_config.py",
        PROJECT_ROOT / "GUI_Qt" / "screens" / "UnifiedBatchScreen.py",
        PROJECT_ROOT / "GUI_Qt" / "screens" / "UploadScreen.py",
        PROJECT_ROOT / "GUI_Qt" / "screens" / "SpecCheckerScreen.py",
        PROJECT_ROOT / "GUI_Qt" / "screens" / "NameGetterScreen.py",
        PROJECT_ROOT / "GUI_Qt" / "screens" / "EarningsScreen.py",
        PROJECT_ROOT / "GUI_Qt" / "MainWindow.py",
    ]
    for path in to_compile:
        py_compile.compile(str(path), doraise=True)
    modules = [
        "Managers.PimboProductEditor",
        "Managers.EarningsManager",
        "Utilities.ProductNavigationHandler",
        "Uploaders.BaseUploader",
        "GUI_Qt.workers.batch_workers",
        "GUI_Qt.screens.UnifiedBatchScreen",
        "GUI_Qt.screens.UploadScreen",
        "GUI_Qt.screens.SpecCheckerScreen",
        "GUI_Qt.screens.NameGetterScreen",
        "GUI_Qt.screens.EarningsScreen",
        "GUI_Qt.MainWindow",
    ]
    for module_name in modules:
        importlib.import_module(module_name)
    print("compile-and-import-ok")


if __name__ == "__main__":
    main()
