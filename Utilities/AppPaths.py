"""Application data paths.

Centralizes where user-specific runtime data lives (DB, session files, etc.)
so packaging/distribution does not accidentally ship personal data.

Windows default:
  %APPDATA%\\UltraBike_Automatizacija

You can override by setting:
  ULTRABIKE_DATA_DIR
"""

from __future__ import annotations

import os
from pathlib import Path


APP_DIR_NAME = "UltraBike_Automatizacija"
ENV_DATA_DIR = "ULTRABIKE_DATA_DIR"


def get_data_dir() -> Path:
    override = os.getenv(ENV_DATA_DIR)
    if override:
        base = Path(override).expanduser()
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


def get_default_db_path() -> Path:
    return get_data_dir() / "ultrabike.db"


def get_default_session_path() -> Path:
    return get_data_dir() / "session.dat"
