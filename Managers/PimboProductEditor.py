"""Current OmnioPIM product editor automation.

This module is the single write-capable boundary used by the desktop app.
Changes remain reviewable by default; automatic Save is a separate, explicit
operation guarded by Draft/product/version verification.
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
    NO_CHANGES = "no_changes"
    SAVED_MANUALLY = "saved_manually"
    SAVED_AUTOMATICALLY = "saved_automatically"
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
    rejected = (
        "prašau pateikti",
        "pateikite produkto duomenis",
        "turimus produkto duomenis",
        "negaliu sugeneruoti",
        "neturiu produkto duomenų",
    )
    return (
        sum(marker in text for marker in markers) >= 3
        and not any(marker in text for marker in rejected)
    )


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
    IMAGE_GROUP_ALIASES = {
        "geometry": ("geometry", "geometrija"),
        "size_tables": (
            "size tables",
            "size table",
            "size charts",
            "size chart",
            "dydžių lentelės",
            "dydziu lenteles",
        ),
    }

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
                  const lines = (current.innerText || '').split(/\\n/)
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
            const scopes = [];
            const combo = input.closest('[role="combobox"]');
            if (combo) scopes.push(combo);
            let node = input.parentElement;
            for (let depth = 0; node && depth < 4; depth++, node = node.parentElement) {
              if (!scopes.includes(node)) scopes.push(node);
            }
            for (const scope of scopes) {
              const matchingInputs = scope.querySelectorAll(
                `input[placeholder="${CSS.escape(arguments[1] || '')}"]`
              );
              if (matchingInputs.length > 1) continue;
              const values = (scope.innerText || '').split(/\\n/)
                .map(v => v.trim()).filter(Boolean)
                .filter(v => !v.toLowerCase().includes(placeholder.replace('...', '')))
                .filter(v => !/^(brand|product family|family|product categories|categories|category|required|draft|in review|published|disabled|status)$/i.test(v));
              if (values.length) return values[0];
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

    def ensure_lithuanian_name_from_english(self) -> bool:
        """Seed an empty LT product name from EN and finish in the LT locale."""

        self.switch_locale("lt")
        if self.product_name():
            return False

        english_name = ""
        try:
            self.switch_locale("en")
            english_name = self.product_name()
        finally:
            self.switch_locale("lt")

        if not english_name:
            raise PimAutomationError(
                "Lithuanian Product Name is empty and the English fallback is also empty"
            )
        changed = self.set_product_name(english_name)
        if not self.product_name():
            raise PimAutomationError(
                "English Product Name was not retained in the Lithuanian field"
            )
        return changed

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
        before = self.description_html()
        if before == value:
            return False
        # Re-resolve after reading the old value because switching in and out of
        # the iframe can invalidate a React-owned element reference.
        self.open_section("general")
        iframe = self._wait_until(
            lambda: self._find_visible(By.CSS_SELECTOR, "main iframe.tox-edit-area__iframe"),
            "HugeRTE description iframe was not found",
        )
        try:
            self.driver.switch_to.frame(iframe)
            body = self.driver.find_element(By.ID, "hugerte")
            self.driver.execute_script(
                """
                const body = arguments[0];
                const value = arguments[1];
                const editor = window.parent.tinymce?.activeEditor;
                if (editor && editor.getBody && editor.getBody() === body) {
                  editor.setContent(value);
                  editor.fire('input');
                  editor.fire('change');
                  editor.save();
                } else {
                  body.focus();
                  body.innerHTML = value;
                  try {
                    body.dispatchEvent(new InputEvent('input', {
                      bubbles: true, inputType: 'insertFromPaste', data: value
                    }));
                  } catch (_) {
                    body.dispatchEvent(new Event('input', {bubbles: true}));
                  }
                  body.dispatchEvent(new Event('change', {bubbles: true}));
                  body.dispatchEvent(new Event('blur', {bubbles: true}));
                }
                """,
                body,
                value,
            )
        finally:
            self.driver.switch_to.default_content()
        expected_text = _strip_html(value)
        self._wait_until(
            lambda: (
                current
                if (current := _strip_html(self.description_html()))
                and (
                    current == expected_text
                    or expected_text[:160] in current
                )
                else ""
            ),
            "PIMBO did not retain the pasted KROSS description",
            6.0,
        )
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

    def product_family(self) -> str:
        return self._combobox_value("Search families...")

    def ensure_product_family(self, expected: str = "Dviračiai") -> bool:
        self.open_section("general")
        field = self._find_visible(By.CSS_SELECTOR, "main input[placeholder='Search families...']")
        if field is None:
            raise PimAutomationError("Product Family combobox was not found")
        current = self._combobox_value("Search families...")
        if current.casefold() == expected.casefold():
            return False
        # The family is an explicit workflow choice. A stale/incorrect current
        # value must be replaced, not treated as a reason to abandon the run.
        return self._select_combobox("Search families...", expected)

    def _image_input_context(self, element: Any) -> str:
        """Return text identifying the smallest upload area around a file input."""

        try:
            context = self.driver.execute_script(
                """
                const input = arguments[0];
                const selector = "input[type='file'][accept*='image']";
                const parts = [
                  input.name, input.id, input.getAttribute('aria-label'),
                  input.getAttribute('data-testid'), input.getAttribute('data-slot')
                ].filter(Boolean);
                if (input.id) {
                  const label = document.querySelector(`label[for="${CSS.escape(input.id)}"]`);
                  if (label) parts.push(label.innerText || label.textContent || '');
                }
                let node = input.parentElement;
                for (let depth = 0; node && depth < 8; depth++, node = node.parentElement) {
                  if (node.querySelectorAll(selector).length !== 1) break;
                  parts.push(node.innerText || node.textContent || '');
                }
                return parts.join(' ');
                """,
                element,
            )
        except Exception:
            context = ""
        attributes: list[str] = []
        for name in ("name", "id", "aria-label", "data-testid", "data-slot"):
            try:
                attributes.append(str(element.get_attribute(name) or ""))
            except Exception:
                continue
        return _clean(" ".join((str(context or ""), *attributes))).casefold()

    def _image_file_inputs(self) -> list[Any]:
        selector = "main input[type='file'][accept*='image']"
        # Upload controls are commonly visually hidden, but Selenium can still
        # assign local paths directly without opening the native file dialog.
        # Keep every input so visible and hidden upload groups can be classified
        # together instead of accidentally dropping Geometry or Size tables.
        return list(self.driver.find_elements(By.CSS_SELECTOR, selector))

    def _image_group_input(self, group: str) -> Any:
        inputs = self._image_file_inputs()
        if not inputs:
            raise PimAutomationError("PIMBO image file inputs were not found")
        contexts = [(element, self._image_input_context(element)) for element in inputs]
        reserved_aliases = tuple(
            alias.casefold()
            for aliases in self.IMAGE_GROUP_ALIASES.values()
            for alias in aliases
        )
        if group == "product":
            candidates = [
                element
                for element, context in contexts
                if not any(alias in context for alias in reserved_aliases)
            ]
            if candidates:
                return candidates[0]
            if len(inputs) == 1:
                return inputs[0]
            raise PimAutomationError(
                "PIMBO product-photo upload area could not be distinguished from table images"
            )

        aliases = self.IMAGE_GROUP_ALIASES.get(group)
        if not aliases:
            raise ValueError(f"Unknown PIMBO image group: {group}")
        matches = [
            element
            for element, context in contexts
            if any(alias.casefold() in context for alias in aliases)
        ]
        if len(matches) == 1:
            return matches[0]
        label = "Geometry" if group == "geometry" else "Size tables"
        if not matches:
            raise PimAutomationError(f"PIMBO {label!r} image upload area was not found")
        raise PimAutomationError(f"PIMBO {label!r} image upload area is ambiguous")

    def _upload_images_to_group(
        self,
        paths: Iterable[str],
        group: str,
        *,
        skip_if_present: bool,
    ) -> int:
        self.open_section("general")
        files = [str(path) for path in paths if str(path)]
        if not files:
            return 0
        if skip_if_present and group == "product":
            remove_buttons = self._displayed(
                self.driver.find_elements(By.XPATH, "//main//button[@aria-label='Remove image']")
            )
            if remove_buttons:
                return 0
        image_input = self._image_group_input(group)
        image_input.send_keys("\n".join(files))
        return len(files)

    def upload_product_images(self, paths: Iterable[str], *, skip_if_present: bool = True) -> int:
        return self._upload_images_to_group(
            paths,
            "product",
            skip_if_present=skip_if_present,
        )

    def upload_geometry_images(self, paths: Iterable[str], *, skip_if_present: bool = True) -> int:
        return self._upload_images_to_group(
            paths,
            "geometry",
            skip_if_present=skip_if_present,
        )

    def upload_size_table_images(
        self,
        paths: Iterable[str],
        *,
        skip_if_present: bool = True,
    ) -> int:
        return self._upload_images_to_group(
            paths,
            "size_tables",
            skip_if_present=skip_if_present,
        )

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

    def _set_specification_in_open_section(
        self,
        name: str,
        value: str,
        *,
        overwrite: bool,
    ) -> bool | None:
        desired = _clean(value)
        changed = False
        last_error: Exception | None = None
        for _attempt in range(2):
            field = self._field_after_label(name, placeholder="Enter value...")
            if field is None:
                return None
            before = _clean(field.get_attribute("value"))
            if before == desired:
                return changed
            if before and not overwrite:
                return False
            self._set_input_value(field, value)
            changed = True
            try:
                self._wait_for_stable_specification_value(name, desired)
                return True
            except Exception as error:
                last_error = error
        raise PimAutomationError(
            f"Specification {name!r} did not retain {desired!r}: {last_error}"
        )

    def _wait_for_stable_specification_value(
        self,
        name: str,
        expected: str,
        *,
        timeout: float = 1.5,
        stable_for: float = 0.12,
    ) -> None:
        """Wait through React rerenders until a specification value is stable."""

        deadline = time.monotonic() + timeout
        stable_since: float | None = None
        last_value = ""
        while time.monotonic() < deadline:
            field = self._field_after_label(name, placeholder="Enter value...")
            if field is not None:
                try:
                    last_value = _clean(field.get_attribute("value"))
                except Exception:
                    last_value = ""
                if last_value == expected:
                    stable_since = stable_since or time.monotonic()
                    if time.monotonic() - stable_since >= stable_for:
                        return
                else:
                    stable_since = None
            time.sleep(0.04)
        raise PimAutomationError(
            f"Specification {name!r} remained {last_value!r}, expected {expected!r}"
        )

    def set_specification(
        self,
        name: str,
        value: str,
        *,
        overwrite: bool = True,
    ) -> bool | None:
        self.open_section("specifications")
        return self._set_specification_in_open_section(
            name,
            value,
            overwrite=overwrite,
        )

    def set_specifications(
        self,
        values: Mapping[str, str] | Iterable[tuple[str, str]],
        *,
        overwrite: bool = True,
        move_if_empty: Iterable[tuple[str, str]] = (),
    ) -> dict[str, bool | None]:
        """Set and migrate specification values after opening the tab once.

        Each ``move_if_empty`` pair is ``(legacy_name, target_name)``. The
        legacy value takes precedence over the planned target value when the
        target is empty. A populated target is preserved. The legacy value is
        cleared only after the target field has been found.
        """

        items = tuple(values.items() if isinstance(values, Mapping) else values)
        planned = dict(items)
        migrations = tuple(move_if_empty)
        migration_targets = {target for _source, target in migrations}
        self.open_section("specifications")

        results: dict[str, bool | None] = {}
        for source_name, target_name in migrations:
            source_field = self._field_after_label(
                source_name,
                placeholder="Enter value...",
            )
            target_field = self._field_after_label(
                target_name,
                placeholder="Enter value...",
            )
            source_value = _clean(
                source_field.get_attribute("value") if source_field is not None else ""
            )
            target_value = _clean(
                target_field.get_attribute("value") if target_field is not None else ""
            )
            fallback_value = _clean(planned.get(target_name, ""))

            if target_field is None and (source_value or fallback_value):
                raise PimAutomationError(
                    f"Target specification {target_name!r} was not found; "
                    f"legacy {source_name!r} was not cleared"
                )
            if target_field is None:
                results[target_name] = None
            elif target_value:
                results[target_name] = False
            elif source_value or fallback_value:
                results[target_name] = self._set_specification_in_open_section(
                    target_name,
                    source_value or fallback_value,
                    overwrite=True,
                )
            else:
                results[target_name] = False

            # Re-resolve after the target input event in case React rerendered
            # this specification group, then clear only the legacy value.
            source_field = self._field_after_label(
                source_name,
                placeholder="Enter value...",
            )
            if source_field is None:
                results[source_name] = None
            elif _clean(source_field.get_attribute("value")):
                results[source_name] = self._set_specification_in_open_section(
                    source_name,
                    "",
                    overwrite=True,
                )
            else:
                results[source_name] = False

        for name, value in items:
            if name in migration_targets:
                continue
            results[name] = self._set_specification_in_open_section(
                name,
                value,
                overwrite=overwrite,
            )
        return results

    @staticmethod
    def _variant_sizes_from_axis_text(value: str) -> list[str]:
        """Extract frame-size values from one labelled Variants axis block."""

        text = str(value or "").replace("\xa0", " ")
        label = re.search(
            r"(?im)(?:^|[\n;|])\s*"
            r"(?:frame\s+size|rėmo\s+dydis|remo\s+dydis|"
            r"rozmiar(?:\s+ramy)?|dydis|size)\s*(?::|[-–])?\s*",
            text,
        )
        if label is None:
            return []
        payload = text[label.end():]
        symbolic_pattern = (
            r"(?<![A-Z0-9])(?:XXXS|3XS|XXS|2XS|XS|XXXL|3XL|XXL|2XL|"
            r"XL|4XL|5XL|S|M|L)(?![A-Z0-9])"
        )
        values = re.findall(symbolic_pattern, payload.upper())
        values.extend(
            match.group(0).strip()
            for match in re.finditer(
                r"(?i)(?<![\d.,])\d{2}(?:[.,]\d+)?\s*(?:CM|[\"″])?(?![\d.,A-Z])",
                payload,
            )
        )
        return list(dict.fromkeys(_clean(item) for item in values if _clean(item)))

    @staticmethod
    def _standalone_variant_size(value: str) -> str:
        candidate = _clean(value)
        if re.fullmatch(
            r"(?i)(?:XXXS|3XS|XXS|2XS|XS|S|M|L|XL|XXL|2XL|XXXL|3XL|4XL|5XL|"
            r"\d{2}(?:[.,]\d+)?\s*(?:CM|[\"″])?)",
            candidate,
        ):
            return candidate
        return ""

    def collect_variant_sizes(self) -> list[str]:
        """Read frame sizes without opening or modifying any variant."""

        self.open_section("variants")
        panel = self._active_panel()
        if panel is None:
            return []
        values: list[str] = []

        def extend(items: Iterable[str]) -> None:
            for item in items:
                cleaned = _clean(item)
                if cleaned and cleaned.casefold() not in {
                    existing.casefold() for existing in values
                }:
                    values.append(cleaned)

        buttons = panel.find_elements(
            By.CSS_SELECTOR, "button[title='Edit axis values']"
        )
        for button in buttons:
            candidate_texts = [
                button.text or "",
                button.get_attribute("aria-label") or "",
            ]
            try:
                candidate_texts.extend(self.driver.execute_script(
                    """
                    const values = [];
                    let node = arguments[0];
                    for (let depth = 0; depth < 5 && node; depth += 1) {
                      node = node.parentElement;
                      if (node) values.push(node.innerText || '');
                    }
                    return values;
                    """,
                    button,
                ) or [])
            except Exception:
                pass
            for candidate in candidate_texts:
                parsed = self._variant_sizes_from_axis_text(candidate)
                if parsed:
                    extend(parsed)
                    break

        tables = panel.find_elements(By.CSS_SELECTOR, "table")
        for table in tables:
            # Some PIMBO layouts render "Size: M" in an axis-values cell.
            for cell in table.find_elements(By.CSS_SELECTOR, "tbody td"):
                extend(self._variant_sizes_from_axis_text(cell.text or ""))

            # Other layouts dedicate a table column to Size/Dydis/Rozmiar.
            headers = table.find_elements(By.CSS_SELECTOR, "thead th")
            size_columns = [
                index
                for index, header in enumerate(headers)
                if _clean(header.text).casefold() in {
                    "size",
                    "frame size",
                    "dydis",
                    "rėmo dydis",
                    "remo dydis",
                    "rozmiar",
                    "rozmiar ramy",
                }
            ]
            for row in table.find_elements(By.CSS_SELECTOR, "tbody tr"):
                cells = row.find_elements(By.CSS_SELECTOR, "td")
                for index in size_columns:
                    if index < len(cells):
                        extend((self._standalone_variant_size(cells[index].text),))
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
        if not _strip_html(before):
            raise PimAutomationError(
                "Description source is empty; Description MagicAI was not run"
            )
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
                # Keep the generated copy and translate this description field
                # itself into LT. This is intentionally distinct from the
                # product-wide Translate action.
                try:
                    translated = self.translate_current_description_to_lt(generated)
                    if _is_lithuanian_copy(translated):
                        return PimAiStepResult(
                            "description",
                            True,
                            translated != before,
                            attempt,
                            "MagicAI description translated to Lithuanian using Translate current field",
                        )
                    raise PimAutomationError(
                        "Description field translation did not produce Lithuanian text"
                    )
                except Exception as translation_error:
                    # The original full KROSS description is the safe final
                    # fallback if the field-level translator itself fails.
                    self.set_description_html(before)
                    return PimAiStepResult(
                        "description",
                        True,
                        False,
                        attempt,
                        "Description field translation failed; kept the complete "
                        f"KROSS description ({translation_error})",
                    )
            except Exception:
                self._cancel_magic(panel)
                try:
                    if self.description_html() != before:
                        self.set_description_html(before)
                except Exception:
                    pass
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
            const scopes = [];
            const combo = input.closest('[role="combobox"]');
            if (combo) scopes.push(combo);
            let node = input.parentElement;
            for (let depth = 0; node && depth < 4; depth++, node = node.parentElement) {
              if (!scopes.includes(node)) scopes.push(node);
            }
            for (const scope of scopes) {
              const matchingInputs = scope.querySelectorAll(
                'input[placeholder="Search categories..."]'
              );
              if (matchingInputs.length > 1) continue;
              const candidates = (scope.innerText || '').split(/\\n/)
                .map(v => v.trim()).filter(Boolean)
                .filter(v => !/search categories|product categor|magicai|suggest categor/i.test(v))
                .filter(v => !/^(category|categories|required|draft|in review|published|disabled|status|import)$/i.test(v));
              if (candidates.length) return candidates[0];
            }
            return '';
            """,
            search,
        )
        return _clean(value)

    @staticmethod
    def _valid_category(value: str) -> bool:
        normalized = _clean(value).casefold()
        return bool(normalized) and normalized not in {
            "import",
            "draft",
            "in review",
            "published",
            "disabled",
            "status",
            "category",
            "categories",
        }

    def suggest_category(self, family: str = "Dviračiai") -> PimAiStepResult:
        self.switch_locale("lt")
        self.open_section("general")
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
                lambda: (
                    value
                    if (value := self._selected_category()) != before
                    and self._valid_category(value)
                    else ""
                ),
                "Category MagicAI did not select a category",
                30.0,
            )
            return PimAiStepResult("category", True, True, 1, after)
        except TimeoutException as error:
            # MagicAI is allowed to retain an already-valid category. Do not
            # click it a second time and then wait for an artificial change.
            current = self._selected_category()
            if current == before and self._valid_category(current):
                return PimAiStepResult(
                    "category",
                    True,
                    False,
                    1,
                    f"MagicAI kept the existing category: {current}",
                )
            raise PimAutomationError(str(error)) from error

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

    @staticmethod
    def _checkbox_checked(element: Any) -> bool:
        return bool(
            element.is_selected()
            or element.get_attribute("aria-checked") == "true"
            or element.get_attribute("data-state") == "checked"
        )

    def _ensure_translation_checkbox(
        self,
        fallback_panel: Any,
        text: str,
        expected: bool,
    ) -> None:
        panel_title = "MagicAI — Translate product copy"

        def resolve() -> Any | None:
            panel = self._magic_panel(panel_title) or fallback_panel
            return self._panel_checkbox(panel, text)

        box = resolve()
        if box is None:
            raise PimAutomationError(f"{text} checkbox was not found")
        if self._checkbox_checked(box) != expected:
            self._click(box)
        self._wait_until(
            lambda: (
                candidate
                if (candidate := resolve()) is not None
                and self._checkbox_checked(candidate) == expected
                else None
            ),
            f"{text} checkbox did not become {'checked' if expected else 'unchecked'}",
            6.0,
        )

    def _current_field_translation_panel(self) -> Any | None:
        phrase = "translate current field"
        lower = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        upper = "abcdefghijklmnopqrstuvwxyz"
        dialogs = self._displayed(self.driver.find_elements(
            By.XPATH,
            "//*[@role='dialog' and .//*[contains(translate(normalize-space(.), "
            f"'{lower}', '{upper}'), '{phrase}')]]",
        ))
        if dialogs:
            return dialogs[-1]

        markers = self._displayed(self.driver.find_elements(
            By.XPATH,
            "//*[self::label or self::span or self::p or self::div]"
            "[contains(translate(normalize-space(.), "
            f"'{lower}', '{upper}'), '{phrase}')]",
        ))
        markers.sort(key=lambda item: len(_clean(getattr(item, "text", ""))))
        for marker in markers:
            containers = marker.find_elements(
                By.XPATH,
                "ancestor::div[.//button[normalize-space()='Translate']][1]",
            )
            visible = self._displayed(containers)
            if visible:
                return visible[0]
        return None

    def _description_translate_button(self) -> Any | None:
        self.open_section("general")
        iframe = self._find_visible(By.CSS_SELECTOR, "main iframe.tox-edit-area__iframe")
        if iframe is None:
            return None
        xpath = (
            "ancestor::div[.//button[normalize-space()='Translate' "
            "or contains(@title, 'Translate')]][1]"
            "//button[normalize-space()='Translate' or contains(@title, 'Translate')]"
        )
        buttons = self._displayed(iframe.find_elements(By.XPATH, xpath))
        return buttons[0] if buttons else None

    def _select_current_field_translation_target_lt(self, panel: Any) -> None:
        label_xpath = (
            ".//*[normalize-space()='Translate to']/following::select[1]"
        )
        native = self._displayed(panel.find_elements(By.XPATH, label_xpath))
        if not native:
            native = self._displayed(panel.find_elements(By.TAG_NAME, "select"))
        for element in native:
            selector = Select(element)
            for option in selector.options:
                text = _clean(option.text).casefold()
                if "lithuanian" in text or "lietuvi" in text or text.startswith("lt"):
                    selector.select_by_visible_text(option.text)
                    return

        combos = self._displayed(panel.find_elements(
            By.XPATH,
            ".//*[normalize-space()='Translate to']/following::*[@role='combobox'][1]",
        ))
        if not combos:
            combos = self._displayed(panel.find_elements(By.CSS_SELECTOR, "[role='combobox']"))
        if not combos:
            raise PimAutomationError("Description Translate to control was not found")
        self._click(combos[-1])
        options = self._wait_until(
            lambda: self._displayed(self.driver.find_elements(
                By.XPATH,
                "//*[@role='option' or self::button]"
                "[contains(normalize-space(), 'Lithuanian') "
                "or contains(normalize-space(), 'Lietuvi') "
                "or starts-with(normalize-space(), 'LT')]",
            )),
            "Lithuanian (LT) translation target was not found",
            8.0,
        )
        self._click(options[-1])

    def translate_current_description_to_lt(self, generated_html: str) -> str:
        """Translate the currently generated description field into Lithuanian."""

        self.switch_locale("lt")
        self.open_section("general")
        button = self._wait_until(
            self._description_translate_button,
            "Description field Translate button was not found",
            8.0,
        )
        self._click(button)
        panel = self._wait_until(
            self._current_field_translation_panel,
            "Description field translation dialog did not open",
            8.0,
        )
        current_field = self._panel_checkbox(panel, "Translate current field")
        if current_field is None:
            raise PimAutomationError("Translate current field checkbox was not found")
        checked = (
            current_field.is_selected()
            or current_field.get_attribute("aria-checked") == "true"
        )
        if not checked:
            self._click(current_field)
        self._select_current_field_translation_target_lt(panel)

        actions = self._displayed(
            panel.find_elements(By.XPATH, ".//button[normalize-space()='Translate']")
        )
        if not actions:
            raise PimAutomationError("Description field Translate action was not found")
        self._click(actions[-1])
        self._wait_until(
            lambda: self._current_field_translation_panel() is None,
            "Description field translation did not finish",
            120.0,
        )
        return self._wait_until(
            lambda: (
                current
                if (current := self.description_html()) != generated_html
                and _is_lithuanian_copy(current)
                else ""
            ),
            "Description field translation did not produce Lithuanian copy",
            30.0,
        )

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
            self._ensure_translation_checkbox(panel, language, True)
        self._ensure_translation_checkbox(
            panel,
            "Overwrite existing translations",
            overwrite,
        )

        panel = self._wait_until(
            lambda: self._magic_panel("MagicAI — Translate product copy"),
            "PIMBO translation panel disappeared before confirmation",
            6.0,
        )
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

    def save_and_verify(self, result: PimPreparationResult) -> PimPreparationResult:
        """Save a prepared Draft product and verify the version increment.

        This is intentionally opt-in: callers must have already prepared a
        ``READY_FOR_REVIEW`` result and explicitly choose an action labelled as
        saving.  The same checks used for manual-save verification protect
        against saving a different product or a non-Draft product.
        """

        if result.status != PimPreparationStatus.READY_FOR_REVIEW:
            return result.with_status(
                PimPreparationStatus.FAILED,
                error="Only a ready_for_review product can be saved automatically",
            )
        if self.product_id != result.product_id:
            return result.with_status(
                PimPreparationStatus.FAILED,
                error="A different PIMBO product is open; automatic Save was cancelled",
            )
        if self.current_status().casefold() != "draft":
            return result.with_status(
                PimPreparationStatus.BLOCKED_NON_DRAFT,
                error="Product is no longer Draft; automatic Save was cancelled",
            )
        if result.initial_version is None:
            return result.with_status(
                PimPreparationStatus.FAILED,
                error="Initial PIMBO product version was not available",
            )

        button = self.save_button()
        if button is None or not button.is_enabled() or not self.is_dirty():
            return result.with_status(
                PimPreparationStatus.FAILED,
                error="PIMBO form has no enabled Save action",
            )

        try:
            self._click(button)
            self._wait_until(
                lambda: not self.is_dirty(),
                "PIMBO still has unsaved changes after automatic Save",
                max(self.timeout, 20.0),
            )
            self._wait_until(
                lambda: (
                    version
                    if (version := self.current_version()) is not None
                    and version > result.initial_version
                    else None
                ),
                "PIMBO product version did not increase after automatic Save",
                max(self.timeout, 20.0),
            )
        except Exception as error:
            return result.with_status(PimPreparationStatus.FAILED, error=str(error))
        return result.with_status(PimPreparationStatus.SAVED_AUTOMATICALLY, error="")
