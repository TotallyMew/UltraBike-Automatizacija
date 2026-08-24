#!/usr/bin/env python3
"""Download Orbea geometry and centimetre size-guide tables as PNG images.

The script reads the ``Orbea URL`` column from the Pimbo match workbook,
deduplicates repeated URLs, and stores one labelled geometry image per available
frame size plus the size guide for each bike page. Runs are resumable: a
checkpoint is updated after every URL and already-valid PNGs are not downloaded
again unless ``--force`` or ``--fresh`` is used.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import struct
import sys
import time
import unicodedata
import zipfile
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import unquote, urlsplit, urlunsplit
from xml.etree import ElementTree as ET


SCRIPT_VERSION = 1
GEOMETRY_CAPTURE_VERSION = 4
AVAILABILITY_PROBE_VERSION = 2
DEFAULT_SHEET = "Matches"
GEOMETRY_CAPTION = "Geometry chart by size"
SIZE_GUIDE_CAPTION = "Size guide by height"
DEFAULT_GEOMETRY_POSITION = "low"
DEFAULT_TIMEOUT = 25.0
DEFAULT_CONTROL_DISCOVERY_TIMEOUT = 3.0
DEFAULT_TABLE_RENDER_TIMEOUT = 8.0
DEFAULT_SELECTOR_TIMEOUT = 5.0
DEFAULT_DELAY = 0.6
IMAGE_PADDING = 24

TABLE_STATUS_DOWNLOADED = "downloaded"
TABLE_STATUS_NOT_AVAILABLE = "not_available"
TABLE_STATUS_TRANSIENT_ERROR = "transient_error"
TABLE_STATUS_PENDING = "pending"
TERMINAL_TABLE_STATUSES = {
    TABLE_STATUS_DOWNLOADED,
    TABLE_STATUS_NOT_AVAILABLE,
}


@dataclass(frozen=True)
class CaptureTimeouts:
    """Timeouts for one Orbea page capture attempt."""

    page_load: float = DEFAULT_TIMEOUT
    control_discovery: float = DEFAULT_CONTROL_DISCOVERY_TIMEOUT
    table_render: float = DEFAULT_TABLE_RENDER_TIMEOUT
    selector: float = DEFAULT_SELECTOR_TIMEOUT


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clean_text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def column_index(cell_reference: str) -> int:
    letters = "".join(character for character in cell_reference if character.isalpha())
    result = 0
    for character in letters.upper():
        result = result * 26 + (ord(character) - ord("A") + 1)
    return max(result - 1, 0)


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    path = "xl/sharedStrings.xml"
    if path not in archive.namelist():
        return []
    namespace = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    root = ET.fromstring(archive.read(path))
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
    available: list[str] = []
    for sheet in workbook.findall(f".//{{{main_ns}}}sheet"):
        name = sheet.get("name", "")
        available.append(name)
        if name.casefold() == sheet_name.casefold():
            relationship_id = sheet.get(f"{{{rel_ns}}}id")
            break
    if not relationship_id:
        names = ", ".join(repr(name) for name in available)
        raise ValueError(f"Worksheet {sheet_name!r} was not found. Available: {names}")

    relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    target = None
    for relationship in relationships.findall(f"{{{package_rel_ns}}}Relationship"):
        if relationship.get("Id") == relationship_id:
            target = relationship.get("Target")
            break
    if not target:
        raise ValueError(f"Worksheet relationship for {sheet_name!r} was not found")

    target = target.replace("\\", "/").lstrip("/")
    if not target.startswith("xl/"):
        target = f"xl/{target}"
    parts: list[str] = []
    for part in target.split("/"):
        if part in {"", "."}:
            continue
        if part == "..":
            if parts:
                parts.pop()
        else:
            parts.append(part)
    return "/".join(parts)


def read_xlsx_rows(path: Path, sheet_name: str) -> list[list[Any]]:
    """Read one worksheet without opening or modifying Excel."""

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
class SourceRow:
    workbook_row: int
    values: dict[str, str]

    @property
    def orbea_url(self) -> str:
        return self.values.get("Orbea URL", "")


@dataclass
class PageJob:
    url: str
    canonical_url: str
    folder_name: str
    rows: list[SourceRow]

    @property
    def label(self) -> str:
        for key in ("Catalogue Model", "Pimbo Product", "Catalogue Code"):
            for row in self.rows:
                value = row.values.get(key, "")
                if value:
                    return value
        return self.folder_name


def load_source_rows(path: Path, sheet_name: str) -> list[SourceRow]:
    rows = read_xlsx_rows(path, sheet_name)
    if not rows:
        raise ValueError(f"Worksheet {sheet_name!r} is empty")

    headers = [clean_text(value) for value in rows[0]]
    if "Orbea URL" not in headers:
        raise ValueError(
            f"Worksheet {sheet_name!r} has no 'Orbea URL' column. "
            f"Columns found: {', '.join(header for header in headers if header)}"
        )

    source_rows: list[SourceRow] = []
    for row_number, raw_row in enumerate(rows[1:], start=2):
        values = {
            header: clean_text(raw_row[index] if index < len(raw_row) else "")
            for index, header in enumerate(headers)
            if header
        }
        source_rows.append(SourceRow(row_number, values))
    return source_rows


def canonicalize_url(raw_url: str) -> str:
    raw_url = raw_url.strip()
    if not raw_url:
        return ""
    parts = urlsplit(raw_url)
    if parts.scheme.lower() not in {"http", "https"} or not parts.netloc:
        return ""
    scheme = "https" if parts.scheme.lower() == "http" else parts.scheme.lower()
    hostname = (parts.hostname or "").lower()
    try:
        port = parts.port
    except ValueError:
        return ""
    netloc = hostname
    if port and not (scheme == "https" and port == 443):
        netloc = f"{hostname}:{port}"
    path = re.sub(r"/{2,}", "/", parts.path).rstrip("/") or "/"
    return urlunsplit((scheme, netloc, path, "", ""))


def slugify(value: str, fallback: str = "orbea-bike") -> str:
    value = unicodedata.normalize("NFKD", unquote(value))
    value = value.encode("ascii", "ignore").decode("ascii").lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return (value or fallback)[:100].rstrip("-")


def build_jobs(source_rows: Iterable[SourceRow]) -> tuple[list[PageJob], list[SourceRow]]:
    grouped: OrderedDict[str, list[SourceRow]] = OrderedDict()
    original_urls: dict[str, str] = {}
    invalid: list[SourceRow] = []

    for row in source_rows:
        canonical = canonicalize_url(row.orbea_url)
        if not canonical:
            invalid.append(row)
            continue
        grouped.setdefault(canonical, []).append(row)
        original_urls.setdefault(canonical, row.orbea_url.strip())

    used_folders: dict[str, str] = {}
    jobs: list[PageJob] = []
    for canonical, rows in grouped.items():
        path_name = urlsplit(canonical).path.rstrip("/").rsplit("/", 1)[-1]
        preferred = path_name or rows[0].values.get("Catalogue Model", "")
        folder = slugify(preferred)
        if folder in used_folders and used_folders[folder] != canonical:
            suffix = hashlib.sha1(canonical.encode("utf-8")).hexdigest()[:8]
            folder = f"{folder}--{suffix}"
        used_folders[folder] = canonical
        jobs.append(PageJob(original_urls[canonical], canonical, folder, rows))

    return jobs, invalid


def png_dimensions(path: Path) -> tuple[int, int] | None:
    try:
        if path.stat().st_size < 1_000:
            return None
        with path.open("rb") as handle:
            if handle.read(8) != b"\x89PNG\r\n\x1a\n":
                return None
            length = struct.unpack(">I", handle.read(4))[0]
            if handle.read(4) != b"IHDR" or length < 8:
                return None
            width, height = struct.unpack(">II", handle.read(8))
        if width < 180 or height < 100:
            return None
        return width, height
    except (OSError, struct.error):
        return None


def relative_path(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path.resolve())


def atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def load_checkpoint(path: Path, fresh: bool) -> dict[str, Any]:
    if fresh and path.exists():
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = path.with_name(f"{path.stem}.{stamp}.bak{path.suffix}")
        shutil.copy2(path, backup)
        print(f"Previous checkpoint backed up as: {backup.name}")
    elif path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(
                f"Could not read checkpoint {path}: {error}. "
                "Use --fresh to start a new checkpoint."
            ) from error
        if data.get("version") != SCRIPT_VERSION:
            raise ValueError(
                f"Unsupported checkpoint version in {path}. Use --fresh to restart."
            )
        data.setdefault("pages", {})
        return data

    return {
        "version": SCRIPT_VERSION,
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "completed": False,
        "pages": {},
    }


def workbook_fingerprint(path: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    details = path.stat()
    return {
        "path": str(path.resolve()),
        "size": details.st_size,
        "modified_ns": details.st_mtime_ns,
        "sha256": digest.hexdigest(),
    }


def concise_error(error: BaseException) -> str:
    message = re.sub(r"\s+", " ", str(error)).strip()
    if len(message) > 500:
        message = f"{message[:497]}..."
    return f"{type(error).__name__}: {message or 'no details'}"


def create_driver(
    browser_name: str,
    show_browser: bool,
    page_load_timeout: float = DEFAULT_TIMEOUT,
):
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

    name = browser_name.casefold()
    if name == "chrome":
        options = ChromeOptions()
        options.page_load_strategy = "eager"
        options.add_experimental_option("excludeSwitches", ["enable-logging"])
        options.add_experimental_option(
            "prefs", {"intl.accept_languages": "en-AU,en-US,en"}
        )
        if not show_browser:
            options.add_argument("--headless=new")
        options.add_argument("--window-size=1800,1400")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-dev-shm-usage")
        driver = webdriver.Chrome(
            service=ChromeService(ChromeDriverManager().install()), options=options
        )
    elif name == "edge":
        options = EdgeOptions()
        options.page_load_strategy = "eager"
        options.add_experimental_option("excludeSwitches", ["enable-logging"])
        if not show_browser:
            options.add_argument("--headless=new")
        options.add_argument("--window-size=1800,1400")
        options.add_argument("--disable-gpu")
        driver = webdriver.Edge(
            service=EdgeService(EdgeChromiumDriverManager().install()), options=options
        )
    elif name == "firefox":
        options = FirefoxOptions()
        options.page_load_strategy = "eager"
        if not show_browser:
            options.add_argument("-headless")
        driver = webdriver.Firefox(
            service=FirefoxService(GeckoDriverManager().install()), options=options
        )
        driver.set_window_size(1800, 1400)
    else:
        raise ValueError(f"Unsupported browser: {browser_name}")

    driver.set_page_load_timeout(page_load_timeout)
    driver.set_script_timeout(20)
    return driver


def first_displayed(elements):
    for element in elements:
        try:
            if element.is_displayed():
                return element
        except Exception:
            continue
    return False


def wait_for_displayed(driver, by: str, selector: str, timeout: float, label: str):
    from selenium.webdriver.support.ui import WebDriverWait

    element = WebDriverWait(driver, timeout).until(
        lambda current: first_displayed(current.find_elements(by, selector)),
        message=f"Timed out waiting for {label}",
    )
    return element


def click_named_button(driver, label: str, timeout: float) -> None:
    from selenium.webdriver.common.by import By

    selector = f"//button[normalize-space(.)={json.dumps(label)}]"
    button = wait_for_displayed(driver, By.XPATH, selector, timeout, repr(label))
    click_control(driver, button)


def click_control(driver, control) -> None:
    """Click a control that was already discovered on the loaded product page."""

    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", control)
    driver.execute_script("arguments[0].click();", control)


def discover_table_controls(
    driver,
    *,
    need_geometry: bool,
    need_size_guide: bool,
    timeout: float = DEFAULT_CONTROL_DISCOVERY_TIMEOUT,
) -> dict[str, Any | None]:
    """Discover both table controls in one short, shared availability window.

    A missing control is a supported page shape, not an exception. Waiting once
    for both controls prevents custom-frame pages from paying two full timeouts.
    """

    from selenium.webdriver.common.by import By

    lower = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    upper = "abcdefghijklmnopqrstuvwxyz"
    selectors = {
        "geometry": (
            "//button[translate(normalize-space(.),"
            f"'{lower}','{upper}')='view geometry']"
        ),
        "size_guide": (
            "//button[translate(normalize-space(.),"
            f"'{lower}','{upper}')='view size guide']"
        ),
    }
    required = {
        "geometry": need_geometry,
        "size_guide": need_size_guide,
    }
    controls: dict[str, Any | None] = {
        "geometry": None,
        "size_guide": None,
    }
    deadline = time.monotonic() + max(timeout, 0.0)

    while True:
        for name, is_required in required.items():
            if is_required and controls[name] is None:
                controls[name] = first_displayed(
                    driver.find_elements(By.XPATH, selectors[name])
                ) or None

        if all(not required[name] or controls[name] is not None for name in required):
            return controls

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return controls
        time.sleep(min(0.1, remaining))


def wait_for_table(driver, caption: str, timeout: float):
    from selenium.webdriver.common.by import By

    selector = f"//table[caption[normalize-space(.)={json.dumps(caption)}]]"
    table = wait_for_displayed(driver, By.XPATH, selector, timeout, repr(caption))

    from selenium.webdriver.support.ui import WebDriverWait

    WebDriverWait(driver, timeout).until(
        lambda _current: len(table.find_elements(By.CSS_SELECTOR, "tbody tr")) > 0,
        message=f"The {caption!r} table did not populate",
    )
    return table


def wait_for_geometry_table(driver, timeout: float):
    """Find both old captioned tables and newer #geometry-data tables."""

    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait

    caption_selector = (
        f"//table[caption[normalize-space(.)={json.dumps(GEOMETRY_CAPTION)}]]"
    )

    def find_table(current):
        candidates = current.find_elements(By.CSS_SELECTOR, "#geometry-data table")
        candidates.extend(current.find_elements(By.XPATH, caption_selector))
        return first_displayed(candidates)

    table = WebDriverWait(driver, timeout).until(
        find_table,
        message="Timed out waiting for the geometry table",
    )
    WebDriverWait(driver, timeout).until(
        lambda _current: len(table.find_elements(By.CSS_SELECTOR, "tbody tr")) > 0,
        message="The geometry table did not populate",
    )
    return table


