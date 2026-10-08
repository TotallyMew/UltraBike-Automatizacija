from __future__ import annotations

import hashlib
import re
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urljoin, urlsplit

from .catalogue import (
    CatalogueIndex,
    MatchResult,
    normalize_code,
    parse_number,
)
from .checkpoint import RunCheckpoint, utc_now
from .models import (
    FilterOption,
    OrbeaRunConfig,
    PimboFilterOptions,
    PimboFilterSpec,
    RunCancelled,
)


PIMBO_PRODUCTS_URL = "https://pim.bo.ultrabike.lt/dashboard/products"
STATUS_LABELS = ("Draft", "In Review", "Published", "Disabled")
STOCK_LABELS = ("Any", "In stock", "Out of stock")
COMPLETENESS_LABELS = ("<40%", "40–80%", "≥80%", "100%")
SORT_LABELS = ("Recent", "Least complete", "Most complete")


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\u00a0", " ")).strip()


def list_variant_code(value: Any) -> str:
    """Read an exposed Orbea code without absorbing a '+3' variant count."""
    from .website import template_code

    match = re.match(r"([A-Z][A-Z0-9]{3}(?:[A-Z0-9]{4})?)\b", _clean(value).upper())
    return match[1] if match and template_code(match[1]) else ""


def _same_label(left: Any, right: Any) -> bool:
    def normalized(value: Any) -> str:
        return (
            _clean(value)
            .casefold()
            .replace("–", "-")
            .replace("—", "-")
            .replace("≥", ">=")
        )

    return normalized(left) == normalized(right)


