"""Current OmnioPIM product editor automation.

This module is the single write-capable boundary used by the desktop app.  It
intentionally has no save operation: all changes remain in the browser until a
person reviews the product and clicks Save in PIMBO.
"""

from __future__ import annotations

import html
import re
import time
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Callable, Iterable, Mapping

from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select


PIMBO_PRODUCTS_URL = "https://pim.bo.ultrabike.lt/dashboard/products"
PIMBO_LOGIN_URL = "https://pim.bo.ultrabike.lt/dashboard/login"


class PimPreparationStatus(str, Enum):
    READY_FOR_REVIEW = "ready_for_review"
    SAVED_MANUALLY = "saved_manually"
    BLOCKED_NON_DRAFT = "blocked_non_draft"
    DISCARDED = "discarded"
    FAILED = "failed"


@dataclass(frozen=True)
class PimAiStepResult:
    step: str
    success: bool
    changed: bool = False
    attempts: int = 1
    detail: str = ""


@dataclass(frozen=True)
class PimPreparationResult:
    product_code: str
    product_id: str = ""
    initial_version: int | None = None
    initial_fields: dict[str, Any] = field(default_factory=dict)
    status: PimPreparationStatus = PimPreparationStatus.FAILED
    changed_fields: tuple[str, ...] = ()
    ai_steps: tuple[PimAiStepResult, ...] = ()
    warnings: tuple[str, ...] = ()
    final_url: str = ""
    failed_stage: str = ""
    error: str = ""

    @property
    def ready_for_review(self) -> bool:
        return self.status == PimPreparationStatus.READY_FOR_REVIEW

    def with_status(
        self,
        status: PimPreparationStatus,
        *,
        error: str | None = None,
    ) -> "PimPreparationResult":
        return replace(self, status=status, error=self.error if error is None else error)

    def to_dict(self) -> dict[str, Any]:
        return {
            "product_code": self.product_code,
            "product_id": self.product_id,
            "initial_version": self.initial_version,
            "initial_fields": dict(self.initial_fields),
            "status": self.status.value,
            "changed_fields": list(self.changed_fields),
            "ai_steps": [
                {
                    "step": item.step,
                    "success": item.success,
                    "changed": item.changed,
                    "attempts": item.attempts,
                    "detail": item.detail,
                }
                for item in self.ai_steps
            ],
            "warnings": list(self.warnings),
            "final_url": self.final_url,
            "failed_stage": self.failed_stage,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PimPreparationResult":
        return cls(
            product_code=str(data.get("product_code") or ""),
            product_id=str(data.get("product_id") or ""),
            initial_version=data.get("initial_version"),
            initial_fields=dict(data.get("initial_fields") or {}),
            status=PimPreparationStatus(
                data.get("status") or PimPreparationStatus.FAILED.value
            ),
            changed_fields=tuple(data.get("changed_fields") or ()),
            ai_steps=tuple(
                PimAiStepResult(
                    step=str(item.get("step") or ""),
                    success=bool(item.get("success")),
                    changed=bool(item.get("changed")),
                    attempts=int(item.get("attempts") or 0),
                    detail=str(item.get("detail") or ""),
                )
                for item in data.get("ai_steps") or ()
            ),
            warnings=tuple(data.get("warnings") or ()),
            final_url=str(data.get("final_url") or ""),
            failed_stage=str(data.get("failed_stage") or ""),
            error=str(data.get("error") or ""),
        )


class PimAutomationError(RuntimeError):
    """A current PIMBO editor operation could not be completed safely."""


class PimNonDraftError(PimAutomationError):
    def __init__(self, status: str):
        self.status = status
        super().__init__(f"Product status is {status!r}; automation is allowed only for Draft")


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\u00a0", " ")).strip()


def _strip_html(value: str) -> str:
    return _clean(html.unescape(re.sub(r"<[^>]+>", " ", value or "")))


def _is_lithuanian_copy(value: str) -> bool:
    """Conservative language guard for generated long-form LT descriptions."""

    text = f" {_strip_html(value).casefold()} "
    if len(text) < 60:
        return False
    markers = (
        " ir ", " su ", " yra ", " bei ", " kad ", " skirt", " užtikrin",
        " dvira", " rėm", " važ", "ė", "ų", "š", "ž",
    )
    return sum(marker in text for marker in markers) >= 3


class PimboProductEditor:
    """Semantic Selenium controller for the current PIMBO product page."""

    SECTION_VALUES = {
        "basic": "general",
        "general": "general",
        "variants": "variants",
        "attributes": "attributes",
        "specifications": "specifications",
        "seo": "seo",
        "metadata": "metadata",
    }
    LOCALES = ("lt", "en", "lv", "ee")

    def __init__(
        self,
        driver: Any,
        logger: Any = None,
        *,
        timeout: float = 12.0,
        title_template: str = "Prekės pavadinimas",
        description_template: str = "Aprašymas LT",
    ) -> None:
        self.driver = driver
        self.logger = logger
        self.timeout = timeout
        self.title_template = title_template
        self.description_template = description_template

    def _log(self, message: str, **context: Any) -> None:
        if self.logger:
            self.logger.log("PimboProductEditor", message, **context)

    def _log_error(self, message: str, exception: Exception | None = None, **context: Any) -> None:
        if self.logger:
            self.logger.error("PimboProductEditor", message, exception=exception, **context)

    @staticmethod
    def _xpath_literal(value: str) -> str:
        if "'" not in value:
            return f"'{value}'"
        if '"' not in value:
            return f'"{value}"'
        return "concat(" + ', "\'", '.join(f"'{part}'" for part in value.split("'")) + ")"

    def _wait_until(
        self,
        predicate: Callable[[], Any],
        message: str,
        timeout: float | None = None,
    ) -> Any:
        deadline = time.monotonic() + (self.timeout if timeout is None else timeout)
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                value = predicate()
                if value:
                    return value
            except Exception as error:  # DOM may rerender between polls
                last_error = error
            time.sleep(0.15)
        suffix = f": {last_error}" if last_error else ""
        raise TimeoutException(f"{message}{suffix}")

    @staticmethod
    def _displayed(elements: Iterable[Any]) -> list[Any]:
        visible: list[Any] = []
        for element in elements:
            try:
                if element.is_displayed():
                    visible.append(element)
            except Exception:
                continue
        return visible

    def _find_visible(self, by: str, value: str) -> Any | None:
        return next(iter(self._displayed(self.driver.find_elements(by, value))), None)

    def _click(self, element: Any) -> None:
        self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
        try:
            element.click()
        except Exception:
            self.driver.execute_script("arguments[0].click();", element)

    def _set_input_value(self, element: Any, value: str) -> None:
        value = str(value or "")
        self.driver.execute_script(
            """
            const element = arguments[0];
            const value = arguments[1];
            const proto = element instanceof HTMLTextAreaElement
              ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
            const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
            if (setter) setter.call(element, value); else element.value = value;
            element.dispatchEvent(new Event('input', {bubbles: true}));
            element.dispatchEvent(new Event('change', {bubbles: true}));
            """,
            element,
            value,
        )

    def wait_ready(self) -> None:
        self._wait_until(
            lambda: re.search(r"/dashboard/products/[^/?#]+", self.driver.current_url or "")
            and self._find_visible(By.CSS_SELECTOR, "main h1"),
            "PIMBO product editor did not become ready",
        )

    @property
    def product_id(self) -> str:
        match = re.search(r"/dashboard/products/([^/?#]+)", self.driver.current_url or "")
        return match.group(1) if match else ""

    def external_id(self) -> str:
        field = self._find_visible(By.CSS_SELECTOR, "input[placeholder='ERP / supplier identifier']")
        return _clean(field.get_attribute("value")) if field else ""

    def current_status(self) -> str:
        candidates = self.driver.find_elements(
            By.XPATH,
            "//main//*[translate(normalize-space(.),'*','')='Status']"
            "/following::*[self::input or self::button or @role='combobox'][1]",
        )
        for element in candidates:
            value = _clean(element.get_attribute("value") or element.text)
            if value.casefold() in {"draft", "in review", "published", "disabled"}:
                return value.title()

        try:
            value = self.driver.execute_script(
                """
                const allowed = new Set(['draft', 'in review', 'published', 'disabled']);
                const nodes = Array.from(document.querySelectorAll('main *'));
                const label = nodes.find(node =>
                  (node.textContent || '').replace('*', '').trim().toLowerCase() === 'status');
                let current = label?.parentElement;
                for (let depth = 0; current && depth < 6; depth++, current = current.parentElement) {
                  const lines = (current.innerText || '').split(/\n/)
                    .map(v => v.trim().toLowerCase()).filter(Boolean);
                  const status = lines.find(line => allowed.has(line));
                  if (status) return status;
                }
                return '';
                """
            )
            if _clean(value).casefold() in {"draft", "in review", "published", "disabled"}:
                return _clean(value).title()
        except Exception:
            pass

        heading = self._find_visible(By.CSS_SELECTOR, "main h1")
        if heading is not None:
            badges = heading.find_elements(By.XPATH, "following::*[1]")
            if badges:
                value = _clean(badges[0].text)
                if value:
                    return value
        return "Unknown"

    def current_version(self) -> int | None:
        def read_visible_version() -> int | None:
            elements = self.driver.find_elements(
                By.XPATH,
                "//main//*[translate(normalize-space(.),'*','')='Version']"
                "/following::*[normalize-space()][1]",
            )
            for element in elements:
                text = element.text or element.get_attribute("textContent") or ""
                match = re.search(r"\d+", _clean(text))
                if match:
                    return int(match.group(0))
            return None

        version = read_visible_version()
        if version is not None:
            return version
        try:
            self.open_section("metadata")
        except Exception:
            return None
        version = read_visible_version()
        if version is not None:
            return version
        return None

    def save_button(self) -> Any | None:
        return self._find_visible(By.XPATH, "//main//button[normalize-space()='Save']")

    def is_dirty(self) -> bool:
        button = self.save_button()
        if button is None or not button.is_enabled():
            return False
        return not any(
            button.get_attribute(name) in {"", "true", "disabled"}
            for name in ("disabled", "aria-disabled", "data-disabled")
            if button.get_attribute(name) is not None
        )

    def assert_draft(self, expected_code: str = "") -> tuple[int | None, str]:
        self.wait_ready()
        actual_code = self.external_id()
        if expected_code and actual_code.casefold() != expected_code.strip().casefold():
            raise PimAutomationError(
                f"Opened product code {actual_code!r}, expected {expected_code!r}"
            )
        status = self.current_status()
        if status.casefold() != "draft":
            raise PimNonDraftError(status)
        version = self.current_version()
        if version is None:
            raise PimAutomationError(
                "PIMBO product version could not be read before preparation"
            )
        return version, actual_code

    def begin(self, product_code: str) -> PimPreparationResult:
        try:
            version, _ = self.assert_draft(product_code)
            initial_fields = self.capture_field_state()
            return PimPreparationResult(
                product_code=product_code,
                product_id=self.product_id,
                initial_version=version,
                initial_fields=initial_fields,
                final_url=self.driver.current_url,
            )
        except PimNonDraftError as error:
            return PimPreparationResult(
                product_code=product_code,
                product_id=self.product_id,
                initial_version=self.current_version(),
                status=PimPreparationStatus.BLOCKED_NON_DRAFT,
                final_url=self.driver.current_url,
                error=str(error),
            )

    def _combobox_value(self, placeholder: str) -> str:
        self.open_section("general")
        field = self._find_visible(
            By.CSS_SELECTOR,
            f"main input[placeholder={self._css_string(placeholder)}]",
        )
        if field is None:
            return ""
        direct = _clean(field.get_attribute("value"))
        if direct:
            return direct
        value = self.driver.execute_script(
            """
            const input = arguments[0];
            const placeholder = (arguments[1] || '').toLowerCase();
            let node = input.parentElement;
            for (let depth = 0; node && depth < 5; depth++, node = node.parentElement) {
              const values = (node.innerText || '').split(/\n/)
                .map(v => v.trim()).filter(Boolean)
                .filter(v => !v.toLowerCase().includes(placeholder.replace('...', '')))
                .filter(v => !/^(brand|product family|family|product categories|categories|category|required)$/i.test(v));
              if (values.length) return values[values.length - 1];
            }
            return '';
            """,
            field,
            placeholder,
        )
        return _clean(value)

    def capture_field_state(self) -> dict[str, Any]:
        """Capture a compact pre-change state for audit and review."""
        self.switch_locale("lt")
        name = self.product_name()
        description = self.description_html()
        return {
            "status": self.current_status(),
            "external_id": self.external_id(),
            "product_name_lt": name,
            "description_lt_present": bool(_strip_html(description)),
            "brand": self._combobox_value("Search brands..."),
            "product_family": self._combobox_value("Search families..."),
            "category": self._selected_category(),
        }

    def open_section(self, section: str) -> None:
        desired = self.SECTION_VALUES.get(section.casefold(), section.casefold())
        selects = self._displayed(self.driver.find_elements(By.CSS_SELECTOR, "main select"))
        for select_element in selects:
            options = select_element.find_elements(By.TAG_NAME, "option")
            values = {str(option.get_attribute("value") or "") for option in options}
            if desired in values:
                Select(select_element).select_by_value(desired)
                self._wait_until(
                    lambda: self._section_is_ready(desired),
                    f"PIMBO section {section!r} did not open",
                    5.0,
                )
                return

        labels = {
            "general": "Basic Info",
            "variants": "Variants",
            "attributes": "Attributes",
            "specifications": "Specifications",
            "seo": "SEO",
            "metadata": "Metadata",
        }
        label = labels.get(desired, section)
        tabs = self._displayed(
            self.driver.find_elements(
                By.XPATH,
                f"//main//*[@role='tab' or self::button][starts-with(normalize-space(), {self._xpath_literal(label)})]",
            )
        )
        if not tabs:
            raise PimAutomationError(f"PIMBO section {section!r} was not found")
        self._click(tabs[0])
        self._wait_until(
            lambda: self._section_is_ready(desired),
            f"PIMBO section {section!r} did not open",
        )

    def _section_is_ready(self, section: str) -> bool:
        panel = self._active_panel()
        if panel is None:
            return False
        if section == "general":
            return bool(
                panel.find_elements(
                    By.CSS_SELECTOR,
                    "input[placeholder='ERP / supplier identifier']",
                )
                or "Product Name" in (panel.text or "")
            )
        if section == "variants":
            return bool(
                panel.find_elements(By.CSS_SELECTOR, "button[title='Edit axis values']")
                or "Variants" in (panel.text or "")
            )
        if section == "attributes":
            return bool(
                panel.find_elements(
                    By.CSS_SELECTOR,
                    "input[placeholder='Search or add new...']",
                )
                or "Attributes" in (panel.text or "")
            )
        if section == "specifications":
            return bool(
                panel.find_elements(
                    By.CSS_SELECTOR,
                    "input[placeholder='Enter value...']",
                )
                or "Specifications" in (panel.text or "")
            )
        if section == "seo":
            return "SEO" in (panel.text or "")
        if section == "metadata":
            return "Version" in (panel.text or "") or "Metadata" in (panel.text or "")
        return True

    def _active_panel(self) -> Any | None:
        panels = self.driver.find_elements(By.CSS_SELECTOR, "main [role='tabpanel']")
        for panel in panels:
            try:
                if panel.is_displayed() and panel.get_attribute("inert") is None:
                    return panel
            except Exception:
                continue
        return next(iter(self._displayed(panels)), None)

    def switch_locale(self, locale: str) -> None:
        locale = locale.casefold()
        if locale not in self.LOCALES:
            raise ValueError(f"Unsupported PIMBO locale: {locale}")
        xpath = (
            "//main//h1/following::button[normalize-space()="
            f"{self._xpath_literal(locale.upper())}][1]"
        )
        button = self._wait_until(
            lambda: self._find_visible(By.XPATH, xpath),
            f"PIMBO locale button {locale.upper()} was not found",
        )
        classes = button.get_attribute("class") or ""
        if "bg-background" not in classes:
            self._click(button)
            self._wait_until(
                lambda: "bg-background" in ((self._find_visible(By.XPATH, xpath).get_attribute("class") or "")),
                f"PIMBO locale {locale.upper()} did not activate",
            )

    def _field_after_label(self, label: str, *, placeholder: str | None = None) -> Any | None:
        panel = self._active_panel()
        if panel is None:
            return None
        label_literal = self._xpath_literal(label)
        suffix = f"[@placeholder={self._xpath_literal(placeholder)}]" if placeholder else ""
        xpath = (
            ".//*[translate(normalize-space(.), '*', '')=" + label_literal + "]"
            f"/following::input{suffix}[1]"
        )
        elements = panel.find_elements(By.XPATH, xpath)
        return next(iter(self._displayed(elements)), None)

    def product_name(self) -> str:
        self.open_section("general")
        field = self._field_after_label("Product Name")
        return _clean(field.get_attribute("value")) if field else ""

    def set_product_name(self, value: str) -> bool:
        self.open_section("general")
        field = self._field_after_label("Product Name")
        if field is None:
            raise PimAutomationError("Product Name input was not found")
        before = _clean(field.get_attribute("value"))
        if before == _clean(value):
            return False
        self._set_input_value(field, value)
        return True

    def description_html(self) -> str:
        self.open_section("general")
        iframe = self._find_visible(By.CSS_SELECTOR, "main iframe.tox-edit-area__iframe")
        if iframe is None:
            return ""
        try:
            self.driver.switch_to.frame(iframe)
            body = self.driver.find_element(By.ID, "hugerte")
            return str(body.get_attribute("innerHTML") or "")
        finally:
            self.driver.switch_to.default_content()

    def set_description_html(self, value: str) -> bool:
        self.open_section("general")
        iframe = self._wait_until(
            lambda: self._find_visible(By.CSS_SELECTOR, "main iframe.tox-edit-area__iframe"),
            "HugeRTE description iframe was not found",
        )
        before = self.description_html()
        if before == value:
            return False
        try:
            self.driver.switch_to.frame(iframe)
            body = self.driver.find_element(By.ID, "hugerte")
            self.driver.execute_script(
                "arguments[0].innerHTML=arguments[1];"
                "arguments[0].dispatchEvent(new Event('input',{bubbles:true}));"
                "arguments[0].dispatchEvent(new Event('change',{bubbles:true}));",
                body,
                value,
            )
        finally:
            self.driver.switch_to.default_content()
        return True

    def set_localized_descriptions(
        self,
        descriptions: Mapping[str, str],
    ) -> tuple[str, ...]:
        """Set supplied description locales and always return the editor to LT."""

        changed_locales: list[str] = []
        try:
            for locale in self.LOCALES:
                html_value = str(descriptions.get(locale) or "").strip()
                if not html_value:
                    continue
                self.switch_locale(locale)
                if self.set_description_html(html_value):
                    changed_locales.append(locale)
        finally:
            self.switch_locale("lt")
        return tuple(changed_locales)

    def _select_combobox(self, placeholder: str, value: str, *, required: bool = True) -> bool:
        self.open_section("general")
        field = self._find_visible(By.CSS_SELECTOR, f"main input[placeholder={self._css_string(placeholder)}]")
        if field is None:
            if required:
                raise PimAutomationError(f"PIMBO combobox {placeholder!r} was not found")
            return False
        before = self._combobox_value(placeholder)
        if before.casefold() == value.casefold():
            return False
        self._click(field)
        field.send_keys(Keys.CONTROL, "a")
        field.send_keys(value)
        literal = self._xpath_literal(value)

        def option() -> Any | None:
            candidates = self.driver.find_elements(
                By.XPATH,
                f"//*[@role='option' and normalize-space()={literal}] | //button[normalize-space()={literal}]",
            )
            return next(iter(self._displayed(candidates)), None)

        selected = self._wait_until(option, f"PIMBO option {value!r} was not found", 6.0)
        self._click(selected)
        self._wait_until(
            lambda: self._combobox_value(placeholder).casefold() == value.casefold(),
            f"PIMBO option {value!r} was not selected",
            5.0,
        )
        return True

    @staticmethod
    def _css_string(value: str) -> str:
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'

    def set_brand(self, brand: str) -> bool:
        return self._select_combobox("Search brands...", brand)

    def ensure_product_family(self, expected: str = "Dviračiai") -> bool:
        self.open_section("general")
        field = self._find_visible(By.CSS_SELECTOR, "main input[placeholder='Search families...']")
        if field is None:
            raise PimAutomationError("Product Family combobox was not found")
        current = self._combobox_value("Search families...")
        if current:
            if current.casefold() != expected.casefold():
                raise PimAutomationError(
                    f"Product Family is {current!r}; expected {expected!r}"
                )
            return False
        return self._select_combobox("Search families...", expected)

    def upload_product_images(self, paths: Iterable[str], *, skip_if_present: bool = True) -> int:
        self.open_section("general")
        files = [str(path) for path in paths if str(path)]
        if not files:
            return 0
        if skip_if_present:
            remove_buttons = self._displayed(
                self.driver.find_elements(By.XPATH, "//main//button[@aria-label='Remove image']")
            )
            if remove_buttons:
                return 0
        inputs = self._displayed(
            self.driver.find_elements(
                By.CSS_SELECTOR,
                "main input[type='file'][multiple][accept*='image']",
            )
        )
        if not inputs:
            # File inputs are commonly hidden but Selenium can still send paths.
            inputs = self.driver.find_elements(
                By.CSS_SELECTOR,
                "main input[type='file'][multiple][accept*='image']",
            )
        if not inputs:
            raise PimAutomationError("Product image file input was not found")
        inputs[0].send_keys("\n".join(files))
        return len(files)

    def attribute_value(self, name: str) -> str | None:
        self.open_section("attributes")
        field = self._field_after_label(name, placeholder="Search or add new...")
        if field is None:
            return None
        return _clean(field.get_attribute("value"))

    def set_attribute(self, name: str, value: str) -> bool | None:
        self.open_section("attributes")
        field = self._field_after_label(name, placeholder="Search or add new...")
        if field is None:
            return None
        before = _clean(field.get_attribute("value"))
        if before.casefold() == _clean(value).casefold():
            return False
        self._click(field)
        field.send_keys(Keys.CONTROL, "a")
        field.send_keys(value)
        literal = self._xpath_literal(value)
        candidates = self._wait_until(
            lambda: self._displayed(
                self.driver.find_elements(
                    By.XPATH,
                    f"//*[@role='option' and normalize-space()={literal}] | //button[normalize-space()={literal}]",
                )
            ),
            f"Attribute option {value!r} for {name!r} was not found",
            5.0,
        )
        self._click(candidates[0])
        return True

    def clear_attribute(self, name: str) -> bool | None:
        self.open_section("attributes")
        field = self._field_after_label(name, placeholder="Search or add new...")
        if field is None:
            return None
        if not _clean(field.get_attribute("value")):
            return False
        self._click(field)
        field.send_keys(Keys.CONTROL, "a")
        field.send_keys(Keys.BACKSPACE)
        return True

    def specification_value(self, name: str) -> str | None:
        self.open_section("specifications")
        field = self._field_after_label(name, placeholder="Enter value...")
        return _clean(field.get_attribute("value")) if field is not None else None

    def specification_field_count(self) -> int:
        """Return Family-provided specification row count without changing data."""
        self.open_section("specifications")
        panel = self._active_panel()
        if panel is None:
            return 0
        return len(panel.find_elements(By.CSS_SELECTOR, "input[placeholder='Enter value...']"))

    @staticmethod
    def validate_specification_transition(
        before: Iterable[str],
        after: Iterable[str],
    ) -> tuple[int, tuple[int, ...]]:
        """Return filled-empty count and indexes of illegally overwritten values."""
        old_values = list(before)
        new_values = list(after)
        filled = sum(
            1 for index, old in enumerate(old_values)
            if not _clean(old)
            and index < len(new_values)
            and _clean(new_values[index])
        )
        overwritten = tuple(
            index for index, old in enumerate(old_values)
            if _clean(old)
            and index < len(new_values)
            and _clean(new_values[index]) != _clean(old)
        )
        return filled, overwritten

    def set_specification(self, name: str, value: str, *, overwrite: bool = True) -> bool | None:
        self.open_section("specifications")
        field = self._field_after_label(name, placeholder="Enter value...")
        if field is None:
            return None
        before = _clean(field.get_attribute("value"))
        if before == _clean(value):
            return False
        if before and not overwrite:
            return False
        self._set_input_value(field, value)
        return True

    def collect_variant_sizes(self) -> list[str]:
        self.open_section("variants")
        values: list[str] = []
        buttons = self.driver.find_elements(By.CSS_SELECTOR, "main button[title='Edit axis values']")
        for button in buttons:
            for line in (button.text or "").splitlines():
                if ":" in line:
                    _, value = line.split(":", 1)
                    value = _clean(value)
                    if value and value not in values:
                        values.append(value)
        return values

    def _magic_panel(self, heading: str) -> Any | None:
        literal = self._xpath_literal(heading)
        headings = self._displayed(
            self.driver.find_elements(
                By.XPATH,
                f"//main//*[self::h2 or self::h3][normalize-space()={literal}]",
            )
        )
        if not headings:
            return None
        candidates = headings[0].find_elements(
            By.XPATH,
            "ancestor::div[.//button[normalize-space()='Cancel']][1]",
        )
        return candidates[0] if candidates else headings[0].find_element(By.XPATH, "..")

    def _choose_magic_template(self, panel: Any, template: str) -> None:
        combos = self._displayed(panel.find_elements(By.CSS_SELECTOR, "[role='combobox']"))
        if not combos:
            raise PimAutomationError("MagicAI template combobox was not found")
        self._click(combos[0])
        literal = self._xpath_literal(template)
        option = self._wait_until(
            lambda: next(
                iter(
                    self._displayed(
                        self.driver.find_elements(
                            By.XPATH,
                            f"//*[@role='option' and normalize-space()={literal}] | //button[normalize-space()={literal}]",
                        )
                    )
                ),
                None,
            ),
            f"Required MagicAI template {template!r} was not found",
            6.0,
        )
        self._click(option)

    def _wait_magic_apply(self, panel: Any, timeout: float = 60.0) -> None:
        self._wait_until(
            lambda: next(
                (
                    button
                    for button in panel.find_elements(By.XPATH, ".//button[normalize-space()='Apply']")
                    if button.is_displayed() and button.is_enabled()
                ),
                None,
            ),
            "MagicAI did not produce an applicable result",
            timeout,
        )

    def _cancel_magic(self, panel: Any | None) -> None:
        if panel is None:
            return
        buttons = self._displayed(panel.find_elements(By.XPATH, ".//button[normalize-space()='Cancel']"))
        if buttons:
            self._click(buttons[-1])

    def generate_product_name(self) -> PimAiStepResult:
        self.switch_locale("lt")
        self.open_section("general")
        button = self._find_visible(
            By.CSS_SELECTOR,
            "main button[title='Generate product name with MagicAI']",
        )
        if button is None:
            raise PimAutomationError("Product name MagicAI button was not found")
        before = self.product_name()
        for attempt in (1, 2):
            self._click(button)
            panel = self._wait_until(
                lambda: self._magic_panel("MagicAI — Generate product name"),
                "Product name MagicAI panel did not open",
            )
            try:
                self._choose_magic_template(panel, self.title_template)
                action = "Generate" if attempt == 1 else "Regenerate"
                actions = self._displayed(panel.find_elements(By.XPATH, f".//button[normalize-space()='{action}']"))
                if not actions:
                    actions = self._displayed(panel.find_elements(By.XPATH, ".//button[normalize-space()='Generate']"))
                if not actions:
                    raise PimAutomationError("MagicAI Generate button was not found")
                self._click(actions[0])
                self._wait_magic_apply(panel)
                apply_button = self._displayed(panel.find_elements(By.XPATH, ".//button[normalize-space()='Apply']"))[0]
                self._click(apply_button)
                self._wait_until(lambda: self._magic_panel("MagicAI — Generate product name") is None, "Name MagicAI panel did not close")
                generated = self.product_name()
                if len(generated) >= 5:
                    return PimAiStepResult("product_name", True, generated != before, attempt)
            except Exception:
                self._cancel_magic(panel)
                if attempt == 2:
                    raise
        raise PimAutomationError("MagicAI returned an invalid product name twice")

    def generate_description(self) -> PimAiStepResult:
        self.switch_locale("lt")
        self.open_section("general")
        before = self.description_html()
        for attempt in (1, 2):
            buttons = self._displayed(
                self.driver.find_elements(By.XPATH, "//main//button[normalize-space()='MagicAI']")
            )
            if not buttons:
                raise PimAutomationError("Description MagicAI button was not found")
            self._click(buttons[0])
            panel = self._wait_until(
                lambda: self._magic_panel("MagicAI — Generate description"),
                "Description MagicAI panel did not open",
            )
            try:
                self._choose_magic_template(panel, self.description_template)
                actions = self._displayed(panel.find_elements(By.XPATH, ".//button[normalize-space()='Generate' or normalize-space()='Regenerate']"))
                if not actions:
                    raise PimAutomationError("Description MagicAI generate action was not found")
                self._click(actions[-1] if attempt > 1 else actions[0])
                self._wait_magic_apply(panel)
                apply_button = self._displayed(panel.find_elements(By.XPATH, ".//button[normalize-space()='Apply']"))[0]
                self._click(apply_button)
                self._wait_until(lambda: self._magic_panel("MagicAI — Generate description") is None, "Description MagicAI panel did not close")
                generated = self.description_html()
                if _is_lithuanian_copy(generated):
                    return PimAiStepResult("description", True, generated != before, attempt)
            except Exception:
                self._cancel_magic(panel)
                if attempt == 2:
                    raise
        raise PimAutomationError("MagicAI returned a non-Lithuanian or empty description twice")

    def _selected_category(self) -> str:
        self.open_section("general")
        search = self._find_visible(By.CSS_SELECTOR, "main input[placeholder='Search categories...']")
        if search is None:
            return ""
        direct = _clean(search.get_attribute("value"))
        if direct:
            return direct
        value = self.driver.execute_script(
            """
            const input = arguments[0];
            let node = input;
            for (let depth = 0; node && depth < 6; depth++, node = node.parentElement) {
              const lines = (node.innerText || '').split(/\n/).map(v => v.trim()).filter(Boolean);
              const candidates = lines.filter(v =>
                !/search categories|product categor|magicai|suggest categor/i.test(v));
              if (candidates.length) return candidates[candidates.length - 1];
            }
            return '';
            """,
            search,
        )
        return _clean(value)

    def suggest_category(self, family: str = "Dviračiai") -> PimAiStepResult:
        self.switch_locale("lt")
        self.open_section("general")
        last_error = ""
        for attempt in (1, 2):
            button = self._find_visible(
                By.CSS_SELECTOR,
                "main button[title='Suggest categories with MagicAI']",
            )
            if button is None:
                raise PimAutomationError("Category MagicAI button was not found")
            before = self._selected_category()
            self._click(button)
            try:
                after = self._wait_until(
                    lambda: (value if (value := self._selected_category()) != before else ""),
                    "Category MagicAI did not change the category",
                    60.0,
                )
                normalized = after.casefold()
                if normalized != "import" and normalized.startswith(family.casefold()):
                    return PimAiStepResult("category", True, after != before, attempt, after)
                last_error = f"MagicAI suggested invalid category {after!r}"
            except TimeoutException as error:
                last_error = str(error)
        raise PimAutomationError(last_error or "Category MagicAI failed twice")

    def fill_empty_specifications_with_ai(self, source_text: str) -> PimAiStepResult:
        source_text = str(source_text or "").strip()
        if not source_text:
            raise PimAutomationError("Specification MagicAI source text is empty")
        self.open_section("specifications")
        panel = self._active_panel()
        if panel is None:
            raise PimAutomationError("Specifications panel was not found")
        buttons = self._displayed(panel.find_elements(By.XPATH, ".//button[normalize-space()='MagicAI']"))
        if not buttons:
            return PimAiStepResult("specifications", True, False, 0, "MagicAI unavailable for this product schema")

        spec_inputs = panel.find_elements(By.CSS_SELECTOR, "input[placeholder='Enter value...']")
        before = [str(item.get_attribute("value") or "") for item in spec_inputs]
        empty_before = sum(not _clean(value) for value in before)
        if empty_before == 0:
            return PimAiStepResult(
                "specifications", True, False, 0, "no empty specification fields"
            )

        last_filled = 0
        for attempt in (1, 2):
            panel = self._active_panel()
            buttons = self._displayed(
                panel.find_elements(By.XPATH, ".//button[normalize-space()='MagicAI']")
            ) if panel else []
            if not buttons:
                raise PimAutomationError("Specification MagicAI button was not found")
            self._click(buttons[0])
            textarea = self._wait_until(
                lambda: self._find_visible(By.CSS_SELECTOR, "main textarea"),
                "Specification MagicAI source field did not appear",
            )
            self._set_input_value(textarea, source_text)
            extract = self._wait_until(
                lambda: self._find_visible(By.XPATH, "//main//button[normalize-space()='Extract & fill']"),
                "Specification MagicAI Extract & fill button was not found",
            )
            self._click(extract)
            self._wait_until(
                lambda: self._find_visible(By.XPATH, "//main//button[normalize-space()='Extract & fill']") is None,
                "Specification MagicAI did not finish",
                90.0,
            )
            panel = self._active_panel()
            after_inputs = panel.find_elements(By.CSS_SELECTOR, "input[placeholder='Enter value...']") if panel else []
            after = [str(item.get_attribute("value") or "") for item in after_inputs]
            last_filled, changed_existing = self.validate_specification_transition(
                before,
                after,
            )
            if changed_existing:
                raise PimAutomationError(
                    "Specification MagicAI changed already-filled fields; product was not saved"
                )
            if last_filled:
                return PimAiStepResult(
                    "specifications",
                    True,
                    True,
                    attempt,
                    f"filled {last_filled} of {empty_before} empty specifications",
                )
        raise PimAutomationError(
            f"Specification MagicAI filled 0 of {empty_before} empty fields after two attempts"
        )

    def seo_copy(self) -> dict[str, str]:
        """Read localized SEO inputs by semantic label/placeholder."""
        self.open_section("seo")
        panel = self._active_panel()
        if panel is None:
            return {}
        result: dict[str, str] = {}
        elements = self._displayed(panel.find_elements(By.CSS_SELECTOR, "input, textarea"))
        for index, element in enumerate(elements):
            if (element.get_attribute("type") or "").casefold() in {
                "checkbox", "file", "hidden", "radio",
            }:
                continue
            value = _clean(element.get_attribute("value"))
            key = _clean(
                element.get_attribute("aria-label")
                or element.get_attribute("name")
                or element.get_attribute("placeholder")
                or f"seo_{index}"
            )
            if key:
                result[key] = value
        return result

    def localized_copy_snapshot(self, locale: str) -> dict[str, Any]:
        self.switch_locale(locale)
        return {
            "name": self.product_name(),
            "description": self.description_html(),
            "seo": self.seo_copy(),
        }

    def _select_translation_source_lt(self, panel: Any) -> None:
        native_selects = self._displayed(panel.find_elements(By.TAG_NAME, "select"))
        for element in native_selects:
            options = Select(element).options
            for option in options:
                option_text = _clean(option.text).casefold()
                if (
                    option_text == "lt"
                    or "lithuanian" in option_text
                    or "lietuvi" in option_text
                ):
                    Select(element).select_by_visible_text(option.text)
                    return

        combos = self._displayed(panel.find_elements(By.CSS_SELECTOR, "[role='combobox']"))
        if not combos:
            raise PimAutomationError("Translation source language control was not found")
        combo = combos[0]
        current = _clean(combo.text or combo.get_attribute("value")).casefold()
        if current == "lt" or "lithuanian" in current or "lietuvi" in current:
            return
        self._click(combo)
        options = self._wait_until(
            lambda: self._displayed(
                self.driver.find_elements(
                    By.XPATH,
                    "//*[@role='option' and (contains(normalize-space(),'Lithuanian')"
                    " or normalize-space()='LT' or contains(normalize-space(),'Lietuvi'))]",
                )
            ),
            "Lithuanian translation source option was not found",
            6.0,
        )
        self._click(options[0])

    def _panel_checkbox(self, panel: Any, text: str) -> Any | None:
        literal = self._xpath_literal(text)
        candidates = panel.find_elements(
            By.XPATH,
            f".//*[@role='checkbox' and contains(@aria-label, {literal})]"
            f" | .//input[@type='checkbox' and contains(@aria-label, {literal})]"
            f" | .//label[contains(normalize-space(), {literal})]//*[@role='checkbox' or @type='checkbox']",
        )
        visible = self._displayed(candidates)
        return visible[0] if visible else (candidates[0] if candidates else None)

    def _run_translation_dialog(self, overwrite: bool) -> None:
        self.switch_locale("lt")
        button = self._wait_until(
            lambda: self._find_visible(
                By.XPATH,
                "//main//h1/following::button[normalize-space()='Translate'][1]",
            ),
            "Top-level PIMBO Translate button was not found",
        )
        self._click(button)
        panel = self._wait_until(
            lambda: self._magic_panel("MagicAI — Translate product copy"),
            "PIMBO translation panel did not open",
        )
        self._select_translation_source_lt(panel)
        for language in ("English", "Latvian", "Estonian"):
            box = self._panel_checkbox(panel, language)
            if box is None:
                raise PimAutomationError(f"Translation destination {language!r} was not found")
            checked = box.is_selected() or box.get_attribute("aria-checked") == "true"
            if not checked:
                self._click(box)

        overwrite_box = self._panel_checkbox(panel, "Overwrite existing translations")
        if overwrite_box is None:
            raise PimAutomationError("Overwrite existing translations checkbox was not found")
        checked = overwrite_box.is_selected() or overwrite_box.get_attribute("aria-checked") == "true"
        if checked != overwrite:
            self._click(overwrite_box)

        actions = self._displayed(
            panel.find_elements(By.XPATH, ".//button[normalize-space()='Translate']")
        )
        if not actions:
            raise PimAutomationError("Translation confirmation button was not found")
        self._click(actions[-1])
        self._wait_until(
            lambda: self._magic_panel("MagicAI — Translate product copy") is None,
            "PIMBO translation did not finish",
            120.0,
        )

    @staticmethod
    def _translation_validation_error(
        before: dict[str, dict[str, Any]],
        after: dict[str, dict[str, Any]],
    ) -> str:
        problems: list[str] = []
        for locale in ("en", "lv", "ee"):
            current = after.get(locale, {})
            if not _clean(current.get("name")):
                problems.append(f"{locale.upper()} name is empty")
            if not _strip_html(str(current.get("description") or "")):
                problems.append(f"{locale.upper()} description is empty")
            seo = current.get("seo") or {}
            if not seo or not any(_clean(value) for value in seo.values()):
                problems.append(f"{locale.upper()} SEO is empty")
            if current == before.get(locale):
                problems.append(f"{locale.upper()} copy was not updated")
        return "; ".join(problems)

    def translate_lt_to_all(self, *, overwrite: bool = True) -> PimAiStepResult:
        before = {
            locale: self.localized_copy_snapshot(locale)
            for locale in ("en", "lv", "ee")
        }
        last_error = ""
        for attempt in (1, 2):
            try:
                self._run_translation_dialog(overwrite)
                after = {
                    locale: self.localized_copy_snapshot(locale)
                    for locale in ("en", "lv", "ee")
                }
                last_error = self._translation_validation_error(before, after)
                if not last_error:
                    self.switch_locale("lt")
                    return PimAiStepResult(
                        "translation", True, True, attempt, "LT → EN, LV, EE (overwrite)"
                    )
            except Exception as error:
                last_error = str(error)
                self._cancel_magic(self._magic_panel("MagicAI — Translate product copy"))
        self.switch_locale("lt")
        raise PimAutomationError(
            f"Translation validation failed after two attempts: {last_error}"
        )

    def run_full_magic_ai(self, source_text: str) -> tuple[PimAiStepResult, ...]:
        """Run the full product enrichment sequence, without saving."""

        steps = [
            self.generate_product_name(),
            self.generate_description(),
            self.suggest_category("Dviračiai"),
            self.fill_empty_specifications_with_ai(source_text),
            self.translate_lt_to_all(overwrite=True),
        ]
        self.switch_locale("lt")
        return tuple(steps)

    def finish(
        self,
        base: PimPreparationResult,
        *,
        changed_fields: Iterable[str] = (),
        ai_steps: Iterable[PimAiStepResult] = (),
        warnings: Iterable[str] = (),
    ) -> PimPreparationResult:
        if base.status == PimPreparationStatus.BLOCKED_NON_DRAFT:
            return base
        changed = tuple(dict.fromkeys(str(item) for item in changed_fields if item))
        result = replace(
            base,
            status=PimPreparationStatus.READY_FOR_REVIEW,
            changed_fields=changed,
            ai_steps=tuple(ai_steps),
            warnings=tuple(warnings),
            final_url=self.driver.current_url,
        )
        if not self.is_dirty():
            return replace(
                result,
                status=PimPreparationStatus.FAILED,
                error="PIMBO form has no reviewable unsaved changes",
            )
        return result

    def verify_manual_save(self, result: PimPreparationResult) -> PimPreparationResult:
        """Verify a human Save using both dirty state and Activity version."""

        if result.status != PimPreparationStatus.READY_FOR_REVIEW:
            return result.with_status(
                PimPreparationStatus.FAILED,
                error="Only a ready_for_review product can be confirmed as saved",
            )
        if self.product_id != result.product_id or self.external_id().casefold() != result.product_code.casefold():
            return result.with_status(
                PimPreparationStatus.FAILED,
                error="A different PIMBO product is open; manual Save cannot be confirmed",
            )
        try:
            self._wait_until(
                lambda: not self.is_dirty(),
                "PIMBO still has unsaved changes",
                self.timeout,
            )
        except TimeoutException as error:
            return result.with_status(
                PimPreparationStatus.FAILED,
                error=str(error),
            )
        if result.initial_version is None:
            return result.with_status(
                PimPreparationStatus.FAILED,
                error="Initial PIMBO product version was not available",
            )
        try:
            current = self._wait_until(
                lambda: (
                    value
                    if (value := self.current_version()) is not None
                    and value > result.initial_version
                    else None
                ),
                "PIMBO product version did not increase after manual Save",
                self.timeout,
            )
        except TimeoutException as error:
            return result.with_status(PimPreparationStatus.FAILED, error=str(error))
        return result.with_status(PimPreparationStatus.SAVED_MANUALLY, error="")
