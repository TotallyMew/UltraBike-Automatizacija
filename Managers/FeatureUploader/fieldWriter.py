from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from generalUtilities import tikrintiArSavybeRasta

class FeatureFieldWriter:
    def __init__(self, driver):
        self.driver = driver

    def fillFields(self, tablesData, lang, first_language=False):
        index = 0 
        for table in tablesData:
            for key, value in table.items():
                if first_language:
                    featureKey = key.capitalize()

                    try:
                        addButton = WebDriverWait(self.driver, 10).until(
                            EC.element_to_be_clickable((By.ID, "add_feature_button"))
                        )
                        self.driver.execute_script("arguments[0].click();", addButton)
                    except Exception as e:
                        print(f"Error clicking add button: {e}")
                        continue

                    try:
                        dropdown = self.driver.find_element(By.ID, f"select2-form_step1_features_{index}_feature-container")
                        self.driver.execute_script("arguments[0].scrollIntoView();", dropdown)
                        dropdown.click()

                        inputField = WebDriverWait(self.driver, 10).until(
                            EC.element_to_be_clickable((By.CLASS_NAME, "select2-search__field"))
                        )
                        inputField.send_keys(featureKey)

                        WebDriverWait(self.driver, 2).until(
                            EC.presence_of_element_located((By.CLASS_NAME, "select2-results__option"))
                        )

                        if tikrintiArSavybeRasta(self.driver):
                            dropdown.click()
                            self.fillFeatureValue(index, lang, value)
                            index += 1
                            continue

                        if featureKey == "Padangos - padangos plotis (mm / col.)":
                            print("PAKEICIAU")
                            featureKey = "Padangos - Padangos plotis (mm / col.)"

                        xpath = f"//li[normalize-space(text()) = '{featureKey}']"
                        option = WebDriverWait(self.driver, 1).until(
                            EC.presence_of_element_located((By.XPATH, xpath))
                        )
                        option.click()

                    except TimeoutException:
                        print(f"Nerasta '{featureKey}'.")
                        continue

                self.fillFeatureValue(index, lang, value)
                index += 1

    def fillFeatureValue(self, index, lang, value):
        fieldId = f"form_step1_features_{index}_custom_value_"
        fieldId += "2" if lang == "lt" else "1" if lang == "en" else "3"

        try:
            valueField = self.driver.find_element(By.ID, fieldId)
            valueField.send_keys(value + Keys.TAB)
        except Exception as e:
            print(f"Failed to fill value for field {fieldId}: {e}")

