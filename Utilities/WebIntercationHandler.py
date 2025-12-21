import time

from selenium.common.exceptions import (
    ElementClickInterceptedException,
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait




class WebInteractionHandler:
    def __init__(self, driver):
        self.driver = driver

    def load_credentials(self, file_path):
        raise RuntimeError(
            "Plaintext credential files are no longer supported. "
            "Please save credentials in the Account screen."
        )

    def add_brand_name(self, brand_name):
        try:
            add_brand = WebDriverWait(self.driver, 2).until(
                EC.element_to_be_clickable((By.ID, "add_brand_button"))
            )
            self.driver.execute_script("arguments[0].scrollIntoView();", add_brand)
            add_brand.click()

            select_brand = self.driver.find_element(By.ID, "select2-form_step1_id_manufacturer-container")
            self.driver.execute_script("arguments[0].scrollIntoView();", select_brand)
            select_brand.click()

            search_field = self.driver.find_element(By.CLASS_NAME, "select2-search__field")
            self.driver.execute_script("arguments[0].scrollIntoView();", search_field)
            search_field.send_keys(brand_name)

            brand_match = WebDriverWait(self.driver, 2).until(
                EC.presence_of_element_located((By.CLASS_NAME, "select2-results__option"))
            )
            self.driver.execute_script("arguments[0].scrollIntoView();", brand_match)
            brand_match.click()
            # GUI/log should handle success feedback
        except:
            # GUI/log should handle already-added feedback
            pass

    def save_information(self, timeout: float = 3.0):
        """Trigger PrestaShop save via ALT+SHIFT+S, then wait for completion.

        Raises on failure so callers can surface a proper error.
        """

        from selenium.webdriver.common.keys import Keys

        # Focus the body or a known input to ensure shortcut works
        try:
            self.driver.switch_to.active_element.send_keys(Keys.NULL)
        except Exception:
            pass

        # Send ALT+SHIFT+S
        actions = None
        try:
            from selenium.webdriver.common.action_chains import ActionChains
            actions = ActionChains(self.driver)
            actions.key_down(Keys.ALT)
            actions.key_down(Keys.SHIFT)
            actions.send_keys('s')
            actions.key_up(Keys.SHIFT)
            actions.key_up(Keys.ALT)
            actions.perform()
        except Exception as e:
            raise RuntimeError("Failed to send ALT+SHIFT+S") from e

        self._wait_for_save_completion(timeout=timeout)

    def _wait_for_save_completion(self, timeout: float = 3.0):
        """Best-effort wait for save to finish.

        PrestaShop UI varies; we mainly wait for the form submit to settle.
        """

        # If an error alert or growl error appears immediately, fail fast.
        try:
            WebDriverWait(self.driver, 1).until(
                EC.presence_of_element_located(
                    (
                        By.CSS_SELECTOR,
                        ".alert.alert-danger, .alert-danger, .notification.notification-danger, .growl.growl-error",
                    )
                )
            )
            # If it's a growl error, extract the message for better reporting
            try:
                growl = self.driver.find_element(By.CSS_SELECTOR, ".growl.growl-error .growl-message")
                msg = growl.text.strip()
                raise RuntimeError(f"PrestaShop growl error: {msg}")
            except Exception:
                raise RuntimeError("PrestaShop reported a save error")
        except TimeoutException:
            pass

        # Wait until the save button is clickable again OR a notification appears.
        try:
            WebDriverWait(self.driver, timeout).until(
                EC.any_of(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "button.js-btn-save")),
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "input.btn.btn-primary.save.uppercase.ml-3")),
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".alert-success, .notification-success, .growl, .ps-alert-success, .alert.alert-success")),
                )
            )
        except (TimeoutException, StaleElementReferenceException):
            # Some saves trigger a soft refresh/navigation; treat as success.
            pass

    def click_product_by_code(self, unique_code):
        try:
            product = WebDriverWait(self.driver, 2).until(
                EC.element_to_be_clickable((By.CLASS_NAME, "odd"))
            )
            self.driver.execute_script("arguments[0].scrollIntoView();", product)
            product.click()
            return True
        except NoSuchElementException:
            # GUI/log should handle not found feedback
            pass
        except ElementClickInterceptedException:
            # GUI/log should handle click error feedback
            pass
        except Exception as e:
            # GUI/log should handle unexpected error feedback
            pass
        return False

    def click_product_by_link(self, unique_code, brand_name):
        if brand_name.lower() == "krosstxt":
            brand_name = "KROSS"
        try:
            code_element = WebDriverWait(self.driver, 2).until(
                EC.presence_of_element_located(
                    (By.XPATH, f"//td[normalize-space()='{unique_code}']")
                )
            )
            self.driver.execute_script("arguments[0].scrollIntoView();", code_element)

            row_element = code_element.find_element(By.XPATH, "./ancestor::tr")
            link_element = row_element.find_element(
                By.XPATH,
                f".//a[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{brand_name.lower()}')]"
            )
            self.driver.execute_script("arguments[0].scrollIntoView();", link_element)
            WebDriverWait(self.driver, 2).until(EC.element_to_be_clickable(link_element))
            link_element.click()
            return True
        except Exception as e:
            # GUI/log should handle error feedback
            pass
        return False

    def is_feature_found(self):
        """Returns True if feature options are available, False if 'No results found'"""
        try:
            self.driver.find_element(By.XPATH, "//*[contains(text(), 'No results found')]")
            return False  # "No results found" exists = feature NOT found
        except NoSuchElementException:
            return True  # No "No results found" message = feature IS found
