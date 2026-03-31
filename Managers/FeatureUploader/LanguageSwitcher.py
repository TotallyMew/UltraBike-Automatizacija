from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import time
from Config.Selectors import ProductEditorSelectors

class LanguageSwitcher:
    def __init__(self, driver, logger=None):
        self.driver = driver
        self.logger = logger

    def _log(self, message, **context):
        if self.logger:
            self.logger.log("LanguageSwitcher", message, **context)

    def switchTo(self, langCode):
        print(f"[LanguageSwitcher] Switching to {langCode}...")
        self._log("Switching language", lang=langCode)

        # Open the locale popup
        print(f"[LanguageSwitcher] Waiting for language switch button...")
        trigger = WebDriverWait(self.driver, 10).until(
            EC.element_to_be_clickable(ProductEditorSelectors.LANGUAGE_SWITCH)
        )
        self.driver.execute_script("arguments[0].click();", trigger)
        print(f"[LanguageSwitcher] Locale popup opened, selecting {langCode}...")

        # Click the option for the requested locale
        option = WebDriverWait(self.driver, 5).until(
            EC.element_to_be_clickable(ProductEditorSelectors.language_option(langCode))
        )
        option.click()
        print(f"[LanguageSwitcher] Option clicked, waiting for page to load...")

        # Wait for the name field to be ready (same element for all locales)
        try:
            WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located(ProductEditorSelectors.NAME_FIELD)
            )
            WebDriverWait(self.driver, 3).until_not(
                EC.presence_of_element_located(ProductEditorSelectors.LOADING_OVERLAY)
            )
        except TimeoutException:
            print(f"[LanguageSwitcher] Timeout waiting for page load, continuing after 0.5s")
            time.sleep(0.5)

        print(f"[LanguageSwitcher] Switched to {langCode} successfully")
        self._log("Language switched successfully", lang=langCode)