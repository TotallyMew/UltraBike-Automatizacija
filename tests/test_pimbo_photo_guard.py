from __future__ import annotations

import json
import shutil
import subprocess
from types import SimpleNamespace

import pytest
from selenium.common.exceptions import NoAlertPresentException

from Managers.PimboProductEditor import PimboProductEditor, PimAutomationError, PimPreparationResult, PimPreparationStatus

PLACEHOLDER = PimboProductEditor.ORBEA_PHOTO_PLACEHOLDER
REAL_PHOTO = "https://cdn.example.com/bike.webp"
PROMPT = "Remove this image from the product? The file will remain in the media library."


class Alert:
    def __init__(self, driver):
        self.driver = driver
        self.text = driver.prompt

    def accept(self):
        self.driver.accepted += 1
        if self.driver.remove_works:
            self.driver.cards.remove(self.driver.pending)
        self.driver.pending = None

    def dismiss(self):
        self.driver.dismissed += 1
        self.driver.pending = None


class GalleryDriver:
    current_url = "https://pim.bo.ultrabike.lt/dashboard/products/p1"
    prompt = PROMPT
    remove_works = True

    def __init__(self, sources):
        self.cards = [{"src": source, "button": object()} for source in sources]
        self.sent = []
        self.clicked = []
        self.accepted = self.dismissed = 0
        self.pending = None
        self.switch_to = self

    @property
    def alert(self):
        if self.pending is None:
            raise NoAlertPresentException()
        return Alert(self)

    def execute_script(self, script, *args):
        if script == "arguments[0].click();":
            self.pending = next(card for card in self.cards if card["button"] is args[0])
            self.clicked.append(self.pending["src"])
            return None
        self.gallery_script = script
        return list(self.cards)

    def send_keys(self, value):
        self.sent.append(value)
        # PIMBO adds these real photos immediately; further batches must still upload.
        self.cards.extend({"src": "https://cdn.example.com/" + path, "button": object()} for path in value.split("\n"))


class GalleryEditor(PimboProductEditor):
    def __init__(self, sources):
        super().__init__(GalleryDriver(sources), timeout=0.05)
        self._bound_product_id = "p1"

    def open_section(self, section):
        assert section == "general"

    def _image_group_input(self, group):
        assert group == "product"
        return self.driver

    def is_dirty(self):
        return bool(self.driver.sent or self.driver.accepted)


def test_only_the_exact_orbea_asset_is_a_placeholder():
    assert PimboProductEditor._is_photo_placeholder(PLACEHOLDER)
    assert PimboProductEditor._is_photo_placeholder(PLACEHOLDER + "?version=1#image")
    for source in [REAL_PHOTO, PLACEHOLDER.replace("www.orbea.com", "cdn.example.com"),
                   PLACEHOLDER.replace("/uploads/products/images/", "/other/"), "", "picture-coming-soon.webp"]:
        assert not PimboProductEditor._is_photo_placeholder(source)


@pytest.mark.parametrize("sources", [[], [PLACEHOLDER], [PLACEHOLDER, PLACEHOLDER]])
def test_empty_or_placeholder_gallery_uploads_all_batches(sources):
    editor = GalleryEditor(sources)
    assert editor.prepare_product_photo_upload(has_replacements=True)
    assert editor.upload_product_images(["one.jpg", "two.jpg"], skip_if_present=False) == 2
    assert editor.upload_product_images(["three.jpg"], skip_if_present=False) == 1
    assert editor.driver.accepted == len(sources)
    assert editor.driver.clicked == sources
    assert editor.photo_upload == {"action": "uploaded", "existing_photos": 0,
                                   "placeholders_removed": len(sources), "uploaded_photos": 3}
    assert len(editor.driver.sent) == 2


@pytest.mark.parametrize("has_replacements", [True, False])
def test_mixed_gallery_removes_only_placeholder_and_skips_upload(has_replacements):
    editor = GalleryEditor([REAL_PHOTO, PLACEHOLDER])
    assert not editor.prepare_product_photo_upload(has_replacements=has_replacements)
    assert editor.upload_product_images(["new.jpg"], skip_if_present=False) == 0
    assert [card["src"] for card in editor.driver.cards] == [REAL_PHOTO]
    assert editor.driver.clicked == [PLACEHOLDER] and editor.driver.accepted == 1
    assert editor.photo_upload["action"] == "skipped_existing"
    assert editor.photo_upload["existing_photos"] == 1
    base = PimPreparationResult("SKU", "p1")
    result = editor.finish(base)
    assert "images" in result.changed_fields
    assert result.photo_upload["placeholders_removed"] == 1
    assert result.status == PimPreparationStatus.READY_FOR_REVIEW


def test_real_photos_always_skip_even_if_legacy_caller_requests_duplicates():
    editor = GalleryEditor([REAL_PHOTO])
    assert editor.upload_product_images(["new.jpg"], skip_if_present=False) == 0
    assert editor.driver.sent == [] and editor.driver.clicked == []
    assert editor.photo_upload["action"] == "skipped_existing"


def test_missing_replacements_preserves_placeholder():
    editor = GalleryEditor([PLACEHOLDER])
    assert not editor.prepare_product_photo_upload(has_replacements=False)
    assert editor.photo_upload["action"] == "missing_photos"
    assert editor.driver.cards[0]["src"] == PLACEHOLDER
    assert editor.driver.accepted == 0


