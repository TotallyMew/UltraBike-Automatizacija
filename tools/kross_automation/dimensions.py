"""Capture a complete, translated KROSS bicycle dimensions table.

KROSS renders wide geometry tables inside a horizontally scrollable
``div.dimensions-table``.  Screenshotting that div directly only captures its
visible client width.  Before taking the screenshot we expand the container to
the table's full ``scrollWidth`` and remove clipping from its ancestors.
"""

from __future__ import annotations

import os
import re
import time
import unicodedata
from pathlib import Path
from typing import Any


DIMENSIONS_IMAGE_NAME = "dimensions-table.png"
SIZE_CHART_IMAGE_NAME = "size-height-table.png"
DIMENSIONS_CONTAINER_SELECTOR = "#choose_size div.dimensions-table, div.dimensions-table"

LABEL_TRANSLATIONS = {
    "rozmiar": "SIZE",
    "wzrost": "HEIGHT (CM)",
    "przekrok": "FRAME HEIGHT",
    "rozmiar kol": "WHEEL SIZE",
    "fs - rozmiar ramy": "FS – FRAME SIZE",
    "st - dlugosc rury podsiodlowej": "ST – SEAT TUBE LENGTH",
    "tt - efektywna dlugosc gornej rury": "TT – EFFECTIVE TOP TUBE LENGTH",
    "ht - dlugosc glowki ramy": "HT – HEAD TUBE LENGTH",
    "sa - kat rury podsiodlowej": "SA – SEAT TUBE ANGLE",
    "ha - kat glowki ramy": "HA – HEAD TUBE ANGLE",
    "cs - dlugosc tylnych widelek": "CS – CHAINSTAY LENGTH",
    "wb - baza kol": "WB – WHEEL BASE",
    "reach": "REACH",
    "stack": "STACK",
    "bbdrop": "BBDROP",
    "szer. kierownicy": "HANDLEBAR WIDTH",
    "wspornik siodla": "SEATPOST",
    "dl. ramienia korby": "L CRANK ARM",
    "wspornik kierownicy": "STEM",
    "waga (kg)": "WEIGHT (KG)",
}

COOKIE_CONSENT_SELECTORS = (
    "#CybotCookiebotDialogBodyButtonDecline",
    "#onetrust-accept-btn-handler",
    "button#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
    "[aria-label='Accept cookies']",
)

OVERLAY_SELECTORS = (
    "#CybotCookiebotDialog",
    "div.snrs-modal",
    "#snrs-wp-subscriber",
)


class KrossDimensionsNotAvailable(RuntimeError):
    """The product page does not expose a KROSS dimensions table."""


def normalize_label(value: str) -> str:
    text = str(value or "").strip().lower().replace("ł", "l")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(character for character in text if not unicodedata.combining(character))
    return re.sub(r"\s+", " ", text)


