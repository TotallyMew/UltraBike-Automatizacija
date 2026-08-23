"""Generate the repository's canonical update manifest from a built installer."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Utilities.Updater import sha256_file


CANONICAL_MANIFEST = PROJECT_ROOT / "latest.json"


def build_manifest(
    installer: Path,
    version: str,
    url: str,
    notes: str,
) -> dict[str, str]:
    installer = installer.resolve(strict=True)
    if installer.suffix.lower() != ".exe":
        raise ValueError("The update installer must be an .exe file")
    if not version.strip():
        raise ValueError("The update version is required")
    if not url.lower().startswith("https://"):
        raise ValueError("The update URL must use HTTPS")
    return {
        "version": version.strip(),
        "url": url.strip(),
        "sha256": sha256_file(str(installer)),
        "notes": notes.strip(),
        "installer": installer.name,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("installer", type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--notes", default="")
    args = parser.parse_args()

    manifest = build_manifest(args.installer, args.version, args.url, args.notes)
    CANONICAL_MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {CANONICAL_MANIFEST}")
    print(f"SHA-256: {manifest['sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
