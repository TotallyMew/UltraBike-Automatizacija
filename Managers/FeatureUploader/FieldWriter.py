from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from Utilities.WebIntercationHandler import WebInteractionHandler

class FeatureFieldWriter:
    def __init__(self, driver, logger=None):
        self.driver = driver
        self.logger = logger
        self.web_handler = WebInteractionHandler(driver)
        self.skipped_features = []
    
    def _log(self, message, **context):
        if self.logger:
            self.logger.log("FeatureFieldWriter", message, **context)
    
    def _log_error(self, message, exception=None, **context):
        if self.logger:
            self.logger.error("FeatureFieldWriter", message, exception=exception, **context)

    def _remove_feature_row_best_effort(self, index: int) -> None:
        """Best-effort removal of an empty/failed feature row.

        PrestaShop's feature editor generates rows dynamically. If we click
        "add" and then fail to select a feature, leaving the row empty can
        break the save step or misalign subsequent language filling.
        """
        try:
            dropdown = self.driver.find_element(By.ID, f"select2-form_step1_features_{index}_feature-container")
        except Exception:
            return

        row_root = None
        try:
            row_root = dropdown.find_element(
                By.XPATH,
                f"./ancestor::*[contains(@id,'form_step1_features_{index}')][1]"
            )
        except Exception:
            row_root = None

        # Try to click a delete/remove control if present.
        candidates = []
        if row_root is not None:
            try:
                candidates.extend(row_root.find_elements(
                    By.XPATH,
                    ".//button[contains(@class,'delete') or contains(@class,'remove') or contains(@class,'btn-danger') or contains(@title,'Delete') or contains(@title,'Remove') or contains(@aria-label,'Delete') or contains(@aria-label,'Remove')]"
                ))
            except Exception:
                pass
            try:
                candidates.extend(row_root.find_elements(
                    By.XPATH,
                    ".//a[contains(@class,'delete') or contains(@class,'remove') or contains(@class,'btn-danger') or contains(@title,'Delete') or contains(@title,'Remove') or contains(@aria-label,'Delete') or contains(@aria-label,'Remove')]"
                ))
            except Exception:
                pass

        for el in candidates:
            try:
                if el.is_displayed() and el.is_enabled():
                    self.driver.execute_script("arguments[0].click();", el)
                    return
            except Exception:
                continue

        # Last resort: remove DOM element (may not fire framework events, but better than leaving empties)
        try:
            if row_root is not None:
                self.driver.execute_script("arguments[0].remove();", row_root)
        except Exception:
            pass


    def fillFields(self, tablesData, lang, first_language, keep_mask=None):
        self._log("Filling fields", lang=lang, first_language=first_language, tables=len(tablesData))
        
        index = 0
        keep = [] if first_language else None
        pos = 0
        for table in tablesData:
            for key, value in table.items():
                if not first_language and keep_mask is not None:
                    if pos < len(keep_mask) and not keep_mask[pos]:
                        pos += 1
                        continue
                    pos += 1

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
                        if keep is not None:
                            keep.append(False)
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
                            if keep is not None:
                                keep.append(True)
                        else:
                            # No results found -> remove empty row and skip
                            self._log_error("Feature not found (no results)", feature=featureKey, index=index)
                            try:
                                self.skipped_features.append({
                                    "key": str(featureKey),
                                    "reason": "not_found",
                                    "lang": str(lang),
                                })
                            except Exception:
                                pass
                            self._remove_feature_row_best_effort(index)
                            if keep is not None:
                                keep.append(False)
                            continue

                    except TimeoutException:
                        self._log_error("Feature not found", feature=featureKey, index=index)
                        try:
                            self.skipped_features.append({
                                "key": str(featureKey),
                                "reason": "timeout",
                                "lang": str(lang),
                            })
                        except Exception:
                            pass
                        self._remove_feature_row_best_effort(index)
                        if keep is not None:
                            keep.append(False)
                        continue
                    except Exception as e:
                        # Any unexpected selection failure should not crash the whole upload
                        self._log_error("Feature selection failed", exception=e, feature=featureKey, index=index)
                        try:
                            self.skipped_features.append({
                                "key": str(featureKey),
                                "reason": "error",
                                "lang": str(lang),
                            })
                        except Exception:
                            pass
                        self._remove_feature_row_best_effort(index)
                        if keep is not None:
                            keep.append(False)
                        continue
                else:
                    # Fill values only for rows that exist (aligned by keep_mask from LT pass)
                    if self.fillFeatureValue(index, lang, value):
                        index += 1
        
        self._log("Field filling completed", lang=lang, features_filled=index)
        return keep

    def fillFeatureValue(self, index, lang, value):
        fieldId = f"form_step1_features_{index}_custom_value_"
        fieldId += "2" if lang == "lt" else "1" if lang == "en" else "3"

        try:
            valueField = self.driver.find_element(By.ID, fieldId)
            valueField.send_keys(value + Keys.TAB)
            return True
        except Exception as e:
            self._log_error("Failed to fill value", exception=e, field_id=fieldId, value=value)
            return False