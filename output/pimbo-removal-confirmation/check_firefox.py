"""Reproduce and verify Firefox native confirmations on an offline test page."""
from pathlib import Path
import json
import sys

from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoAlertPresentException, UnexpectedAlertPresentException

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from Managers.PimboProductEditor import PimboProductEditor

OUT = Path(__file__).parent
page = OUT / 'dashboard/products/p1/index.html'
page.parent.mkdir(parents=True, exist_ok=True)
page.write_text('''<!doctype html><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'">
<div class="geometry-card"><span>Existing geometry</span>
<button aria-label="Remove geometry image" onclick="if(confirm('Remove this geometry image from the product?'))this.closest('.geometry-card').remove()">Remove geometry image</button></div>''', encoding='utf-8')
options = Options()
options.add_argument('-headless')
# Keep Firefox's default unhandledPromptBehavior: this is the reported failure.
driver = webdriver.Firefox(service=Service('C:/Users/User/.wdm/drivers/geckodriver/win64/v0.37.1/geckodriver.exe'), options=options)
try:
    driver.get(page.as_uri())
    driver.execute_script('arguments[0].click();', driver.find_element(By.CSS_SELECTOR, 'button'))
    try:
        _ = driver.current_url
        raise AssertionError('The old ordering did not reproduce the pending-confirm failure')
    except UnexpectedAlertPresentException as error:
        reproduced = error.alert_text
    try:
        driver.switch_to.alert
        raise AssertionError('Expected Firefox to dismiss the unhandled confirm')
    except NoAlertPresentException:
        pass
    assert len(driver.find_elements(By.CSS_SELECTOR, '.geometry-card')) == 1

    class Editor(PimboProductEditor):
        def _geometry_image_cards(self):
            return [{'src': 'existing.png', 'button': card.find_element(By.CSS_SELECTOR, 'button')}
                    for card in self.driver.find_elements(By.CSS_SELECTOR, '.geometry-card')]

    editor = Editor(driver, timeout=3)
    editor._bound_product_id = 'p1'
    editor._remove_table_image(editor._geometry_image_cards()[0], 1, 'geometry')
    assert not driver.find_elements(By.CSS_SELECTOR, '.geometry-card')
    assert editor._geometry_upload_changed
    print(json.dumps({'browser': driver.capabilities['browserName'],
                      'prompt_behavior': driver.capabilities.get('unhandledPromptBehavior'),
                      'old_failure_reproduced': reproduced, 'fixed_removal_verified': True}))
finally:
    driver.quit()
