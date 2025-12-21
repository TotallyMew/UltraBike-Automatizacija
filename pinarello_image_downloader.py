import argparse
import os
import re
import time
from dataclasses import dataclass
from typing import Callable, Iterable, Optional
from urllib.parse import urljoin, urlparse

import certifi
import requests
from bs4 import BeautifulSoup
from PIL import Image

from selenium import webdriver
from selenium.common.exceptions import (  # type: ignore
    ElementClickInterceptedException,
    JavascriptException,
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.firefox import GeckoDriverManager
from webdriver_manager.microsoft import EdgeChromiumDriverManager
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.firefox.options import Options as FirefoxOptions


IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")
PINARELLO_HOST = "pinarello.com"

TARGET_MAX_W = 4000
TARGET_MAX_H = 2998


def _log(log: Callable[[str], None] | None, message: str) -> None:
    if log is None:
        print(message)
        return
    try:
        log(message)
    except Exception:
        # Logging must never break the downloader
        print(message)


@dataclass(frozen=True)
class Variant:
    label: str
    folder_name: str


def _sanitize_folder_name(name: str) -> str:
    name = name.strip()
    name = re.sub(r"\s+", " ", name)
    name = re.sub(r"[\\/:*?\"<>|]", "_", name)
    name = name.strip(" .")
    return name or "unknown"


def _slug_from_url(url: str) -> str:
    path = urlparse(url).path.strip("/")
    if not path:
        return "pinarello"
    return _sanitize_folder_name(path.split("/")[-1])


def _split_srcset(srcset: str) -> list[str]:
    # Format: "url 320w, url 640w"; we keep all, later we de-dupe.
    out: list[str] = []
    for part in srcset.split(","):
        part = part.strip()
        if not part:
            continue
        url = part.split(" ")[0].strip()
        if url:
            out.append(url)
    return out


def _normalize_storage_url(url: str) -> str:
    """Convert thumb URLs to their likely full-res equivalents.

    Observed patterns:
      /storage/thumbs/Variant/944__resize__<hash>.png  -> /storage/Variant/<hash>.png
      /storage/thumbs/Product/464__resize__<hash>.jpg  -> /storage/Product/<hash>.jpg

    If the URL doesn't match a known pattern, it's returned unchanged.
    """
    try:
        parsed = urlparse(url)
        if not parsed.netloc:
            return url
        if PINARELLO_HOST not in parsed.netloc.lower():
            return url

        path = parsed.path
        if "/storage/thumbs/" not in path:
            return url

        # /storage/thumbs/<Category>/<size>__resize__<hash>.<ext>
        m = re.search(r"/storage/thumbs/(?P<cat>[^/]+)/(?P<file>[^/]+)$", path)
        if not m:
            return url

        cat = m.group("cat")
        filename = m.group("file")
        m2 = re.match(r"\d+__resize__(?P<hash>.+?)(?P<ext>\.(?:png|jpe?g|webp))$", filename, flags=re.I)
        if not m2:
            return url

        full = f"/storage/{cat}/{m2.group('hash')}{m2.group('ext')}"
        return parsed._replace(path=full, query="").geturl()
    except Exception:
        return url


def _looks_like_image_url(url: str) -> bool:
    lower = url.lower()
    return any(lower.endswith(ext) for ext in IMAGE_EXTENSIONS)


def _collect_storage_image_urls_from_html(base_url: str, html: str) -> set[str]:
    soup = BeautifulSoup(html, "html.parser")

    urls: set[str] = set()

    # Pinarello uses various data-* attributes for galleries/zoom.
    data_url_attrs = (
        "data-image",
        "data-image-zoom",
        "data-zoom-image",
        "data-zoom",
        "data-srcset",
        "data-thumb-srcset",
        "data-src",
        "data-original",
    )

    # Capture inline style background-image URLs.
    def _extract_urls_from_style(style: str) -> list[str]:
        found = []
        for m in re.findall(r"url\(([^)]+)\)", style, flags=re.I):
            m = m.strip().strip('"').strip("'")
            if m:
                found.append(m)
        return found

    for img in soup.find_all("img"):
        for attr in ("src", "data-src", "data-lazy-src"):
            src = img.get(attr)
            if src:
                urls.add(urljoin(base_url, src))

        for attr in data_url_attrs:
            v = img.get(attr)
            if v:
                urls.add(urljoin(base_url, v))

        srcset = img.get("srcset")
        if srcset:
            for u in _split_srcset(srcset):
                urls.add(urljoin(base_url, u))

        style = img.get("style")
        if style:
            for u in _extract_urls_from_style(style):
                urls.add(urljoin(base_url, u))

    for source in soup.find_all("source"):
        srcset = source.get("srcset")
        if srcset:
            for u in _split_srcset(srcset):
                urls.add(urljoin(base_url, u))

        for attr in ("data-srcset", "data-thumb-srcset"):
            v = source.get(attr)
            if v:
                for u in _split_srcset(v):
                    urls.add(urljoin(base_url, u))

        style = source.get("style")
        if style:
            for u in _extract_urls_from_style(style):
                urls.add(urljoin(base_url, u))

    # Capture background images on generic elements.
    for el in soup.find_all(True):
        style = el.get("style")
        if style and "url(" in style.lower():
            for u in _extract_urls_from_style(style):
                urls.add(urljoin(base_url, u))

        for attr in data_url_attrs:
            v = el.get(attr)
            if v:
                urls.add(urljoin(base_url, v))

        href = el.get("href")
        if href and "/storage/" in href:
            urls.add(urljoin(base_url, href))

    # Also scan raw HTML for storage URLs that might be embedded in inline JS.
    for m in re.findall(
        r"https?://[^\s\"']*pinarello\.com/storage/[^\s\"']+\.(?:png|jpe?g|webp)",
        html,
        flags=re.I,
    ):
        urls.add(m)

    # Keep only pinarello storage images.
    filtered: set[str] = set()
    for u in urls:
        pu = urlparse(u)
        if PINARELLO_HOST not in pu.netloc.lower():
            continue
        if "/storage/" not in pu.path:
            continue
        if not _looks_like_image_url(u):
            continue
        filtered.add(_normalize_storage_url(u))

    return filtered


def _collect_product_gallery_urls(page_url: str, session: requests.Session) -> set[str]:
    """Extract bike gallery images embedded on the product page.

    Pinarello pages frequently embed extra bike photos under `/storage/ProductGallery/`
    using either:
    - `<a href=... data-fancybox=...>` (older pages)
    - `data-image` / `data-image-zoom` attributes (newer pages)
    """
    try:
        resp = session.get(page_url, timeout=30)
        resp.raise_for_status()
    except requests.RequestException:
        return set()

    soup = BeautifulSoup(resp.text, "html.parser")
    urls: set[str] = set()

    for a in soup.select('a[href*="/storage/ProductGallery/"]'):
        href = a.get("href")
        if href:
            urls.add(urljoin(page_url, href))

    for el in soup.select('[data-image*="/storage/ProductGallery/"], [data-image-zoom*="/storage/ProductGallery/"]'):
        for attr in ("data-image", "data-image-zoom"):
            v = el.get(attr)
            if v and "/storage/ProductGallery/" in v:
                urls.add(urljoin(page_url, v))

    for img in soup.select('img[src*="/storage/ProductGallery/"]'):
        src = img.get("src")
        if src:
            urls.add(urljoin(page_url, src))
        srcset = img.get("srcset")
        if srcset:
            for u in _split_srcset(srcset):
                if "/storage/ProductGallery/" in u:
                    urls.add(urljoin(page_url, u))

    # Normalize thumbs to full-res.
    normalized = {_normalize_storage_url(u) for u in urls}
    return {u for u in normalized if "/storage/ProductGallery/" in urlparse(u).path}


def _setup_driver(browser: str, headless: bool) -> webdriver.Remote:
    browser = browser.lower().strip()

    if browser == "chrome":
        options = ChromeOptions()
        options.add_experimental_option("excludeSwitches", ["enable-logging"])
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        if headless:
            # Chrome 109+ supports --headless=new.
            options.add_argument("--headless=new")
        return webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=options)

    if browser == "edge":
        options = EdgeOptions()
        options.use_chromium = True
        options.add_experimental_option("excludeSwitches", ["enable-logging"])
        if headless:
            options.add_argument("--headless=new")
            options.add_argument("--disable-gpu")
        return webdriver.Edge(service=EdgeService(EdgeChromiumDriverManager().install()), options=options)

    if browser == "firefox":
        options = FirefoxOptions()
        if headless:
            options.add_argument("-headless")
        return webdriver.Firefox(service=FirefoxService(GeckoDriverManager().install()), options=options)

    raise ValueError(f"Unsupported browser: {browser}. Use chrome/edge/firefox")


