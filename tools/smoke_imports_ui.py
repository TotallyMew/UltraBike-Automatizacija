"""Small import smoke-test script.

This is used during refactors to quickly validate there are no syntax/import errors
in UI modules without launching the full application.
"""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


import py_compile


def main() -> None:
    # Importing GUI modules (or even some style modules) can pull in Qt/QFluentWidgets
    # and execute import-time side effects. Keep this script compile-only.
    to_compile = [
        PROJECT_ROOT / "GUI_Qt" / "styles" / "global_styles.py",
        PROJECT_ROOT / "GUI_Qt" / "styles" / "theme_config.py",
        PROJECT_ROOT / "GUI_Qt" / "screens" / "BatchUploadScreen.py",
        PROJECT_ROOT / "GUI_Qt" / "screens" / "BatchTitlesScreen.py",
        PROJECT_ROOT / "GUI_Qt" / "screens" / "BatchDescriptionsScreen.py",
    ]
    for path in to_compile:
        py_compile.compile(str(path), doraise=True)
    print("compile-ok")


if __name__ == "__main__":
    main()