def geometry_position_details(driver, table) -> tuple[Any | None, dict[str, Any]]:
    """Return the POSITION select (if present) and its current state."""

    from selenium.webdriver.common.by import By

    root = driver.execute_script(
        "return arguments[0].closest('#geometry-data');", table
    )
    if root is None:
        return None, {"value": "", "text": "", "options": []}

    for select in root.find_elements(By.CSS_SELECTOR, "select"):
        details = driver.execute_script(
            """
            const select = arguments[0];
            const group = select.closest('.select-container') || select.parentElement;
            const label = group?.querySelector('label')?.textContent?.trim() || '';
            const options = Array.from(select.options).map(option => ({
              value: option.value,
              text: option.textContent.trim(),
              selected: option.selected
            }));
            const selected = select.options[select.selectedIndex];
            return {
              label,
              value: select.value || '',
              text: selected?.textContent?.trim() || '',
              options
            };
            """,
            select,
        )
        option_names = {
            clean_text(option.get("text")).casefold()
            for option in details.get("options", [])
        }
        if details.get("label", "").casefold() == "position" or {
            "low",
            "high",
        }.issubset(option_names):
            return select, details

    return None, {"value": "", "text": "", "options": []}


def geometry_size_details(driver, table) -> tuple[Any | None, dict[str, Any]]:
    """Return the frame-size selector and every geometry size it offers.

    Orbea currently labels this selector ``TALLA`` even on some English pages.
    Identifying it as the non-POSITION selector keeps the logic independent of
    that translated label and supports pages that also expose HIGH/LOW geometry.
    """

    from selenium.webdriver.common.by import By

    root = driver.execute_script(
        "return arguments[0].closest('#geometry-data');", table
    )
    if root is None:
        return None, {"value": "", "text": "", "options": []}

    for select in root.find_elements(By.CSS_SELECTOR, "select"):
        details = driver.execute_script(
            """
            const select = arguments[0];
            const group = select.closest('.select-container') || select.parentElement;
            const label = group?.querySelector('label')?.textContent?.trim() || '';
            const options = Array.from(select.options).map(option => ({
              value: option.value,
              text: option.textContent.trim(),
              selected: option.selected
            }));
            const selected = select.options[select.selectedIndex];
            return {
              label,
              value: select.value || '',
              text: selected?.textContent?.trim() || '',
              options
            };
            """,
            select,
        )
        option_names = {
            clean_text(option.get("text")).casefold()
            for option in details.get("options", [])
        }
        is_position = details.get("label", "").casefold() == "position" or {
            "low",
            "high",
        }.issubset(option_names)
        if not is_position and details.get("options"):
            return select, details

    return None, {"value": "", "text": "", "options": []}