def _try_accept_cookies(driver: webdriver.Remote, wait: WebDriverWait) -> None:
    # Pinarello pages sometimes show a cookie consent modal.
    # We try a few common button locators in multiple languages.
    candidates = [
        # Cookiebot-ish
        (By.ID, "CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll"),
        (By.ID, "CybotCookiebotDialogBodyButtonAccept"),
        # Generic "Accept" buttons
        (By.XPATH, "//button[contains(translate(.,'abcdefghijklmnopqrstuvwxyz','ABCDEFGHIJKLMNOPQRSTUVWXYZ'),'ACCEPT')]"),
        (By.XPATH, "//a[contains(translate(.,'abcdefghijklmnopqrstuvwxyz','ABCDEFGHIJKLMNOPQRSTUVWXYZ'),'ACCEPT')]"),
        # Japanese consent buttons (agree/allow)
        (By.XPATH, "//button[contains(.,'同意') or contains(.,'許可')]"),
        (By.XPATH, "//a[contains(.,'同意') or contains(.,'許可')]"),
    ]

    for by, sel in candidates:
        try:
            el = wait.until(EC.element_to_be_clickable((by, sel)))
            driver.execute_script("arguments[0].click();", el)
            time.sleep(0.5)
            return
        except TimeoutException:
            continue
        except (ElementClickInterceptedException, JavascriptException, WebDriverException):
            continue


