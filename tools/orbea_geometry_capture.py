"""Use the size-table screenshot routine for each native geometry combination."""
from __future__ import annotations

import math


PREPARE_GEOMETRY_CAPTURE_JS = r"""
const table = arguments[0], settings = arguments[1], expected = arguments[2];
const clean = value => (value || '').replace(/\s+/g, ' ').trim();
const data = {
  headers: [...table.querySelectorAll('thead th,thead td')].map(cell => clean(cell.innerText)),
  rows: [...table.querySelectorAll('tbody tr')].map(row =>
    [...row.querySelectorAll('td,th')].map(cell => clean(cell.innerText)))
};
if (JSON.stringify(data) !== JSON.stringify(expected)) throw Error('Geometry changed before its styled capture');
const source = table.closest('#geometry-data') || table;
const fields = [...source.querySelectorAll('select')];
for (const setting of settings) {
  const field = fields.find(select => select.id === setting.key || select.name === setting.key);
  if (!field || field.value !== setting.value) throw Error('Geometry settings changed before capture');
}
if (source.__ultraGeometryCapture) throw Error('An earlier geometry capture was not restored');
const styles = [], controls = [];
const saveStyle = node => {
  if (!styles.some(record => record.node === node)) styles.push({node, style: node.getAttribute('style')});
};
const dialog = table.closest('dialog[open]');
// Only release scroll clipping temporarily. Screenshot the original DOM, just
// as Size Tables do; do not clone or redraw the table and its measured values.
for (let node = table; node && node !== document.body; node = node.parentElement) {
  saveStyle(node);
  node.style.setProperty('overflow', 'visible', 'important');
  node.style.setProperty('max-height', 'none', 'important');
  if (node === dialog) break;
}
const width = Math.ceil(Math.max(source.getBoundingClientRect().width, table.scrollWidth, source.scrollWidth));
saveStyle(source);
source.style.setProperty('width', `${width}px`, 'important');
if (dialog) {
  for (const [name, value] of Object.entries({top:'0', left:'0', bottom:'auto', transform:'none', margin:'0'})) {
    dialog.style.setProperty(name, value, 'important');
  }
}
// A native change can refresh the table while leaving an old decorative label.
// Display the verified value during the screenshot, then restore the original
// child nodes (and their listeners) before the next selection.
for (const field of fields) {
  const setting = settings.find(item => item.key === field.id || item.key === field.name);
  const group = field.closest('.select-container') || field.parentElement;
  const control = group.querySelector('.ts-control');
  if (control) {
    controls.push({node: control, children: [...control.childNodes]});
    const item = control.querySelector('.item')?.cloneNode(false) || document.createElement('div');
    item.className = 'item';
    item.textContent = setting ? setting.text : clean(field.selectedOptions[0]?.textContent);
    Object.assign(item.style, {whiteSpace: 'normal', overflow: 'visible', textOverflow: 'clip', maxWidth: 'none'});
    control.replaceChildren(item);
  }
  group.querySelectorAll('.ts-dropdown').forEach(node => {
    saveStyle(node);
    node.style.setProperty('display', 'none', 'important');
  });
}
source.__ultraGeometryCapture = {styles, controls};
return {element: source, width, height: Math.ceil(source.getBoundingClientRect().height)};
"""

RESTORE_GEOMETRY_CAPTURE_JS = r"""
const source = arguments[0].element;
const saved = source.__ultraGeometryCapture;
if (!saved) throw Error('Geometry screenshot restoration data is missing');
for (const record of saved.controls) record.node.replaceChildren(...record.children);
for (const record of saved.styles) {
  if (record.style === null) record.node.removeAttribute('style');
  else record.node.setAttribute('style', record.style);
}
delete source.__ultraGeometryCapture;
"""


def capture_styled_geometry(driver, table, destination, settings, data, *, screenshot):
    """Screenshot the native geometry element using the unchanged Size routine."""
    headers, rows = data.get('headers', []), data.get('rows', [])
    if not headers or not rows or any(len(row) != len(headers) for row in rows):
        raise RuntimeError('The complete geometry table could not be read')
    prepared = driver.execute_script(PREPARE_GEOMETRY_CAPTURE_JS, table, settings, data)
    original_size = None
    resized = False
    try:
        width, height = math.ceil(prepared['width']), math.ceil(prepared['height'])
        if not width or not height or max(width, height) > 16000:
            raise RuntimeError('The styled geometry table has an invalid capture size')
        original_size = driver.get_window_size()
        # This is the dedicated Orbea download browser. The Pimbo browser is
        # never resized. A taller viewport makes WebDriver capture all rows.
        required = (max(original_size['width'], width + 100), max(original_size['height'], height + 160))
        if required != (original_size['width'], original_size['height']):
            resized = True
            driver.set_window_size(*required)
        dimensions = screenshot(driver, prepared['element'], destination)
        if dimensions[0] < width or dimensions[1] < height:
            raise RuntimeError('The styled geometry screenshot was clipped')
        return dimensions
    finally:
        # Restore the live controls and original viewport even after a failed
        # screenshot, before the next geometry combination is selected.
        try:
            if resized and original_size:
                driver.set_window_size(original_size['width'], original_size['height'])
        finally:
            driver.execute_script(RESTORE_GEOMETRY_CAPTURE_JS, prepared)
