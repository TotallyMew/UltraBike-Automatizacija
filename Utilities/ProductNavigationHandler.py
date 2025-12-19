import time
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from Utilities.WebIntercationHandler import WebInteractionHandler
from Utilities.ErrorManager import ErrorManager

class ProductNavigationHandler:
    def __init__(self, driver, logger=None):
        self.driver = driver
        self.logger = logger
        self.web_interaction = WebInteractionHandler(driver)
    
    def _log(self, message, **context):
        if self.logger:
            self.logger.log("ProductNavigation", message, **context)
    
    def _log_error(self, message, exception=None, **context):
        if self.logger:
            self.logger.error("ProductNavigation", message, exception=exception, **context)

    def fix_invisible_products(self):
        self._log("Attempting to fix invisible products")
        prekesKodoElementID = "filter_column_name_category"

        try:
            prekesElement = WebDriverWait(self.driver, 3).until(
                EC.element_to_be_clickable((By.NAME, prekesKodoElementID))
            )
            self.driver.execute_script("arguments[0].scrollIntoView();", prekesElement)
            prekesElement.click()
            self._log("Products filter clicked successfully")
        except TimeoutException:
            self._log("Products button not found, trying alternative methods")
            try:
                self._navigate_via_products_button()
            except TimeoutException:
                try:
                    self._navigate_via_catalog_button()
                except TimeoutException:
                    try:
                        self._expand_menu_and_navigate()
                    except TimeoutException:
                        self._log_error("All navigation methods failed")
                        ErrorManager.show_error("BROWSER_ELEMENT_NOT_FOUND")
                        return
        
        self._log("Products visibility fixed")

    def _navigate_via_products_button(self):
        self._log("Navigating via products button")
        prekesMygtukasElement = WebDriverWait(self.driver, 3).until(
            EC.element_to_be_clickable((By.ID, "subtab-AdminProducts"))
        )
        self.driver.execute_script("arguments[0].scrollIntoView();", prekesMygtukasElement)
        prekesMygtukasElement.click()

    def _navigate_via_catalog_button(self):
        self._log("Navigating via catalog button")
        katalogasMygtukasElement = WebDriverWait(self.driver, 3).until(
            EC.element_to_be_clickable((By.ID, "subtab-AdminCatalog"))
        )
        self.driver.execute_script("arguments[0].scrollIntoView();", katalogasMygtukasElement)
        katalogasMygtukasElement.click()
        prekesMygtukasElement = WebDriverWait(self.driver, 3).until(
            EC.element_to_be_clickable((By.ID, "subtab-AdminProducts"))
        )
        self.driver.execute_script("arguments[0].scrollIntoView();", prekesMygtukasElement)
        prekesMygtukasElement.click()

    def _expand_menu_and_navigate(self):
        self._log("Expanding menu and navigating")
        sutraukimoIsskleidimoMygtukasElement = WebDriverWait(self.driver, 3).until(
            EC.element_to_be_clickable((By.CLASS_NAME, "menu-collapse"))
        )
        self.driver.execute_script("arguments[0].scrollIntoView();", sutraukimoIsskleidimoMygtukasElement)
        sutraukimoIsskleidimoMygtukasElement.click()
        time.sleep(3)
        self._navigate_via_catalog_button()

    def navigate_to_product(self, brand_name, unique_code):
        self._log("Navigating to product", brand=brand_name, code=unique_code)
        
        if unique_code.startswith("UB-"):
            try:
                WebDriverWait(self.driver, 3).until(
                    EC.element_to_be_clickable((By.NAME, "filter_column_name_category"))
                )
            except TimeoutException:
                self._log("Filter not visible, fixing...")
                self.fix_invisible_products()

            while True:
                try:
                    self._search_product(unique_code)
                    if self.web_interaction.click_product_by_link(unique_code, brand_name):
                        self._log("Product found and clicked", code=unique_code)
                        ErrorManager.show_success("Prekė rasta!")
                        break
                    else:
                        self._log_error("Product not found", code=unique_code)
                        ErrorManager.show_error("UPLOAD_PRODUCT_NOT_FOUND", code=unique_code)
                except Exception as e:
                    self._log_error("Error during product navigation", exception=e, code=unique_code)
                    ErrorManager.show_error("UPLOAD_PRODUCT_NOT_FOUND", code=unique_code)

                res = self._retry_search()
                if res is False:
                    raise ValueError(f"Product search cancelled for code: {unique_code}")
                elif isinstance(res, str):
                    # User provided a new code to retry with
                    unique_code = res
                    continue
                else:
                    # True -> retry with same code
                    continue
        else:
            while True:
                try:
                    self._search_product_simple(unique_code)
                    if self.web_interaction.click_product_by_code(unique_code):
                        self._log("Product found and clicked (simple search)", code=unique_code)
                        ErrorManager.show_success("Prekė rasta!")
                        break
                    else:
                        self._log_error("Product not found (simple search)", code=unique_code)
                        ErrorManager.show_error("UPLOAD_PRODUCT_NOT_FOUND", code=unique_code)
                except Exception as e:
                    self._log_error("Error during simple search", exception=e, code=unique_code)
                    ErrorManager.show_error("UPLOAD_PRODUCT_NOT_FOUND", code=unique_code)

                res = self._retry_search()
                if res is False:
                    raise ValueError(f"Product search cancelled for code: {unique_code}")
                elif isinstance(res, str):
                    unique_code = res
                    continue
                else:
                    continue

    def _search_product(self, unique_code):
        self._log("Searching product (UB code)", code=unique_code)
        
        # Scroll to top to ensure all elements are visible
        self.driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(0.5)
        
        search_name = self.driver.find_element(By.NAME, "filter_column_name")
        search_name.clear()
        search_category = self.driver.find_element(By.NAME, "filter_column_name_category")
        search_category.clear()
        search_product = self.driver.find_element(By.NAME, "filter_column_reference")
        search_product.clear()
        
        # Scroll search field into view before entering code
        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", search_product)
        time.sleep(0.3)
        
        search_product.send_keys(unique_code + Keys.ENTER)

    def _search_product_simple(self, unique_code):
        self._log("Searching product (SKU)", code=unique_code)
        
        # Scroll to top
        self.driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(0.5)
        
        search_product = self.driver.find_element(By.ID, "bo_query")
        search_product.clear()
        
        # Scroll search field into view
        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", search_product)
        time.sleep(0.3)
        
        search_product.send_keys(unique_code + Keys.ENTER)

    def set_retry_callback(self, callback):
        self._retry_callback = callback

    def _retry_search(self):
        if hasattr(self, '_retry_callback') and self._retry_callback:
            return self._retry_callback("paiešką")
        return ErrorManager.prompt_retry("paiešką")