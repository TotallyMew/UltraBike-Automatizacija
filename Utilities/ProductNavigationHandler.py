import time
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from Config.Selectors import ProductListSelectors
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
        el = WebDriverWait(self.driver, 3).until(
            EC.element_to_be_clickable(ProductListSelectors.NAV_PRODUCTS)
        )
        self.driver.execute_script("arguments[0].scrollIntoView();", el)
        el.click()

    def _navigate_via_catalog_button(self):
        self._log("Navigating via catalog button")
        catalog = WebDriverWait(self.driver, 3).until(
            EC.element_to_be_clickable(ProductListSelectors.NAV_CATALOG)
        )
        self.driver.execute_script("arguments[0].scrollIntoView();", catalog)
        catalog.click()
        el = WebDriverWait(self.driver, 3).until(
            EC.element_to_be_clickable(ProductListSelectors.NAV_PRODUCTS)
        )
        self.driver.execute_script("arguments[0].scrollIntoView();", el)
        el.click()

    def _expand_menu_and_navigate(self):
        self._log("Expanding menu and navigating")
        hamburger = WebDriverWait(self.driver, 3).until(
            EC.element_to_be_clickable(ProductListSelectors.NAV_MENU_COLLAPSE)
        )
        self.driver.execute_script("arguments[0].scrollIntoView();", hamburger)
        hamburger.click()
        time.sleep(3)
        self._navigate_via_catalog_button()

    def navigate_to_product(self, brand_name, unique_code):
        self._log("Navigating to product", brand=brand_name, code=unique_code)

        if unique_code.startswith("UB-"):
            try:
                WebDriverWait(self.driver, 3).until(
                    EC.element_to_be_clickable(ProductListSelectors.SEARCH_NAME)
                )
            except TimeoutException:
                self._log("Product list not visible, fixing...")
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
        self._log("Searching product by External Id filter", code=unique_code)

        self.driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(0.5)

        # Open the filters panel
        toggle = WebDriverWait(self.driver, 5).until(
            EC.element_to_be_clickable(ProductListSelectors.TOGGLE_FILTERS)
        )
        toggle.click()
        time.sleep(0.3)

        # Add a new filter row (button is only present when no filters exist yet)
        try:
            add_btn = WebDriverWait(self.driver, 3).until(
                EC.element_to_be_clickable(ProductListSelectors.ADD_FILTER_BUTTON)
            )
            add_btn.click()
            time.sleep(0.3)
        except TimeoutException:
            # Filter row already present from a previous search
            pass

        # Type the code into the value input (field defaults to External Id = equals)
        value_input = WebDriverWait(self.driver, 5).until(
            EC.element_to_be_clickable(ProductListSelectors.FILTER_VALUE)
        )
        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", value_input)
        value_input.clear()
        value_input.send_keys(unique_code + Keys.ENTER)

    def _search_product_simple(self, unique_code):
        self._log("Searching product by name", code=unique_code)

        self.driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(0.5)

        search_input = WebDriverWait(self.driver, 5).until(
            EC.element_to_be_clickable(ProductListSelectors.SEARCH_NAME)
        )
        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", search_input)
        search_input.clear()
        search_input.send_keys(unique_code + Keys.ENTER)

    def set_retry_callback(self, callback):
        self._retry_callback = callback

    def _retry_search(self):
        if hasattr(self, '_retry_callback') and self._retry_callback:
            return self._retry_callback("paiešką")
        return ErrorManager.prompt_retry("paiešką")