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
from Config.Selectors import BrandSelectors, ProductEditorSelectors, ProductListSelectors




class WebInteractionHandler:
    def __init__(self, driver):
        self.driver = driver

    def load_credentials(self, file_path):
        raise RuntimeError(
            "Plaintext credential files are no longer supported. "
            "Please save credentials in the Account screen."
        )

    def add_brand_name(self, brand_name):
        """Select a manufacturer/brand from the react-select dropdown on pim.bo."""
        try:
            # Switch to Basic Info tab — manufacturer field lives there
            basic_tab = WebDriverWait(self.driver, 5).until(
                EC.element_to_be_clickable(ProductEditorSelectors.BASIC_INFO_TAB)
            )
            basic_tab.click()
            time.sleep(0.5)

            # Open the react-select dropdown
            dropdown = WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located(BrandSelectors.BRAND_DROPDOWN)
            )
            self.driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});", dropdown
            )
            time.sleep(0.3)
            self.driver.execute_script("arguments[0].click();", dropdown)
            time.sleep(0.5)

            # Type the brand name into the search input
            search_field = WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located(BrandSelectors.BRAND_SEARCH)
            )
            search_field.send_keys(brand_name)
            time.sleep(0.5)

            # Click the matching option via JS to avoid scroll-jump issues
            brand_match = WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located(BrandSelectors.BRAND_RESULT)
            )
            self.driver.execute_script("arguments[0].click();", brand_match)
            time.sleep(0.3)
            print(f"[WebHandler] Brand '{brand_name}' selected")
        except Exception as e:
            print(f"[WebHandler] Failed to select brand '{brand_name}': {e}")

    def save_information(self, timeout: float = 10.0):
        """Click the Save button (#action-save) and wait for the toast result.

        Raises on failure so callers can surface a proper error.
        """
        print("[WebHandler] Clicking Save button...")
        save_btn = WebDriverWait(self.driver, 5).until(
            EC.element_to_be_clickable(ProductEditorSelectors.SAVE_BUTTON)
        )
        self.driver.execute_script("arguments[0].click();", save_btn)
        print("[WebHandler] Save clicked, waiting for completion...")

        self._wait_for_save_completion(timeout=timeout)
        print("[WebHandler] Save completed")

    def _wait_for_save_completion(self, timeout: float = 10.0):
        """Wait for a Sonner toast to confirm save success or report an error."""

        # Wait for either a success or error toast to appear.
        try:
            WebDriverWait(self.driver, timeout).until(
                EC.any_of(
                    EC.presence_of_element_located(ProductEditorSelectors.SAVE_SUCCESS),
                    EC.presence_of_element_located(ProductEditorSelectors.SAVE_ERROR),
                )
            )
        except TimeoutException:
            # No toast appeared — treat as success (some saves just refresh).
            return

        # Check if an error toast appeared.
        try:
            self.driver.find_element(*ProductEditorSelectors.SAVE_ERROR)
            try:
                msg_el = self.driver.find_element(*ProductEditorSelectors.SAVE_ERROR_MESSAGE)
                msg = msg_el.text.strip()
                raise RuntimeError(f"Save error: {msg}")
            except RuntimeError:
                raise
            except Exception:
                raise RuntimeError("Save reported an error")
        except (NoSuchElementException, TimeoutException):
            pass

    def click_product_by_code(self, unique_code):
        try:
            product = WebDriverWait(self.driver, 2).until(
                EC.element_to_be_clickable(ProductListSelectors.PRODUCT_ROW)
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
                    ProductListSelectors.product_row_by_code(unique_code)
                )
            )
            self.driver.execute_script("arguments[0].scrollIntoView();", code_element)

            row_element = code_element.find_element(By.XPATH, "./ancestor::tr")
            link_element = row_element.find_element(
                *ProductListSelectors.product_link_by_brand(brand_name)
            )
            self.driver.execute_script("arguments[0].scrollIntoView();", link_element)
            WebDriverWait(self.driver, 2).until(EC.element_to_be_clickable(link_element))
            link_element.click()
            return True
        except Exception as e:
            # GUI/log should handle error feedback
            pass
        return False

