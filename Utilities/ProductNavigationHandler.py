import time

from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

from Config.Selectors import ProductListSelectors
from Managers.PimboProductEditor import PimAutomationError, PimboProductEditor
from Utilities.ErrorManager import ErrorManager


class ProductNavigationHandler:
    """Open an exact product from the current PIMBO Products page."""

    def __init__(self, driver, logger=None):
        self.driver = driver
        self.logger = logger

    def _log(self, message, **context):
        if self.logger:
            self.logger.log("ProductNavigation", message, **context)

    def _log_error(self, message, exception=None, **context):
        if self.logger:
            self.logger.error("ProductNavigation", message, exception=exception, **context)

    def fix_invisible_products(self):
        self._log("Opening current PIMBO Products page")
        if "/dashboard/products/" in (self.driver.current_url or ""):
            if PimboProductEditor(self.driver, self.logger).is_dirty():
                raise PimAutomationError(
                    "The open PIMBO product has unsaved changes; save or discard them "
                    "before opening another product."
                )
        try:
            self._navigate_via_products_button()
        except TimeoutException:
            self.driver.get(ProductListSelectors.URL)
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located(ProductListSelectors.PRODUCT_TABLE)
            )

    def _navigate_via_products_button(self):
        try:
            element = WebDriverWait(self.driver, 3).until(
                EC.element_to_be_clickable(ProductListSelectors.NAV_PRODUCTS)
            )
            self.driver.execute_script("arguments[0].scrollIntoView();", element)
            element.click()
        except TimeoutException:
            self.driver.get(ProductListSelectors.URL)
        WebDriverWait(self.driver, 10).until(
            EC.presence_of_element_located(ProductListSelectors.PRODUCT_TABLE)
        )

    def navigate_to_product(self, brand_name, unique_code):
        """Return a ready editor only after validating the exact External ID."""

        unique_code = str(unique_code or "").strip()
        if not unique_code:
            raise ValueError("Product code is required")
        self._log("Navigating to product", brand=brand_name, code=unique_code)

        try:
            WebDriverWait(self.driver, 3).until(
                EC.element_to_be_clickable(ProductListSelectors.SEARCH_NAME)
            )
        except TimeoutException:
            self.fix_invisible_products()

        while True:
            try:
                self._search_product_simple(unique_code)
                self._open_exact_result(unique_code)

                editor = PimboProductEditor(self.driver, self.logger)
                editor.wait_ready()
                actual_code = editor.external_id()
                if actual_code.casefold() != unique_code.casefold():
                    raise LookupError(
                        f"Opened product code {actual_code!r}, expected {unique_code!r}"
                    )
                self._log(
                    "Exact product opened",
                    code=unique_code,
                    product_id=editor.product_id,
                )
                ErrorManager.show_success("Prekė rasta!")
                return editor
            except Exception as error:
                self._log_error(
                    "Product navigation failed",
                    exception=error,
                    code=unique_code,
                )
                ErrorManager.show_error("UPLOAD_PRODUCT_NOT_FOUND", code=unique_code)

            retry = self._retry_search()
            if retry is False:
                raise ValueError(f"Product search cancelled for code: {unique_code}")
            if isinstance(retry, str):
                unique_code = retry.strip()

    def _search_product_simple(self, unique_code):
        """Search and wait for the result set itself, not merely the table shell."""

        self._log("Searching product by dashboard search", code=unique_code)
        self.driver.execute_script("window.scrollTo(0, 0);")
        search_input = WebDriverWait(self.driver, 5).until(
            EC.element_to_be_clickable(ProductListSelectors.SEARCH_NAME)
        )
        previous_rows = tuple(
            row.text for row in self.driver.find_elements(*ProductListSelectors.PRODUCT_ROWS)
        )
        self.driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center'});",
            search_input,
        )
        search_input.click()
        search_input.send_keys(Keys.CONTROL, "a")
        search_input.send_keys(unique_code)
        search_input.send_keys(Keys.ENTER)

        def results_updated(driver):
            if (search_input.get_attribute("value") or "").strip() != unique_code:
                return False
            current_rows = tuple(
                row.text for row in driver.find_elements(*ProductListSelectors.PRODUCT_ROWS)
            )
            exact = driver.find_elements(*ProductListSelectors.product_row_by_code(unique_code))
            return bool(exact) or current_rows != previous_rows

        WebDriverWait(self.driver, 12).until(results_updated)
        # Give the row click handler one render frame after a debounced search.
        time.sleep(0.15)

    def _open_exact_result(self, unique_code):
        """Open the exact External ID row returned by the current product search."""

        row = WebDriverWait(self.driver, 5).until(
            EC.element_to_be_clickable(
                ProductListSelectors.product_row_by_code(unique_code)
            )
        )
        self.driver.execute_script(
            "arguments[0].scrollIntoView({block:'center'});",
            row,
        )
        try:
            row.click()
        except Exception:
            self.driver.execute_script("arguments[0].click();", row)

    def set_retry_callback(self, callback):
        self._retry_callback = callback

    def _retry_search(self):
        if getattr(self, "_retry_callback", None):
            return self._retry_callback("paiešką")
        return ErrorManager.prompt_retry("paiešką")
