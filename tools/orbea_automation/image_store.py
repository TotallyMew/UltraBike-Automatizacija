"""Share immutable Orbea images while preserving each product's upload paths."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .checkpoint import atomic_write_json, file_sha256


def link_image(source: Path, destination: Path, *, allow_copy: bool = True) -> bool:
    """Atomically replace a path with a hard link; never remove the source.

    Hard links are ordinary files and keep working when another product or the
    cache is removed. Unsupported filesystems retain the original copy behavior.
    """
    source, destination = Path(source), Path(destination)
    if destination.is_file() and os.path.samefile(source, destination):
        return True
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(prefix=".orbea-link-", dir=destination.parent)
    os.close(handle)
    temporary = Path(name)
    try:
        temporary.unlink()
        try:
            os.link(source, temporary)
            shared = True
        except OSError:
            if not allow_copy:
                raise
            shutil.copy2(source, temporary)
            shared = False
        os.replace(temporary, destination)
        return shared
    finally:
        temporary.unlink(missing_ok=True)


class OrbeaImageStore:
    def __init__(self, root: Path, log: Callable[[str], None] | None = None):
        self.root = Path(root)
        self.log = log
        self._verified: set[str] = set()

    def _path(self, digest: str) -> Path:
        return self.root / "images" / f"{digest}.png"

    def _valid(self, digest: str) -> bool:
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            return False
        path = self._path(digest)
        if not path.is_file():
            return False
        if digest not in self._verified:
            if file_sha256(path) != digest:
                return False
            self._verified.add(digest)
        return True

    def _link(self, source: Path, destination: Path) -> None:
        if not link_image(source, destination) and self.log:
            self.log("This output drive cannot share image storage; saved a separate copy")

    def intern(self, path: Path) -> str:
        """Keep one copy of each PNG's contents and share its existing path."""
        digest = file_sha256(path)
        stored = self._path(digest)
        if not self._valid(digest):
            self._link(path, stored)
            self._verified.add(digest)
        self._link(stored, path)
        return digest

    @staticmethod
    def recipe_key(layer_urls: list[str]) -> str:
        # Order matters for alpha compositing. Names, SKUs and locales do not.
        payload = json.dumps([1, layer_urls], separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def reuse(self, key: str, destination: Path) -> str | None:
        record = self.root / "recipes" / f"{key}.json"
        try:
            digest = json.loads(record.read_text(encoding="utf-8"))["sha256"]
            if not isinstance(digest, str) or not self._valid(digest):
                return None
        except (OSError, ValueError, KeyError, TypeError):
            return None
        self._link(self._path(digest), destination)
        return digest

    def remember(self, key: str, digest: str) -> None:
        atomic_write_json(self.root / "recipes" / f"{key}.json", {"sha256": digest})


@dataclass(frozen=True)
class DeduplicationResult:
    images: int
    linked: int
    bytes_reclaimed: int


def deduplicate_saved_images(output_root: Path) -> DeduplicationResult:
    """Compact existing runs without changing any image bytes or package paths.

    Only PNGs inside Orbea runs are eligible. Browser profiles, metadata, and
    other output are excluded. On an unsupported filesystem the operation
    raises and leaves the current destination intact.
    """
    root = Path(output_root).resolve()
    paths: list[Path] = []
    for checkpoint in root.glob("*/run_checkpoint.json"):
        run = checkpoint.parent
        for directory in (run / "products", run / "images", run / "product-photos"):
            paths.extend(p for p in directory.rglob("*.png")
                         if p.is_file() and not p.is_symlink() and p.resolve().is_relative_to(root))
    # Include the store when counting physical copies, so a second pass reports
    # zero reclaimed bytes and pre-existing links elsewhere are not overstated.
    cached = root / ".orbea-assets" / "images"
    before: dict[tuple[int, int], list[int]] = {}
    for path in [*paths, *cached.glob("*.png")]:
        stat = path.stat()
        item = before.setdefault((stat.st_dev, stat.st_ino), [stat.st_size, stat.st_nlink, 0])
        item[2] += 1
    store = OrbeaImageStore(root / ".orbea-assets")
    linked = 0
    for path in paths:
        digest = file_sha256(path)
        stored = store._path(digest)
        if not store._valid(digest):
            link_image(path, stored, allow_copy=False)
            store._verified.add(digest)
        if not os.path.samefile(path, stored):
            link_image(stored, path, allow_copy=False)
            linked += 1
    after = {(s.st_dev, s.st_ino) for p in [*paths, *cached.glob("*.png")] for s in [p.stat()]}
    reclaimed = sum(size for identity, (size, links, names) in before.items()
                    if identity not in after and links <= names)
    return DeduplicationResult(len(paths), linked, reclaimed)
