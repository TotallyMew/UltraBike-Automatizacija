from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from Config.Selectors import FeatureSelectors


class FeatureFieldWriter:
    def __init__(self, driver, logger=None):
        self.driver = driver
        self.logger = logger
        self.skipped_features = []

    def _log(self, message, **context):
        if self.logger:
            self.logger.log("FeatureFieldWriter", message, **context)

    def _log_error(self, message, exception=None, **context):
        if self.logger:
            self.logger.error("FeatureFieldWriter", message, exception=exception, **context)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fillFields(self, tablesData, lang, first_language, keep_mask=None):
        """Fill specification values on the pim.bo product editor.

        first_language (LT): applies the template and fills all values.
        subsequent languages (EN): fills translated values into the same
        spec rows (the product must be saved first so values carry over).

        Returns None — keep_mask is not used in pim.bo.
        """
        print(f"[FieldWriter] fillFields called (lang={lang}, first_language={first_language}, tables={len(tablesData)})")
        self._log("Filling specifications", lang=lang, first_language=first_language, tables=len(tablesData))
        self.skipped_features = []

        if first_language:
            print("[FieldWriter] Applying template...")
            self._ensure_template_applied()
            print("[FieldWriter] Template applied")

        filled = 0
        for table in tablesData:
            for spec_name, value in table.items():
                if not value:
                    continue
                print(f"[FieldWriter] Filling spec: {spec_name} = {value[:50] if len(str(value)) > 50 else value}")
                if self._fill_spec(spec_name, str(value)):
                    filled += 1
                else:
                    print(f"[FieldWriter] FAILED to fill: {spec_name}")

        print(f"[FieldWriter] Done (lang={lang}, filled={filled}, skipped={len(self.skipped_features)})")
        self._log("Specifications filled", lang=lang, filled=filled, skipped=len(self.skipped_features))
        return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_template_applied(self):
        """Apply the Dviračiai template if spec rows are not yet present."""
        try:
            WebDriverWait(self.driver, 3).until(
                EC.presence_of_element_located(FeatureSelectors.FIRST_SPEC_VALUE)
            )
            print("[FieldWriter] Template already applied, skipping")
            self._log("Template already applied, skipping")
            return
        except TimeoutException:
            pass

        print("[FieldWriter] Applying Dviračiai template...")
        self._log("Applying Dviračiai template")
        self._click_specs_tab()
        print("[FieldWriter] Specs tab clicked")
        self._select_template("Dviračiai")
        print("[FieldWriter] Template selected")
        self._click_apply_template()
        print("[FieldWriter] Apply button clicked, waiting for spec rows...")

        # Wait for first spec row to appear
        try:
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located(FeatureSelectors.FIRST_SPEC_VALUE)
            )
            print("[FieldWriter] Spec rows appeared")
        except TimeoutException:
            print("[FieldWriter] ERROR: Spec rows did NOT appear after applying template")
            self._log_error("Spec rows did not appear after applying template")

    def _click_specs_tab(self):
        try:
            tab = WebDriverWait(self.driver, 5).until(
                EC.element_to_be_clickable(FeatureSelectors.SPECS_TAB)
            )
            self.driver.execute_script("arguments[0].click();", tab)
            self._log("Specs tab clicked")
        except TimeoutException:
            self._log_error("Specs tab not found — continuing anyway")

    def _select_template(self, template_name: str):
        try:
            el = WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located(FeatureSelectors.TEMPLATE_SELECT)
            )
            Select(el).select_by_visible_text(template_name)
            self._log("Template selected", template=template_name)
        except TimeoutException as e:
            self._log_error("Failed to select template", exception=e, template=template_name)

    def _click_apply_template(self):
        try:
            btn = WebDriverWait(self.driver, 5).until(
                EC.element_to_be_clickable(FeatureSelectors.APPLY_TEMPLATE_BUTTON)
            )
            self.driver.execute_script("arguments[0].click();", btn)
            self._log("Apply Template button clicked")
        except TimeoutException as e:
            self._log_error("Apply Template button not found", exception=e)

    def _fill_spec(self, spec_name: str, value: str) -> bool:
        locator = FeatureSelectors.spec_value_by_name(spec_name)
        try:
            field = WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located(locator)
            )
            self.driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});", field
            )
            field.clear()
            field.send_keys(value)
            self._log("Spec filled", name=spec_name, value=value)
            return True
        except TimeoutException:
            self._log_error("Spec row not found", feature=spec_name)
            self.skipped_features.append({"key": spec_name, "reason": "not_found"})
            return False
        except Exception as e:
            self._log_error("Failed to fill spec", exception=e, feature=spec_name)
            self.skipped_features.append({"key": spec_name, "reason": "error"})
            return False