def set_geometry_size(
    driver, table, requested_value: str, timeout: float
) -> tuple[Any, str]:
    """Select one frame size and return the refreshed geometry table."""

    from selenium.webdriver.support.ui import WebDriverWait

    select, details = geometry_size_details(driver, table)
    if select is None:
        raise RuntimeError("The geometry SIZE selector is not available")

    target = clean_text(requested_value)
    matching_option = next(
        (
            option
            for option in details.get("options", [])
            if clean_text(option.get("value")).casefold() == target.casefold()
            or clean_text(option.get("text")).casefold() == target.casefold()
        ),
        None,
    )
    if matching_option is None:
        raise RuntimeError(f"The geometry SIZE selector does not offer {target}")

    target_value = clean_text(matching_option.get("value"))
    if clean_text(details.get("value")).casefold() != target_value.casefold():
        previous_table_id = getattr(table, "id", None)
        previous_table_text = clean_text(getattr(table, "text", ""))
        driver.execute_script(
            """
            const select = arguments[0];
            const value = arguments[1];
            if (select.tomselect) {
              select.tomselect.setValue(value);
            } else {
              select.value = value;
              select.dispatchEvent(new Event('input', {bubbles: true}));
              select.dispatchEvent(new Event('change', {bubbles: true}));
            }
            """,
            select,
            target_value,
        )

        last_signature: tuple[str | None, str] | None = None
        stable_reads = 0

        def size_changed(_current):
            nonlocal last_signature, stable_reads
            try:
                current_table = wait_for_geometry_table(driver, 1.0)
                _select, current = geometry_size_details(driver, current_table)
                if (
                    clean_text(current.get("value")).casefold()
                    != target_value.casefold()
                ):
                    last_signature = None
                    stable_reads = 0
                    return False

                current_text = clean_text(getattr(current_table, "text", ""))
                current_id = getattr(current_table, "id", None)
                refreshed = (
                    current_id != previous_table_id
                    or current_text != previous_table_text
                )
                if not refreshed:
                    last_signature = None
                    stable_reads = 0
                    return False

                signature = (current_id, current_text)
                if signature == last_signature:
                    stable_reads += 1
                else:
                    last_signature = signature
                    stable_reads = 1
                return current_table if stable_reads >= 2 else False
            except Exception:
                return False

        table = WebDriverWait(driver, timeout, poll_frequency=0.15).until(
            size_changed,
            message=f"The geometry table did not switch to size {target}",
        )

    _select, final_details = geometry_size_details(driver, table)
    actual = clean_text(final_details.get("text") or final_details.get("value"))
    if clean_text(final_details.get("value")).casefold() != target_value.casefold():
        raise RuntimeError(
            f"Expected geometry size {target}, got {actual or 'blank'}"
        )
    return table, actual or clean_text(matching_option.get("text")) or target


def geometry_variant_path(destination: Path, size_label: str) -> Path:
    """Return a visibly size-labelled filename such as geometry-xs.png."""

    size_slug = slugify(size_label, "size")
    return destination.with_name(
        f"{destination.stem}-{size_slug}{destination.suffix}"
    )


def geometry_wheel_size(table) -> str:
    """Read every wheel-size heading paired with the selected frame size."""

    from selenium.webdriver.common.by import By

    headers = table.find_elements(By.CSS_SELECTOR, "thead th")
    wheel_sizes: list[str] = []
    for header in headers[1:]:
        value = clean_text(header.text)
        if value and value not in wheel_sizes:
            wheel_sizes.append(value)
    return "; ".join(wheel_sizes)


def set_geometry_position(
    driver, table, requested_position: str, timeout: float
) -> tuple[Any, str, bool]:
    """Select one geometry position and return the refreshed table."""

    from selenium.webdriver.support.ui import WebDriverWait

    select, details = geometry_position_details(driver, table)
    if select is None:
        return table, "", False

    selected_text = clean_text(details.get("text") or details.get("value"))
    if requested_position == "page-default":
        return table, selected_text, True

    target = requested_position.casefold()
    matching_option = next(
        (
            option
            for option in details.get("options", [])
            if clean_text(option.get("text")).casefold() == target
            or clean_text(option.get("value")).casefold() == target
        ),
        None,
    )
    if matching_option is None:
        raise RuntimeError(
            f"The geometry POSITION selector does not offer {requested_position.upper()}"
        )

    target_value = clean_text(matching_option.get("value"))
    if clean_text(details.get("value")).casefold() != target_value.casefold():
        driver.execute_script(
            """
            const select = arguments[0];
            const value = arguments[1];
            if (select.tomselect) {
              select.tomselect.setValue(value);
            } else {
              select.value = value;
              select.dispatchEvent(new Event('input', {bubbles: true}));
              select.dispatchEvent(new Event('change', {bubbles: true}));
            }
            """,
            select,
            target_value,
        )

        def position_changed(_current) -> bool:
            try:
                current_table = wait_for_geometry_table(driver, 1.0)
                _select, current = geometry_position_details(driver, current_table)
                return clean_text(current.get("value")).casefold() == target_value.casefold()
            except Exception:
                return False

        WebDriverWait(driver, timeout).until(
            position_changed,
            message=f"The geometry table did not switch to {requested_position.upper()}",
        )
        # Orbea replaces the values just after Tom Select changes its value.
        time.sleep(0.6)
        table = wait_for_geometry_table(driver, timeout)

    _select, final_details = geometry_position_details(driver, table)
    actual = clean_text(final_details.get("text") or final_details.get("value"))
    if actual.casefold() != target:
        raise RuntimeError(
            f"Expected geometry position {requested_position.upper()}, got {actual or 'blank'}"
        )
    return table, actual, True


def wait_for_fonts(driver) -> None:
    try:
        driver.execute_async_script(
            """
            const done = arguments[arguments.length - 1];
            if (!document.fonts || !document.fonts.ready) { done(); return; }
            Promise.race([
              document.fonts.ready,
              new Promise(resolve => setTimeout(resolve, 3000))
            ]).then(() => done());
            """
        )
    except Exception:
        pass