PREPARE_TABLE_JS = r"""
const selector = arguments[0];
const translations = arguments[1];
const overlays = arguments[2];

function normalize(text) {
    return String(text || '').trim().toLowerCase()
        .replace(/\u0142/g, 'l')
        .normalize('NFKD')
        .replace(/[\u0300-\u036f]/g, '')
        .replace(/\s+/g, ' ');
}

const container = document.querySelector(selector);
if (!container) return {ok: false, reason: 'container not found'};
const table = container.querySelector('table');
if (!table) return {ok: false, reason: 'table not found'};

const headerCells = table.querySelectorAll('thead th, thead td');
if (headerCells.length) {
    const key = normalize(headerCells[0].textContent);
    if (translations[key]) headerCells[0].textContent = translations[key];
}

const bodyRows = table.querySelectorAll('tbody tr');
if (!bodyRows.length) return {ok: false, reason: 'no body rows'};
for (const row of bodyRows) {
    const cells = row.querySelectorAll('td, th');
    if (!cells.length) continue;
    const key = normalize(cells[0].textContent);
    cells[0].textContent = translations[key]
        || cells[0].textContent.trim().replace(/\s+/g, ' ').toUpperCase();
    for (let index = 1; index < cells.length; index++) {
        cells[index].textContent = cells[index].textContent.trim()
            .replace(/\s+/g, ' ')
            .replace(/(\d),(?=\d)/g, '$1.');
    }
}

for (const overlaySelector of overlays) {
    for (const overlay of document.querySelectorAll(overlaySelector)) {
        overlay.style.setProperty('display', 'none', 'important');
    }
}

// KROSS keeps both the global header and the product-tab navigation stuck to
// the top of the viewport. Selenium's element screenshot includes anything
// painted over the target, so hide external sticky/fixed chrome while leaving
// sticky cells inside the dimensions table untouched.
for (const candidate of document.querySelectorAll('body *')) {
    if (
        candidate === container
        || candidate.contains(container)
        || container.contains(candidate)
    ) continue;
    const position = window.getComputedStyle(candidate).position;
    if (position === 'fixed' || position === 'sticky') {
        candidate.style.setProperty('visibility', 'hidden', 'important');
    }
}

const tableWidth = Math.ceil(Math.max(table.scrollWidth, table.getBoundingClientRect().width));
container.style.setProperty('box-sizing', 'border-box', 'important');
container.style.setProperty('width', `${tableWidth}px`, 'important');
container.style.setProperty('min-width', `${tableWidth}px`, 'important');
container.style.setProperty('max-width', 'none', 'important');
container.style.setProperty('flex', `0 0 ${tableWidth}px`, 'important');
container.style.setProperty('overflow', 'visible', 'important');
container.style.setProperty('background', '#fff', 'important');
table.style.setProperty('width', `${tableWidth}px`, 'important');
table.style.setProperty('min-width', `${tableWidth}px`, 'important');
table.style.setProperty('max-width', 'none', 'important');

let ancestor = container.parentElement;
while (ancestor && ancestor !== document.body) {
    ancestor.style.setProperty('overflow-x', 'visible', 'important');
    ancestor.style.setProperty('max-width', 'none', 'important');
    ancestor = ancestor.parentElement;
}
document.documentElement.style.setProperty('min-width', `${tableWidth}px`, 'important');
document.body.style.setProperty('min-width', `${tableWidth}px`, 'important');

const captureWidth = Math.ceil(container.getBoundingClientRect().width);
const tableRect = table.getBoundingClientRect();
const firstTwoRows = Array.from(table.rows).slice(0, 2);
const sizeChartHeight = firstTwoRows.length
    ? Math.ceil(Math.max(...firstTwoRows.map(row => row.getBoundingClientRect().bottom)) - tableRect.top)
    : 0;
return {
    ok: captureWidth >= tableWidth,
    reason: captureWidth >= tableWidth ? '' : 'capture target is still clipped',
    rows: bodyRows.length,
    columns: table.rows.length ? table.rows[0].cells.length : 0,
    tableWidth,
    captureWidth,
    clientWidth: container.clientWidth,
    scrollWidth: container.scrollWidth,
    sizeChartHeight,
};
"""


def _visible_elements(driver: Any, selector: str) -> list[Any]:
    from selenium.webdriver.common.by import By

    result: list[Any] = []
    for element in driver.find_elements(By.CSS_SELECTOR, selector):
        try:
            if element.is_displayed():
                result.append(element)
        except Exception:
            continue
    return result


def _dismiss_cookie_consent(driver: Any) -> None:
    for selector in COOKIE_CONSENT_SELECTORS:
        for element in _visible_elements(driver, selector):
            try:
                element.click()
                time.sleep(0.15)
                break
            except Exception:
                continue
    from selenium.webdriver.common.by import By

    for label in ("Nie, dziękuję", "Nie, dziekuje", "Odmowa", "Zezwól na wszystkie"):
        try:
            elements = driver.find_elements(
                By.XPATH,
                f"//button[contains(normalize-space(.), '{label}')]",
            )
        except Exception:
            elements = []
        for element in elements:
            try:
                if element.is_displayed():
                    driver.execute_script("arguments[0].click();", element)
                    time.sleep(0.15)
                    break
            except Exception:
                continue


def _wait_for_container(driver: Any, timeout: float) -> Any:
    from selenium.webdriver.support.ui import WebDriverWait

    try:
        return WebDriverWait(driver, timeout, poll_frequency=0.15).until(
            lambda current: next(
                iter(_visible_elements(current, DIMENSIONS_CONTAINER_SELECTOR)),
                None,
            )
        )
    except Exception as error:
        raise KrossDimensionsNotAvailable(
            "KROSS dimensions table was not found on this product page"
        ) from error


def _wait_for_fonts(driver: Any) -> None:
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


def _validate_capture_metrics(result: Any) -> dict[str, Any]:
    if not isinstance(result, dict) or not result.get("ok"):
        reason = result.get("reason") if isinstance(result, dict) else "invalid browser response"
        raise RuntimeError(f"KROSS dimensions preparation failed: {reason}")
    table_width = int(result.get("tableWidth") or 0)
    capture_width = int(result.get("captureWidth") or 0)
    if table_width <= 0 or capture_width < table_width:
        raise RuntimeError(
            "KROSS dimensions capture is still horizontally clipped "
            f"({capture_width}px of {table_width}px)"
        )
    return result


