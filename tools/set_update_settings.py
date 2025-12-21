from __future__ import annotations

import os
import sqlite3
from pathlib import Path

MANIFEST_URL = "https://raw.githubusercontent.com/TotallyMew/UltraBike_Automatizacija_Release/main/latest.json"


def main() -> None:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise RuntimeError("APPDATA env var is not set")

    db_path = Path(appdata) / "UltraBike_Automatizacija" / "ultrabike.db"
    if not db_path.exists():
        raise FileNotFoundError(f"DB not found: {db_path}")

    con = sqlite3.connect(db_path)
    try:
        cur = con.cursor()
        cur.execute("UPDATE settings SET value=? WHERE key=?", (MANIFEST_URL, "update_manifest_url"))
        cur.execute("UPDATE settings SET value='true' WHERE key='update_check_enabled'")
        con.commit()

        print("Updated settings in:", db_path)
        for k in ("update_check_enabled", "update_manifest_url"):
            row = cur.execute("SELECT key, value FROM settings WHERE key=?", (k,)).fetchone()
            print(row)
    finally:
        con.close()


if __name__ == "__main__":
    main()