def screenshot_element(driver, element, destination: Path) -> tuple[int, int]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.stem}.tmp{destination.suffix}")
    if temporary.exists():
        temporary.unlink()

    driver.execute_script(
        "arguments[0].scrollIntoView({block:'center', inline:'center'});", element
    )
    wait_for_fonts(driver)
    time.sleep(0.25)
    if not element.screenshot(str(temporary)):
        raise RuntimeError(f"Selenium did not save {destination.name}")

    # A small white border keeps edge-aligned labels from looking clipped while
    # preserving the site's own table styling.
    try:
        from PIL import Image

        with Image.open(temporary) as source:
            source.load()
            canvas = Image.new(
                "RGB",
                (source.width + IMAGE_PADDING * 2, source.height + IMAGE_PADDING * 2),
                "white",
            )
            if source.mode == "RGBA":
                canvas.paste(source, (IMAGE_PADDING, IMAGE_PADDING), source)
            else:
                canvas.paste(source.convert("RGB"), (IMAGE_PADDING, IMAGE_PADDING))
            canvas.save(temporary, "PNG", optimize=True)
    except ImportError:
        pass

    dimensions = png_dimensions(temporary)
    if not dimensions:
        temporary.unlink(missing_ok=True)
        raise RuntimeError(f"The captured {destination.name} PNG is empty or too small")
    os.replace(temporary, destination)
    return dimensions


def close_table_dialog(driver, table) -> None:
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys

    try:
        dialog = table.find_element(By.XPATH, "./ancestor::dialog[1]")
    except Exception:
        dialog = None

    if dialog is not None:
        for button in dialog.find_elements(By.XPATH, ".//button[normalize-space(.)='Close']"):
            try:
                if button.is_displayed():
                    driver.execute_script("arguments[0].click();", button)
                    return
            except Exception:
                continue
        try:
            driver.execute_script(
                "if (arguments[0].open && arguments[0].close) arguments[0].close();",
                dialog,
            )
            return
        except Exception:
            pass
    try:
        driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
    except Exception:
        pass


def dismiss_open_table_dialogs(driver) -> None:
    """Best-effort cleanup so one failed table cannot block the other."""

    try:
        driver.execute_script(
            """
            for (const dialog of document.querySelectorAll('dialog[open]')) {
              const close = Array.from(dialog.querySelectorAll('button')).find(
                button => button.textContent.trim().toLowerCase() === 'close'
              );
              if (close) close.click();
              else if (dialog.close) dialog.close();
              else dialog.removeAttribute('open');
            }
            """
        )
    except Exception:
        pass


def force_size_guide_to_cm(driver, table, timeout: float) -> None:
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait

    try:
        dialog = table.find_element(By.XPATH, "./ancestor::dialog[1]")
    except Exception:
        dialog = table

    toggles = dialog.find_elements(By.CSS_SELECTOR, "input#metric-units")
    toggle = toggles[0] if toggles else None
    if toggle is not None and toggle.is_selected():
        driver.execute_script("arguments[0].click();", toggle)
        WebDriverWait(driver, timeout).until(lambda _current: not toggle.is_selected())

    WebDriverWait(driver, timeout).until(
        lambda _current: " cm" in f" {table.text.casefold()}",
        message="The size guide did not switch to centimetres",
    )


def capture_geometry(
    driver,
    destination: Path,
    timeout: float,
    requested_position: str,
    *,
    control=None,
    selector_timeout: float | None = None,
) -> tuple[tuple[int, int], str, bool, list[dict[str, Any]]]:
    """Capture one geometry PNG per available frame size.

    The legacy ``geometry.png`` is retained as a compatibility copy of the
    first successful size. Every authoritative capture is saved with its size
    in the filename and includes the visible selector in the screenshot.
    """

    if control is None:
        click_named_button(driver, "View geometry", timeout)
    else:
        click_control(driver, control)
    table = wait_for_geometry_table(driver, timeout)
    effective_selector_timeout = (
        selector_timeout if selector_timeout is not None else timeout
    )
    try:
        _size_select, size_details = geometry_size_details(driver, table)
        size_options = [
            option
            for option in size_details.get("options", [])
            if clean_text(option.get("value") or option.get("text"))
        ]
        if not size_options:
            table, actual_position, has_position_selector = set_geometry_position(
                driver,
                table,
                requested_position,
                effective_selector_timeout,
            )
            capture_target = driver.execute_script(
                "return arguments[0].closest('#geometry-data') || arguments[0];",
                table,
            )
            dimensions = screenshot_element(driver, capture_target, destination)
            return dimensions, actual_position, has_position_selector, []

        variants: list[dict[str, Any]] = []
        primary_path: Path | None = None
        primary_position = ""
        has_any_position_selector = False
        for option in size_options:
            requested_size = clean_text(option.get("value") or option.get("text"))
            display_size = clean_text(option.get("text") or requested_size)
            variant_path = geometry_variant_path(destination, display_size)
            variant: dict[str, Any] = {
                "size": display_size,
                "wheel_size": "",
                "filename": variant_path.name,
                "status": TABLE_STATUS_TRANSIENT_ERROR,
                "dimensions": None,
                "position": "",
                "error": "",
            }
            for attempt in range(2):
                try:
                    table, actual_size = set_geometry_size(
                        driver, table, requested_size, effective_selector_timeout
                    )
                    table, actual_position, has_position_selector = set_geometry_position(
                        driver,
                        table,
                        requested_position,
                        effective_selector_timeout,
                    )
                    capture_target = driver.execute_script(
                        "return arguments[0].closest('#geometry-data') || arguments[0];",
                        table,
                    )
                    dimensions = screenshot_element(driver, capture_target, variant_path)
                    variant.update(
                        {
                            "size": actual_size or display_size,
                            "wheel_size": geometry_wheel_size(table),
                            "status": TABLE_STATUS_DOWNLOADED,
                            "dimensions": list(dimensions),
                            "position": actual_position,
                            "error": "",
                        }
                    )
                    if primary_path is None:
                        primary_path = variant_path
                        primary_position = actual_position
                    has_any_position_selector = (
                        has_any_position_selector or has_position_selector
                    )
                    break
                except KeyboardInterrupt:
                    raise
                except Exception as error:
                    variant["error"] = concise_error(error)
                    try:
                        table = wait_for_geometry_table(driver, 1.0)
                    except Exception:
                        pass
                    if attempt == 0:
                        time.sleep(0.25)
            variants.append(variant)

        if primary_path is None:
            errors = "; ".join(
                f"{variant['size']}: {variant['error']}"
                for variant in variants
                if variant.get("error")
            )
            raise RuntimeError(
                f"No size-specific geometry could be captured{': ' + errors if errors else ''}"
            )

        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(
            f".{destination.stem}.compat.tmp{destination.suffix}"
        )
        shutil.copy2(primary_path, temporary)
        os.replace(temporary, destination)
        dimensions = png_dimensions(destination)
        if dimensions is None:
            raise RuntimeError("The compatibility geometry PNG is invalid")
        return (
            dimensions,
            primary_position,
            has_any_position_selector,
            variants,
        )
    finally:
        close_table_dialog(driver, table)