class PimboBrowserClient:
    """Cancellable controller for the existing authenticated Pimbo driver."""

    def __init__(
        self,
        driver: Any,
        *,
        cancellation: Any = None,
        search_term: str = "orbea",
        expected_brand: str | None = "orbea",
        run_name: str = "Orbea",
    ) -> None:
        self.driver = driver
        self.cancellation = cancellation
        self.search_term = _clean(search_term)
        self.expected_brand = _clean(expected_brand).casefold() if expected_brand else ""
        self.run_name = _clean(run_name) or "Pimbo"

    @staticmethod
    def _by():
        from selenium.webdriver.common.by import By

        return By

    @staticmethod
    def _keys():
        from selenium.webdriver.common.keys import Keys

        return Keys

    def _cancelled(self) -> bool:
        token = self.cancellation
        if token is None:
            return False
        if hasattr(token, "is_cancelled"):
            return bool(token.is_cancelled())
        if hasattr(token, "is_set"):
            return bool(token.is_set())
        return False

    def _check_cancelled(self) -> None:
        if self._cancelled():
            raise RunCancelled(f"The {self.run_name} run was stopped")

    def _wait_until(
        self,
        condition: Callable[[], Any],
        timeout: float,
        message: str,
    ) -> Any:
        deadline = time.monotonic() + timeout
        last_error: BaseException | None = None
        while time.monotonic() < deadline:
            self._check_cancelled()
            try:
                value = condition()
                if value:
                    return value
            except RunCancelled:
                raise
            except Exception as error:
                last_error = error
            time.sleep(0.15)
        detail = f": {last_error}" if last_error else ""
        raise TimeoutError(f"{message}{detail}")

    def _safe_click(
        self,
        target: Any | Callable[[], Any],
        message: str,
        *,
        attempts: int = 5,
    ) -> Any:
        """Click a PIMBO control even when its sticky toolbar overlaps it.

        PIMBO can replace controls while React refreshes the product list, and
        its fixed header sometimes covers the native WebDriver click point.
        Re-resolve callable targets on every attempt and use a DOM click when
        the native pointer click is intercepted.
        """

        resolve = target if callable(target) else lambda: target
        last_error: BaseException | None = None
        for _attempt in range(max(1, attempts)):
            self._check_cancelled()
            try:
                element = resolve()
                if element is None:
                    raise RuntimeError("control is not available")
                try:
                    self.driver.execute_script(
                        "arguments[0].scrollIntoView({block:'center', inline:'nearest'});",
                        element,
                    )
                except Exception:
                    # Some lightweight test drivers do not implement scrolling.
                    pass
                try:
                    element.click()
                except Exception:
                    self.driver.execute_script("arguments[0].click();", element)
                return element
            except RunCancelled:
                raise
            except Exception as error:
                last_error = error
                time.sleep(0.15)
        detail = f": {last_error}" if last_error else ""
        raise RuntimeError(f"{message}{detail}")

    def _on_products_page(self) -> bool:
        return "/dashboard/products" in self.driver.current_url and not re.search(
            r"/dashboard/products/[^/?#]+", self.driver.current_url
        )

    def ensure_products_page(self, timeout: float = 20.0) -> None:
        By = self._by()
        if not self._on_products_page():
            if re.search(r"/dashboard/products/[^/?#]+", self.driver.current_url or ""):
                from Managers.PimboProductEditor import PimboProductEditor

                if PimboProductEditor(self.driver).is_dirty():
                    raise RuntimeError(
                        "The open PIMBO product has unsaved changes; the read-only "
                        f"{self.run_name} tool will not discard them."
                    )
            self.driver.get(PIMBO_PRODUCTS_URL)
        try:
            self._wait_until(
                lambda: self._on_products_page()
                and self.driver.find_elements(
                    By.CSS_SELECTOR, "input[placeholder='Search...']"
                ),
                timeout,
                "Pimbo Products did not become ready",
            )
        except TimeoutError as error:
            raise RuntimeError(
                "Pimbo is not ready. Log in using the app browser and open Products."
            ) from error

    def _filter_dialog(self) -> Any | None:
        By = self._by()
        for dialog in self.driver.find_elements(By.CSS_SELECTOR, "[role='dialog']"):
            try:
                if dialog.is_displayed():
                    return dialog
            except Exception:
                continue
        return None

    def _filter_button(self) -> Any:
        By = self._by()
        buttons = self.driver.find_elements(
            By.XPATH,
            "//button[@aria-haspopup='dialog' and contains(normalize-space(.), 'Filter')]",
        )
        displayed = [button for button in buttons if button.is_displayed()]
        if len(displayed) != 1:
            raise RuntimeError(f"Expected one Pimbo Filter button, found {len(displayed)}")
        return displayed[0]

    def _open_filter_dialog(self) -> Any:
        dialog = self._filter_dialog()
        if dialog is not None:
            return dialog
        self._safe_click(
            self._filter_button,
            "The Pimbo Filter button remained covered",
        )
        return self._wait_until(
            self._filter_dialog, 5.0, "The Pimbo filter dialog did not open"
        )

    def _close_filter_dialog(self) -> None:
        if self._filter_dialog() is not None:
            self._safe_click(
                self._filter_button,
                "The Pimbo Filter button remained covered",
            )
            self._wait_until(
                lambda: self._filter_dialog() is None,
                5.0,
                "The Pimbo filter dialog did not close",
            )

    @staticmethod
    def _button_is_active(button: Any) -> bool:
        classes = button.get_attribute("class") or ""
        data_active = button.get_attribute("data-active")
        return (
            "bg-foreground" in classes
            or button.get_attribute("aria-pressed") == "true"
            or data_active in {"", "true"} and data_active is not None
        )

    def _button(self, label: str) -> Any:
        By = self._by()
        dialog = self._open_filter_dialog()
        buttons = [
            button
            for button in dialog.find_elements(By.CSS_SELECTOR, "button")
            if _same_label(button.text, label)
        ]
        if len(buttons) != 1:
            raise RuntimeError(
                f"Expected one {label!r} filter button, found {len(buttons)}"
            )
        return buttons[0]

    def _active_button_labels(self, labels: tuple[str, ...]) -> tuple[str, ...]:
        active: list[str] = []
        for label in labels:
            try:
                if self._button_is_active(self._button(label)):
                    active.append(label)
            except RuntimeError:
                continue
        return tuple(active)

    def _set_button(self, label: str, active: bool) -> None:
        button = self._button(label)
        if self._button_is_active(button) == active:
            return
        self._safe_click(
            lambda: self._button(label),
            f"The Pimbo filter {label!r} remained covered",
        )
        self._wait_until(
            lambda: self._button_is_active(self._button(label)) == active,
            5.0,
            f"Pimbo filter {label!r} did not change",
        )

    def _select_label(self, select: Any, index: int) -> str:
        label = self.driver.execute_script(
            """
            const select = arguments[0];
            let node = select;
            for (let depth = 0; node && depth < 6; depth++, node = node.parentElement) {
              const direct = Array.from(node.children || []).find(child =>
                child.tagName === 'LABEL' || child.getAttribute?.('data-slot') === 'label');
              if (direct?.textContent?.trim()) return direct.textContent.trim();
              const previous = node.previousElementSibling;
              if (previous?.tagName === 'LABEL' && previous.textContent.trim()) {
                return previous.textContent.trim();
              }
            }
            return '';
            """,
            select,
        )
        if label:
            return _clean(label)
        return ("Brand", "Family", "Category", "Source", "Locale")[index] if index < 5 else f"Select {index + 1}"

    def _selects(self) -> dict[str, Any]:
        By = self._by()
        dialog = self._open_filter_dialog()
        result: dict[str, Any] = {}
        for index, select in enumerate(dialog.find_elements(By.CSS_SELECTOR, "select")):
            result[self._select_label(select, index).casefold()] = select
        return result

    def _named_select(self, label: str) -> Any:
        selects = self._selects()
        direct = selects.get(label.casefold())
        if direct is not None:
            return direct
        for name, select in selects.items():
            if label.casefold() in name:
                return select
        raise RuntimeError(f"The Pimbo {label} select was not found")

    def _select_options(self, label: str) -> tuple[FilterOption, ...]:
        By = self._by()
        select = self._named_select(label)
        options: list[FilterOption] = []
        for option in select.find_elements(By.TAG_NAME, "option"):
            group = ""
            try:
                parent = option.find_element(By.XPATH, "..")
                if parent.tag_name.casefold() == "optgroup":
                    group = parent.get_attribute("label") or ""
            except Exception:
                pass
            options.append(
                FilterOption(
                    value=str(option.get_attribute("value") or ""),
                    label=_clean(option.text),
                    group=_clean(group),
                )
            )
        return tuple(options)

    def _set_select_value(self, label: str, value: str) -> None:
        select = self._named_select(label)
        options = self._select_options(label)
        desired = str(value or "")
        if not desired:
            desired = options[0].value if options else ""
        elif desired not in {option.value for option in options}:
            matching = next(
                (option for option in options if _same_label(option.label, desired)), None
            )
            if matching is None:
                raise ValueError(f"Pimbo {label} option {value!r} no longer exists")
            desired = matching.value
        if str(select.get_attribute("value") or "") == desired:
            return
        self.driver.execute_script(
            """
            const select = arguments[0];
            const value = arguments[1];
            if (select.tomselect) {
              select.tomselect.setValue(value, false);
            } else {
              select.value = value;
              select.dispatchEvent(new Event('input', {bubbles: true}));
              select.dispatchEvent(new Event('change', {bubbles: true}));
            }
            """,
            select,
            desired,
        )
        self._wait_until(
            lambda: str(self._named_select(label).get_attribute("value") or "") == desired,
            5.0,
            f"Pimbo {label} did not change",
        )

    def discover_filter_options(self) -> PimboFilterOptions:
        self.ensure_products_page()
        self._open_filter_dialog()
        try:
            available_buttons = {
                _clean(button.text)
                for button in self._filter_dialog().find_elements(
                    self._by().CSS_SELECTOR, "button"
                )
                if _clean(button.text)
            }

            def fixed(labels: tuple[str, ...]) -> tuple[FilterOption, ...]:
                return tuple(
                    FilterOption(label, label)
                    for label in labels
                    if any(_same_label(label, value) for value in available_buttons)
                )

            return PimboFilterOptions(
                statuses=fixed(STATUS_LABELS),
                families=self._select_options("Family"),
                categories=self._select_options("Category"),
                sources=self._select_options("Source"),
                stock=fixed(STOCK_LABELS),
                completeness_locales=self._select_options("Locale"),
                completeness_buckets=fixed(COMPLETENESS_LABELS),
                sort=fixed(SORT_LABELS),
            )
        finally:
            self._close_filter_dialog()

    def _set_search(self) -> None:
        By = self._by()
        Keys = self._keys()
        search = self._wait_until(
            lambda: next(
                iter(
                    self.driver.find_elements(
                        By.CSS_SELECTOR, "input[placeholder='Search...']"
                    )
                ),
                None,
            ),
            10.0,
            "The Pimbo search field did not appear",
        )
        desired = self.search_term
        if _clean(search.get_attribute("value")).casefold() != desired.casefold():
            first_search = [search]

            def current_search() -> Any:
                if first_search:
                    return first_search.pop()
                return next(
                    iter(
                        self.driver.find_elements(
                            By.CSS_SELECTOR, "input[placeholder='Search...']"
                        )
                    ),
                    None,
                )

            search = self._safe_click(
                current_search,
                "The Pimbo search field remained covered",
            )
            search.send_keys(Keys.CONTROL, "a")
            search.send_keys(desired)
            search.send_keys(Keys.ENTER)
            self._wait_until(
                lambda: _clean(
                    self.driver.find_element(
                        By.CSS_SELECTOR, "input[placeholder='Search...']"
                    ).get_attribute("value")
                ).casefold() == desired.casefold(),
                5.0,
                f"The fixed {self.run_name} search was not applied",
            )

    def apply_filters(self, spec: PimboFilterSpec) -> None:
        self.ensure_products_page()
        self._set_search()
        self._open_filter_dialog()
        try:
            desired_statuses = set(spec.statuses)
            unknown_statuses = desired_statuses - set(STATUS_LABELS)
            if unknown_statuses:
                raise ValueError(f"Unknown Pimbo statuses: {sorted(unknown_statuses)}")
            for label in STATUS_LABELS:
                self._set_button(label, label in desired_statuses)

            # Brand is deliberately hidden in supplier tabs. Reset it so the
            # fixed supplier search is the sole brand restriction.
            self._set_select_value("Brand", "")
            self._set_select_value("Family", spec.family_id)
            self._set_select_value("Category", spec.category_id)
            self._set_select_value("Source", spec.source_id)
            self._set_select_value("Locale", spec.completeness_locale)

            if spec.stock not in STOCK_LABELS:
                raise ValueError(f"Unknown Pimbo stock filter: {spec.stock}")
            self._set_button(spec.stock, True)

            desired_buckets = set(spec.completeness_buckets)
            unknown_buckets = desired_buckets - set(COMPLETENESS_LABELS)
            if unknown_buckets:
                raise ValueError(
                    f"Unknown completeness filters: {sorted(unknown_buckets)}"
                )
            for label in COMPLETENESS_LABELS:
                self._set_button(label, label in desired_buckets)

            if spec.sort not in SORT_LABELS:
                raise ValueError(f"Unknown Pimbo sort option: {spec.sort}")
            self._set_button(spec.sort, True)
        finally:
            self._close_filter_dialog()

        self.go_to_page(1)
        self._verify_filters(spec)

    def _verify_filters(self, spec: PimboFilterSpec) -> None:
        By = self._by()
        search = self.driver.find_element(
            By.CSS_SELECTOR, "input[placeholder='Search...']"
        )
        if _clean(search.get_attribute("value")).casefold() != self.search_term.casefold():
            raise RuntimeError("Pimbo search verification failed")

        self._open_filter_dialog()
        try:
            if set(self._active_button_labels(STATUS_LABELS)) != set(spec.statuses):
                raise RuntimeError("Pimbo status filter verification failed")
            if set(self._active_button_labels(STOCK_LABELS)) != {spec.stock}:
                raise RuntimeError("Pimbo stock filter verification failed")
            if set(self._active_button_labels(COMPLETENESS_LABELS)) != set(
                spec.completeness_buckets
            ):
                raise RuntimeError("Pimbo completeness filter verification failed")
            if set(self._active_button_labels(SORT_LABELS)) != {spec.sort}:
                raise RuntimeError("Pimbo sort verification failed")
            for label, expected in (
                ("Family", spec.family_id),
                ("Category", spec.category_id),
                ("Source", spec.source_id),
                ("Locale", spec.completeness_locale),
            ):
                select = self._named_select(label)
                options = self._select_options(label)
                desired = expected or (options[0].value if options else "")
                if desired not in {option.value for option in options}:
                    matching = next(
                        (
                            option
                            for option in options
                            if _same_label(option.label, desired)
                        ),
                        None,
                    )
                    desired = matching.value if matching else desired
                if str(select.get_attribute("value") or "") != desired:
                    raise RuntimeError(f"Pimbo {label} verification failed")
        finally:
            self._close_filter_dialog()

        rows = self._wait_for_rows(allow_empty=True)
        for row in rows[:10]:
            cells = row.find_elements(By.CSS_SELECTOR, "td")
            brand = _clean(cells[2].text).casefold() if len(cells) > 2 else ""
            status = _clean(cells[6].text) if len(cells) > 6 else ""
            stock = parse_number(cells[5].text) if len(cells) > 5 else None
            if self.expected_brand and brand != self.expected_brand:
                raise RuntimeError(f"Pimbo returned a non-{self.run_name} row")
            if spec.statuses and status not in spec.statuses:
                raise RuntimeError("Pimbo returned a row outside the selected status filters")
            if spec.stock == "In stock" and (stock or 0) <= 0:
                raise RuntimeError("Pimbo returned an out-of-stock row")
            if spec.stock == "Out of stock" and (stock or 0) > 0:
                raise RuntimeError("Pimbo returned an in-stock row")

    def _rows_signature(self, rows: list[Any]) -> tuple[str, ...]:
        return tuple(self.driver.execute_script(
            """return arguments[0].map(row => {
                const link = row.querySelector("a[href*='/dashboard/products/']");
                return link ? link.href : row.textContent.trim();
            });""", rows,
        ))

    def _wait_for_rows(
        self, *, allow_empty: bool = False,
        previous_rows: tuple[str, ...] | None = None,
    ) -> list[Any]:
        By = self._by()
        deadline = time.monotonic() + 15.0
        last_error: BaseException | None = None
        stable_signature = None
        stable_since = time.monotonic()
        while time.monotonic() < deadline:
            self._check_cancelled()
            try:
                if self._on_products_page():
                    rows = self.driver.find_elements(
                        By.CSS_SELECTOR,
                        "main table tbody tr[data-slot='table-row']",
                    )
                    loading = self.driver.execute_script(
                        "return !!document.querySelector(\"main [aria-busy='true'], main table .animate-spin, main [data-loading='true']\");"
                    )
                    signature = self._rows_signature(rows)
                    ready = not loading and (rows or (allow_empty and self.driver.find_elements(By.CSS_SELECTOR, "main table")))
                    if previous_rows is not None and signature == previous_rows:
                        ready = False
                    if not ready or signature != stable_signature:
                        stable_signature = signature if ready else None
                        stable_since = time.monotonic()
                    elif time.monotonic() - stable_since >= 0.45:
                        return rows
            except Exception as error:
                last_error = error
                stable_signature = None
                stable_since = time.monotonic()
            time.sleep(0.15)
        detail = f": {last_error}" if last_error else ""
        raise TimeoutError(f"The Pimbo product list did not load{detail}")

    def _page_input(self) -> Any | None:
        By = self._by()
        candidates = self.driver.find_elements(
            By.CSS_SELECTOR, "main input[type='number'][min='1'][max]"
        )
        if len(candidates) > 1:
            raise RuntimeError(f"Expected one Pimbo page input, found {len(candidates)}")
        return candidates[0] if candidates else None

    def go_to_page(self, page_number: int) -> None:
        Keys = self._keys()
        page_input = self._page_input()
        if page_input is None:
            if page_number == 1:
                return
            raise RuntimeError("Pimbo pagination was not found")
        current = int(page_input.get_attribute("value") or "1")
        if current == page_number:
            self._wait_for_rows(allow_empty=True)
            return
        previous_rows = self._rows_signature(self._wait_for_rows(allow_empty=True))
        page_input = self._safe_click(
            self._page_input,
            "The Pimbo page field remained covered",
        )
        # React can submit a request for every digit typed (2, then 23).
        # Set the complete number in one input event to avoid racing requests.
        self.driver.execute_script(
            """const input = arguments[0];
            const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
            setter.call(input, arguments[1]);
            input.dispatchEvent(new Event('input', {bubbles: true}));
            input.dispatchEvent(new Event('change', {bubbles: true}));""",
            page_input, str(page_number),
        )
        page_input.send_keys(Keys.ENTER)
        self._wait_until(
            lambda: self._page_input() is not None
            and int(self._page_input().get_attribute("value") or "0") == page_number,
            12.0,
            f"Pimbo did not move to page {page_number}",
        )
        self._wait_for_rows(allow_empty=True, previous_rows=previous_rows)

    def _totals(self) -> tuple[int | None, int]:
        By = self._by()
        headings = self.driver.find_elements(
            By.XPATH, "//main//h1[contains(normalize-space(.), 'Products')]"
        )
        products = None
        if headings:
            match = re.search(r"\(([\d,.\s]+)\)", headings[0].text)
            if match:
                products = int(re.sub(r"\D", "", match.group(1)))
        page_input = self._page_input()
        pages = int(page_input.get_attribute("max") or "1") if page_input else 1
        return products, pages

    @staticmethod
    def _row_key(
        snapshot: dict[str, Any], page_number: int, row_number: int
    ) -> str:
        identity = snapshot.get("row_href") or (
            f"{page_number}\0{row_number}\0"
            f"{snapshot.get('title', '')}\0{snapshot.get('visible_code', '')}"
        )
        return hashlib.sha1(str(identity).encode("utf-8")).hexdigest()

    def _row_snapshot(self, row_index: int) -> tuple[Any, dict[str, Any]]:
        By = self._by()
        rows = self.driver.find_elements(
            By.CSS_SELECTOR, "main table tbody tr[data-slot='table-row']"
        )
        if row_index >= len(rows):
            raise IndexError(f"Pimbo product row {row_index + 1} disappeared")
        row = rows[row_index]
        cells = row.find_elements(By.CSS_SELECTOR, "td")
        title_elements = row.find_elements(By.CSS_SELECTOR, "span.font-medium[title]")
        code_elements = row.find_elements(By.CSS_SELECTOR, "span.font-mono")
        product_links = row.find_elements(
            By.CSS_SELECTOR, "a[href*='/dashboard/products/']"
        )
        title = (
            _clean(title_elements[0].get_attribute("title") or title_elements[0].text)
            if title_elements
            else ""
        )
        visible_code = _clean(code_elements[0].text) if code_elements else ""
        return row, {
            "title": title,
            "visible_code": visible_code,
            "row_href": product_links[0].get_attribute("href") if product_links else "",
            "brand": _clean(cells[2].text) if len(cells) > 2 else "",
            "variant_count": parse_number(cells[4].text) if len(cells) > 4 else None,
            "list_stock": parse_number(cells[5].text) if len(cells) > 5 else None,
            "list_status": _clean(cells[6].text) if len(cells) > 6 else "",
        }

    def _page_list_snapshots(self) -> list[dict[str, Any]]:
        """Read the rendered list page in one browser call, without clicking rows."""
        self._check_cancelled()
        snapshots = self.driver.execute_script(
            r"""return Array.from(document.querySelectorAll("main table tbody tr[data-slot='table-row']"), row => {
                const cells = Array.from(row.children).filter(cell => cell.tagName === 'TD');
                const text = node => (node?.textContent || '').replace(/\s+/g, ' ').trim();
                const title = row.querySelector('span.font-medium[title]');
                const code = cells[1]?.querySelector('span.font-mono');
                const link = row.querySelector("a[href*='/dashboard/products/']");
                return {
                    title: title?.getAttribute('title') || text(title) || row.querySelector('img[alt]')?.getAttribute('alt') || '',
                    visible_code: text(code),
                    row_href: link?.href || '',
                    brand: text(cells[2]),
                    variant_count: text(cells[4]),
                    list_stock: text(cells[5]),
                    list_status: text(cells[6]),
                };
            });"""
        )
        if not isinstance(snapshots, list):
            raise RuntimeError("The Pimbo product list could not be read")
        for snapshot in snapshots:
            for key in ('title', 'visible_code', 'row_href', 'brand', 'list_status'):
                snapshot[key] = _clean(snapshot.get(key))
            for key in ('variant_count', 'list_stock'):
                snapshot[key] = parse_number(snapshot.get(key))
        return snapshots

    @classmethod
    def _list_row_key(cls, snapshot: dict[str, Any], page_number: int, row_number: int) -> str:
        if snapshot.get('row_href'):
            return cls._row_key(snapshot, page_number, row_number)
        code = list_variant_code(snapshot.get('visible_code') or snapshot.get('sku'))
        if code:
            # Stable across pagination, title edits and changing '+N' labels.
            return hashlib.sha1(f"pimbo-list-sku\0{code}".encode('utf-8')).hexdigest()
        return cls._row_key(snapshot, page_number, row_number)

    @staticmethod
    def _list_row_detail(snapshot: dict[str, Any]) -> dict[str, Any]:
        sku = list_variant_code(snapshot.get('visible_code'))
        url = urljoin(PIMBO_PRODUCTS_URL, str(snapshot.get('row_href') or '')) if snapshot.get('row_href') else ''
        parts = urlsplit(url)
        product = re.fullmatch(r'/dashboard/products/([^/]+)/?', parts.path)
        if parts.scheme != 'https' or parts.hostname != urlsplit(PIMBO_PRODUCTS_URL).hostname or product is None:
            url, product_id = '', ''
        else:
            product_id = product[1]
        return {
            'sku': sku, 'sku_source': 'Pimbo product list',
            'product_url': url, 'product_id': product_id,
            # The list exposes aggregate stock, not this variant's stock.
            'variant_stock': None, 'variant_count_found': None,
        }

    def _restore_list(self, page: int, filters: PimboFilterSpec) -> None:
        try:
            self.driver.back()
            self._wait_until(
                self._on_products_page, 12.0, "Pimbo did not return to Products"
            )
            self._wait_for_rows(allow_empty=True)
        except RunCancelled:
            raise
        except Exception:
            self.driver.get(PIMBO_PRODUCTS_URL)
            self.apply_filters(filters)

        try:
            search = self.driver.find_element(
                self._by().CSS_SELECTOR, "input[placeholder='Search...']"
            ).get_attribute("value")
        except Exception:
            search = ""
        if _clean(search).casefold() != self.search_term.casefold():
            self.apply_filters(filters)
        self.go_to_page(page)

    @staticmethod
    def _blank_entry_fields() -> dict[str, Any]:
        return MatchResult("", "", None).catalogue_fields()

    def collect(
        self,
        catalogue: CatalogueIndex,
        checkpoint: RunCheckpoint,
        config: OrbeaRunConfig,
        *,
        retry_failed: bool = False,
        row_progress: Callable[[int, int | None, str], None] | None = None,
        log: Callable[[str], None] | None = None,
    ) -> None:
        self.apply_filters(config.filters)
        products, pages = self._totals()
        checkpoint.set_totals(products=products, pages=pages)
        processed = checkpoint.processed_row_keys(retry_failed=retry_failed)
        # Older partial scans used position keys for rows without links. Retain
        # their completed work when resuming with the exposed list code.
        for saved in checkpoint.results:
            if saved.get('row_key') in processed:
                processed.add(self._list_row_key(saved, saved.get('page', 1), saved.get('row', 1)))
        product_ids = checkpoint.known_product_ids()
        newly_scanned = 0
        visited_rows = 0
        checkpoint.data['scan_source'] = 'Pimbo product list'
        checkpoint.data['scan_completed'] = False

        if log:
            log(f"Filtered Pimbo list: {products or 'unknown'} products across {pages} pages")
            log("Reading exposed list codes and titles; product and Variants pages are not opened")
            if config.product_code_prefix:
                log(f"Product code must start with: {config.product_code_prefix}")
        for page_number in range(1, pages + 1):
            self._check_cancelled()
            products, current_pages = self._totals()
            checkpoint.set_totals(products=products, pages=current_pages)
            if page_number > current_pages:
                break
            self.go_to_page(page_number)
            self._wait_for_rows(allow_empty=True)
            snapshots = self._page_list_snapshots()
            for row_number, snapshot in enumerate(snapshots, 1):
                self._check_cancelled()
                if config.max_products is not None and newly_scanned >= config.max_products:
                    checkpoint.data['scan_completed'] = False
                    checkpoint.save()
                    return
                visited_rows += 1
                if config.product_code_prefix and not snapshot['visible_code'].upper().startswith(config.product_code_prefix):
                    if row_progress:
                        row_progress(visited_rows, products,
                            f"Skipped {snapshot['visible_code'] or '(no code)'}: code does not start with {config.product_code_prefix}")
                    continue
                row_key = self._list_row_key(snapshot, page_number, row_number)
                if row_key in processed:
                    if row_progress:
                        row_progress(visited_rows, products, "Reusing a saved list row")
                    continue
                likely, candidate_reason = catalogue.is_likely_bicycle(snapshot['visible_code'], snapshot['title'])
                detail = self._list_row_detail(snapshot)
                if not config.all_products and not likely:
                    match = MatchResult('excluded', 'catalogue prefilter', None, 'No bicycle code/title candidate')
                elif detail['product_id'] and detail['product_id'] in product_ids:
                    match = MatchResult('duplicate', 'Pimbo product ID', None, 'This Pimbo product was already processed')
                elif not detail['sku']:
                    match = MatchResult('no_variant', 'Pimbo product list', None, 'No recognised Orbea code was exposed in this list row')
                else:
                    match = MatchResult('unmatched', 'Pending Orbea TTCC search', None, 'List code saved; URL lookup follows the Pimbo scan')
                result = {
                    'row_key': row_key, 'page': page_number, 'row': row_number,
                    'scanned_at': utc_now(), 'candidate_reason': candidate_reason,
                    **snapshot, **detail,
                    'status': match.status, 'match_method': match.method,
                    'note': match.note, **match.catalogue_fields(),
                }
                checkpoint.upsert_result(result)
                processed.add(row_key)
                if detail['product_id']:
                    product_ids.add(detail['product_id'])
                newly_scanned += 1
                if row_progress:
                    row_progress(visited_rows, products, f"{result.get('sku') or snapshot['visible_code']} → {result['status']}")

        checkpoint.data['scan_completed'] = True
        checkpoint.data['scan_completed_at'] = utc_now()
        checkpoint.save()