def _prepare_screenshot(source_path: Path) -> tuple[int, int]:
    """Validate and efficiently encode a screenshot without adding a border."""

    try:
        from PIL import Image
    except ImportError as error:
        raise RuntimeError("Pillow is required to verify the KROSS dimensions PNG") from error

    with Image.open(source_path) as source:
        source.load()
        if source.width < 20 or source.height < 20:
            raise RuntimeError("The KROSS dimensions screenshot is empty or too small")
        dimensions = (source.width, source.height)
        image = source.convert("RGB").copy()

    # Pillow's exhaustive PNG optimiser becomes a visible multi-second pause
    # on very wide multi-size tables. A low compression level keeps the exact
    # pixels while making the hand-off to the next SKU fast.
    image.save(source_path, "PNG", compress_level=1)
    return dimensions


def _save_size_chart_crop(
    source_path: Path,
    destination: Path,
    crop_height: int,
) -> tuple[int, int]:
    """Save the full-width SIZE + HEIGHT rows flush to the PNG edges."""

    try:
        from PIL import Image
    except ImportError as error:
        raise RuntimeError("Pillow is required to crop the KROSS size table") from error

    with Image.open(source_path) as source:
        source.load()
        height = min(int(crop_height), source.height)
        if source.width < 20 or height < 20:
            raise RuntimeError("The KROSS size/height table crop is empty or too small")
        crop = source.crop((0, 0, source.width, height)).convert("RGB")
        destination.parent.mkdir(parents=True, exist_ok=True)
        crop.save(destination, "PNG", compress_level=1)
        return crop.width, crop.height


def capture_kross_dimensions_table(
    driver: Any,
    page_url: str,
    destination: Path,
    *,
    timeout: float = 15.0,
    size_chart_destination: Path | None = None,
) -> tuple[int, int]:
    """Save the full table plus a separate SIZE/HEIGHT crop.

    ``KrossDimensionsNotAvailable`` means the product has no table.  Other
    errors mean a table was found but could not be captured safely; callers
    should surface those errors instead of silently uploading a partial image.
    """

    driver.set_page_load_timeout(timeout)
    current_url = str(getattr(driver, "current_url", "") or "").rstrip("/")
    if current_url != str(page_url).rstrip("/"):
        driver.get(page_url)
    _dismiss_cookie_consent(driver)
    container = _wait_for_container(driver, timeout)

    translations = {normalize_label(key): value for key, value in LABEL_TRANSLATIONS.items()}
    metrics = _validate_capture_metrics(
        driver.execute_script(
            PREPARE_TABLE_JS,
            DIMENSIONS_CONTAINER_SELECTOR,
            translations,
            list(OVERLAY_SELECTORS),
        )
    )

    # Re-resolve the element after the DOM text/style updates so a driver that
    # invalidates element references on reflow does not produce a stale capture.
    from selenium.webdriver.common.by import By

    container = _wait_for_container(driver, min(timeout, 3.0))
    table = container.find_element(By.CSS_SELECTOR, "table")
    driver.execute_script(
        "arguments[0].scrollIntoView({block:'center', inline:'center'});",
        table,
    )
    _wait_for_fonts(driver)
    time.sleep(0.2)

    destination = Path(destination)
    size_chart_destination = Path(
        size_chart_destination or destination.with_name(SIZE_CHART_IMAGE_NAME)
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.stem}.tmp{destination.suffix}")
    size_temporary = size_chart_destination.with_name(
        f".{size_chart_destination.stem}.tmp{size_chart_destination.suffix}"
    )
    temporary.unlink(missing_ok=True)
    size_temporary.unlink(missing_ok=True)
    try:
        if not table.screenshot(str(temporary)):
            raise RuntimeError("Selenium did not save the KROSS dimensions PNG")
        _save_size_chart_crop(
            temporary,
            size_temporary,
            int(metrics.get("sizeChartHeight") or 0),
        )
        dimensions = _prepare_screenshot(temporary)
        # The PNG must never be narrower than the expanded full table that was
        # measured immediately before capture.
        if dimensions[0] < int(metrics["tableWidth"]):
            raise RuntimeError(
                "KROSS dimensions PNG is horizontally clipped "
                f"({dimensions[0]}px of {metrics['tableWidth']}px)"
            )
        os.replace(temporary, destination)
        os.replace(size_temporary, size_chart_destination)
        return dimensions
    except Exception:
        temporary.unlink(missing_ok=True)
        size_temporary.unlink(missing_ok=True)
        raise