def capture_size_guide(
    driver,
    destination: Path,
    timeout: float,
    *,
    control=None,
    selector_timeout: float | None = None,
) -> tuple[int, int]:
    if control is None:
        click_named_button(driver, "View size guide", timeout)
    else:
        click_control(driver, control)
    table = wait_for_table(driver, SIZE_GUIDE_CAPTION, timeout)
    try:
        force_size_guide_to_cm(
            driver,
            table,
            selector_timeout if selector_timeout is not None else timeout,
        )
        capture_target = driver.execute_script(
            """
            let node = arguments[0].parentElement;
            while (node && !node.hasAttribute('x-data')) node = node.parentElement;
            return node || arguments[0];
            """,
            table,
        )
        return screenshot_element(driver, capture_target, destination)
    finally:
        close_table_dialog(driver, table)


def _capture_result_status(need_capture: bool, image_path: Path) -> str:
    if png_dimensions(image_path) is not None:
        return TABLE_STATUS_DOWNLOADED
    return TABLE_STATUS_PENDING if need_capture else TABLE_STATUS_NOT_AVAILABLE


def capture_orbea_tables(
    driver,
    url: str,
    geometry_path: Path,
    size_guide_path: Path,
    *,
    need_geometry: bool = True,
    need_size_guide: bool = True,
    geometry_position: str = DEFAULT_GEOMETRY_POSITION,
    timeouts: CaptureTimeouts | None = None,
) -> dict[str, Any]:
    """Capture the available Orbea tables once and classify each independently.

    Missing controls are terminal ``not_available`` results. Navigation errors
    and failures after a visible control was found are ``transient_error`` and
    may be retried by the caller once.
    """

    timeouts = timeouts or CaptureTimeouts()
    geometry_dimensions = png_dimensions(geometry_path)
    size_dimensions = png_dimensions(size_guide_path)
    result: dict[str, Any] = {
        "availability_probe_version": AVAILABILITY_PROBE_VERSION,
        "geometry_status": _capture_result_status(need_geometry, geometry_path),
        "size_guide_status": _capture_result_status(need_size_guide, size_guide_path),
        "geometry_ok": not need_geometry and geometry_dimensions is not None,
        "size_guide_ok": not need_size_guide and size_dimensions is not None,
        "geometry_dimensions": geometry_dimensions,
        "size_guide_dimensions": size_dimensions,
        "geometry_position": None,
        "geometry_position_supported": None,
        "geometry_size_selector_supported": None,
        "geometry_variants": [],
        "geometry_error": "",
        "size_guide_error": "",
        "errors": [],
        "retryable": False,
    }

    try:
        driver.set_page_load_timeout(timeouts.page_load)
        driver.get(url)
    except KeyboardInterrupt:
        raise
    except Exception as error:
        message = f"page: {concise_error(error)}"
        if need_geometry:
            result["geometry_status"] = TABLE_STATUS_TRANSIENT_ERROR
            result["geometry_error"] = message
        if need_size_guide:
            result["size_guide_status"] = TABLE_STATUS_TRANSIENT_ERROR
            result["size_guide_error"] = message
        result["errors"].append(message)
        result["retryable"] = need_geometry or need_size_guide
        return result

    try:
        controls = discover_table_controls(
            driver,
            need_geometry=need_geometry,
            need_size_guide=need_size_guide,
            timeout=timeouts.control_discovery,
        )
    except KeyboardInterrupt:
        raise
    except Exception as error:
        message = f"controls: {concise_error(error)}"
        if need_geometry:
            result["geometry_status"] = TABLE_STATUS_TRANSIENT_ERROR
            result["geometry_error"] = message
        if need_size_guide:
            result["size_guide_status"] = TABLE_STATUS_TRANSIENT_ERROR
            result["size_guide_error"] = message
        result["errors"].append(message)
        result["retryable"] = need_geometry or need_size_guide
        return result

    if need_geometry:
        if controls["geometry"] is None:
            result["geometry_status"] = TABLE_STATUS_NOT_AVAILABLE
        else:
            try:
                capture = capture_geometry(
                    driver,
                    geometry_path,
                    timeouts.table_render,
                    geometry_position,
                    control=controls["geometry"],
                    selector_timeout=timeouts.selector,
                )
                dimensions, actual_position, position_supported = capture[:3]
                variants = list(capture[3]) if len(capture) > 3 else []
                failed_variants = [
                    variant
                    for variant in variants
                    if variant.get("status") != TABLE_STATUS_DOWNLOADED
                ]
                result["geometry_status"] = (
                    TABLE_STATUS_TRANSIENT_ERROR
                    if failed_variants
                    else TABLE_STATUS_DOWNLOADED
                )
                result["geometry_ok"] = not failed_variants
                result["geometry_dimensions"] = dimensions
                result["geometry_position"] = actual_position
                result["geometry_position_supported"] = position_supported
                result["geometry_size_selector_supported"] = bool(variants)
                result["geometry_variants"] = variants
                if failed_variants:
                    messages = [
                        f"geometry {variant.get('size') or 'unknown size'}: "
                        f"{variant.get('error') or 'capture failed'}"
                        for variant in failed_variants
                    ]
                    result["geometry_error"] = " | ".join(messages)
                    result["errors"].extend(messages)
            except KeyboardInterrupt:
                raise
            except Exception as error:
                message = f"geometry: {concise_error(error)}"
                result["geometry_status"] = TABLE_STATUS_TRANSIENT_ERROR
                result["geometry_error"] = message
                result["errors"].append(message)
                dismiss_open_table_dialogs(driver)

    if need_size_guide:
        if controls["size_guide"] is None:
            result["size_guide_status"] = TABLE_STATUS_NOT_AVAILABLE
        else:
            try:
                dimensions = capture_size_guide(
                    driver,
                    size_guide_path,
                    timeouts.table_render,
                    control=controls["size_guide"],
                    selector_timeout=timeouts.selector,
                )
                result["size_guide_status"] = TABLE_STATUS_DOWNLOADED
                result["size_guide_ok"] = True
                result["size_guide_dimensions"] = dimensions
            except KeyboardInterrupt:
                raise
            except Exception as error:
                message = f"size guide: {concise_error(error)}"
                result["size_guide_status"] = TABLE_STATUS_TRANSIENT_ERROR
                result["size_guide_error"] = message
                result["errors"].append(message)
                dismiss_open_table_dialogs(driver)

    result["retryable"] = any(
        result[key] == TABLE_STATUS_TRANSIENT_ERROR
        for key in ("geometry_status", "size_guide_status")
    )
    return result


def capture_page(
    driver,
    job: PageJob,
    geometry_path: Path,
    size_guide_path: Path,
    need_geometry: bool,
    need_size_guide: bool,
    timeout: float,
    geometry_position: str,
    *,
    timeouts: CaptureTimeouts | None = None,
) -> dict[str, Any]:
    """Backward-compatible PageJob adapter for :func:`capture_orbea_tables`."""

    effective_timeouts = timeouts or CaptureTimeouts(page_load=timeout)
    return capture_orbea_tables(
        driver,
        job.url,
        geometry_path,
        size_guide_path,
        need_geometry=need_geometry,
        need_size_guide=need_size_guide,
        geometry_position=geometry_position,
        timeouts=effective_timeouts,
    )


def page_paths(job: PageJob, output_dir: Path) -> tuple[Path, Path, Path]:
    folder = output_dir / "images" / job.folder_name
    return folder, folder / "geometry.png", folder / "size-guide-cm.png"


