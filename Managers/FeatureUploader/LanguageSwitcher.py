from selenium.webdriver.support.ui import Select
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import time

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

        # Wait for language-specific element to appear
        from Config.LanguageConfig import LANG_CODE_TO_PRESTASHOP_ID
        lang_id = LANG_CODE_TO_PRESTASHOP_ID.get(langCode, "1")

        try:
            # Wait for the title field for this language to be present
            WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located((By.ID, f"form_step1_name_{lang_id}"))
            )

            # Additional check: wait for any loading overlays to disappear
            WebDriverWait(self.driver, 3).until_not(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".loading, .spinner, .overlay"))
            )
        except TimeoutException:
            # Fallback: short sleep if dynamic wait fails
            time.sleep(0.5)

        self._log("Language switched successfully", lang=langCode)