"""Compact saved Orbea images without changing their contents or upload paths."""
from __future__ import annotations

import argparse
from pathlib import Path

from tools.orbea_automation.image_store import deduplicate_saved_images


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_root", type=Path, help="The UltraBike Orbea Runs folder")
    parser.add_argument("--apply", action="store_true", help="Replace duplicate image storage with hard links")
    args = parser.parse_args()
    if not args.output_root.is_dir():
        parser.error("The Orbea output folder does not exist")
    if not args.apply:
        parser.error("Add --apply to compact image storage while preserving all file paths")
    result = deduplicate_saved_images(args.output_root)
    print(f"Checked {result.images} images; shared {result.linked} duplicates; "
          f"reclaimed {result.bytes_reclaimed / 1_000_000_000:.2f} GB")


if __name__ == "__main__":
    main()