def page_record(
    job: PageJob,
    output_dir: Path,
    prior: dict[str, Any] | None = None,
) -> dict[str, Any]:
    folder, geometry, size_guide = page_paths(job, output_dir)
    record = dict(prior or {})
    record.update(
        {
            "url": job.url,
            "canonical_url": job.canonical_url,
            "folder": relative_path(folder, output_dir),
            "geometry_image": relative_path(geometry, output_dir),
            "size_guide_cm_image": relative_path(size_guide, output_dir),
            "models": list(
                dict.fromkeys(
                    row.values.get("Catalogue Model", "")
                    for row in job.rows
                    if row.values.get("Catalogue Model", "")
                )
            ),
            "variant_skus": list(
                dict.fromkeys(
                    row.values.get("Variant SKU", "")
                    for row in job.rows
                    if row.values.get("Variant SKU", "")
                )
            ),
            "source_rows": [row.workbook_row for row in job.rows],
        }
    )
    record.setdefault("status", "pending")
    record.setdefault("attempts", 0)
    record.setdefault("errors", [])
    record.setdefault("availability_probe_version", 0)
    record.setdefault("geometry_status", TABLE_STATUS_PENDING)
    record.setdefault("size_guide_status", TABLE_STATUS_PENDING)
    record.setdefault("geometry_variants", [])
    return record


def _normalise_table_status(value: Any) -> str:
    status = clean_text(value)
    if status in {
        TABLE_STATUS_DOWNLOADED,
        TABLE_STATUS_NOT_AVAILABLE,
        TABLE_STATUS_TRANSIENT_ERROR,
        TABLE_STATUS_PENDING,
    }:
        return status
    return TABLE_STATUS_PENDING


def update_record_status(record: dict[str, Any]) -> str:
    statuses = (
        _normalise_table_status(record.get("geometry_status")),
        _normalise_table_status(record.get("size_guide_status")),
    )
    if all(status in TERMINAL_TABLE_STATUSES for status in statuses):
        status = "complete"
    elif TABLE_STATUS_TRANSIENT_ERROR in statuses:
        status = "error"
    elif any(status in TERMINAL_TABLE_STATUSES for status in statuses):
        status = "partial"
    else:
        status = "pending"
    record["status"] = status
    return status


def record_needs_processing(record: dict[str, Any]) -> bool:
    if record.get("availability_probe_version") != AVAILABILITY_PROBE_VERSION:
        return True
    if (
        _normalise_table_status(record.get("geometry_status"))
        == TABLE_STATUS_DOWNLOADED
        and record.get("geometry_capture_version") != GEOMETRY_CAPTURE_VERSION
    ):
        return True
    return any(
        _normalise_table_status(record.get(key)) not in TERMINAL_TABLE_STATUSES
        for key in ("geometry_status", "size_guide_status")
    )


def refresh_record_from_files(
    record: dict[str, Any],
    output_dir: Path,
    required_geometry_position: str | None = None,
) -> None:
    geometry = output_dir / record["geometry_image"]
    size_guide = output_dir / record["size_guide_cm_image"]
    geometry_dimensions = png_dimensions(geometry)
    size_dimensions = png_dimensions(size_guide)
    geometry_ok = geometry_dimensions is not None
    if required_geometry_position is not None:
        geometry_ok = (
            geometry_ok
            and record.get("geometry_capture_version") == GEOMETRY_CAPTURE_VERSION
            and record.get("geometry_position_requested") == required_geometry_position
        )
    variants = list(record.get("geometry_variants", []) or [])
    if geometry_ok and record.get("geometry_size_selector_supported"):
        geometry_ok = bool(variants) and all(
            variant.get("status") == TABLE_STATUS_DOWNLOADED
            and png_dimensions(
                geometry.parent / clean_text(variant.get("filename"))
            )
            is not None
            for variant in variants
        )
    probe_is_current = (
        record.get("availability_probe_version") == AVAILABILITY_PROBE_VERSION
    )
    prior_geometry_status = _normalise_table_status(record.get("geometry_status"))
    prior_size_status = _normalise_table_status(record.get("size_guide_status"))
    if geometry_ok:
        record["geometry_status"] = TABLE_STATUS_DOWNLOADED
    elif probe_is_current and prior_geometry_status in {
        TABLE_STATUS_NOT_AVAILABLE,
        TABLE_STATUS_TRANSIENT_ERROR,
    }:
        record["geometry_status"] = prior_geometry_status
    else:
        record["geometry_status"] = TABLE_STATUS_PENDING

    if size_dimensions is not None:
        record["size_guide_status"] = TABLE_STATUS_DOWNLOADED
    elif probe_is_current and prior_size_status in {
        TABLE_STATUS_NOT_AVAILABLE,
        TABLE_STATUS_TRANSIENT_ERROR,
    }:
        record["size_guide_status"] = prior_size_status
    else:
        record["size_guide_status"] = TABLE_STATUS_PENDING

    record["geometry_ok"] = record["geometry_status"] == TABLE_STATUS_DOWNLOADED
    record["size_guide_cm_ok"] = (
        record["size_guide_status"] == TABLE_STATUS_DOWNLOADED
    )
    record["geometry_dimensions"] = list(geometry_dimensions) if geometry_dimensions else None
    record["size_guide_cm_dimensions"] = list(size_dimensions) if size_dimensions else None
    if (
        record["geometry_status"] == TABLE_STATUS_DOWNLOADED
        and record["size_guide_status"] == TABLE_STATUS_DOWNLOADED
    ):
        record["availability_probe_version"] = AVAILABILITY_PROBE_VERSION
    update_record_status(record)


def apply_capture_result(
    record: dict[str, Any],
    result: dict[str, Any],
    geometry_position: str,
) -> None:
    """Merge one capture attempt without overwriting terminal skipped tables."""

    for record_key, result_key in (
        ("geometry_status", "geometry_status"),
        ("size_guide_status", "size_guide_status"),
    ):
        result_status = _normalise_table_status(result.get(result_key))
        if result_status != TABLE_STATUS_PENDING:
            record[record_key] = result_status

    record["availability_probe_version"] = result.get(
        "availability_probe_version", AVAILABILITY_PROBE_VERSION
    )
    record["errors"] = list(result.get("errors", []))
    record["geometry_error"] = clean_text(result.get("geometry_error"))
    record["size_guide_error"] = clean_text(result.get("size_guide_error"))
    if "geometry_variants" in result:
        record["geometry_variants"] = list(result.get("geometry_variants") or [])
    if result.get("geometry_size_selector_supported") is not None:
        record["geometry_size_selector_supported"] = bool(
            result.get("geometry_size_selector_supported")
        )
    geometry_dimensions = result.get("geometry_dimensions")
    size_dimensions = result.get("size_guide_dimensions")
    if geometry_dimensions is not None:
        record["geometry_dimensions"] = list(geometry_dimensions)
    if size_dimensions is not None:
        record["size_guide_cm_dimensions"] = list(size_dimensions)

    if result.get("geometry_status") == TABLE_STATUS_DOWNLOADED:
        record["geometry_position"] = result.get("geometry_position") or ""
        record["geometry_position_supported"] = bool(
            result.get("geometry_position_supported")
        )
        record["geometry_position_requested"] = geometry_position
        record["geometry_capture_version"] = GEOMETRY_CAPTURE_VERSION

    record["geometry_ok"] = (
        record.get("geometry_status") == TABLE_STATUS_DOWNLOADED
    )
    record["size_guide_cm_ok"] = (
        record.get("size_guide_status") == TABLE_STATUS_DOWNLOADED
    )
    update_record_status(record)


def save_checkpoint(path: Path, checkpoint: dict[str, Any]) -> None:
    checkpoint["updated_at"] = utc_now()
    atomic_write_json(path, checkpoint)


