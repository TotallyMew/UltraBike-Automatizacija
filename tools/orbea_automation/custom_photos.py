"""Save the untouched Your Design gallery, without choosing any paint options."""
from __future__ import annotations

import base64
import hashlib
import json
import re
import time
from io import BytesIO
from pathlib import Path

from PIL import Image
from selenium.common.exceptions import ElementClickInterceptedException, TimeoutException
from selenium.webdriver.support.ui import WebDriverWait

from .checkpoint import atomic_write_json
from .image_store import OrbeaImageStore
from .photos import MAX_IMAGE_BYTES, OrbeaPhotoRunResult, OrbeaPhotoService

# Orbea's real Frame Options toggle is a checkbox with two captions in one
# label. Its checked caption selects You design; no paint control is touched.
DESIGN_CONTROL_SCRIPT = r"""
const root = document.querySelector('#product-bike-detail');
if (!root) return null;
const visible = node => node && node.getClientRects().length && getComputedStyle(node).visibility === 'visible';
if (!window.Alpine) return null;
const state = window.Alpine.$data(root);
if (!state.currentTemplate || !state.customization || state.initialize === false || state.canvasesReady === false || state.loadingTemplate) return null;
const checkbox = root.querySelector('input#frame-options[type="checkbox"]');
if (checkbox && !checkbox.disabled && visible(checkbox)) return {control: checkbox, input: checkbox};
const key = value => String(value || '').toLowerCase().replace(/\s+/g, '');
const choices = [];
for (const label of root.querySelectorAll('label')) {
    const caption = label.querySelector('[x-ref="option-checked"]');
    if (!['yourdesign', 'youdesign'].includes(key(caption ? caption.textContent : label.innerText))) continue;
    if (!visible(label)) continue;
    const input = label.control || label.querySelector('input[type="radio"], input[type="checkbox"]');
    if (!input || !['radio', 'checkbox'].includes(input.type) || input.disabled || !root.contains(input)) continue;
    if (!choices.some(choice => choice.input === input)) choices.push({control: input, input});
}
if (choices.length > 1) throw new Error('More than one Your Design option is visible');
if (choices.length) return choices[0];
if (window.Alpine) {
    if (state.templates?.length && state.templates.every(template => template.type !== 'standard') &&
        state.currentTemplate && state.isStandardTemplate === false) return {control: null, input: null, default_only: true};
}
return null;
"""

