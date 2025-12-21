"""Application version helper.

Reads VERSION.txt from bundled resources (PyInstaller) or project root.
"""

from __future__ import annotations

from Utilities.ResourcePaths import resource_path


def get_app_version(default: str = "0.0.0") -> str:
    try:
        p = resource_path("VERSION.txt")
        if p.exists():
            value = p.read_text(encoding="utf-8").strip()
            return value or default
    except Exception:
        pass
    return default
