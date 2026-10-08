from __future__ import annotations

import errno
import json
import os
from unittest.mock import patch

import pytest
from PIL import Image

from tools.orbea_automation.image_store import deduplicate_saved_images, link_image
from tools.orbea_automation.upload import OrbeaUploadService


def test_compact_saved_run_preserves_paths_bytes_and_metadata_and_is_idempotent(tmp_path):
    run = tmp_path / "20261006-192848"
    run.mkdir()
    checkpoint = run / "run_checkpoint.json"
    checkpoint.write_text('{"completed": false}')
    paths = [run / "products" / sku / "photos" / "colour" / "side.png" for sku in ("SKU1", "SKU2", "SKU3")]
    for path in paths:
        path.parent.mkdir(parents=True)
        Image.new("RGB", (500, 400), "blue").save(path)
    original = paths[0].read_bytes()
    other = paths[-1].with_name("front.png")
    Image.new("RGB", (500, 400), "red").save(other)
    # The browser cache is deliberately outside the eligible image trees.
    browser = tmp_path / ".orbea-browser/side.png"
    browser.parent.mkdir()
    browser.write_bytes(original)
    result = deduplicate_saved_images(tmp_path)
    assert result.images == 4 and result.linked == 2
    assert result.bytes_reclaimed == 2 * len(original)
    assert all(path.read_bytes() == original for path in paths)
    assert all(os.path.samefile(paths[0], path) for path in paths)
    assert not os.path.samefile(paths[0], other)
    assert not os.path.samefile(paths[0], browser)
    assert checkpoint.read_text() == '{"completed": false}'
    again = deduplicate_saved_images(tmp_path)
    assert again.linked == 0 and again.bytes_reclaimed == 0
    # Removing the cache or another product cannot break the upload path.
    for cached in (tmp_path / ".orbea-assets/images").glob("*.png"):
        cached.unlink()
    paths[0].unlink()
    assert paths[1].read_bytes() == original


def test_link_failure_leaves_existing_image_intact(tmp_path):
    source, target = tmp_path / "source.png", tmp_path / "target.png"
    source.write_bytes(b"source")
    target.write_bytes(b"original target")
    with patch("tools.orbea_automation.image_store.os.link", side_effect=OSError(errno.EPERM, "unsupported")):
        with pytest.raises(OSError):
            link_image(source, target, allow_copy=False)
        assert target.read_bytes() == b"original target"
        assert link_image(source, target) is False
    assert target.read_bytes() == source.read_bytes()
    assert not list(tmp_path.glob(".orbea-link-*"))


def test_upload_includes_shared_photos_in_colour_subfolders(tmp_path):
    photos = tmp_path / "photos"
    nested = photos / "Blue/blue-side.png"
    nested.parent.mkdir(parents=True)
    Image.new("RGB", (500, 400), "blue").save(nested)
    alias = photos / "Black/black-side.png"
    link_image(nested, alias)
    (photos / "download_manifest.json").write_text(json.dumps({"files": []}))
    candidates = OrbeaUploadService.local_photo_candidates(tmp_path)
    assert set(candidates) == {nested, alias}
    assert all(OrbeaUploadService._local_product_photo_is_uploadable(p) for p in candidates)
