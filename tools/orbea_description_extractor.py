"""Extract readable bicycle-description text from Orbea CMS model pages.

Examples:
    python tools/orbea_description_extractor.py https://cms.orbea.com/en-au/m/kemen-adv
    python tools/orbea_description_extractor.py --url-file orbea_urls.txt

The extractor renders each page in Selenium, scrolls through lazy-loaded
sections, opens every ``View content`` detail dialog, removes slider/button
noise, and writes UTF-8-with-BOM text files that open cleanly in Notepad.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse, urlunparse


PAGE_LOAD_TIMEOUT = 25
CONTENT_TIMEOUT = 12
EXPANDED_CONTENT_TIMEOUT = 8
SCROLL_STEPS = 12
SCROLL_PAUSE = 0.12
MAX_SLIDER_ADVANCES = 30

CONTROL_TEXT = {
    "accessible text",
    "accesible text",  # Spelling used on the current Orbea site.
    "button accessible text",
    "button accesible text",
    "close",
    "customize yours",
    "next slide",
    "power",
    "previous slide",
    "range",
    "handling",
    "view content",
}


@dataclass
class DescriptionDocument:
    url: str
    model: str
    main_lines: list[str]
    heading_keys: set[str] = field(default_factory=set)
    expanded_sections: list[list[str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def normalize_space(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def clean_lines(text: str, *, deduplicate: bool = True) -> list[str]:
    """Remove page-control noise while preserving human-facing descriptions."""
    output: list[str] = []
    seen: set[str] = set()
    for raw_line in str(text or "").splitlines():
        line = normalize_space(raw_line)
        if not line:
            continue
        key = line.casefold()
        if key in CONTROL_TEXT or re.fullmatch(r"\d+(?:\s*/\s*\d+)?", line):
            continue
        if deduplicate and key in seen:
            continue
        seen.add(key)
        output.append(line)
    return output


def normalize_orbea_url(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("URL is empty")
    if not re.match(r"^https?://", raw, flags=re.IGNORECASE):
        raw = "https://" + raw
    parsed = urlparse(raw)
    host = parsed.netloc.lower().split(":", 1)[0]
    if host != "cms.orbea.com":
        raise ValueError("Only cms.orbea.com model-page URLs are supported")
    if not parsed.path or "/m/" not in parsed.path.lower():
        raise ValueError("Expected an Orbea model URL containing /m/")
    normalized_path = re.sub(r"/{2,}", "/", parsed.path).rstrip("/")
    return urlunparse(("https", parsed.netloc.lower(), normalized_path, "", "", ""))


def safe_slug(url: str) -> str:
    path_parts = [part for part in urlparse(url).path.split("/") if part]
    source = path_parts[-1] if path_parts else "orbea-description"
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", source).strip("-._").lower()
    return slug or "orbea-description"


def unique_preserving_order(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result


def create_driver(browser_name: str, show_browser: bool = False):
    """Create one reusable browser without depending on the GUI application."""
    from selenium import webdriver

    name = browser_name.strip().lower()
    if name == "chrome":
        from selenium.webdriver.chrome.service import Service
        from webdriver_manager.chrome import ChromeDriverManager

        options = webdriver.ChromeOptions()
        options.page_load_strategy = "eager"
        if not show_browser:
            options.add_argument("--headless=new")
        options.add_argument("--window-size=1600,1200")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()), options=options
        )
    elif name == "edge":
        from selenium.webdriver.edge.service import Service
        from webdriver_manager.microsoft import EdgeChromiumDriverManager

        options = webdriver.EdgeOptions()
        options.page_load_strategy = "eager"
        if not show_browser:
            options.add_argument("--headless=new")
        options.add_argument("--window-size=1600,1200")
        driver = webdriver.Edge(
            service=Service(EdgeChromiumDriverManager().install()), options=options
        )
    elif name == "firefox":
        from selenium.webdriver.firefox.options import Options
        from selenium.webdriver.firefox.service import Service
        from webdriver_manager.firefox import GeckoDriverManager

        options = Options()
        options.page_load_strategy = "eager"
        if not show_browser:
            options.add_argument("-headless")
        driver = webdriver.Firefox(
            service=Service(GeckoDriverManager().install()), options=options
        )
        driver.set_window_size(1600, 1200)
    else:
        raise ValueError(f"Unsupported browser: {browser_name}")

    driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
    driver.set_script_timeout(10)
    return driver


def _wait_for_main(driver):
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait

    return WebDriverWait(driver, CONTENT_TIMEOUT).until(
        lambda current: next(
            (
                element
                for element in current.find_elements(By.CSS_SELECTOR, "main")
                if element.is_displayed()
                and normalize_space(element.get_attribute("innerText"))
            ),
            False,
        ),
        message="The Orbea page did not render its main content",
    )


def _load_page(driver, url: str):
    from selenium.common.exceptions import TimeoutException

    try:
        driver.get(url)
    except TimeoutException:
        # Eager loading can still be held up by third-party media. Stop those
        # requests and continue when the product text itself is available.
        try:
            driver.execute_script("window.stop();")
        except Exception:
            pass
    return _wait_for_main(driver)


def _scroll_for_lazy_text(driver) -> None:
    try:
        height = int(
            driver.execute_script(
                "return Math.max(document.body.scrollHeight, "
                "document.documentElement.scrollHeight);"
            )
            or 0
        )
    except Exception:
        return

    for step in range(SCROLL_STEPS + 1):
        y = int(height * (step / max(SCROLL_STEPS, 1)))
        try:
            driver.execute_script("window.scrollTo(0, arguments[0]);", y)
        except Exception:
            break
        time.sleep(SCROLL_PAUSE)


def _visible_dialog(driver):
    from selenium.webdriver.common.by import By

    for dialog in driver.find_elements(By.CSS_SELECTOR, "dialog, [role='dialog']"):
        try:
            if dialog.is_displayed():
                return dialog
        except Exception:
            continue
    return None


def _advance_all_sliders(driver) -> list[str]:
    """Advance horizontal carousels so remotely/lazily mounted cards are loaded."""
    from selenium.webdriver.common.by import By

    warnings: list[str] = []
    nav_xpath = "//main//nav[contains(@aria-label, 'Slider navigation')]"
    navigation_count = len(driver.find_elements(By.XPATH, nav_xpath))

    for navigation_index in range(navigation_count):
        for _advance in range(MAX_SLIDER_ADVANCES):
            try:
                navigations = driver.find_elements(By.XPATH, nav_xpath)
                if navigation_index >= len(navigations):
                    break
                navigation = navigations[navigation_index]
                next_button = None
                for button in navigation.find_elements(By.CSS_SELECTOR, "button"):
                    accessible_name = normalize_space(
                        getattr(button, "accessible_name", "")
                        or button.get_attribute("aria-label")
                        or button.get_attribute("title")
                        or button.text
                    ).casefold()
                    if accessible_name == "next slide":
                        next_button = button
                        break
                if next_button is None:
                    break
                if (
                    next_button.get_attribute("disabled") is not None
                    or (next_button.get_attribute("aria-disabled") or "").lower()
                    == "true"
                ):
                    break
                driver.execute_script("arguments[0].click();", next_button)
                time.sleep(SCROLL_PAUSE)
            except Exception as error:
                warnings.append(
                    f"Slider {navigation_index + 1}: {type(error).__name__}: {error}"
                )
                break
    return warnings


def _expand_detail_dialogs(driver) -> tuple[list[list[str]], list[str]]:
    """Open every English ``View content`` feature and collect its text."""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait

    button_xpath = (
        "//main//button[normalize-space()='View content' "
        "or normalize-space()='Accesible text' "
        "or normalize-space()='Accessible text']"
    )
    buttons = driver.find_elements(By.XPATH, button_xpath)
    sections: list[list[str]] = []
    warnings: list[str] = []
    seen: set[tuple[str, ...]] = set()

    for index in range(len(buttons)):
        try:
            current_buttons = driver.find_elements(By.XPATH, button_xpath)
            if index >= len(current_buttons):
                break
            driver.execute_script("arguments[0].click();", current_buttons[index])
            dialog = WebDriverWait(driver, EXPANDED_CONTENT_TIMEOUT).until(
                lambda current: _visible_dialog(current),
                message="Expanded description dialog did not open",
            )
            dialog_text = driver.execute_script(
                "return arguments[0].innerText || '';", dialog
            )
            lines = clean_lines(dialog_text)
            key = tuple(line.casefold() for line in lines)
            if lines and key not in seen:
                sections.append(lines)
                seen.add(key)

            close_buttons = dialog.find_elements(
                By.XPATH, ".//button[normalize-space()='Close']"
            )
            if close_buttons:
                driver.execute_script("arguments[0].click();", close_buttons[0])
                WebDriverWait(driver, 3).until(lambda current: not _visible_dialog(current))
            else:
                driver.execute_script(
                    "document.dispatchEvent(new KeyboardEvent('keydown', {key:'Escape'}));"
                )
        except Exception as error:
            warnings.append(f"Expanded detail {index + 1}: {type(error).__name__}: {error}")
            try:
                dialog = _visible_dialog(driver)
                if dialog:
                    close_buttons = dialog.find_elements(
                        By.XPATH, ".//button[normalize-space()='Close']"
                    )
                    if close_buttons:
                        driver.execute_script("arguments[0].click();", close_buttons[0])
            except Exception:
                pass

    return sections, warnings


def extract_description(driver, url: str) -> DescriptionDocument:
    from selenium.webdriver.common.by import By

    main = _load_page(driver, url)
    _scroll_for_lazy_text(driver)
    slider_warnings = _advance_all_sliders(driver)
    main = _wait_for_main(driver)

    main_text = driver.execute_script("return arguments[0].innerText || '';", main)
    main_lines = clean_lines(main_text)

    heading_keys: set[str] = set()
    for heading in driver.find_elements(By.CSS_SELECTOR, "main h1, main h2, main h3"):
        try:
            text = normalize_space(heading.get_attribute("innerText") or heading.text)
        except Exception:
            text = ""
        if text:
            heading_keys.add(text.casefold())

    expanded_sections, warnings = _expand_detail_dialogs(driver)
    warnings = [*slider_warnings, *warnings]
    model = main_lines[0] if main_lines else safe_slug(url).replace("-", " ").title()
    return DescriptionDocument(
        url=url,
        model=model,
        main_lines=main_lines,
        heading_keys=heading_keys,
        expanded_sections=expanded_sections,
        warnings=warnings,
    )


def _render_lines(lines: list[str], heading_keys: set[str]) -> list[str]:
    rendered: list[str] = []
    for line in lines:
        if rendered and line.casefold() in heading_keys:
            rendered.append("")
        rendered.append(line)
    return rendered


def render_document(document: DescriptionDocument) -> str:
    lines = [
        "ORBEA BICYCLE DESCRIPTION",
        f"URL: {document.url}",
        f"MODEL: {document.model}",
        "",
    ]
    body_lines = list(document.main_lines)
    if body_lines and body_lines[0].casefold() == document.model.casefold():
        body_lines = body_lines[1:]
    lines.extend(_render_lines(body_lines, document.heading_keys))

    if document.expanded_sections:
        lines.extend(["", "EXPANDED DETAILS"])
        for section in document.expanded_sections:
            lines.extend(["", *section])

    if document.warnings:
        lines.extend(["", "EXTRACTION WARNINGS"])
        lines.extend(f"- {warning}" for warning in document.warnings)

    return "\n".join(lines).strip() + "\n"


def write_documents(documents: list[DescriptionDocument], output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    used_names: dict[str, int] = {}
    combined: list[str] = []

    for document in documents:
        base = safe_slug(document.url)
        used_names[base] = used_names.get(base, 0) + 1
        suffix = f"-{used_names[base]}" if used_names[base] > 1 else ""
        destination = output_dir / f"{base}{suffix}.txt"
        rendered = render_document(document)
        destination.write_text(rendered, encoding="utf-8-sig")
        written.append(destination)
        combined.append(rendered.rstrip())

    combined_path = output_dir / "all_orbea_descriptions.txt"
    combined_path.write_text(
        ("\n\n" + "=" * 80 + "\n\n").join(combined) + "\n",
        encoding="utf-8-sig",
    )
    written.append(combined_path)
    return written


def _read_url_file(path: Path) -> list[str]:
    if not path.is_file():
        raise FileNotFoundError(f"URL file not found: {path}")
    values: list[str] = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            values.extend(part for part in re.split(r"[\s,;]+", stripped) if part)
    return values


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Save visible Orbea model descriptions as Notepad-friendly TXT files."
    )
    parser.add_argument("urls", nargs="*", help="One or more cms.orbea.com /m/ URLs")
    parser.add_argument("--url-file", type=Path, help="Text file containing one URL per line")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output") / "orbea_descriptions",
        help="Destination folder (default: output/orbea_descriptions)",
    )
    parser.add_argument(
        "--browser", choices=("Chrome", "Edge", "Firefox"), default="Chrome"
    )
    parser.add_argument(
        "--show-browser", action="store_true", help="Show the browser while extracting"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    raw_urls = list(args.urls)
    if args.url_file:
        raw_urls.extend(_read_url_file(args.url_file.expanduser().resolve()))
    if not raw_urls:
        entered = input("Paste one or more Orbea model URLs: ").strip()
        raw_urls.extend(part for part in re.split(r"[\s,;]+", entered) if part)

    normalized: list[str] = []
    for raw_url in raw_urls:
        try:
            normalized.append(normalize_orbea_url(raw_url))
        except ValueError as error:
            print(f"Skipping {raw_url!r}: {error}")
    urls = unique_preserving_order(normalized)
    if not urls:
        print("No valid Orbea model URLs were supplied.")
        return 2

    output_dir = args.output_dir.expanduser().resolve()
    driver = None
    documents: list[DescriptionDocument] = []
    failures: list[str] = []
    try:
        print(f"Starting {args.browser} for {len(urls)} Orbea page(s)...")
        driver = create_driver(args.browser, show_browser=args.show_browser)
        for index, url in enumerate(urls, start=1):
            print(f"[{index}/{len(urls)}] {url}")
            try:
                document = extract_description(driver, url)
                documents.append(document)
                print(
                    f"  collected {len(document.main_lines)} main text lines and "
                    f"{len(document.expanded_sections)} expanded section(s)"
                )
            except KeyboardInterrupt:
                raise
            except Exception as error:
                message = f"{url}: {type(error).__name__}: {error}"
                failures.append(message)
                print(f"  failed: {message}")
    except KeyboardInterrupt:
        print("\nStopped by user.")
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass

    written: list[Path] = []
    if documents:
        written = write_documents(documents, output_dir)
        print("\nSaved:")
        for path in written:
            print(f"  {path}")

    if failures:
        output_dir.mkdir(parents=True, exist_ok=True)
        failure_path = output_dir / f"errors_{datetime.now():%Y%m%d_%H%M%S}.txt"
        failure_path.write_text("\n".join(failures) + "\n", encoding="utf-8-sig")
        print(f"Errors: {failure_path}")

    return 0 if documents and not failures else (1 if documents else 2)


if __name__ == "__main__":
    raise SystemExit(main())
