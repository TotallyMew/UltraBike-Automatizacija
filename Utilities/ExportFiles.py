"""Atomic generated exports that tolerate an existing file held open in Excel."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def replace_generated_export(
    temporary: Path, destination: Path, *, fallback_base: Path | None = None
) -> Path:
    """Keep a locked original and publish the finished export beside it.

    Only replacement of an existing file gets this fallback. A directory
    permission error, missing output directory or disk error must still surface.
    """
    destination = Path(destination)
    try:
        os.replace(temporary, destination)
        return destination
    except PermissionError:
        if not destination.is_file():
            raise
        base = Path(fallback_base or destination)
        for index in range(1, 101):
            suffix = "" if index == 1 else f"_{index}"
            candidate = base.with_name(f"{base.stem}_updated{suffix}{base.suffix}")
            if candidate == destination:
                continue
            try:
                os.replace(temporary, candidate)
                return candidate
            except PermissionError:
                if not candidate.is_file():
                    raise
        raise


def atomic_save_workbook(workbook, destination, *, fallback_base=None) -> Path:
    """Finish an XLSX before replacing it; return the file actually written."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle, filename = tempfile.mkstemp(
        prefix=f".{destination.stem}-", suffix=".tmp.xlsx", dir=destination.parent,
    )
    os.close(handle)
    temporary = Path(filename)
    try:
        workbook.save(temporary)
        return replace_generated_export(temporary, destination, fallback_base=fallback_base)
    finally:
        workbook.close()
        temporary.unlink(missing_ok=True)