def test_unexpected_confirmation_is_dismissed_without_upload():
    editor = GalleryEditor([PLACEHOLDER])
    editor.driver.prompt = "Delete this product permanently?"
    with pytest.raises(PimAutomationError, match="Unexpected image removal confirmation"):
        editor.upload_product_images(["new.jpg"])
    assert editor.driver.dismissed == 1 and editor.driver.accepted == 0
    assert editor.driver.sent == [] and editor.driver.cards[0]["src"] == PLACEHOLDER
    assert editor.photo_upload["action"] == "failed"


def test_failed_removal_blocks_upload():
    editor = GalleryEditor([PLACEHOLDER])
    editor.driver.remove_works = False
    with pytest.raises(Exception, match="placeholder remained"):
        editor.upload_product_images(["new.jpg"])
    assert editor.driver.sent == [] and editor.photo_upload["action"] == "failed"


def test_missing_remove_control_blocks_upload():
    editor = GalleryEditor([PLACEHOLDER])
    editor.driver.cards[0]["button"] = None
    with pytest.raises(PimAutomationError, match="no Remove image control"):
        editor.upload_product_images(["new.jpg"])
    assert editor.driver.sent == []


def test_wrong_product_stops_before_removal_or_upload():
    editor = GalleryEditor([PLACEHOLDER])
    editor.driver.current_url = editor.driver.current_url.replace("/p1", "/p2")
    with pytest.raises(PimAutomationError, match="different PIMBO product"):
        editor.upload_product_images(["new.jpg"])
    assert editor.driver.sent == editor.driver.clicked == []


def test_photo_result_round_trips_and_old_records_remain_readable():
    result = PimPreparationResult("SKU", photo_upload={"action": "skipped_existing", "placeholders_removed": 1})
    assert PimPreparationResult.from_dict(result.to_dict()) == result
    assert PimPreparationResult.from_dict({"product_code": "SKU"}).photo_upload == {}


DOM_RUNTIME = r"""
const payload = JSON.parse(require('fs').readFileSync(0, 'utf8'));
class Node {
  constructor(data) {
    this.tagName = (data.tag || 'div').toUpperCase();
    this.attrs = data.attrs || {};
    this.children = (data.children || []).map(child => new Node(child));
    this.children.forEach(child => child.parentElement = this);
  }
  matches(selector) {
    if (selector === 'img') return this.tagName === 'IMG';
    if (selector === 'img.size-full.object-cover') return this.tagName === 'IMG' && (this.attrs.class || '').includes('size-full') && (this.attrs.class || '').includes('object-cover');
    if (selector === 'button[aria-label="Remove image"]') return this.tagName === 'BUTTON' && this.attrs['aria-label'] === 'Remove image';
    if (selector === "input[type='file'][accept*='image']") return this.tagName === 'INPUT' && this.attrs.type === 'file' && (this.attrs.accept || '').includes('image');
    throw new Error('Unsupported selector: ' + selector);
  }
  querySelectorAll(selector) {
    const found = [];
    for (const child of this.children) {
      if (child.matches(selector)) found.push(child);
      found.push(...child.querySelectorAll(selector));
    }
    return found;
  }
  getAttribute(name) { return this.attrs[name] || null; }
}
const root = new Node(payload.dom);
const input = root.querySelectorAll("input[type='file'][accept*='image']")[0];
const cards = new Function(payload.script).apply(null, [input]);
process.stdout.write(JSON.stringify(cards.map(card => ({src: card.src, button: !!card.button}))));
"""


def test_production_gallery_script_excludes_table_and_description_images():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is required to execute the browser script fixture")
    editor = GalleryEditor([])
    editor._product_photo_cards()
    def area(source):
        return {"children": [
            {"tag": "input", "attrs": {"type": "file", "accept": "image/*"}},
            {"children": [{"tag": "img", "attrs": {"src": source, "class": "size-full object-cover"}},
                          {"tag": "button", "attrs": {"aria-label": "Remove image", "class": "opacity-0"}}]},
        ]}
    dom = {"tag": "main", "children": [{"children": [area(PLACEHOLDER), area("geometry.png"), area("size.png")]},
            {"tag": "img", "attrs": {"src": "description.png"}}]}
    result = subprocess.run([node, "-e", DOM_RUNTIME], input=json.dumps({"dom": dom, "script": editor.driver.gallery_script}),
                            text=True, capture_output=True, check=True)
    assert json.loads(result.stdout) == [{"src": PLACEHOLDER, "button": True}]


def test_a_lone_table_input_cannot_be_used_for_product_photos():
    field = object()
    editor = PimboProductEditor(SimpleNamespace(find_elements=lambda *args: [field]))
    editor._image_input_context = lambda element: "geometry"
    with pytest.raises(PimAutomationError, match="distinguished from table images"):
        editor._image_group_input("product")


def test_ambiguous_product_gallery_blocks_photo_upload():
    editor = PimboProductEditor(SimpleNamespace(find_elements=lambda *args: [object(), object()]))
    editor._image_input_context = lambda element: "product images"
    with pytest.raises(PimAutomationError, match="ambiguous"):
        editor._image_group_input("product")


def test_photos_available_after_missing_preflight_recheck_and_replace_placeholder():
    editor = GalleryEditor([PLACEHOLDER])
    assert not editor.prepare_product_photo_upload(has_replacements=False)
    assert editor.upload_product_images(["new.jpg"]) == 1
    assert editor.driver.accepted == 1 and editor.driver.clicked == [PLACEHOLDER]