def _get_product_title(driver: webdriver.Remote) -> str:
    try:
        h1 = driver.find_element(By.TAG_NAME, "h1")
        text = (h1.text or "").strip()
        if text:
            return text
    except NoSuchElementException:
        pass

    # Fallback: document.title
    try:
        title = driver.title.strip()
        return title or "Pinarello"
    except Exception:
        return "Pinarello"


def _extract_variant_folder_name_from_label(label: str) -> str:
    # Most Pinarello variant labels follow a pattern like:
    #   "PINARELLO F5 - FURIOUS WHITE - 105 Di2 - DTSWISS A1800"
    # or
    #   "MY26 GREVIL F7 - POLARIS PURPLE - SRAM FORCE XPLR"
    label = re.sub(r"\s+", " ", label).strip()
    parts = [p.strip() for p in label.split(" - ") if p.strip()]
    if len(parts) >= 2:
        return _sanitize_folder_name(parts[1])
    return _sanitize_folder_name(label)


def _extract_product_hint_tokens(product_title: str) -> set[str]:
    tokens = re.findall(r"[A-Za-z0-9]+", product_title.upper())

    # Remove very common spec tokens that appear in many labels.
    stop = {
        "NEW",
        "DISC",
        "DI2",
        "AXS",
        "XPLR",
        "SRAM",
        "FORCE",
        "RIVAL",
        "RED",
        "ULTEGRA",
        "DURA",
        "ACE",
        "SHIMANO",
        "CAMPAGNOLO",
        "COMPETITION",
        "ROAD",
        "GRAVEL",
        "MY",
        "MYWAY",
    }

    out: set[str] = set()
    for t in tokens:
        if t in stop:
            continue
        # keep model-like tokens: GREVIL, DOGMA, PINARELLO, F5, F7, etc.
        if len(t) >= 4 or re.fullmatch(r"[A-Z]+\d+", t) or re.fullmatch(r"[A-Z]\d+", t):
            out.add(t)

    # As a fallback, include the first token if nothing survived.
    if not out and tokens:
        out.add(tokens[0])
    return out


