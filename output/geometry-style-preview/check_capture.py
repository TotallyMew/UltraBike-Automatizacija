"""Visual QA of native table captures using saved Orbea DOM/CSS, entirely offline."""
import json
from pathlib import Path
import shutil
import sys

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.orbea_geometry_capture import capture_styled_geometry
from tools.orbea_table_image_downloader import GEOMETRY_TABLE_DATA_JS, screenshot_element

OUT = Path(__file__).parent
CSS_ROOT = Path('C:/Users/User/AppData/Local/Temp/browser-use/assets/1d689bef-bc03-4f7c-93be-490bcd81ea43')
shutil.copyfile(CSS_ROOT / '02c9ab966254de50.css', OUT / 'orbea-original.css')
shutil.copyfile(CSS_ROOT / 'be20c1c29ce004cd.css', OUT / 'orbea-fonts.css')
manifest = json.loads((ROOT / 'output/occam-lt-m10-geometry-repair/manifest.json').read_text(encoding='utf-8'))
variant = next(v for v in manifest['variants'] if 'low-head-angle-steep' in v['filename'])
soup = BeautifulSoup((ROOT / 'tests/fixtures/orbea_occam_geometry.html').read_text(encoding='utf-8'), 'html.parser')
table = soup.select_one('table')
for row, values in zip(table.select('tbody tr'), variant['rows']):
    cells = row.select('td,th')
    for cell, value in zip(cells[1:], values[1:]):
        cell.string = value
for setting in variant['settings']:
    field = soup.find('select', id=setting['key'])
    for option in field.select('option'):
        option.attrs.pop('selected', None)
        if option['value'] == setting['value']:
            option['selected'] = ''
html = ('<!doctype html><html><head><meta charset="utf-8">'
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'self\' \'unsafe-inline\'; font-src \'none\'">'
        '<link rel="stylesheet" href="orbea-fonts.css"><link rel="stylesheet" href="orbea-original.css">'
        '<style>body{background:white}dialog{position:fixed;top:48px;left:48px;width:960px;'
        'max-height:350px;overflow:hidden;background:white}#geometry-data{width:720px}</style></head>'
        '<body><dialog open id="qa-dialog">' + str(soup.select_one('#geometry-data')) + '</dialog></body></html>')
path = OUT / 'original-layout-fixture.html'
path.write_text(html, encoding='utf-8')
options = Options()
options.add_argument('--headless=new')
options.add_argument('--window-size=1200,800')
options.add_argument('--disable-gpu')
options.add_argument('--disable-dev-shm-usage')
options.add_argument('--host-resolver-rules=MAP * 127.0.0.1')
driver = webdriver.Chrome(service=Service('C:/Users/User/.wdm/drivers/chromedriver/win64/154.0.8037.92/chromedriver-win32/chromedriver.exe'), options=options)
try:
    driver.get(path.as_uri())
    table = driver.find_element(By.CSS_SELECTOR, '#geometry-data table')
    data = driver.execute_script(GEOMETRY_TABLE_DATA_JS, table)
    original = driver.get_window_size()
    dialog_style = driver.find_element(By.ID, 'qa-dialog').get_attribute('style')
    original_html = driver.find_element(By.ID, 'geometry-data').get_attribute('outerHTML')
    dimensions = capture_styled_geometry(driver, table, OUT / 'geometry-original-style.png', variant['settings'], data, screenshot=screenshot_element)
    assert driver.get_window_size() == original
    assert not driver.find_elements(By.CSS_SELECTOR, '[data-orbea-geometry-capture]')
    assert driver.find_element(By.ID, 'qa-dialog').get_attribute('style') == dialog_style
    assert driver.execute_script(GEOMETRY_TABLE_DATA_JS, table) == data
    restored_html = driver.find_element(By.ID, 'geometry-data').get_attribute('outerHTML')
    # WebDriver's native element screenshot can leave empty style attributes.
    # All effective styles, original nodes/labels and table data must match.
    assert restored_html.replace(' style=""', '') == original_html.replace(' style=""', '')
    assert driver.execute_script("return arguments[0].__ultraGeometryCapture || null", driver.find_element(By.ID, 'geometry-data')) is None
    print(json.dumps({'dimensions': dimensions, 'rows': len(data['rows']), 'restored': True, 'preview': str(OUT / 'geometry-original-style.png')}))
finally:
    driver.quit()
