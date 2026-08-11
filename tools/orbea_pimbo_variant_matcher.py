r"""Collect one real Pimbo variant SKU per Orbea bicycle and match it to Orbea.

The tool is deliberately read-only in Pimbo.  It applies these filters:

* search: ``orbea``
* status: ``Draft``
* stock: ``In stock``

It scans every filtered list row, opens likely bicycle products, selects the
Variants tab, and reads one in-stock SKU (falling back to the first SKU).
Progress is checkpointed after every row, so Ctrl+C is safe and the next run
resumes.  A formatted Excel report is built from the checkpoint at the end.

Typical use from the project folder:

    .\.venv\Scripts\python.exe tools\orbea_pimbo_variant_matcher.py

Use ``--all-products`` only when every Orbea accessory/component should also
be opened.  The default still scans every row, but only opens rows whose code
or title can plausibly belong to a bicycle in the catalogue.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from xml.etree import ElementTree as ET


PIMBO_PRODUCTS_URL = "https://pim.bo.ultrabike.lt/dashboard/products"
DEFAULT_CATALOGUE = (
    Path.home()
    / "Desktop"
    / "Orbea-Scraper"
    / "data"
    / "output"
    / "orbea_bicycle_catalogue.xlsx"
)
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parents[1] / "output" / "orbea_pimbo"
CHECKPOINT_VERSION = 1
IDENTIFIER_RE = re.compile(r"\b([A-Z][A-Z0-9]*TTCC)\b", re.IGNORECASE)
SKU_RE = re.compile(r"\b([A-Z][A-Z0-9]{4,})\b", re.IGNORECASE)
YEAR_SUFFIX_RE = re.compile(r"\s+20\d{2}$")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_code(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def first_code_token(value: Any) -> str:
    match = SKU_RE.search(str(value or "").upper())
    return normalize_code(match.group(1)) if match else ""


def normalize_name(value: Any) -> str:
    text = str(value or "").upper()
    text = re.sub(r"\bORBEA\b", " ", text)
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def model_key(value: Any) -> str:
    return YEAR_SUFFIX_RE.sub("", normalize_name(value))


def parse_number(value: Any) -> float | int | None:
    if value is None:
        return None
    text = str(value).strip().replace("\u00a0", "").replace(",", ".")
    if not text or text in {"—", "-", "N/A"}:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    number = float(match.group(0))
    return int(number) if number.is_integer() else number


def column_index(cell_reference: str) -> int:
    letters = re.match(r"[A-Z]+", cell_reference.upper())
    if not letters:
        return 0
    result = 0
    for char in letters.group(0):
        result = result * 26 + ord(char) - ord("A") + 1
    return result - 1


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        xml = archive.read("xl/sharedStrings.xml")
    except KeyError:
        return []
    root = ET.fromstring(xml)
    namespace = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    return [
        "".join(node.text or "" for node in item.findall(".//x:t", namespace))
        for item in root.findall("x:si", namespace)
    ]


def _sheet_xml_path(archive: zipfile.ZipFile, sheet_name: str) -> str:
    main_ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel_ns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    package_rel_ns = "http://schemas.openxmlformats.org/package/2006/relationships"

    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    relationship_id = None
    for sheet in workbook.findall(f".//{{{main_ns}}}sheet"):
        if sheet.get("name") == sheet_name:
            relationship_id = sheet.get(f"{{{rel_ns}}}id")
            break
    if not relationship_id:
        raise ValueError(f"Worksheet {sheet_name!r} was not found")

    relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    target = None
    for relationship in relationships.findall(f"{{{package_rel_ns}}}Relationship"):
        if relationship.get("Id") == relationship_id:
            target = relationship.get("Target")
            break
    if not target:
        raise ValueError(f"Worksheet relationship for {sheet_name!r} was not found")

    target = target.replace("\\", "/").lstrip("/")
    if target.startswith("xl/"):
        return target
    return f"xl/{target}"


def read_xlsx_rows(path: Path, sheet_name: str) -> list[list[Any]]:
    """Read cell values from one .xlsx worksheet without modifying the file."""

    namespace = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    with zipfile.ZipFile(path) as archive:
        shared = _shared_strings(archive)
        sheet_path = _sheet_xml_path(archive, sheet_name)
        root = ET.fromstring(archive.read(sheet_path))

    rows: list[list[Any]] = []
    for row_node in root.findall(f".//{{{namespace}}}sheetData/{{{namespace}}}row"):
        values: dict[int, Any] = {}
        for cell in row_node.findall(f"{{{namespace}}}c"):
            index = column_index(cell.get("r", "A1"))
            cell_type = cell.get("t")
            value_node = cell.find(f"{{{namespace}}}v")
            inline_node = cell.find(f"{{{namespace}}}is")
            value: Any = None

            if cell_type == "inlineStr" and inline_node is not None:
                value = "".join(
                    node.text or ""
                    for node in inline_node.findall(f".//{{{namespace}}}t")
                )
            elif value_node is not None:
                raw = value_node.text or ""
                if cell_type == "s":
                    value = shared[int(raw)] if raw else ""
                elif cell_type == "b":
                    value = raw == "1"
                elif cell_type in {"str", "e"}:
                    value = raw
                else:
                    try:
                        number = float(raw)
                        value = int(number) if number.is_integer() else number
                    except ValueError:
                        value = raw
            values[index] = value

        if values:
            width = max(values) + 1
            rows.append([values.get(index) for index in range(width)])
    return rows


@dataclass(frozen=True)
class CatalogueEntry:
    prefix: str
    template_code: str
    model: str
    year: int | None
    category: str
    subcategory: str
    product_link: str
    identifiers: str
    unique_model_id: str
    regional_listings: int

    @property
    def model_key(self) -> str:
        return model_key(self.model)


@dataclass(frozen=True)
class MatchResult:
    status: str
    method: str
    entry: CatalogueEntry | None
    note: str = ""


class CatalogueIndex:
    def __init__(self, entries: Iterable[CatalogueEntry]):
        grouped: dict[str, dict[str, list[CatalogueEntry]]] = {}
        for entry in entries:
            grouped.setdefault(entry.prefix, {}).setdefault(entry.model_key, []).append(entry)

        self.by_prefix: dict[str, list[CatalogueEntry]] = {}
        for prefix, model_groups in grouped.items():
            canonical: list[CatalogueEntry] = []
            for candidates in model_groups.values():
                canonical.append(
                    max(
                        candidates,
                        key=lambda entry: (
                            entry.regional_listings,
                            entry.year is not None,
                            entry.year or 0,
                            bool(entry.product_link),
                        ),
                    )
                )
            self.by_prefix[prefix] = canonical

        self.prefixes = sorted(self.by_prefix, key=len, reverse=True)
        by_model: dict[str, list[CatalogueEntry]] = {}
        for candidates in self.by_prefix.values():
            for entry in candidates:
                by_model.setdefault(entry.model_key, []).append(entry)
        self.by_model = by_model
        self.model_keys = sorted(by_model, key=lambda value: (-len(value), value))

    @classmethod
    def from_workbook(cls, path: Path) -> "CatalogueIndex":
        rows = read_xlsx_rows(path, "Unique Models")
        if not rows:
            raise ValueError("The catalogue's Unique Models sheet is empty")

        headers = {str(name): index for index, name in enumerate(rows[0]) if name is not None}
        required = {
            "Model",
            "Year",
            "Category",
            "Subcategory",
            "Regional Listings",
            "Product Link",
            "Other Links",
            "Identifiers",
            "Unique Model ID",
        }
        missing = sorted(required - set(headers))
        if missing:
            raise ValueError(f"Catalogue columns are missing: {', '.join(missing)}")

        def get(row: list[Any], name: str) -> Any:
            index = headers[name]
            return row[index] if index < len(row) else None

        entries: list[CatalogueEntry] = []
        for row in rows[1:]:
            identifiers = str(get(row, "Identifiers") or "")
            product_link = str(get(row, "Product Link") or "").strip()
            if not product_link.lower().startswith(("http://", "https://")):
                other_links = re.findall(
                    r"https?://[^\s\u2022]+",
                    str(get(row, "Other Links") or ""),
                )
                product_link = next(
                    (url for url in other_links if "/catalog" not in url.lower()),
                    other_links[0] if other_links else "",
                )
            for template_code in dict.fromkeys(
                match.group(1).upper() for match in IDENTIFIER_RE.finditer(identifiers)
            ):
                year_value = parse_number(get(row, "Year"))
                entries.append(
                    CatalogueEntry(
                        prefix=template_code[:-4],
                        template_code=template_code,
                        model=str(get(row, "Model") or "").strip(),
                        year=int(year_value) if year_value is not None else None,
                        category=str(get(row, "Category") or "").strip(),
                        subcategory=str(get(row, "Subcategory") or "").strip(),
                        product_link=product_link,
                        identifiers=identifiers.strip(),
                        unique_model_id=str(get(row, "Unique Model ID") or "").strip(),
                        regional_listings=int(parse_number(get(row, "Regional Listings")) or 0),
                    )
                )
        if not entries:
            raise ValueError("No catalogue identifiers ending in TTCC were found")
        return cls(entries)

    def title_candidates(self, title: str) -> list[CatalogueEntry]:
        normalized = normalize_name(title)
        matches: list[CatalogueEntry] = []
        best_length = 0
        for key in self.model_keys:
            if normalized == key or normalized.startswith(f"{key} "):
                if len(key) > best_length:
                    matches = list(self.by_model[key])
                    best_length = len(key)
                elif len(key) == best_length:
                    matches.extend(self.by_model[key])
        return self._dedupe_entries(matches)

    @staticmethod
    def _dedupe_entries(entries: Iterable[CatalogueEntry]) -> list[CatalogueEntry]:
        unique: dict[tuple[str, str], CatalogueEntry] = {}
        for entry in entries:
            key = (entry.prefix, entry.model_key)
            incumbent = unique.get(key)
            if incumbent is None or entry.regional_listings > incumbent.regional_listings:
                unique[key] = entry
        return list(unique.values())

    def code_candidates(self, sku: str) -> list[CatalogueEntry]:
        code = normalize_code(sku)
        matching_prefixes = [prefix for prefix in self.prefixes if code.startswith(prefix)]
        if not matching_prefixes:
            return []
        longest = len(matching_prefixes[0])
        entries: list[CatalogueEntry] = []
        for prefix in matching_prefixes:
            if len(prefix) != longest:
                break
            entries.extend(self.by_prefix[prefix])
        return self._dedupe_entries(entries)

    def is_likely_bicycle(self, visible_code: str, title: str) -> tuple[bool, str]:
        if self.code_candidates(first_code_token(visible_code)):
            return True, "catalogue code prefix"
        if self.title_candidates(title):
            return True, "catalogue model title"
        return False, "not in bicycle catalogue"

    def match(self, sku: str, title: str) -> MatchResult:
        code_matches = self.code_candidates(sku)
        if len(code_matches) == 1:
            return MatchResult("code_match", "variant SKU prefix", code_matches[0])
        if len(code_matches) > 1:
            title_matches = {
                (entry.prefix, entry.model_key): entry
                for entry in self.title_candidates(title)
            }
            narrowed = [
                entry
                for entry in code_matches
                if (entry.prefix, entry.model_key) in title_matches
            ]
            if len(narrowed) == 1:
                return MatchResult(
                    "code_match",
                    "variant SKU prefix + title",
                    narrowed[0],
                )
            return MatchResult(
                "ambiguous",
                "variant SKU prefix",
                None,
                "More than one catalogue model uses this code prefix",
            )

        title_matches = self.title_candidates(title)
        if len(title_matches) == 1:
            return MatchResult(
                "title_only",
                "title only",
                title_matches[0],
                "Model title matches, but the variant SKU prefix does not",
            )
        if len(title_matches) > 1:
            return MatchResult(
                "ambiguous",
                "title only",
                None,
                "More than one catalogue model matches this title",
            )
        return MatchResult(
            "unmatched",
            "none",
            None,
            "No catalogue code prefix or model title matched",
        )


class Checkpoint:
    def __init__(
        self,
        path: Path,
        catalogue_path: Path,
        *,
        all_products: bool,
        fresh: bool = False,
    ):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        run_config = {
            "catalogue_path": str(catalogue_path),
            "catalogue_sha256": file_sha256(catalogue_path),
            "all_products": all_products,
            "filters": {
                "search": "orbea",
                "status": "Draft",
                "stock": "In stock",
            },
        }

        if fresh and path.exists():
            backup = path.with_name(
                f"{path.stem}.{datetime.now():%Y%m%d_%H%M%S}.bak{path.suffix}"
            )
            path.replace(backup)
            print(f"Previous checkpoint kept as: {backup}")

        if path.exists():
            self.data = json.loads(path.read_text(encoding="utf-8"))
            if self.data.get("version") != CHECKPOINT_VERSION:
                raise ValueError("The checkpoint was created by an incompatible version")
            if self.data.get("run_config") != run_config:
                raise ValueError(
                    "The existing checkpoint uses a different catalogue or scan mode. "
                    "Run again with --fresh; the old checkpoint will be backed up."
                )
            self.data["resumed_at"] = utc_now()
        else:
            self.data = {
                "version": CHECKPOINT_VERSION,
                "started_at": utc_now(),
                "updated_at": utc_now(),
                "completed": False,
                "filters": {
                    "search": "orbea",
                    "status": "Draft",
                    "stock": "In stock",
                },
                "run_config": run_config,
                "catalogue_path": str(catalogue_path),
                "total_products": None,
                "total_pages": None,
                "results": [],
            }
        self.save()

    @property
    def results(self) -> list[dict[str, Any]]:
        return self.data["results"]

    def processed_keys(self, retry_errors: bool) -> set[str]:
        ignored = {"error"} if retry_errors else set()
        return {
            str(item.get("row_key"))
            for item in self.results
            if item.get("row_key") and item.get("status") not in ignored
        }

    def known_product_ids(self) -> set[str]:
        return {
            str(item.get("product_id"))
            for item in self.results
            if item.get("product_id")
        }

    def remove_row_key(self, row_key: str) -> None:
        self.data["results"] = [
            item for item in self.results if item.get("row_key") != row_key
        ]

    def add(self, result: dict[str, Any]) -> None:
        self.remove_row_key(str(result["row_key"]))
        self.results.append(result)
        self.save()

    def save(self) -> None:
        self.data["updated_at"] = utc_now()
        temp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        temp_path.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temp_path, self.path)


class PimboCollector:
    def __init__(
        self,
        driver: Any,
        catalogue: CatalogueIndex,
        checkpoint: Checkpoint,
        *,
        all_products: bool,
        max_products: int | None,
        retry_errors: bool,
    ):
        self.driver = driver
        self.catalogue = catalogue
        self.checkpoint = checkpoint
        self.all_products = all_products
        self.max_products = max_products
        self.processed = checkpoint.processed_keys(retry_errors)
        self.product_ids = checkpoint.known_product_ids()
        self.newly_scanned = 0

    @staticmethod
    def _selenium():
        from selenium.common.exceptions import TimeoutException
        from selenium.webdriver.common.by import By
        from selenium.webdriver.common.keys import Keys
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.support.ui import WebDriverWait

        return TimeoutException, By, Keys, EC, WebDriverWait

    def _wait(self, seconds: int = 20):
        return self._selenium()[4](self.driver, seconds)

    def _on_products_page(self) -> bool:
        return "/dashboard/products" in self.driver.current_url and not re.search(
            r"/dashboard/products/[^/?#]+", self.driver.current_url
        )

    def _wait_for_login_if_needed(self) -> None:
        _, By, _, _, _ = self._selenium()
        self.driver.get(PIMBO_PRODUCTS_URL)
        try:
            self._wait(8).until(
                lambda driver: self._on_products_page()
                and driver.find_elements(By.CSS_SELECTOR, "input[placeholder='Search...']")
            )
            return
        except Exception:
            pass

        print()
        print("Log into Pimbo in the opened browser.")
        input("When the Products page is visible, press Enter here to continue: ")
        self.driver.get(PIMBO_PRODUCTS_URL)
        self._wait(30).until(
            lambda driver: self._on_products_page()
            and driver.find_elements(By.CSS_SELECTOR, "input[placeholder='Search...']")
        )

    def _filter_dialog(self):
        _, By, _, _, _ = self._selenium()
        dialogs = self.driver.find_elements(By.CSS_SELECTOR, "[role='dialog']")
        return next((dialog for dialog in dialogs if dialog.is_displayed()), None)

    @staticmethod
    def _button_is_active(button: Any) -> bool:
        classes = button.get_attribute("class") or ""
        return (
            "bg-foreground" in classes
            or button.get_attribute("aria-pressed") == "true"
            or button.get_attribute("data-active") in {"", "true"}
            and button.get_attribute("data-active") is not None
        )

    def _open_filter_dialog(self):
        _, By, _, EC, _ = self._selenium()
        dialog = self._filter_dialog()
        if dialog is not None:
            return dialog
        button = self._wait().until(
            EC.element_to_be_clickable(
                (
                    By.XPATH,
                    "//button[@aria-haspopup='dialog' and "
                    "contains(normalize-space(.), 'Filter')]",
                )
            )
        )
        button.click()
        return self._wait().until(
            lambda _driver: self._filter_dialog()
        )

    def _set_filter_button(self, dialog: Any, label: str) -> None:
        _, By, _, _, _ = self._selenium()
        buttons = dialog.find_elements(
            By.XPATH, f".//button[normalize-space()={json.dumps(label)}]"
        )
        if len(buttons) != 1:
            raise RuntimeError(f"Expected one {label!r} filter button, found {len(buttons)}")
        if not self._button_is_active(buttons[0]):
            buttons[0].click()
            time.sleep(0.8)

    def apply_filters(self) -> None:
        _, By, Keys, EC, _ = self._selenium()
        if not self._on_products_page():
            self.driver.get(PIMBO_PRODUCTS_URL)

        search = self._wait().until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "input[placeholder='Search...']"))
        )
        if (search.get_attribute("value") or "").strip().lower() != "orbea":
            old_heading = ""
            headings = self.driver.find_elements(
                By.XPATH, "//main//h1[contains(normalize-space(.), 'Products')]"
            )
            if headings:
                old_heading = headings[0].text
            search.click()
            search.send_keys(Keys.CONTROL, "a")
            search.send_keys("orbea")
            search.send_keys(Keys.ENTER)
            self._wait().until(
                lambda driver: (
                    driver.find_element(
                        By.CSS_SELECTOR, "input[placeholder='Search...']"
                    ).get_attribute("value")
                    or ""
                ).strip().lower()
                == "orbea"
            )
            if old_heading:
                try:
                    self._wait(8).until(
                        lambda driver: driver.find_element(
                            By.XPATH,
                            "//main//h1[contains(normalize-space(.), 'Products')]",
                        ).text
                        != old_heading
                    )
                except Exception:
                    # Some list states keep the same count; the row-level
                    # verification below is the final source of truth.
                    pass
            time.sleep(1.2)

        dialog = self._open_filter_dialog()
        self._set_filter_button(dialog, "Draft")
        dialog = self._filter_dialog() or self._open_filter_dialog()
        self._set_filter_button(dialog, "In stock")

        filter_button = self.driver.find_element(
            By.XPATH,
            "//button[@aria-haspopup='dialog' and contains(normalize-space(.), 'Filter')]",
        )
        if self._filter_dialog() is not None:
            filter_button.click()
        time.sleep(1.0)

        search = self.driver.find_element(By.CSS_SELECTOR, "input[placeholder='Search...']")
        if (search.get_attribute("value") or "").strip().lower() != "orbea":
            raise RuntimeError("Pimbo search filter was not applied")
        rows = self._wait_for_rows()
        for row in rows[:10]:
            cells = row.find_elements(By.CSS_SELECTOR, "td")
            brand = cells[2].text.strip().lower() if len(cells) > 2 else ""
            status = cells[6].text.strip().lower() if len(cells) > 6 else ""
            if brand != "orbea" or status != "draft":
                raise RuntimeError(
                    "Pimbo returned rows outside the Orbea + Draft filter"
                )

        dialog = self._open_filter_dialog()
        for label in ("Draft", "In stock"):
            button = dialog.find_element(
                By.XPATH, f".//button[normalize-space()={json.dumps(label)}]"
            )
            if not self._button_is_active(button):
                raise RuntimeError(f"Pimbo {label!r} filter was not applied")
        filter_button = self.driver.find_element(
            By.XPATH,
            "//button[@aria-haspopup='dialog' and contains(normalize-space(.), 'Filter')]",
        )
        filter_button.click()
        self._wait_for_rows()

    def _wait_for_rows(self) -> list[Any]:
        _, By, _, _, _ = self._selenium()
        self._wait().until(
            lambda driver: self._on_products_page()
            and driver.find_elements(
                By.CSS_SELECTOR, "main table tbody tr[data-slot='table-row']"
            )
        )
        return self.driver.find_elements(
            By.CSS_SELECTOR, "main table tbody tr[data-slot='table-row']"
        )

    def _page_input(self):
        _, By, _, _, _ = self._selenium()
        candidates = self.driver.find_elements(
            By.CSS_SELECTOR, "main input[type='number'][min='1'][max]"
        )
        if len(candidates) != 1:
            raise RuntimeError(f"Expected one page input, found {len(candidates)}")
        return candidates[0]

    def go_to_page(self, page_number: int) -> None:
        _, _, Keys, _, _ = self._selenium()
        page_input = self._page_input()
        current = int(page_input.get_attribute("value") or "1")
        if current == page_number:
            return
        page_input.click()
        page_input.send_keys(Keys.CONTROL, "a")
        page_input.send_keys(str(page_number))
        page_input.send_keys(Keys.ENTER)
        self._wait().until(
            lambda _driver: int(self._page_input().get_attribute("value") or "0")
            == page_number
        )
        self._wait_for_rows()
        time.sleep(0.4)

    def _total_products(self) -> int | None:
        _, By, _, _, _ = self._selenium()
        headings = self.driver.find_elements(
            By.XPATH, "//main//h1[contains(normalize-space(.), 'Products')]"
        )
        if not headings:
            return None
        match = re.search(r"\(([\d,.\s]+)\)", headings[0].text)
        return int(re.sub(r"\D", "", match.group(1))) if match else None

    @staticmethod
    def _row_key(page_number: int, title: str, visible_code: str) -> str:
        raw = f"{page_number}\0{title}\0{visible_code}".encode("utf-8")
        return hashlib.sha1(raw).hexdigest()

    def _row_snapshot(self, row_index: int) -> tuple[Any, dict[str, Any]]:
        _, By, _, _, _ = self._selenium()
        rows = self.driver.find_elements(
            By.CSS_SELECTOR, "main table tbody tr[data-slot='table-row']"
        )
        if row_index >= len(rows):
            raise IndexError(f"Product row {row_index + 1} disappeared")
        row = rows[row_index]
        cells = row.find_elements(By.CSS_SELECTOR, "td")
        title_elements = row.find_elements(By.CSS_SELECTOR, "span.font-medium[title]")
        code_elements = row.find_elements(By.CSS_SELECTOR, "span.font-mono")
        title = (
            (title_elements[0].get_attribute("title") or title_elements[0].text).strip()
            if title_elements
            else ""
        )
        visible_code = code_elements[0].text.strip() if code_elements else ""
        snapshot = {
            "title": title,
            "visible_code": visible_code,
            "brand": cells[2].text.strip() if len(cells) > 2 else "",
            "variant_count": parse_number(cells[4].text) if len(cells) > 4 else None,
            "list_stock": parse_number(cells[5].text) if len(cells) > 5 else None,
            "list_status": cells[6].text.strip() if len(cells) > 6 else "",
        }
        return row, snapshot

    def _extract_one_variant(self, row: Any) -> dict[str, Any]:
        _, By, _, EC, _ = self._selenium()
        self.driver.execute_script(
            "arguments[0].scrollIntoView({block:'center'});", row
        )
        self.driver.execute_script("arguments[0].click();", row)
        self._wait().until(
            lambda driver: bool(
                re.search(r"/dashboard/products/[^/?#]+", driver.current_url)
            )
        )
        product_url = self.driver.current_url
        product_id = product_url.rstrip("/").split("/")[-1]

        variants_tab = self._wait().until(
            EC.element_to_be_clickable(
                (
                    By.XPATH,
                    "//button[@role='tab' and normalize-space()='Variants']",
                )
            )
        )
        if variants_tab.get_attribute("aria-selected") != "true":
            variants_tab.click()
        self._wait().until(
            lambda driver: variants_tab.get_attribute("aria-selected") == "true"
            and driver.find_elements(By.CSS_SELECTOR, "div[role='tabpanel']")
        )
        time.sleep(0.6)

        rows = self.driver.find_elements(
            By.CSS_SELECTOR,
            "div[role='tabpanel'] table tbody tr[data-slot='table-row']",
        )
        if not rows:
            return {
                "product_url": product_url,
                "product_id": product_id,
                "sku": "",
                "variant_stock": None,
                "variant_count_found": 0,
            }

        parsed: list[tuple[Any, str, float | int | None]] = []
        for variant_row in rows:
            cells = variant_row.find_elements(By.CSS_SELECTOR, "td")
            if not cells:
                continue
            links = cells[0].find_elements(
                By.CSS_SELECTOR, "a[href^='/dashboard/variants/']"
            )
            sku = (links[0].text if links else cells[0].text).strip()
            stock = parse_number(cells[6].text) if len(cells) > 6 else None
            if sku:
                parsed.append((variant_row, sku, stock))

        if not parsed:
            return {
                "product_url": product_url,
                "product_id": product_id,
                "sku": "",
                "variant_stock": None,
                "variant_count_found": len(rows),
            }

        chosen = next(
            (item for item in parsed if item[2] is not None and item[2] > 0),
            parsed[0],
        )
        return {
            "product_url": product_url,
            "product_id": product_id,
            "sku": normalize_code(chosen[1]),
            "variant_stock": chosen[2],
            "variant_count_found": len(rows),
        }

    def _restore_list(self, page_number: int) -> None:
        try:
            self.driver.back()
            self._wait().until(lambda _driver: self._on_products_page())
            self._wait_for_rows()
        except Exception:
            self.driver.get(PIMBO_PRODUCTS_URL)
            self.apply_filters()

        search_value = ""
        try:
            _, By, _, _, _ = self._selenium()
            search_value = self.driver.find_element(
                By.CSS_SELECTOR, "input[placeholder='Search...']"
            ).get_attribute("value") or ""
        except Exception:
            pass
        if search_value.strip().lower() != "orbea":
            self.apply_filters()
        self.go_to_page(page_number)

    @staticmethod
    def _entry_fields(match: MatchResult) -> dict[str, Any]:
        entry = match.entry
        if entry is None:
            return {
                "catalogue_prefix": "",
                "catalogue_code": "",
                "catalogue_model": "",
                "catalogue_year": None,
                "catalogue_category": "",
                "catalogue_subcategory": "",
                "catalogue_url": "",
                "catalogue_unique_model_id": "",
            }
        return {
            "catalogue_prefix": entry.prefix,
            "catalogue_code": entry.template_code,
            "catalogue_model": entry.model,
            "catalogue_year": entry.year,
            "catalogue_category": entry.category,
            "catalogue_subcategory": entry.subcategory,
            "catalogue_url": entry.product_link,
            "catalogue_unique_model_id": entry.unique_model_id,
        }

    def collect(self) -> None:
        self._wait_for_login_if_needed()
        self.apply_filters()
        self.go_to_page(1)

        total_pages = int(self._page_input().get_attribute("max") or "1")
        self.checkpoint.data["total_pages"] = total_pages
        self.checkpoint.data["total_products"] = self._total_products()
        self.checkpoint.save()

        expected = self.checkpoint.data.get("total_products") or "unknown"
        print(
            f"Filtered Pimbo list: {expected} products across {total_pages} pages."
        )
        print("Every row is checkpointed. Press Ctrl+C at any time to stop safely.")

        for page_number in range(1, total_pages + 1):
            self.go_to_page(page_number)
            row_count = len(self._wait_for_rows())
            print(f"Page {page_number}/{total_pages}: {row_count} rows")

            for row_index in range(row_count):
                if self.max_products is not None and self.newly_scanned >= self.max_products:
                    print(f"Stopped at --max-products {self.max_products}.")
                    return

                row, snapshot = self._row_snapshot(row_index)
                row_key = self._row_key(
                    page_number, snapshot["title"], snapshot["visible_code"]
                )
                if row_key in self.processed:
                    continue

                likely, candidate_reason = self.catalogue.is_likely_bicycle(
                    snapshot["visible_code"], snapshot["title"]
                )
                base = {
                    "row_key": row_key,
                    "page": page_number,
                    "row": row_index + 1,
                    "scanned_at": utc_now(),
                    "candidate_reason": candidate_reason,
                    **snapshot,
                }

                if not self.all_products and not likely:
                    result = {
                        **base,
                        "status": "excluded",
                        "match_method": "catalogue prefilter",
                        "note": "Scanned but not opened: no bicycle code/title candidate",
                        "product_url": "",
                        "product_id": "",
                        "sku": "",
                        "variant_stock": None,
                        "variant_count_found": None,
                        **self._entry_fields(
                            MatchResult("excluded", "catalogue prefilter", None)
                        ),
                    }
                    self.checkpoint.add(result)
                    self.processed.add(row_key)
                    self.newly_scanned += 1
                    continue

                try:
                    detail = self._extract_one_variant(row)
                    if detail["product_id"] in self.product_ids:
                        status = MatchResult(
                            "duplicate",
                            "Pimbo product ID",
                            None,
                            "This Pimbo product was already processed",
                        )
                    elif not detail["sku"]:
                        status = MatchResult(
                            "no_variant",
                            "Variants tab",
                            None,
                            "No variant SKU was found",
                        )
                    else:
                        status = self.catalogue.match(detail["sku"], snapshot["title"])

                    result = {
                        **base,
                        **detail,
                        "status": status.status,
                        "match_method": status.method,
                        "note": status.note,
                        **self._entry_fields(status),
                    }
                    if detail["product_id"]:
                        self.product_ids.add(detail["product_id"])
                except KeyboardInterrupt:
                    raise
                except Exception as error:
                    result = {
                        **base,
                        "status": "error",
                        "match_method": "browser",
                        "note": f"{type(error).__name__}: {error}",
                        "product_url": self.driver.current_url,
                        "product_id": "",
                        "sku": "",
                        "variant_stock": None,
                        "variant_count_found": None,
                        **self._entry_fields(
                            MatchResult("error", "browser", None)
                        ),
                    }
                finally:
                    if not self._on_products_page():
                        self._restore_list(page_number)

                self.checkpoint.add(result)
                self.processed.add(row_key)
                self.newly_scanned += 1
                code_label = result.get("sku") or result.get("visible_code") or "(no code)"
                print(
                    f"  {page_number}:{row_index + 1} "
                    f"{code_label} -> {result['status']}"
                )

        self.checkpoint.data["completed"] = True
        self.checkpoint.data["completed_at"] = utc_now()
        self.checkpoint.save()


def create_driver(browser_name: str):
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    from selenium.webdriver.chrome.service import Service as ChromeService
    from selenium.webdriver.edge.options import Options as EdgeOptions
    from selenium.webdriver.edge.service import Service as EdgeService
    from selenium.webdriver.firefox.options import Options as FirefoxOptions
    from selenium.webdriver.firefox.service import Service as FirefoxService
    from webdriver_manager.chrome import ChromeDriverManager
    from webdriver_manager.firefox import GeckoDriverManager
    from webdriver_manager.microsoft import EdgeChromiumDriverManager

    name = browser_name.lower()
    if name == "chrome":
        options = ChromeOptions()
        options.add_experimental_option("excludeSwitches", ["enable-logging"])
        return webdriver.Chrome(
            service=ChromeService(ChromeDriverManager().install()), options=options
        )
    if name == "edge":
        options = EdgeOptions()
        options.add_experimental_option("excludeSwitches", ["enable-logging"])
        return webdriver.Edge(
            service=EdgeService(EdgeChromiumDriverManager().install()), options=options
        )
    if name == "firefox":
        options = FirefoxOptions()
        return webdriver.Firefox(
            service=FirefoxService(GeckoDriverManager().install()), options=options
        )
    raise ValueError(f"Unsupported browser: {browser_name}")


def find_node() -> str | None:
    candidates = [
        Path.home()
        / ".cache"
        / "codex-runtimes"
        / "codex-primary-runtime"
        / "dependencies"
        / "node"
        / "bin"
        / "node.exe",
        Path(shutil.which("node") or ""),
    ]
    for candidate in candidates:
        if str(candidate) and candidate.is_file():
            return str(candidate)
    return None


def build_report(checkpoint_path: Path, output_path: Path) -> bool:
    node = find_node()
    if not node:
        print("Excel report was not built: Node.js was not found.")
        print(f"The complete checkpoint is safe at: {checkpoint_path}")
        return False

    builder = Path(__file__).with_name("build_orbea_pimbo_report.mjs")
    preview_dir = output_path.parent / ".report-preview"
    command = [
        node,
        str(builder),
        str(checkpoint_path),
        str(output_path),
        str(preview_dir),
    ]
    try:
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError as error:
        print(f"Excel report build failed (exit code {error.returncode}).")
        print(f"The complete checkpoint is safe at: {checkpoint_path}")
        return False
    print(f"Excel report: {output_path}")
    return True


def run_self_test(catalogue_path: Path) -> None:
    catalogue = CatalogueIndex.from_workbook(catalogue_path)
    assert catalogue.match("U10707SV", "Orbea ORCA M30i").status == "code_match"
    assert catalogue.match("U10707SV", "Orbea ORCA M30i").entry is not None
    assert catalogue.match("U10707SV", "Orbea ORCA M30i").entry.template_code == "U107TTCC"
    assert catalogue.match("U10707SV", "Orbea ORCA M30i").entry.product_link.startswith(
        "http"
    )
    likely, reason = catalogue.is_likely_bicycle(
        "U10707SV +5", "Orbea ORCA M30i Carbon"
    )
    assert likely and reason == "catalogue code prefix"
    print(
        f"Self-test passed: {len(catalogue.by_prefix)} unique catalogue code prefixes."
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Read one real variant SKU from each filtered Pimbo Orbea bicycle "
            "and match it to the Orbea catalogue."
        )
    )
    parser.add_argument(
        "--catalogue",
        type=Path,
        default=DEFAULT_CATALOGUE,
        help=f"Orbea catalogue workbook (default: {DEFAULT_CATALOGUE})",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Checkpoint/report folder (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--browser",
        choices=("chrome", "firefox", "edge"),
        default="chrome",
        help="Visible browser used for Pimbo (default: chrome)",
    )
    parser.add_argument(
        "--all-products",
        action="store_true",
        help="Open every filtered Orbea row, including accessories/components",
    )
    parser.add_argument(
        "--max-products",
        type=int,
        help="Scan at most this many new rows (useful for a quick test)",
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Start a new checkpoint; the previous checkpoint is backed up",
    )
    parser.add_argument(
        "--no-retry-errors",
        action="store_true",
        help="Do not retry rows that previously ended with a browser error",
    )
    parser.add_argument(
        "--keep-browser-open",
        action="store_true",
        help="Leave the Selenium browser open when the run stops",
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Build Excel from the existing checkpoint without opening Pimbo",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Test catalogue parsing/matching without opening Pimbo",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    catalogue_path = args.catalogue.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    checkpoint_path = output_dir / "orbea_pimbo_checkpoint.json"
    report_path = output_dir / "orbea_pimbo_variant_matches.xlsx"

    output_dir.mkdir(parents=True, exist_ok=True)
    if args.report_only:
        if not checkpoint_path.is_file():
            raise FileNotFoundError(f"Checkpoint not found: {checkpoint_path}")
        return 0 if build_report(checkpoint_path, report_path) else 1
    if not catalogue_path.is_file():
        raise FileNotFoundError(f"Catalogue workbook not found: {catalogue_path}")
    if args.self_test:
        run_self_test(catalogue_path)
        return 0

    catalogue = CatalogueIndex.from_workbook(catalogue_path)
    checkpoint = Checkpoint(
        checkpoint_path,
        catalogue_path,
        all_products=args.all_products,
        fresh=args.fresh,
    )
    driver = None
    interrupted = False
    try:
        driver = create_driver(args.browser)
        collector = PimboCollector(
            driver,
            catalogue,
            checkpoint,
            all_products=args.all_products,
            max_products=args.max_products,
            retry_errors=not args.no_retry_errors,
        )
        collector.collect()
    except KeyboardInterrupt:
        interrupted = True
        checkpoint.data["completed"] = False
        checkpoint.data["stopped_at"] = utc_now()
        checkpoint.save()
        print("\nStopped safely. The next run will resume from the checkpoint.")
    finally:
        if driver is not None and not args.keep_browser_open:
            try:
                driver.quit()
            except Exception:
                pass

    report_ok = build_report(checkpoint_path, report_path)
    if interrupted:
        print("The Excel report contains the partial results collected so far.")
    return 0 if report_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
