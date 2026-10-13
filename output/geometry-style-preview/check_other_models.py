"""Verify the real native capture code against saved Orbea DOM, entirely offline."""
import json
from pathlib import Path
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
MODELS = {
    'rallon-rs': ('orbea_rallon_rs_geometry.html', ['27', 'High', 'Steep (+0,75 degrees)']),
    'wild': ('orbea_wild_geometry.html', ['29', 'High']),
    'rallon-e': ('orbea_rallon_e_geometry.html', ['29', 'High Progressive', 'Neutral (+0 degrees)', 'Short (442 mm)']),
}
options = Options()
options.add_argument('--headless=new')
options.add_argument('--window-size=1200,800')
options.add_argument('--host-resolver-rules=MAP * 127.0.0.1')
driver = webdriver.Chrome(service=Service('C:/Users/User/.wdm/drivers/chromedriver/win64/154.0.8037.92/chromedriver-win32/chromedriver.exe'), options=options)
results = []
try:
    for name, (fixture, values) in MODELS.items():
        soup = BeautifulSoup((ROOT / 'tests/fixtures' / fixture).read_text(encoding='utf-8'), 'html.parser')
        settings = []
        for field, value in zip(soup.select('select'), values):
            for option in field.select('option'):
                option.attrs.pop('selected', None)
                if option['value'] == value:
                    option['selected'] = ''
            settings.append({'key': field['id'], 'text': value, 'value': value})
        path = OUT / f'{name}-fixture.html'
        path.write_text('<!doctype html><html><head><meta charset="utf-8">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'self\' \'unsafe-inline\'; font-src \'none\'">'
            '<link rel="stylesheet" href="orbea-fonts.css"><link rel="stylesheet" href="orbea-original.css">'
            '<style>body{background:white;font-family:neue-haas-grotesk-text,sans-serif;font-size:15px}dialog{position:fixed;top:48px;left:48px;width:960px;'
            'max-height:350px;overflow:hidden;background:white}#geometry-data{width:481px}</style></head>'
            '<body><dialog open id="qa-dialog">' + str(soup.select_one('#geometry-data')) + '</dialog></body></html>', encoding='utf-8')
        driver.get(path.as_uri())
        table = driver.find_element(By.CSS_SELECTOR, '#geometry-data table')
        data = driver.execute_script(GEOMETRY_TABLE_DATA_JS, table)
        assert len(data['rows']) == 14
        assert data['headers'] == ['Concept', 'S', 'M', 'L', 'XL']
        original_window = driver.get_window_size()
        original_html = driver.find_element(By.ID, 'geometry-data').get_attribute('outerHTML')
        # The native table uses black numbered badges, unlike the retired redraw.
        badges = table.find_elements(By.CSS_SELECTOR, 'tbody td span')
        assert len(badges) >= 14
        preview = OUT / f'{name}-original-style.png'
        dimensions = capture_styled_geometry(driver, table, preview, settings, data, screenshot=screenshot_element)
        restored = driver.find_element(By.ID, 'geometry-data').get_attribute('outerHTML')
        assert original_html.replace(' style=""', '') == restored.replace(' style=""', '')
        assert driver.get_window_size() == original_window
        assert driver.execute_script(GEOMETRY_TABLE_DATA_JS, table) == data
        assert driver.execute_script('return arguments[0].__ultraGeometryCapture || null', driver.find_element(By.ID, 'geometry-data')) is None
        results.append({'model': name, 'rows': len(data['rows']), 'dimensions': dimensions, 'restored': True, 'preview': str(preview)})
finally:
    driver.quit()
(OUT / 'other-models-verification.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
print(json.dumps(results))
