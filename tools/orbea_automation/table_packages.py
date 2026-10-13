"""Keep collected table uploads scoped to the latest completed file manifest."""
from __future__ import annotations

import json
from pathlib import Path


def is_table_image(path: Path) -> bool:
    name = path.name.casefold()
    return name in {"geometry.png", "size-guide-cm.png"} or (name.startswith("geometry-") and name.endswith(".png"))


def geometry_layout_outdated(stage: dict) -> bool:
    """The old adjustable-table renderer must be recaptured from Orbea's DOM.

    Single tables already used native screenshots. Unknown legacy packages keep
    their existing compatibility behaviour; a known older variant export does
    not become current merely because all its PNGs exist.
    """
    from tools.orbea_table_image_downloader import GEOMETRY_CAPTURE_VERSION
    version = stage.get("geometry_capture_version")
    files = stage.get("package_files", stage.get("files", [])) or []
    return (isinstance(version, int) and version < GEOMETRY_CAPTURE_VERSION
            and any(Path(value).name.lower().startswith("geometry-") for value in files))


def geometry_needs_recollection(folder: Path) -> bool:
    metadata = Path(folder) / "orbea-product.json"
    if not metadata.is_file():
        return False
    data = json.loads(metadata.read_text(encoding="utf-8-sig"))
    return geometry_layout_outdated((data.get("stages") or {}).get("tables", {}))


def current_table_files(folder: Path) -> tuple[Path, ...] | None:
    """Read new package paths or rebase older run-relative manifests safely.

    None means an older package has no table manifest: callers may use the
    explicitly named main table, but must not discover additional files by glob.
    """
    folder = Path(folder).resolve()
    metadata = folder / "orbea-product.json"
    if not metadata.is_file():
        return None
    data = json.loads(metadata.read_text(encoding="utf-8-sig"))
    stages = data.get("stages") or {}
    if "tables" not in stages:
        return None
    stage = stages["tables"]
    if stage.get("status") not in {"downloaded", "not_available"}:
        raise ValueError("Table downloads are not complete; finish or retry the table download before uploading")
    recorded = stage.get("package_files", stage.get("files"))
    if not isinstance(recorded, list) or any(not isinstance(item, str) or not item for item in recorded):
        raise ValueError("The saved table file list is missing or invalid; refresh Geometry + CM size tables")
    if (stage["status"] == "downloaded" and not recorded) or (stage["status"] == "not_available" and recorded):
        raise ValueError("The saved table status contradicts its file list; refresh Geometry + CM size tables")
    owners = {folder.name.casefold(), str(data.get("sku", "")).casefold()}
    paths = []
    for value in recorded:
        recorded_path = Path(value)
        if (".." in recorded_path.parts or not is_table_image(recorded_path)
                or (len(recorded_path.parts) > 1 and recorded_path.parent.name.casefold() != "tables")
                or (len(recorded_path.parts) > 2 and recorded_path.parent.parent.name.casefold() not in owners)):
            raise ValueError(f"A saved table path is outside this product's table folder: {value}")
        path = (folder / "tables" / recorded_path.name).resolve()
        if not path.is_relative_to(folder):
            raise ValueError("A saved table file is outside this product folder")
        if path not in paths:
            paths.append(path)
    return tuple(paths)


def prune_obsolete_tables(folder: Path, current: list[Path]) -> list[str]:
    """Remove only generated table filenames after the new set is complete.

    Unlinking product hard links retains the original cached files and other
    products' copies. Locked leftovers are reported and stay excluded by the
    current manifest.
    """
    folder = Path(folder).resolve()
    tables = folder / "tables"
    root = tables.resolve()
    if not root.is_relative_to(folder):
        raise ValueError("The tables folder is outside this product folder")
    if not tables.is_dir():
        return []
    keep = {Path(path).resolve() for path in current}
    if any(path.parent != root for path in keep):
        raise ValueError("A replacement table is outside this product's table folder")
    failures = []
    for path in tables.iterdir():
        resolved = path.resolve()
        if (not is_table_image(path) or path.is_symlink() or resolved.parent != root
                or not path.is_file() or resolved in keep):
            continue
        try:
            path.unlink()
        except OSError as error:
            failures.append(f"Could not remove obsolete table {path.name}: {error}")
    return failures
