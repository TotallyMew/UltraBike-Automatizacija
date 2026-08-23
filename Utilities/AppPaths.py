"""Application data paths.

Centralizes where user-specific runtime data lives (DB, session files, logs, etc.).

Defaults (Windows):
    %APPDATA%\\UltraBike_Automatizacija

Overrides:
    - Set env var ULTRABIKE_DATA_DIR to force a directory.
    - Create a file named portable.flag next to the .exe (PyInstaller) or next
        to the project root (source) to keep runtime files alongside the app.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


APP_DIR_NAME = "UltraBike_Automatizacija"
ENV_DATA_DIR = "ULTRABIKE_DATA_DIR"


def get_data_dir() -> Path:
    override = os.getenv(ENV_DATA_DIR)
    if override:
        base = Path(override).expanduser()
    else:
        # Portable mode: keep data near the executable (frozen) or near project root (source).
        portable_base = _get_portable_base_dir()
        if portable_base is not None:
            base = portable_base
        else:
            # Prefer roaming AppData on Windows.
            appdata = os.getenv("APPDATA")
            if appdata:
                base = Path(appdata)
            else:
                base = Path.home() / ".config"

    path = base / APP_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def _get_portable_base_dir() -> Path | None:
    """Return a base dir for portable mode if portable.flag exists."""
    try:
        if getattr(sys, "frozen", False):
            exe_dir = Path(sys.executable).resolve().parent
            if (exe_dir / "portable.flag").exists():
                return exe_dir
            return None

        # Source mode: detect portable.flag at repo root (Utilities/ is one level below).
        root_dir = Path(__file__).resolve().parents[1]
        if (root_dir / "portable.flag").exists():
            return root_dir
        return None
    except Exception:
        return None


def get_default_db_path() -> Path:
    return get_data_dir() / "ultrabike.db"


def get_default_session_path() -> Path:
    return get_data_dir() / "session.dat"


def get_default_logs_dir() -> Path:
    path = get_data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_default_backups_dir() -> Path:
    path = get_data_dir() / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path