# Follow the official downloadImage / H0 renderer: canvases belonging to the
# selected template and view are composited in DOM order. imagesCanvas tells us
# which component/paint layers must finish loading before exporting any view.
_GALLERY_HELPER = r"""
function defaultGallery(input) {
    const root = document.querySelector('#product-bike-detail');
    if (!root || (input && !input.checked) || !window.Alpine) return null;
    const state = window.Alpine.$data(root);
    const template = (state.templates || []).find(item => String(item.id) === String(state.template));
    if (!template || !template.hash || template.type === 'standard' || state.isStandardTemplate === true) return null;
    if (!input && (state.templates || []).some(item => item.type === 'standard')) return null;
    if (state.canvasesReady === false || state.loadingTemplate || state.loadingInspiration ||
        state.loadingVarnish || state.componentUpdating) return null;
    const id = String(template.id);
    if (!/^[A-Za-z0-9_-]{1,96}$/.test(id)) return null;
    const viewItems = [...(template.views || [])].filter(item => item.status == null || item.status === 'published')
        .sort((a, b) => Number(a.order || 0) - Number(b.order || 0));
    const available = state.imagesCanvas?.[id];
    if (!available || !viewItems.length) return null;
    const views = [], unavailable = [];
    for (const item of viewItems) {
        const view = String(item.type || '');
        if (!/^[A-Za-z0-9_-]{1,96}$/.test(view)) return null;
        const expected = available[view];
        if (!expected || !expected.base) { unavailable.push(view); continue; }
        const prefix = `canvas-${id}_${view}_`;
        const base = document.getElementById(prefix + 'base');
        if (!base || !root.contains(base) || !base.dataset.drawn || base.width < 640 || base.height < 320) return null;
        for (const [zone, url] of Object.entries(expected)) {
            if (!url) continue;
            const layer = document.getElementById(prefix + zone);
            if (!layer || !root.contains(layer) || !layer.dataset.drawn || layer.width !== base.width || layer.height !== base.height) return null;
        }
        const layers = [...root.querySelectorAll(`canvas[id^="${prefix}"]`)].filter(layer =>
            (view.endsWith('_alt') || !layer.id.startsWith(prefix + 'alt')) &&
            layer.dataset.drawn && layer.width === base.width && layer.height === base.height &&
            (expected[layer.id.slice(prefix.length)] || layer.dataset.textZone));
        if (!layers.length) return null;
        views.push({view, width: base.width, height: base.height,
            layers: layers.map(layer => ({id: layer.id, url: expected[layer.id.slice(prefix.length)] || ''}))});
    }
    if (!views.length) return null;
    return {asset_hash: String(template.hash), template_id: id, template_type: template.type,
        views, unavailable};
}
"""
GALLERY_METADATA_SCRIPT = _GALLERY_HELPER + "\nreturn defaultGallery(arguments[0]);"
GALLERY_SCRIPT = _GALLERY_HELPER + r"""
const gallery = defaultGallery(arguments[0]);
if (!gallery) return null;
const images = [];
for (const view of gallery.views) {
    const output = document.createElement('canvas'); output.width = view.width; output.height = view.height;
    const context = output.getContext('2d', {willReadFrequently: true});
    for (const layer of view.layers) context.drawImage(document.getElementById(layer.id), 0, 0);
    images.push({view: view.view, width: output.width, height: output.height, data_url: output.toDataURL('image/png')});
    context.clearRect(0, 0, output.width, output.height); output.width = 0; output.height = 0;
}
return {asset_hash: gallery.asset_hash, template_id: gallery.template_id, template_type: gallery.template_type,
    unavailable: gallery.unavailable, images};
"""
RELOAD_VIEWS_SCRIPT = r"""
const done = arguments[arguments.length - 1];
const root = document.querySelector('#product-bike-detail');
const state = root && window.Alpine ? window.Alpine.$data(root) : null;
if (!state || state.isStandardTemplate || typeof state.loadTemplateCanvases !== 'function') { done(false); return; }
const template = (state.templates || []).find(item => String(item.id) === String(state.template));
if (!template || state.loadingTemplate || !state.imagesCanvas?.[state.template]) { done(false); return; }
const views = template.views.filter(view => view.status == null || view.status === 'published').map(view => view.type);
Promise.resolve(state.loadTemplateCanvases(state.template, null, views)).then(() => done(true)).catch(error => done(String(error)));
"""


class CustomDesignAlreadySelected(ValueError):
    pass


class CustomDesignNotReady(ValueError):
    pass


