from selenium.webdriver.support.ui import Select
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

class LanguageSwitcher:
    def __init__(self, driver, logger=None):
        self.driver = driver
        self.logger = logger
    
    def _log(self, message, **context):
        if self.logger:
            self.logger.log("LanguageSwitcher", message, **context)

    def switchTo(self, langCode):
        self._log("Switching language", lang=langCode)
        
        dropdown = WebDriverWait(self.driver, 10).until(
            EC.element_to_be_clickable((By.ID, "form_switch_language"))
        )
        self.driver.execute_script("arguments[0].click();", dropdown)

        Select(dropdown).select_by_value(langCode)
        self._log("Language switched successfully", lang=langCode)