def _find_variant_elements(driver: webdriver.Remote, product_title: str) -> list:
    # Pinarello pages (older + newer) can expose variants as:
    # - text links (often <a href="javascript:;">MODEL - COLOR - ...</a>)
    # - swatches with data-* attributes and little/no visible text.
    #
    # Important: Selenium's `.text` can be empty for hidden elements; we prefer
    # `textContent` as a best-effort label.

    def label_for(el) -> str:
        try:
            txt = (el.get_attribute("textContent") or "").strip()
            if txt:
                return re.sub(r"\s+", " ", txt)
            for attr in (
                "alt",
                "aria-label",
                "title",
                "data-title",
                "data-label",
                "data-original-title",
                "data-bs-original-title",
            ):
                v = (el.get_attribute(attr) or "").strip()
                if v:
                    return re.sub(r"\s+", " ", v)
            return ""
        except StaleElementReferenceException:
            return ""

    product_tokens = _extract_product_hint_tokens(product_title)

    def looks_like_variant_label(txt: str, *, require_product_token: bool) -> bool:
        upper = txt.upper()
        if len(txt) < 6:
            return False
        if "PLAY VIDEO" in upper:
            return False
        if any(k in upper for k in ("COOKIE", "COOKIEBOT", "USERCENTRICS", "PRIVACY", "TERMS", "ACCESSIBILITY", "SCREEN-READER")):
            return False
        if require_product_token and product_tokens and not any(t in upper for t in product_tokens):
            # When searching the whole page, avoid footer/compare links by requiring at least one product token.
            return False
        # Most variant labels have at least one " - " separator.
        if " - " in txt:
            return True
        # Some swatches might only contain a color name.
        if any(k in upper for k in ("WHITE", "BLACK", "BLUE", "RED", "GREEN", "PURPLE", "SILVER", "GOLD", "GREY", "GRAY", "TURQUOISE")):
            return True
        return False

    selectors = [
        # Variant thumbnail images: alt contains the full label.
        (By.CSS_SELECTOR, "img[alt*=' - '][src*='/storage/Variant/'], img[alt*=' - '][src*='/storage/thumbs/Variant/']"),
        # Text-link based variants
        (By.CSS_SELECTOR, "a[href^='javascript']"),
        (By.CSS_SELECTOR, "a[href='javascript:;']"),
        (By.CSS_SELECTOR, "a[href='javascript:void(0);']"),
        # Swatches / data-driven variants
        (By.CSS_SELECTOR, "[data-variant], [data-variant-id], [data-variant_id], [data-variantcode], [data-variantCode]"),
        # Generic fallback
        (By.CSS_SELECTOR, "button, a, [role='button']"),
    ]

    seen: set[str] = set()
    out: list = []

    # Search locally within the hero container first (variant controls tend to be there).
    hero_root = _hero_container_element(driver)
    roots: list[tuple[object, bool]] = []
    if hero_root is not None:
        roots.append((hero_root, False))
    roots.append((driver, True))

    for root, require_product_token in roots:
        for by, sel in selectors:
            try:
                els = root.find_elements(by, sel)  # type: ignore[union-attr]
            except WebDriverException:
                continue

            for el in els:
                txt = label_for(el)
                if not txt or not looks_like_variant_label(txt, require_product_token=require_product_token):
                    continue

                key = txt
                if key in seen:
                    continue
                seen.add(key)
                out.append(el)

    # Heuristic cleanup: prefer labels with " - " (more likely to be the actual variant list)
    with_dash = [e for e in out if " - " in (label_for(e) or "")]
    return with_dash or out


def _hero_container_element(driver: webdriver.Remote) -> Optional[object]:
    # Try to locate a "hero" image for the selected variant, then get an ancestor container.
    hero_xpaths = [
        "//img[contains(@src,'/storage/Variant/') or contains(@src,'/storage/thumbs/Variant/')]",
        "//img[contains(@src,'/storage/Product/') or contains(@src,'/storage/thumbs/Product/')]",
    ]

    hero = None
    for xp in hero_xpaths:
        try:
            candidates = driver.find_elements(By.XPATH, xp)
            for c in candidates:
                try:
                    if c.is_displayed():
                        hero = c
                        break
                except WebDriverException:
                    continue
            if hero is not None:
                break
        except WebDriverException:
            continue

    if hero is None:
        return None

    try:
        return driver.execute_script("return arguments[0].closest('section,div')", hero)
    except JavascriptException:
        return None


