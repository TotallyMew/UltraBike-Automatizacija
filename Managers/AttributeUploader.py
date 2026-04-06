"""Managers/AttributeUploader.py

Automates filling product-level attributes on the pim.bo Attributes tab.

Supports:
  - Applying the attribute template ("Dviračiai").
  - Setting Value Text for attributes by name.
  - Selecting Value Options from react-select dropdowns.
  - Clearing Value Text for specific attributes (e.g. Modelis).
"""

from __future__ import annotations

import time

from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

from Config.Selectors import AttributeSelectors


class AttributeUploader:
    """Fills product-level attributes on the pim.bo admin."""

    def __init__(self, driver, logger=None):
        self.driver = driver
        self.logger = logger
        self.skipped: list[dict] = []

    # -- logging -------------------------------------------------------------

    def _log(self, message: str, **ctx):
        if self.logger:
            self.logger.log("AttributeUploader", message, **ctx)

    def _log_error(self, message: str, exception=None, **ctx):
        if self.logger:
            self.logger.error("AttributeUploader", message, exception=exception, **ctx)

    # -- public API ----------------------------------------------------------

    def upload_attributes(
        self,
        attribute_values: list[dict] | None = None,
        clear_value_text: list[str] | None = None,
    ) -> list[dict]:
        """Fill attributes on the current product page.

        Args:
            attribute_values: List of dicts, each with:
                - name: str          — attribute display name (e.g. "Spalva")
                - value: str         — value to set
                - field: str         — "text", "options", "number", "measurement"
                                       (default "text")
            clear_value_text: List of attribute names whose Value Text field
                should be cleared (e.g. ["Modelis", "Modelis (vidinis)"]).

        Returns:
            List of skipped attribute dicts with "key" and "reason".
        """
        self.skipped = []

        if not attribute_values and not clear_value_text:
            return self.skipped

        print("[AttributeUploader] Starting attribute upload")
        self._log("Starting attribute upload",
                  values=len(attribute_values or []),
                  clears=len(clear_value_text or []))

        # 1. Click the Attributes tab
        self._click_attributes_tab()

        # 2. Apply template if no attribute rows exist yet
        self._ensure_template_applied()

        # 3. Fill attribute values
        if attribute_values:
            for attr in attribute_values:
                name = attr.get("name", "")
                value = attr.get("value", "")
                field = attr.get("field", "text")
                if not name or not value:
                    continue
                self._fill_attribute(name, value, field)

        # 4. Clear specified attribute Value Text fields
        if clear_value_text:
            for attr_name in clear_value_text:
                self._clear_value_text(attr_name)

        print(f"[AttributeUploader] Done (skipped={len(self.skipped)})")
        self._log("Attribute upload complete", skipped=len(self.skipped))
        return self.skipped

    # -- navigation ----------------------------------------------------------

    def _click_attributes_tab(self):
        try:
            tab = WebDriverWait(self.driver, 5).until(
                EC.element_to_be_clickable(AttributeSelectors.ATTRIBUTES_TAB)
            )
            self.driver.execute_script("arguments[0].click();", tab)
            time.sleep(0.5)
            self._log("Attributes tab clicked")
        except TimeoutException:
            self._log_error("Attributes tab not found")

    # -- template ------------------------------------------------------------

    def _ensure_template_applied(self):
        """Apply the Dviračiai attribute template if rows don't exist yet."""
        try:
            WebDriverWait(self.driver, 3).until(
                EC.presence_of_element_located(AttributeSelectors.FIRST_ATTRIBUTE_ROW)
            )
            self._log("Attribute rows already present, skipping template")
            return
        except TimeoutException:
            pass

        self._log("Applying Dviračiai attribute template")
        try:
            el = WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located(AttributeSelectors.TEMPLATE_SELECT)
            )
            Select(el).select_by_visible_text("Dviračiai")
        except TimeoutException:
            self._log_error("Attribute template select not found")
            return

        try:
            btn = WebDriverWait(self.driver, 5).until(
                EC.element_to_be_clickable(AttributeSelectors.APPLY_TEMPLATE_BUTTON)
            )
            self.driver.execute_script("arguments[0].click();", btn)
        except TimeoutException:
            self._log_error("Apply Template button not found")
            return

        # Wait for first row to appear
        try:
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located(AttributeSelectors.FIRST_ATTRIBUTE_ROW)
            )
            self._log("Attribute template applied")
        except TimeoutException:
            self._log_error("Attribute rows did not appear after applying template")

    # -- filling values ------------------------------------------------------

    def _fill_attribute(self, name: str, value: str, field: str):
        """Fill a single attribute's value by name."""
        print(f"[AttributeUploader] Filling {name} ({field}) = {value[:50]}")
        self._log("Filling attribute", name=name, field=field, value=value[:80])

        if field == "text":
            self._fill_value_text(name, value)
        elif field == "options":
            self._select_value_option(name, value)
        elif field == "number":
            self._fill_value_number(name, value)
        elif field == "measurement":
            # value format: "123|kg"
            parts = value.split("|", 1)
            num = parts[0].strip()
            unit = parts[1].strip() if len(parts) > 1 else ""
            self._fill_measurement(name, num, unit)
        else:
            self._log_error("Unknown field type", name=name, field=field)
            self.skipped.append({"key": name, "reason": f"unknown_field_{field}"})

    def _fill_value_text(self, name: str, value: str):
        locator = AttributeSelectors.value_text_by_name(name)
        try:
            field = WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located(locator)
            )
            self.driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});", field
            )
            field.clear()
            field.send_keys(value)
            self._log("Value Text filled", name=name)
        except TimeoutException:
            self._log_error("Value Text field not found", name=name)
            self.skipped.append({"key": name, "reason": "not_found"})
        except Exception as e:
            self._log_error("Failed to fill Value Text", exception=e, name=name)
            self.skipped.append({"key": name, "reason": "error"})

    def _select_value_option(self, name: str, value: str):
        """Type into the Value Options react-select and pick the matching option."""
        locator = AttributeSelectors.value_options_input_by_name(name)
        try:
            inp = WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located(locator)
            )
            self.driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});", inp
            )
            inp.click()
            time.sleep(0.3)
            inp.send_keys(value)
            time.sleep(1)

            # Pick the first matching option
            from selenium.webdriver.common.by import By
            options = self.driver.find_elements(By.CSS_SELECTOR, ".rs__option")
            for opt in options:
                if value.lower() in opt.text.strip().lower():
                    opt.click()
                    self._log("Value Option selected", name=name, value=value)
                    return

            # No match — press Escape to close dropdown
            inp.send_keys(Keys.ESCAPE)
            self._log_error("No matching option found", name=name, value=value)
            self.skipped.append({"key": name, "reason": "option_not_found"})
        except TimeoutException:
            self._log_error("Value Options input not found", name=name)
            self.skipped.append({"key": name, "reason": "not_found"})
        except Exception as e:
            self._log_error("Failed to select Value Option", exception=e, name=name)
            self.skipped.append({"key": name, "reason": "error"})

    def _fill_value_number(self, name: str, value: str):
        locator = AttributeSelectors.value_number_by_name(name)
        try:
            field = WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located(locator)
            )
            self.driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});", field
            )
            field.clear()
            field.send_keys(value)
            self._log("Value Number filled", name=name)
        except TimeoutException:
            self._log_error("Value Number field not found", name=name)
            self.skipped.append({"key": name, "reason": "not_found"})

    def _fill_measurement(self, name: str, num: str, unit: str):
        try:
            num_field = WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located(
                    AttributeSelectors.measurement_value_by_name(name)
                )
            )
            self.driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});", num_field
            )
            num_field.clear()
            num_field.send_keys(num)

            if unit:
                unit_field = self.driver.find_element(
                    *AttributeSelectors.measurement_unit_by_name(name)
                )
                unit_field.clear()
                unit_field.send_keys(unit)

            self._log("Measurement filled", name=name, value=num, unit=unit)
        except TimeoutException:
            self._log_error("Measurement fields not found", name=name)
            self.skipped.append({"key": name, "reason": "not_found"})

    # -- clearing fields -----------------------------------------------------

    def _clear_value_text(self, name: str):
        """Clear the Value Text field for a specific attribute."""
        print(f"[AttributeUploader] Clearing Value Text for: {name}")
        locator = AttributeSelectors.value_text_by_name(name)
        try:
            field = WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located(locator)
            )
            self.driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});", field
            )
            field.clear()
            # Some fields need explicit select-all + delete
            field.send_keys(Keys.CONTROL, "a")
            field.send_keys(Keys.DELETE)
            self._log("Value Text cleared", name=name)
        except TimeoutException:
            self._log_error("Could not find Value Text to clear", name=name)
            self.skipped.append({"key": name, "reason": "clear_not_found"})
        except Exception as e:
            self._log_error("Failed to clear Value Text", exception=e, name=name)
            self.skipped.append({"key": name, "reason": "clear_error"})
