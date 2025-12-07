from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from Utilities.WebIntercationHandler import WebInteractionHandler

class FeatureFieldWriter:
    def __init__(self, driver, logger=None):
        self.driver = driver
        self.logger = logger
        self.web_handler = WebInteractionHandler(driver)
    
    def _log(self, message, **context):
        if self.logger:
            self.logger.log("FeatureFieldWriter", message, **context)
    
    def _log_error(self, message, exception=None, **context):
        if self.logger:
            self.logger.error("FeatureFieldWriter", message, exception=exception, **context)

    def fillFields(self, tablesData, lang, first_language):
        self._log("Filling fields", lang=lang, first_language=first_language, tables=len(tablesData))
        
        index = 0 
        for table in tablesData:
            for key, value in table.items():
                if first_language:
                    featureKey = key
                    try:
                        addButton = WebDriverWait(self.driver, 10).until(
                            EC.element_to_be_clickable((By.ID, "add_feature_button"))
                        )
                        try:
                            self.driver.execute_script("arguments[0].click();", addButton)
                        except Exception:
                            self.driver.execute_script(
                                "arguments[0].scrollIntoView({ behavior: 'auto', block: 'center' });",
                                addButton
                            )
                            self.driver.execute_script("arguments[0].click();", addButton)
                    except Exception as e:
                        self._log_error("Failed to click add button", exception=e, index=index)
                        continue

                    try:
                        dropdown = self.driver.find_element(By.ID, f"select2-form_step1_features_{index}_feature-container")
                        try:
                            self.driver.execute_script(
                                "arguments[0].scrollIntoView({ behavior: 'auto', block: 'center' });",
                                dropdown
                            )
                            dropdown.click()
                        except Exception:
                            self.driver.execute_script(
                                "arguments[0].scrollIntoView({ behavior: 'auto', block: 'center' });",
                                dropdown
                            )
                            dropdown.click()

                        inputField = WebDriverWait(self.driver, 10).until(
                            EC.element_to_be_clickable((By.CLASS_NAME, "select2-search__field"))
                        )
                        inputField.send_keys(featureKey)

                        WebDriverWait(self.driver, 2).until(
                            EC.presence_of_element_located((By.CLASS_NAME, "select2-results__option"))
                        )

                        if self.web_handler.is_feature_found():
                            if featureKey == "Padangos - padangos plotis (mm / col.)":
                                featureKey = "Padangos - Padangos plotis (mm / col.)"

                            xpath = f"//li[normalize-space(text()) = '{featureKey}']"
                            option = WebDriverWait(self.driver, 1).until(
                                EC.presence_of_element_located((By.XPATH, xpath))
                            )
                            option.click()
                            self.fillFeatureValue(index, lang, value)
                            self._log("Feature added", key=featureKey, index=index)
                            index += 1

                    except TimeoutException:
                        self._log_error("Feature not found", feature=featureKey, index=index)
                        continue
                else:
                    self.fillFeatureValue(index, lang, value)
                    index += 1
        
        self._log("Field filling completed", lang=lang, features_filled=index)

    def fillFeatureValue(self, index, lang, value):
        fieldId = f"form_step1_features_{index}_custom_value_"
        fieldId += "2" if lang == "lt" else "1" if lang == "en" else "3"

        try:
            valueField = self.driver.find_element(By.ID, fieldId)
            valueField.send_keys(value + Keys.TAB)
        except Exception as e:
            self._log_error("Failed to fill value", exception=e, field_id=fieldId, value=value)