def _collect_variant_images(driver: webdriver.Remote, base_url: str) -> set[str]:
    # Prefer collecting from the hero container to avoid downloading unrelated images
    # (technology tiles, compare-model thumbs, footer logos).
    container = _hero_container_element(driver)

    if container is not None:
        try:
            html = driver.execute_script("return arguments[0].outerHTML", container)
            if isinstance(html, str) and html:
                urls = _collect_storage_image_urls_from_html(base_url, html)
                # In practice the hero container can still include a few extra images.
                # We bias towards Variant images.
                variant_urls = {u for u in urls if "/storage/Variant/" in urlparse(u).path}
                return variant_urls or urls
        except JavascriptException:
            pass

    # Fallback to full page scan.
    return _collect_storage_image_urls_from_html(base_url, driver.page_source)


def _transfer_cookies_to_session(driver: webdriver.Remote, session: requests.Session) -> None:
    try:
        for c in driver.get_cookies():
            name = c.get("name")
            value = c.get("value")
            domain = c.get("domain")
            path = c.get("path") or "/"
            if name and value:
                session.cookies.set(name, value, domain=domain, path=path)
    except WebDriverException:
        return


def _download_images(
    urls: Iterable[str],
    out_dir: str,
    session: requests.Session,
    sleep_s: float = 0.2,
    log: Callable[[str], None] | None = None,
) -> int:
    os.makedirs(out_dir, exist_ok=True)

    downloaded = 0
    for idx, url in enumerate(sorted(set(urls)), start=1):
        try:
            parsed = urlparse(url)
            base_name = os.path.basename(parsed.path)
            if not base_name:
                base_name = f"image_{idx}.jpg"

            stem, ext = os.path.splitext(base_name)
            if not stem:
                stem = f"image_{idx}"

            # We always want PNG output.
            png_path = os.path.join(out_dir, f"{stem}.png")
            if os.path.exists(png_path) and os.path.getsize(png_path) > 0:
                continue

            # Download to a temporary/original-extension file first.
            tmp_path = os.path.join(out_dir, base_name)

            resp = session.get(url, timeout=60, stream=True)
            resp.raise_for_status()

            with open(tmp_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=1024 * 256):
                    if chunk:
                        f.write(chunk)

            _convert_to_png_and_resize_in_place(tmp_path, png_path)
            if os.path.exists(tmp_path) and os.path.abspath(tmp_path) != os.path.abspath(png_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

            downloaded += 1
            time.sleep(sleep_s)
        except requests.RequestException as e:
            _log(log, f"[WARN] failed download: {url} ({e})")
            continue

    return downloaded


def _convert_to_png_and_resize_in_place(src_path: str, dst_png_path: str) -> None:
    """Convert any image file to .png and resize if larger than TARGET_MAX_W x TARGET_MAX_H.

    Requirement interpretation:
    - If image exceeds either dimension (width > 4000 OR height > 2998), resize to exactly 4000x2998.
    - All output files must be .png.
    """
    with Image.open(src_path) as im:
        # Normalize mode for PNG save
        if im.mode not in ("RGB", "RGBA"):
            # Preserve alpha if present
            if "A" in im.getbands():
                im = im.convert("RGBA")
            else:
                im = im.convert("RGB")

        w, h = im.size
        if w > TARGET_MAX_W or h > TARGET_MAX_H:
            im = im.resize((TARGET_MAX_W, TARGET_MAX_H), Image.Resampling.LANCZOS)

        os.makedirs(os.path.dirname(dst_png_path), exist_ok=True)
        im.save(dst_png_path, format="PNG", optimize=True)


def _click_variant_element(driver: webdriver.Remote, el) -> bool:
    """Best-effort click.

    Pinarello variant selectors are often thumbnail <img> elements wrapped by a clickable <a>.
    Selenium may find the <img>, so we try to click its nearest clickable ancestor.
    """
    try:
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
        time.sleep(0.15)
    except WebDriverException:
        pass

    click_target = el
    try:
        if (getattr(el, "tag_name", "") or "").lower() == "img":
            try:
                click_target = el.find_element(By.XPATH, "./ancestor::a[1]")
            except NoSuchElementException:
                try:
                    click_target = el.find_element(By.XPATH, "./ancestor::button[1]")
                except NoSuchElementException:
                    click_target = el
    except WebDriverException:
        click_target = el

    for attempt in range(2):
        try:
            driver.execute_script("arguments[0].click();", click_target)
            return True
        except (JavascriptException, ElementClickInterceptedException, WebDriverException):
            if attempt == 0:
                # Fallback to native click once.
                try:
                    click_target.click()
                    return True
                except WebDriverException:
                    pass
            time.sleep(0.25)

    return False


def _variant_label_from_element(el) -> str:
    for attr in ("textContent", "alt", "aria-label", "title"):
        try:
            v = (el.get_attribute(attr) or "").strip()
        except Exception:
            v = ""
        if v:
            v = v.replace("\n", " ")
            v = re.sub(r"\s+", " ", v).strip()
            if v:
                return v
    return ""


def _open_in_new_tab(driver: webdriver.Remote, url: str) -> tuple[Optional[str], Optional[str]]:
    """Open url in a new tab and switch to it.

    Returns: (original_handle, new_handle)
    """
    try:
        original = driver.current_window_handle
    except WebDriverException:
        original = None

    try:
        before = set(driver.window_handles)
    except WebDriverException:
        before = set()

    try:
        driver.execute_script("window.open(arguments[0], '_blank');", url)
    except WebDriverException:
        # Fallback: navigate in the same tab.
        try:
            driver.get(url)
        except WebDriverException:
            return (original, None)
        return (original, None)

    try:
        after = set(driver.window_handles)
        new_handles = list(after - before)
        new_handle = new_handles[-1] if new_handles else (driver.window_handles[-1] if driver.window_handles else None)
        if new_handle:
            driver.switch_to.window(new_handle)
        return (original, new_handle)
    except WebDriverException:
        return (original, None)


def _close_tab_and_restore(driver: webdriver.Remote, original_handle: Optional[str], opened_handle: Optional[str]) -> None:
    try:
        if opened_handle:
            try:
                driver.close()
            except WebDriverException:
                pass
        if original_handle:
            driver.switch_to.window(original_handle)
    except WebDriverException:
        return


def _download_pinarello_variants_with_driver(
    driver: webdriver.Remote,
    url: str,
    output_dir: str,
    wait_s: int,
    log: Callable[[str], None] | None = None,
    *,
    use_new_tab: bool = True,
) -> dict:
    wait = WebDriverWait(driver, wait_s)

    original_handle: Optional[str] = None
    opened_handle: Optional[str] = None
    try:
        _log(log, f"[INFO] Opening: {url}")

        if use_new_tab:
            original_handle, opened_handle = _open_in_new_tab(driver, url)
        else:
            driver.get(url)

        # Let the main content render.
        try:
            wait.until(lambda d: d.execute_script("return document.readyState") in ("interactive", "complete"))
        except TimeoutException:
            pass
        time.sleep(1.0)
        _try_accept_cookies(driver, wait)
        time.sleep(0.5)

        title = _get_product_title(driver)
        slug = _slug_from_url(url)
        product_dir = os.path.join(output_dir, _sanitize_folder_name(title)[:80] + "__" + slug)

        _log(log, f"[INFO] Product: {title}")
        _log(log, f"[INFO] Output:  {product_dir}")

        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0"})
        session.verify = certifi.where()
        _transfer_cookies_to_session(driver, session)

        # Download non-color-specific product gallery bike images once.
        gallery_count = 0
        gallery_urls = _collect_product_gallery_urls(url, session)
        if gallery_urls:
            gallery_dir = os.path.join(product_dir, "_gallery")
            gallery_count = _download_images(gallery_urls, gallery_dir, session, log=log)
            _log(log, f"[INFO] Downloaded {gallery_count} gallery images into: {gallery_dir}")

        # Some pages inject variant controls after first paint; give it a moment.
        variant_elements = _find_variant_elements(driver, product_title=title)
        if not variant_elements:
            time.sleep(2.0)
            variant_elements = _find_variant_elements(driver, product_title=title)
        if not variant_elements:
            _log(log, "[WARN] No variant selectors detected; downloading best-effort images from current page")
            urls_found = _collect_variant_images(driver, base_url=url)
            count = _download_images(urls_found, os.path.join(product_dir, "default"), session, log=log)
            _log(log, f"[INFO] Downloaded {count} images")
            return {
                "url": url,
                "title": title,
                "product_dir": product_dir,
                "gallery_count": gallery_count,
                "variants": 0,
                "variant_images": count,
            }

        _log(log, f"[INFO] Detected {len(variant_elements)} possible variants")

        visited: set[str] = set()
        variant_downloads = 0
        variant_images_total = 0

        for i, el in enumerate(variant_elements, start=1):
            try:
                label = _variant_label_from_element(el)
                if not label:
                    continue

                if label in visited:
                    continue
                visited.add(label)

                variant = Variant(label=label, folder_name=_extract_variant_folder_name_from_label(label))

                _log(log, f"[INFO] ({i}/{len(variant_elements)}) Variant: {variant.label}")

                # Click variant.
                if not _click_variant_element(driver, el):
                    _log(log, "[WARN] click failed; skipping")
                    continue

                # Wait a bit for image swap/lazy-load.
                time.sleep(1.0)

                urls_found = _collect_variant_images(driver, base_url=url)
                if not urls_found:
                    _log(log, "[WARN] No images found after selecting variant")
                    continue

                variant_dir = os.path.join(product_dir, variant.folder_name)
                count = _download_images(urls_found, variant_dir, session, log=log)
                variant_downloads += 1
                variant_images_total += count
                _log(log, f"[INFO] Downloaded {count} images into: {variant_dir}")

            except StaleElementReferenceException:
                # DOM changed; best effort: re-find variants and continue.
                variant_elements = _find_variant_elements(driver, product_title=title)
                continue

        return {
            "url": url,
            "title": title,
            "product_dir": product_dir,
            "gallery_count": gallery_count,
            "variants": variant_downloads,
            "variant_images": variant_images_total,
        }
    finally:
        if use_new_tab:
            _close_tab_and_restore(driver, original_handle, opened_handle)


def download_pinarello_variants(
    url: str,
    output_dir: str,
    browser: str,
    headless: bool,
    wait_s: int,
    log: Callable[[str], None] | None = None,
) -> dict:
    driver = _setup_driver(browser=browser, headless=headless)
    try:
        return _download_pinarello_variants_with_driver(
            driver,
            url=url,
            output_dir=output_dir,
            wait_s=wait_s,
            log=log,
            use_new_tab=False,
        )

    finally:
        try:
            driver.quit()
        except Exception:
            pass


def download_pinarello_variants_in_existing_browser(
    driver: webdriver.Remote,
    url: str,
    output_dir: str,
    wait_s: int = 20,
    log: Callable[[str], None] | None = None,
) -> dict:
    """Download Pinarello images using an already-running Selenium session.

    This will open the product page in a new tab, do the scraping/downloading,
    then close the tab and return to the previous tab.
    """
    return _download_pinarello_variants_with_driver(
        driver,
        url=url,
        output_dir=output_dir,
        wait_s=wait_s,
        log=log,
        use_new_tab=True,
    )


def main() -> None:
    default_urls = [
        "https://pinarello.com/global/ja/bikes/road/competition/pinarello-f/pinarello-f5-ultegra",
        "https://pinarello.com/global/ja/bikes/gravel/competition/new-grevil-f/new-grevil-f7-sram-force-xplr-axs",
    ]

    parser = argparse.ArgumentParser(
        description="Download Pinarello product images into per-color-variant folders. Works best-effort across older/newer Pinarello pages.",
    )
    parser.add_argument(
        "url",
        nargs="*",
        help="One or more Pinarello product URLs (if omitted, runs the two example URLs)",
    )
    parser.add_argument("--out", default="_pinarello_images", help="Output directory")
    parser.add_argument("--browser", default="chrome", choices=["chrome", "edge", "firefox"], help="Browser to use")
    parser.add_argument("--headless", action="store_true", help="Run browser headless")
    parser.add_argument("--wait", type=int, default=20, help="Selenium explicit wait seconds")

    args = parser.parse_args()

    urls = args.url if args.url else default_urls
    if not args.url:
        _log(None, "[INFO] No URL argument provided; using default Pinarello example URLs")

    for url in urls:
        download_pinarello_variants(
            url=url,
            output_dir=args.out,
            browser=args.browser,
            headless=args.headless,
            wait_s=args.wait,
        )


if __name__ == "__main__":
    main()
