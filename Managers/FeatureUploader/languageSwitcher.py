from selenium.webdriver.support.ui import Select
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

class LanguageSwitcher:
    def __init__(self, driver):
        self.driver = driver

    def switchTo(self, langCode):
        dropdown = WebDriverWait(self.driver, 10).until(
            EC.element_to_be_clickable((By.ID, "form_switch_language"))
        )
        self.driver.execute_script("arguments[0].click();", dropdown)

        Select(dropdown).select_by_value(langCode)