def write_manifests(
    output_dir: Path,
    checkpoint: dict[str, Any],
    source_rows: list[SourceRow],
) -> None:
    pages = checkpoint.get("pages", {})
    manifest_json = {
        "generated_at": utc_now(),
        "workbook": checkpoint.get("workbook"),
        "summary": checkpoint.get("summary", {}),
        "pages": list(pages.values()),
    }
    atomic_write_json(output_dir / "download_manifest.json", manifest_json)

    page_by_url = {
        record.get("canonical_url", ""): record for record in pages.values()
    }
    selected_headers = [
        "Variant SKU",
        "Pimbo Product",
        "Stock",
        "Catalogue Code",
        "Catalogue Model",
        "Year",
        "Category",
        "Subcategory",
        "Match Method",
        "Pimbo URL",
        "Orbea URL",
        "Page",
    ]
    csv_headers = [
        "Workbook Row",
        *selected_headers,
        "Image Status",
        "Image Folder",
        "Geometry Status",
        "Geometry PNG",
        "Geometry Sizes",
        "Geometry Wheel Sizes",
        "Geometry PNGs",
        "Geometry Position",
        "Size Guide Status",
        "Size Guide CM PNG",
        "Image Error",
    ]
    csv_path = output_dir / "image_manifest.csv"
    temporary = csv_path.with_name(f".{csv_path.name}.tmp")
    output_dir.mkdir(parents=True, exist_ok=True)
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=csv_headers)
        writer.writeheader()
        for source in source_rows:
            record = page_by_url.get(canonicalize_url(source.orbea_url), {})
            image_folder = output_dir / record["folder"] if record.get("folder") else None
            geometry = (
                output_dir / record["geometry_image"]
                if record.get("geometry_image")
                else None
            )
            geometry_variants = list(record.get("geometry_variants", []) or [])
            geometry_variant_paths = [
                output_dir / record["folder"] / clean_text(variant.get("filename"))
                for variant in geometry_variants
                if record.get("folder") and clean_text(variant.get("filename"))
            ]
            size_guide = (
                output_dir / record["size_guide_cm_image"]
                if record.get("size_guide_cm_image")
                else None
            )
            writer.writerow(
                {
                    "Workbook Row": source.workbook_row,
                    **{header: source.values.get(header, "") for header in selected_headers},
                    "Image Status": record.get("status", "invalid URL"),
                    "Image Folder": str(image_folder.resolve()) if image_folder else "",
                    "Geometry Status": record.get("geometry_status", ""),
                    "Geometry PNG": str(geometry.resolve()) if geometry else "",
                    "Geometry Sizes": "; ".join(
                        clean_text(variant.get("size"))
                        for variant in geometry_variants
                        if clean_text(variant.get("size"))
                    ),
                    "Geometry Wheel Sizes": "; ".join(
                        clean_text(variant.get("wheel_size"))
                        for variant in geometry_variants
                        if clean_text(variant.get("wheel_size"))
                    ),
                    "Geometry PNGs": "; ".join(
                        str(path.resolve()) for path in geometry_variant_paths
                    ),
                    "Geometry Position": record.get("geometry_position", ""),
                    "Size Guide Status": record.get("size_guide_status", ""),
                    "Size Guide CM PNG": str(size_guide.resolve()) if size_guide else "",
                    "Image Error": " | ".join(record.get("errors", [])),
                }
            )
    os.replace(temporary, csv_path)


def update_summary(checkpoint: dict[str, Any], total_pages: int) -> dict[str, int]:
    records = list(checkpoint.get("pages", {}).values())
    summary = {
        "total_pages": total_pages,
        "complete": sum(record.get("status") == "complete" for record in records),
        "partial": sum(record.get("status") == "partial" for record in records),
        "failed": sum(record.get("status") == "error" for record in records),
        "pending": max(
            total_pages
            - sum(
                record.get("status") in {"complete", "partial", "error"}
                for record in records
            ),
            0,
        ),
    }
    checkpoint["summary"] = summary
    checkpoint["completed"] = summary["complete"] == total_pages
    if checkpoint["completed"]:
        checkpoint["completed_at"] = utc_now()
    return summary


def safely_quit(driver) -> None:
    if driver is None:
        return
    try:
        driver.quit()
    except Exception:
        pass


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    project_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description=(
            "Save every size-specific Orbea geometry and the centimetre "
            "size-guide table as labelled PNG files."
        )
    )
    parser.add_argument(
        "--workbook",
        type=Path,
        default=project_root / "output" / "orbea_pimbo" / "orbea_pimbo_variant_matches.xlsx",
        help="Input .xlsx file (default: output/orbea_pimbo/orbea_pimbo_variant_matches.xlsx)",
    )
    parser.add_argument("--sheet", default=DEFAULT_SHEET, help="Worksheet name")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=project_root / "output" / "orbea_table_images",
        help="Destination folder (default: output/orbea_table_images)",
    )
    parser.add_argument(
        "--browser", choices=("chrome", "edge", "firefox"), default="chrome"
    )
    parser.add_argument(
        "--geometry-position",
        choices=("low", "high", "page-default"),
        default=DEFAULT_GEOMETRY_POSITION,
        help=(
            "Position used when an Orbea geometry table offers HIGH/LOW "
            f"(default: {DEFAULT_GEOMETRY_POSITION})"
        ),
    )
    parser.add_argument(
        "--show-browser", action="store_true", help="Show the automated browser window"
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Back up the old checkpoint and recapture every image",
    )
    parser.add_argument(
        "--force", action="store_true", help="Recapture images even when valid files exist"
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        help="Process at most this many pending pages (useful for a test run)",
    )
    parser.add_argument(
        "--attempts", type=int, default=2, help="Attempts per page (default: 2)"
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help=f"Maximum page-navigation seconds (default: {DEFAULT_TIMEOUT:g})",
    )
    parser.add_argument(
        "--control-timeout",
        type=float,
        default=DEFAULT_CONTROL_DISCOVERY_TIMEOUT,
        help=(
            "Seconds to discover Geometry/Size Guide controls together "
            f"(default: {DEFAULT_CONTROL_DISCOVERY_TIMEOUT:g})"
        ),
    )
    parser.add_argument(
        "--table-timeout",
        type=float,
        default=DEFAULT_TABLE_RENDER_TIMEOUT,
        help=f"Seconds for a visible table to render (default: {DEFAULT_TABLE_RENDER_TIMEOUT:g})",
    )
    parser.add_argument(
        "--selector-timeout",
        type=float,
        default=DEFAULT_SELECTOR_TIMEOUT,
        help=f"Seconds for LOW/CM selector changes (default: {DEFAULT_SELECTOR_TIMEOUT:g})",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=DEFAULT_DELAY,
        help=f"Seconds between pages (default: {DEFAULT_DELAY:g})",
    )
    args = parser.parse_args(argv)
    if args.max_pages is not None and args.max_pages < 1:
        parser.error("--max-pages must be at least 1")
    if args.attempts not in {1, 2}:
        parser.error("--attempts must be 1 or 2 (one initial attempt and one retry)")
    for option in ("timeout", "control_timeout", "table_timeout", "selector_timeout"):
        if getattr(args, option) <= 0:
            parser.error(f"--{option.replace('_', '-')} must be greater than zero")
    if args.delay < 0:
        parser.error("--delay cannot be negative")
    return args


