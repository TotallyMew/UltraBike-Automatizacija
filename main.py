"""Project entrypoint.

UltraBike is now Qt-only (PySide6 + QFluentWidgets). The legacy CLI and Flet
entrypoints have been removed.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path


def smoke_test() -> int:
    """Validate packaged resources and local services without login or network."""
    from Database.DatabaseManager import DatabaseManager
    from GUI_Qt.i18n import TRANSLATIONS, validate_translation_catalogs
    from GUI_Qt.routes import ROUTE_REGISTRY
    from Managers.OperationTracker import OperationKind, OperationTracker

    validate_translation_catalogs(TRANSLATIONS)
    if not {"upload", "activity", "spotify"} <= set(ROUTE_REGISTRY):
        raise RuntimeError("Required application routes are missing")
    with tempfile.TemporaryDirectory(prefix="ultrabike-smoke-") as temp_dir:
        database = DatabaseManager(Path(temp_dir) / "smoke.db")
        try:
            tracker = OperationTracker(database)
            operation = tracker.create(OperationKind.OTHER, "smoke", message="offline")
            tracker.start(operation.id)
            tracker.finish(operation.id)
            if database.conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("Smoke-test database integrity check failed")
        finally:
            database.close()
    print("ultrabike-smoke-ok")
    return 0


def main() -> None:
    if "--smoke-test" in sys.argv:
        raise SystemExit(smoke_test())
    from GUI_Qt.main import main as qt_main

    qt_main()


if __name__ == "__main__":
    main()
