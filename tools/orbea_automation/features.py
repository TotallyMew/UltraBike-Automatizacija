"""Read the product Features dialog without navigation or slider controls."""
from __future__ import annotations

import html
import json
import re
import time
from typing import Any, Callable

from bs4 import BeautifulSoup, NavigableString, Tag
from selenium.common.exceptions import ElementClickInterceptedException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from .photos import _json_assignment


DESCRIPTION_CAPTURE_VERSION = 3
FEATURE_BUTTON = 'button[aria-controls="feature-modules-dialog"]'
FEATURE_DIALOG = '#feature-modules-dialog, [aria-labelledby="dialog-heading-feature-modules-dialog"]'


def feature_description_html(page_html: str) -> str:
    """Preserve the feature headings and copy from a full page or dialog HTML.

    All carousel cards are included, even outside the current slide. Embedded
    section card data also covers cards that have not been mounted in the DOM.
    Only simple text markup is emitted, suitable for a product description.
    """
    soup = BeautifulSoup(page_html, "html.parser")
    scope = soup.select_one(FEATURE_DIALOG)
    if scope is None:
        heading = soup.find(id="dialog-heading-feature-modules-dialog")
        if heading:
            scope = heading.find_parent(class_="dialog__content")
    if scope is None:
        return ""
    for unwanted in scope.select('script, style, noscript, template, svg, button, nav, picture, img, video, form, .sr-only'):
        unwanted.decompose()

    blocks: list[str] = []
    seen: set[tuple[str, str]] = set()

    def emit(tag: str, text: str) -> None:
        text = " ".join(text.split())
        key = (tag, text.casefold())
        if text and key not in seen:
            seen.add(key)
            blocks.append(f"<{tag}>{html.escape(text)}</{tag}>")

    def source_text(value: Any) -> str:
        return BeautifulSoup(str(value or ""), "html.parser").get_text(" ", strip=True)

    def walk(node: Tag) -> None:
        if node.name == "section" and node.get("data"):
            try:
                data = json.loads(node["data"])
            except (ValueError, TypeError):
                data = {}
            if isinstance(data, dict) and isinstance(data.get("cards"), list) and any(isinstance(card, dict) and (card.get("textLang") or card.get("text")) for card in data["cards"]):
                emit("h2", source_text(data.get("headingLang") or data.get("heading")))
                for card in data["cards"]:
                    if isinstance(card, dict):
                        emit("h3", source_text(card.get("subheadingLang") or card.get("subheading")))
                        emit("p", source_text(card.get("textLang") or card.get("text")))
                return
        if node.name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            emit("h2" if node.name in {"h1", "h2"} else "h3", node.get_text(" ", strip=True))
            return
        if node.name in {"p", "li", "blockquote"}:
            emit("p", node.get_text(" ", strip=True))
            return
        inline: list[str] = []
        for child in node.children:
            if isinstance(child, NavigableString):
                inline.append(str(child))
            elif isinstance(child, Tag):
                if child.name in {"span", "strong", "b", "em", "i", "a", "small", "br"}:
                    inline.append(child.get_text(" ", strip=True))
                else:
                    emit("p", " ".join(inline))
                    inline.clear()
                    walk(child)
        emit("p", " ".join(inline))

    # The dialog's sticky header is a UI label and close control, not copy.
    sections = scope.find_all("section")
    section_ids = {id(section) for section in sections}
    sections = [section for section in sections if not any(id(parent) in section_ids for parent in section.parents)]
    for section in sections:
        walk(section)
    return "\n".join(blocks)


def read_feature_description(
    driver: Any, *, timeout: float = 12,
    check: Callable[[], None] | None = None,
) -> str | None:
    """Click the locale-independent Features opener and wait for its copy.

    ``None`` means this is an older page without this dialog. A present opener
    that fails to open is an extraction error, never a short-summary fallback.
    An empty string means the page explicitly declares no feature content.
    """
    if check:
        check()
    if not driver.find_elements(By.CSS_SELECTOR, FEATURE_BUTTON):
        return None
    soup = BeautifulSoup(driver.page_source, "html.parser")
    root = soup.select_one("#product-bike-detail[x-init]")
    if root is not None:
        initializer = str(root.get("x-init") or "")
        microsite = _json_assignment(initializer, "microsite")
        if re.search(r"\bmicrosite\s*=\s*null\s*;", initializer) or (
            isinstance(microsite, dict) and microsite.get("modules") == []
        ):
            return ""

    def opener(current):
        if check:
            check()
        return next((button for button in current.find_elements(By.CSS_SELECTOR, FEATURE_BUTTON)
                     if button.is_displayed() and button.is_enabled()), False)

    button = WebDriverWait(driver, timeout).until(opener, message="The Orbea Features button did not become ready")
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", button)
    try:
        button.click()
    except ElementClickInterceptedException:
        # Cookie overlays can cover this button; use its own click handler.
        driver.execute_script("arguments[0].click();", button)

    dialog = None
    previous = ""
    stable_since = time.monotonic()

    def description(current):
        nonlocal dialog, previous, stable_since
        if check:
            check()
        dialog = next((element for element in current.find_elements(By.CSS_SELECTOR, FEATURE_DIALOG)
                       if element.is_displayed()), None)
        if dialog is None:
            return False
        content = feature_description_html(dialog.get_attribute("outerHTML") or "")
        if content != previous:
            previous, stable_since = content, time.monotonic()
            return False
        return content if content and time.monotonic() - stable_since >= 0.25 else False

    try:
        return WebDriverWait(driver, timeout, poll_frequency=0.1).until(description, message="The Orbea Features dialog did not load its description")
    finally:
        if dialog is not None:
            try:
                close = dialog.find_elements(By.CSS_SELECTOR, 'button[x-on\\:click*="closeDialog"], button[\\@click*="closeDialog"]')
                if close:
                    close[0].click()
                else:
                    dialog.send_keys(Keys.ESCAPE)
            except WebDriverException:
                # The next navigation clears this dialog; keep captured copy.
                pass