def run(args: argparse.Namespace) -> int:
    workbook = args.workbook.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    checkpoint_path = output_dir / "checkpoint.json"
    capture_timeouts = CaptureTimeouts(
        page_load=getattr(args, "timeout", DEFAULT_TIMEOUT),
        control_discovery=getattr(
            args, "control_timeout", DEFAULT_CONTROL_DISCOVERY_TIMEOUT
        ),
        table_render=getattr(args, "table_timeout", DEFAULT_TABLE_RENDER_TIMEOUT),
        selector=getattr(args, "selector_timeout", DEFAULT_SELECTOR_TIMEOUT),
    )

    if not workbook.is_file():
        raise FileNotFoundError(f"Workbook not found: {workbook}")
    output_dir.mkdir(parents=True, exist_ok=True)

    source_rows = load_source_rows(workbook, args.sheet)
    jobs, invalid_rows = build_jobs(source_rows)
    if not jobs:
        raise ValueError("No valid web addresses were found in the 'Orbea URL' column")

    checkpoint = load_checkpoint(checkpoint_path, args.fresh)
    checkpoint["workbook"] = workbook_fingerprint(workbook)
    checkpoint["sheet"] = args.sheet
    checkpoint["output_dir"] = str(output_dir)
    checkpoint["geometry_position"] = args.geometry_position
    checkpoint["availability_probe_version"] = AVAILABILITY_PROBE_VERSION

    for job in jobs:
        prior = checkpoint["pages"].get(job.canonical_url)
        record = page_record(job, output_dir, prior)
        refresh_record_from_files(record, output_dir, args.geometry_position)
        if args.fresh or args.force:
            record["availability_probe_version"] = 0
            record["geometry_status"] = TABLE_STATUS_PENDING
            record["size_guide_status"] = TABLE_STATUS_PENDING
            update_record_status(record)
        checkpoint["pages"][job.canonical_url] = record

    # Keep the checkpoint aligned with the current workbook if rows were removed.
    active_urls = {job.canonical_url for job in jobs}
    checkpoint["pages"] = {
        url: record
        for url, record in checkpoint["pages"].items()
        if url in active_urls
    }

    valid_rows = len(source_rows) - len(invalid_rows)
    print(
        f"Workbook rows: {len(source_rows)} | Valid URLs: {valid_rows} | "
        f"Unique Orbea pages: {len(jobs)} | Geometry: every available frame size"
    )
    if invalid_rows:
        print(f"Rows skipped because the Orbea URL is blank/invalid: {len(invalid_rows)}")

    update_summary(checkpoint, len(jobs))
    save_checkpoint(checkpoint_path, checkpoint)
    write_manifests(output_dir, checkpoint, source_rows)

    pending_jobs = []
    for job in jobs:
        record = checkpoint["pages"][job.canonical_url]
        if args.fresh or args.force or record_needs_processing(record):
            pending_jobs.append(job)

    if args.max_pages is not None:
        pending_jobs = pending_jobs[: args.max_pages]

    if not pending_jobs:
        print("Everything is already complete; there is nothing to download.")
        print(f"Images: {output_dir / 'images'}")
        print(f"Manifest: {output_dir / 'image_manifest.csv'}")
        return 0

    already_complete = sum(
        checkpoint["pages"][job.canonical_url].get("status") == "complete"
        for job in jobs
    )
    print(f"Starting: {already_complete} complete, {len(pending_jobs)} selected for this run.")
    print("You can press Ctrl+C at any time; run the same command again to resume.\n")

    driver = None
    interrupted = False
    try:
        driver = create_driver(
            args.browser,
            args.show_browser,
            page_load_timeout=capture_timeouts.page_load,
        )
        for position, job in enumerate(pending_jobs, start=1):
            record = checkpoint["pages"][job.canonical_url]
            folder, geometry_path, size_guide_path = page_paths(job, output_dir)
            geometry_status = _normalise_table_status(record.get("geometry_status"))
            size_status = _normalise_table_status(record.get("size_guide_status"))
            need_geometry = args.fresh or args.force or (
                geometry_status not in TERMINAL_TABLE_STATUSES
            )
            need_size_guide = args.fresh or args.force or (
                size_status not in TERMINAL_TABLE_STATUSES
            )

            print(f"[{position}/{len(pending_jobs)}] {job.label}")
            last_result: dict[str, Any] | None = None
            for attempt in range(1, args.attempts + 1):
                if not need_geometry and not need_size_guide:
                    break
                try:
                    last_result = capture_page(
                        driver,
                        job,
                        geometry_path,
                        size_guide_path,
                        need_geometry=need_geometry,
                        need_size_guide=need_size_guide,
                        timeout=args.timeout,
                        geometry_position=args.geometry_position,
                        timeouts=capture_timeouts,
                    )
                    apply_capture_result(record, last_result, args.geometry_position)
                except KeyboardInterrupt:
                    raise
                except Exception as error:
                    last_result = {
                        "availability_probe_version": AVAILABILITY_PROBE_VERSION,
                        "geometry_status": (
                            TABLE_STATUS_TRANSIENT_ERROR
                            if need_geometry
                            else record.get("geometry_status", TABLE_STATUS_PENDING)
                        ),
                        "size_guide_status": (
                            TABLE_STATUS_TRANSIENT_ERROR
                            if need_size_guide
                            else record.get("size_guide_status", TABLE_STATUS_PENDING)
                        ),
                        "errors": [f"page: {concise_error(error)}"],
                        "retryable": True,
                    }
                    apply_capture_result(record, last_result, args.geometry_position)

                record["attempts"] = int(record.get("attempts", 0)) + 1
                need_geometry = (
                    record.get("geometry_status") == TABLE_STATUS_TRANSIENT_ERROR
                )
                need_size_guide = (
                    record.get("size_guide_status") == TABLE_STATUS_TRANSIENT_ERROR
                )
                if not need_geometry and not need_size_guide:
                    break
                if attempt < args.attempts:
                    reasons = " | ".join(last_result.get("errors", []))
                    print(f"  attempt {attempt} incomplete; retrying ({reasons})")
                    time.sleep(1.0)

            update_record_status(record)
            record["last_attempt_at"] = utc_now()
            checkpoint["pages"][job.canonical_url] = record
            summary = update_summary(checkpoint, len(jobs))
            save_checkpoint(checkpoint_path, checkpoint)
            write_manifests(output_dir, checkpoint, source_rows)

            geometry_mark = record.get("geometry_status", TABLE_STATUS_PENDING).replace(
                "_", " "
            ).upper()
            size_mark = record.get("size_guide_status", TABLE_STATUS_PENDING).replace(
                "_", " "
            ).upper()
            position_label = record.get("geometry_position") or "not adjustable"
            print(
                f"  geometry: {geometry_mark} ({position_label}) | "
                f"size guide (CM): {size_mark}"
            )
            if record["errors"]:
                print(f"  {' | '.join(record['errors'])}")
            print(
                f"  overall: {summary['complete']}/{summary['total_pages']} pages complete"
            )
            if args.delay and position < len(pending_jobs):
                time.sleep(args.delay)
    except KeyboardInterrupt:
        interrupted = True
        print("\nStopped by Ctrl+C. Progress has been saved.")
    finally:
        safely_quit(driver)
        summary = update_summary(checkpoint, len(jobs))
        save_checkpoint(checkpoint_path, checkpoint)
        write_manifests(output_dir, checkpoint, source_rows)

    print("\nOutput")
    print(f"  Images:   {output_dir / 'images'}")
    print(f"  Manifest: {output_dir / 'image_manifest.csv'}")
    print(f"  Progress: {checkpoint_path}")
    print(
        f"  Complete: {summary['complete']}/{summary['total_pages']} | "
        f"Partial: {summary['partial']} | Failed: {summary['failed']}"
    )

    if interrupted:
        return 130
    if args.max_pages is not None:
        selected_errors = sum(
            checkpoint["pages"][job.canonical_url].get("status") != "complete"
            for job in pending_jobs
        )
        return 2 if selected_errors else 0
    return 0 if summary["complete"] == summary["total_pages"] else 2


def main(argv: list[str] | None = None) -> int:
    try:
        return run(parse_args(argv))
    except KeyboardInterrupt:
        print("\nStopped by Ctrl+C.")
        return 130
    except Exception as error:
        print(f"ERROR: {concise_error(error)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