def capture_default_design(driver, *, timeout=25, check=lambda: None, settle_seconds=1.0, allow_selected_default=False):
    """Select the real toggle and export complete default preview layers."""
    def find_control(unused):
        check()
        return driver.execute_script(DESIGN_CONTROL_SCRIPT) or False
    try:
        choice = WebDriverWait(driver, timeout).until(find_control)
    except TimeoutException:
        raise ValueError('The Custom bike has no visible Your Design option or default Custom-only preview') from None
    check()
    if choice['input'] is not None and driver.execute_script('return arguments[0].checked === true;', choice['input']):
        if not allow_selected_default:
            raise CustomDesignAlreadySelected('Your Design was already selected; reload the product before collecting its default photos')
    elif choice['control'] is not None:
        try:
            choice['control'].click()
        except ElementClickInterceptedException:
            driver.execute_script('arguments[0].click();', choice['control'])
    last_digest, stable_since = None, None

    def ready(unused):
        nonlocal last_digest, stable_since
        check()
        metadata = driver.execute_script(GALLERY_METADATA_SCRIPT, choice['input'])
        if not metadata:
            last_digest, stable_since = None, None
            return False
        digest = hashlib.sha256(json.dumps(metadata, sort_keys=True).encode()).hexdigest()
        now = time.monotonic()
        if digest != last_digest:
            last_digest, stable_since = digest, now
        return metadata if now - stable_since >= settle_seconds else False
    try:
        try:
            metadata = WebDriverWait(driver, timeout, poll_frequency=.25).until(ready)
        except TimeoutException:
            # Orbea lazily loads views and uses a short image timeout. Retry
            # rendering the same configuration once, without changing paint.
            check()
            if driver.execute_async_script(RELOAD_VIEWS_SCRIPT) is not True:
                raise
            last_digest, stable_since = None, None
            metadata = WebDriverWait(driver, timeout, poll_frequency=.25).until(ready)
        check()
        snapshot = driver.execute_script(GALLERY_SCRIPT, choice['input'])
        if not snapshot or snapshot['asset_hash'] != metadata['asset_hash']:
            raise ValueError('The default Your Design preview changed while exporting its photos')
        return snapshot
    except TimeoutException:
        raise CustomDesignNotReady('The complete untouched Your Design photos did not finish loading') from None


def save_default_design(snapshot, output_dir, *, asset_root=None, log=None, check=lambda: None):
    """Validate the gallery PNGs before adding them to shared photo storage."""
    output = Path(output_dir).resolve()
    images = snapshot.get('images') or []
    asset_hash = str(snapshot.get('asset_hash') or '')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,96}', asset_hash) or not images:
        raise ValueError('The default Your Design gallery is incomplete')
    decoded = []
    seen = set()
    for item in images:
        check()
        view = str(item.get('view') or '')
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,96}', view) or view in seen:
            raise ValueError('The default Your Design gallery has invalid or duplicate views')
        seen.add(view)
        data_url = str(item.get('data_url') or '')
        if not data_url.startswith('data:image/png;base64,') or len(data_url) > MAX_IMAGE_BYTES * 4 // 3 + 100:
            raise ValueError('The default Your Design image is not a supported PNG')
        payload = base64.b64decode(data_url.split(',', 1)[1], validate=True)
        with Image.open(BytesIO(payload)) as image:
            if image.format != 'PNG' or image.size != (item.get('width'), item.get('height')):
                raise ValueError('The default Your Design image dimensions are invalid')
            if image.width < 640 or image.height < 320 or image.width * image.height > 40_000_000:
                raise ValueError('The default Your Design image resolution is invalid')
            rgba = image.convert('RGBA')
            if not rgba.getchannel('A').getbbox() or len(rgba.resize((32, 18)).getcolors(577) or []) < 2:
                raise ValueError('The default Your Design image is blank')
            decoded.append((view, rgba.copy()))
    store = OrbeaImageStore(Path(asset_root) if asset_root else output / '.orbea-assets', log=log)
    files = []
    digests = {}
    for view, image in decoded:
        check()
        path = output / f'Custom_{view}.png'
        OrbeaPhotoService._atomic_save(image, path)
        digests[path.name] = store.intern(path)
        files.append(path)
        if log:
            log(f'Saved untouched Your Design photo: {path.name}')
    unavailable = tuple(f'Custom Your Design view not published: {view}' for view in snapshot.get('unavailable', []))
    atomic_write_json(output / 'download_manifest.json', {'source': 'your_design_default',
        'asset_hash': asset_hash, 'template_id': snapshot.get('template_id'), 'template_type': snapshot.get('template_type'),
        'views': [view for view, _ in decoded], 'files': [path.name for path in files],
        'unavailable': list(unavailable), 'sha256': digests})
    return OrbeaPhotoRunResult(output_dir=output.parent, product_dir=output, title='Your Design (default)',
        variants=1, views=len(files), files=tuple(files), failures=(), cancelled=False, unavailable=unavailable,
        variant_files={'Custom': tuple(files)})
