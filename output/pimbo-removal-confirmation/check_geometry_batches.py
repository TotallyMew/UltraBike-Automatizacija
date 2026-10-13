"""Exercise native Firefox file inputs and the actual editor against offline DOM."""
import json
from pathlib import Path
import sys

from PIL import Image
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import ElementNotInteractableException
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from Managers.PimboProductEditor import PimboProductEditor

OUT = Path(__file__).parent / 'batch-test'
page = OUT / 'dashboard/products/p1/index.html'
page.parent.mkdir(parents=True, exist_ok=True)
page.write_text('''<!doctype html><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'">
<style>.hidden{display:none}</style>
<div data-slot="card"><h2>Geometry</h2><input id="geometry-input" class="hidden" type="file" multiple>
<button id="upload">Upload</button><p id="error" role="alert"></p><div id="gallery"></div></div>
<script>
const gallery = document.querySelector('#gallery');
const error = document.querySelector('#error');
const upload = document.querySelector('#upload');
document.body.dataset.requests = '[]';
function attach(name) {
  const card = document.createElement('div');
  const image = document.createElement('img');
  image.src = 'https://cdn.example.com/' + name;
  const remove = document.createElement('button');
  remove.setAttribute('aria-label','Remove geometry image');
  remove.textContent = 'Remove geometry image';
  remove.onclick = () => { if (confirm('Remove this geometry image from the product?')) card.remove(); };
  card.append(image, remove); gallery.append(card);
}
function bind(input) {
  input.onchange = () => {
    const files = [...input.files];
    if (!files.length) return;
    document.body.dataset.requests = JSON.stringify([...JSON.parse(document.body.dataset.requests), files.length]);
    if (files.length > 12) { error.textContent = 'Too many files'; return; }
    upload.disabled = true;
    setTimeout(() => {
      files.forEach(file => attach(file.name));
      upload.disabled = false;
      // React can replace the input after each asynchronous upload.
      const next = input.cloneNode(); input.replaceWith(next); bind(next);
    }, 50);
  };
}
attach('old-geometry.png'); bind(document.querySelector('#geometry-input'));
</script>''', encoding='utf-8')
paths = []
for index in range(48):
    path = OUT / f'geometry-configuration-{index}.png'
    Image.new('RGB', (100, 80), (index * 5, 40, 50)).save(path)
    paths.append(path)
options = Options()
options.add_argument('-headless')
driver = webdriver.Firefox(service=Service('C:/Users/User/.wdm/drivers/geckodriver/win64/v0.37.1/geckodriver.exe'), options=options)
try:
    driver.get(page.as_uri())
    try:
        driver.find_element(By.ID, 'geometry-input').clear()
        raise AssertionError('Expected native Element Clear to fail on the hidden input')
    except ElementNotInteractableException:
        pass
    class Editor(PimboProductEditor):
        def open_section(self, section):
            assert section == 'general'
        def _image_group_input(self, group):
            assert group == 'geometry'
            return self.driver.find_element(By.ID, 'geometry-input')
    editor = Editor(driver, timeout=3)
    editor._bound_product_id = 'p1'
    assert editor.upload_geometry_images(paths, replace_existing=True) == 48
    counts = json.loads(driver.find_element(By.TAG_NAME, 'body').get_attribute('data-requests'))
    assert counts == [12, 12, 12, 12]
    assert len(editor._geometry_expected_sources) == 48
    assert len(set(editor._geometry_expected_sources)) == 48
    assert not driver.find_element(By.ID, 'error').text
    print(json.dumps({'browser': driver.capabilities['browserName'], 'batches': counts,
                      'attachments': len(editor._geometry_expected_sources), 'react_input_replacement': True,
                      'hidden_input': True, 'original_failure_reproduced': True}))
finally:
    driver.quit()
