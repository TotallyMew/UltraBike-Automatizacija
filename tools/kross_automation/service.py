"""A focused KROSS → PIMBO workflow.

KROSS has changed its catalogue/search routes over time, so discovery tries
the site's public search variants and validates a returned product page by its
SKU rather than trusting a result-card URL. PIMBO writes stay behind
:class:`PimboProductEditor` and are limited to Draft products.
"""

from __future__ import annotations

import html
import json
import re
import time
from dataclasses import asdict, dataclass, field, replace
from io import BytesIO
from pathlib import Path
from typing import Any, Callable, ClassVar, Iterable, Sequence
from urllib.parse import quote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from Managers.PimboProductEditor import (
    PimAiStepResult,
    PimAutomationError,
    PimPreparationResult,
    PimPreparationStatus,
    PimboProductEditor,
)
from tools.orbea_automation.models import PimboFilterOptions, PimboFilterSpec
from tools.orbea_automation.pimbo import PimboBrowserClient


KROSS_HOME_URL = "https://kross.pl/"
PIMBO_PRODUCTS_URL = "https://pim.bo.ultrabike.lt/dashboard/products"
IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp")
KROSS_METADATA_NAME = "kross-product.json"
KROSS_DESCRIPTION_NAME = "description.html"
KROSS_SPECIFICATIONS_NAME = "specifications.txt"
PRODUCT_PHOTO_UPLOAD_BATCH_SIZE = 10
PRODUCT_PHOTO_UPLOAD_BATCH_PAUSE_SECONDS = 1.0
MIN_KROSS_PRODUCT_PHOTO_LONG_EDGE = 400


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\xa0", " ")).strip()


def normalize_sku(value: str) -> str:
    """Normalize supplier/presentation whitespace without changing the code."""

    return re.sub(r"[^A-Za-z0-9._-]", "", str(value or "").upper())


def is_kross_variant_sku(value: str) -> bool:
    """Return whether a value has the shape of a real KROSS variant code."""

    return bool(re.fullmatch(r"KR[A-Z0-9]{12,28}", normalize_sku(value)))


def unique_skus(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        sku = normalize_sku(value)
        if sku and sku not in seen:
            seen.add(sku)
            result.append(sku)
    return tuple(result)


@dataclass(frozen=True)
class KrossMatch:
    sku: str
    status: str
    pimbo_product_id: str = ""
    pimbo_product_name: str = ""
    pimbo_product_url: str = ""
    kross_product_name: str = ""
    kross_url: str = ""
    note: str = ""
    variant_skus: tuple[str, ...] = ()
    local_folder: str = ""

    @property
    def ready(self) -> bool:
        if self.status not in {"found", "collected", "collected_with_warnings", "local_ready"}:
            return False
        return bool(
            self.sku
            and (
                self.local_folder
                or (self.pimbo_product_url and self.kross_url)
            )
        )


@dataclass(frozen=True)
class KrossDiscoveryResult:
    matches: tuple[KrossMatch, ...]

    @property
    def found(self) -> int:
        return sum(item.ready for item in self.matches)


@dataclass(frozen=True)
class KrossProductData:
    url: str
    name: str
    description_html: str
    specification_text: str
    image_urls: tuple[str, ...]
    variant_skus: tuple[str, ...] = ()


@dataclass(frozen=True)
class KrossCollectionTarget:
    """One manually supplied SKU, URL, or explicit SKU/URL pair."""

    sku: str = ""
    url: str = ""

    @property
    def label(self) -> str:
        return self.sku or self.url


def parse_collection_targets(
    values: Iterable[str | KrossCollectionTarget],
) -> tuple[KrossCollectionTarget, ...]:
    """Parse pasted SKUs, KROSS URLs, and ``SKU | URL`` pairs."""

    targets: list[KrossCollectionTarget] = []
    seen: set[tuple[str, str]] = set()
    for value in values:
        if isinstance(value, KrossCollectionTarget):
            candidates = (value,)
        else:
            text = str(value or "").strip()
            if not text:
                continue
            urls = re.findall(r"https?://[^\s|,;]+", text, flags=re.IGNORECASE)
            remainder = re.sub(r"https?://[^\s|,;]+", " ", text, flags=re.IGNORECASE)
            skus = unique_skus(re.split(r"[\s|,;]+", remainder))
            if urls:
                candidates_list = [
                    KrossCollectionTarget(skus[0] if skus else "", urls[0])
                ]
                candidates_list.extend(KrossCollectionTarget(sku=sku) for sku in skus[1:])
                candidates_list.extend(KrossCollectionTarget(url=url) for url in urls[1:])
                candidates = tuple(candidates_list)
            else:
                candidates = tuple(KrossCollectionTarget(sku=sku) for sku in skus)
        for candidate in candidates:
            normalized = KrossCollectionTarget(
                normalize_sku(candidate.sku), str(candidate.url or "").strip()
            )
            key = (normalized.sku, normalized.url.casefold())
            if (normalized.sku or normalized.url) and key not in seen:
                seen.add(key)
                targets.append(normalized)
    return tuple(targets)


@dataclass(frozen=True)
class KrossPimboProduct:
    product_id: str
    product_name: str
    product_url: str
    visible_code: str
    variant_skus: tuple[str, ...]
    error: str = ""


@dataclass(frozen=True)
class KrossCollectionOptions:
    """KROSS data that should be saved locally during the collection pass."""

    STAGES: ClassVar[tuple[str, ...]] = (
        "product_photos",
        "dimensions",
        "description_source",
        "specifications_source",
    )

    product_photos: bool = True
    dimensions: bool = True
    description_source: bool = True
    specifications_source: bool = True

    @property
    def any_selected(self) -> bool:
        return any(getattr(self, name) for name in self.STAGES)

    @classmethod
    def only(cls, *stages: str) -> "KrossCollectionOptions":
        unknown = set(stages) - set(cls.STAGES)
        if unknown:
            raise ValueError(f"Unknown KROSS collection stage(s): {', '.join(sorted(unknown))}")
        selected = set(stages)
        return cls(**{name: name in selected for name in cls.STAGES})


@dataclass(frozen=True)
class KrossWorkflowOptions:
    """Independently selectable stages for one KROSS → PIMBO run."""

    STAGES: ClassVar[tuple[str, ...]] = (
        "product_photos",
        "size_tables",
        "geometry",
        "description_source",
        "description_magic_ai",
        "product_family",
        "brand",
        "category_magic_ai",
        "translations",
        "save",
        "specifications_magic_ai",
    )

    product_photos: bool = True
    size_tables: bool = True
    geometry: bool = True
    brand: bool = True
    product_family: bool = True
    description_source: bool = True
    description_magic_ai: bool = True
    category_magic_ai: bool = True
    specifications_magic_ai: bool = True
    translations: bool = True
    save: bool = True

    @property
    def any_selected(self) -> bool:
        return any(getattr(self, name) for name in self.STAGES)

    @property
    def needs_catalogue(self) -> bool:
        return any((
            self.product_photos,
            self.size_tables,
            self.geometry,
            self.description_source,
            self.specifications_magic_ai,
        ))

    @property
    def needs_output_folder(self) -> bool:
        return self.product_photos or self.size_tables or self.geometry

    @property
    def selected_stages(self) -> tuple[str, ...]:
        return tuple(name for name in self.STAGES if getattr(self, name))

    @classmethod
    def only(cls, *stages: str) -> "KrossWorkflowOptions":
        unknown = set(stages) - set(cls.STAGES)
        if unknown:
            raise ValueError(f"Unknown KROSS workflow stage(s): {', '.join(sorted(unknown))}")
        selected = set(stages)
        return cls(**{name: name in selected for name in cls.STAGES})


@dataclass(frozen=True)
class KrossUploadResult:
    match: KrossMatch
    preparation: PimPreparationResult
    downloaded_images: tuple[Path, ...] = ()
    product: KrossProductData | None = None
    dimensions_image: Path | None = None
    size_chart_image: Path | None = None
    options: KrossWorkflowOptions = field(default_factory=KrossWorkflowOptions)
    completed_stages: tuple[str, ...] = ()

    @property
    def succeeded(self) -> bool:
        return self.preparation.status in {
            PimPreparationStatus.NO_CHANGES,
            PimPreparationStatus.READY_FOR_REVIEW,
            PimPreparationStatus.SAVED_AUTOMATICALLY,
        }


class KrossPublicCatalog:
    """Read KROSS public product pages and download their product images."""

    def __init__(
        self,
        session: requests.Session | None = None,
        *,
        timeout: float = 30.0,
        browser_driver: Any | None = None,
    ) -> None:
        self.session = session or requests.Session()
        self.timeout = timeout
        self.browser_driver = browser_driver
        self.session.headers.setdefault(
            "User-Agent",
            "UltraBike KROSS catalogue assistant/1.0 (+https://ultrabike.lt)",
        )

    def _get(self, url: str) -> requests.Response:
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        return response

    @staticmethod
    def _absolute(base_url: str, value: str) -> str:
        return urljoin(base_url, str(value or "").strip())

    @staticmethod
    def _hosted_by_kross(value: str) -> bool:
        parsed = urlparse(value)
        return parsed.scheme == "https" and parsed.netloc.casefold().endswith("kross.pl")

    @classmethod
    def _is_product_url(cls, value: str) -> bool:
        if not cls._hosted_by_kross(value):
            return False
        path = urlparse(value).path.rstrip("/").casefold()
        if not path or path.startswith("/catalogsearch/result"):
            return False
        return not any(
            path.startswith(prefix)
            for prefix in (
                "/customer", "/checkout", "/cart", "/wishlist", "/blog",
                "/kontakt", "/uslugi", "/salony-firmowe", "/mapa-sklepow",
            )
        )

    @staticmethod
    def _dismiss_browser_overlays(driver: Any) -> None:
        """Dismiss KROSS cookie/newsletter layers without retaining elements."""

        from selenium.webdriver.common.by import By

        selectors = (
            "#CybotCookiebotDialogBodyButtonDecline",
            "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
            "#onetrust-reject-all-handler",
            "#onetrust-accept-btn-handler",
        )
        text_labels = (
            "Nie, dziękuję", "Nie, dziekuje", "Odmowa",
            "Zezwól na wszystkie", "Akceptuję", "Akceptuj",
        )
        for _attempt in range(3):
            clicked = False
            for selector in selectors:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, selector)
                except Exception:
                    elements = []
                for element in elements:
                    try:
                        if element.is_displayed():
                            driver.execute_script("arguments[0].click();", element)
                            clicked = True
                            break
                    except Exception:
                        continue
                if clicked:
                    break
            if not clicked:
                for label in text_labels:
                    literal = label.replace("'", "\\'")
                    try:
                        elements = driver.find_elements(
                            By.XPATH,
                            f"//button[contains(normalize-space(.), '{literal}')]|"
                            f"//*[@role='button' and contains(normalize-space(.), '{literal}') ]",
                        )
                    except Exception:
                        elements = []
                    for element in elements:
                        try:
                            if element.is_displayed():
                                driver.execute_script("arguments[0].click();", element)
                                clicked = True
                                break
                        except Exception:
                            continue
                    if clicked:
                        break
            if not clicked:
                break
            time.sleep(0.2)

        # The direct Magento search does not require either overlay. Hiding a
        # leftover known layer is a safe final fallback for browser automation.
        try:
            driver.execute_script(
                """
                for (const selector of [
                  '#CybotCookiebotDialog', '#CybotCookiebotDialogBodyUnderlay',
                  'div.snrs-modal', '#snrs-wp-subscriber'
                ]) {
                  for (const node of document.querySelectorAll(selector)) {
                    node.style.setProperty('display', 'none', 'important');
                  }
                }
                document.documentElement.style.removeProperty('overflow');
                document.body.style.removeProperty('overflow');
                """
            )
        except Exception:
            pass

    def _page_contains_sku(self, url: str, sku: str) -> bool:
        try:
            response = self._get(url)
        except requests.RequestException:
            return False
        text = normalize_sku(BeautifulSoup(response.text, "html.parser").get_text(" ", strip=True))
        return normalize_sku(sku) in text

    @staticmethod
    def _visible(elements: Iterable[Any]) -> list[Any]:
        visible: list[Any] = []
        for element in elements:
            try:
                if element.is_displayed():
                    visible.append(element)
            except Exception:
                continue
        return visible

    def _find_product_url_in_browser(self, sku: str) -> tuple[str, str]:
        """Use Magento's direct search URL, avoiding the blocked search widget."""

        driver = self.browser_driver
        if driver is None:
            return "", ""
        sku = normalize_sku(sku)
        lookup_timeout = min(max(float(self.timeout), 1.0), 12.0)
        try:
            driver.set_page_load_timeout(lookup_timeout)
        except Exception:
            pass
        search_url = f"https://kross.pl/catalogsearch/result/?q={quote(sku)}"
        try:
            driver.get(search_url)
        except Exception:
            # Firefox can report a page-load timeout after the useful search DOM
            # is already present.  Inspect that partial page before giving up.
            pass
        self._dismiss_browser_overlays(driver)
        deadline = time.monotonic() + lookup_timeout
        while time.monotonic() < deadline:
            current_url = str(driver.current_url or "")
            try:
                page_html = str(driver.page_source or "")
                page_text = normalize_sku(page_html)
            except Exception:
                page_html = ""
                page_text = ""
            if self._is_product_url(current_url) and sku in page_text:
                try:
                    title = _clean(driver.title)
                except Exception:
                    title = ""
                return current_url, title
            if "BRAKWYNIKOWWYSZUKIWANIA" in page_text:
                return "", ""
            # Some KROSS searches show a result tile instead of redirecting.
            # Open likely product tiles in the browser and validate their page
            # against the exact SKU, avoiding slow serial requests in the
            # background while the old geometry page remains visible.
            if page_html:
                soup = BeautifulSoup(page_html, "html.parser")
                links: list[tuple[int, str, str]] = []
                seen: set[str] = set()
                for anchor in soup.select("a[href]"):
                    href = self._absolute(current_url or search_url, anchor.get("href", ""))
                    if href in seen or not self._is_product_url(href):
                        continue
                    parent = anchor.find_parent(
                        class_=re.compile(r"product|item|tile", re.IGNORECASE)
                    )
                    if parent is None:
                        continue
                    parent_text = normalize_sku(parent.get_text(" ", strip=True))
                    title = _clean(anchor.get_text(" ", strip=True))
                    image = anchor.select_one("img[alt]")
                    if not title and image is not None:
                        title = _clean(image.get("alt"))
                    seen.add(href)
                    links.append((0 if sku in parent_text else 1, href, title))
                if links:
                    for _priority, href, title in sorted(links)[:8]:
                        try:
                            driver.get(href)
                        except Exception:
                            pass
                        try:
                            candidate_url = str(driver.current_url or href)
                            candidate_text = normalize_sku(driver.page_source)
                        except Exception:
                            continue
                        if self._is_product_url(candidate_url) and sku in candidate_text:
                            try:
                                browser_title = _clean(driver.title)
                            except Exception:
                                browser_title = ""
                            return candidate_url, browser_title or title
                    return "", ""
            time.sleep(0.15)
        return "", ""

    def find_product_url(self, sku: str) -> tuple[str, str]:
        """Find and validate one KROSS product page for ``sku``.

        Direct search URLs are tried first to keep discovery fast.  Every
        candidate is validated against the product page, so stale result cards
        and generic category pages cannot become upload targets.
        """

        sku = normalize_sku(sku)
        if not sku:
            return "", ""
        # With a connected browser, move away from the preceding geometry page
        # immediately.  Previously the browser appeared frozen there while up
        # to five background HTTP searches each waited on a network timeout.
        if self.browser_driver is not None:
            return self._find_product_url_in_browser(sku)
        candidates = (
            f"https://kross.pl/catalogsearch/result/?q={sku}",
            f"https://kross.pl/szukaj?query={sku}",
            f"https://kross.pl/search?query={sku}",
            f"https://kross.pl/search?q={sku}",
            f"https://kross.pl/search?search={sku}",
        )
        for search_url in candidates:
            try:
                response = self._get(search_url)
            except requests.RequestException:
                continue
            soup = BeautifulSoup(response.text, "html.parser")
            response_url = str(response.url or search_url)
            page_text = normalize_sku(soup.get_text(" ", strip=True))
            if self._is_product_url(response_url) and sku in page_text:
                return response_url, self._first_text(soup, ("main h1", "h1", "title"))
            links: list[tuple[int, str, str]] = []
            for anchor in soup.select("a[href]"):
                href = self._absolute(response.url or search_url, anchor.get("href", ""))
                if not self._hosted_by_kross(href):
                    continue
                path = urlparse(href).path.rstrip("/").casefold()
                if not path or path in {"/", "/konto", "/koszyk", "/kontakt"}:
                    continue
                title = _clean(anchor.get_text(" ", strip=True))
                image = anchor.select_one("img[alt]")
                if not title and image is not None:
                    title = _clean(image.get("alt"))
                parent = anchor.find_parent(class_=re.compile(r"product|item|tile", re.IGNORECASE))
                parent_text = normalize_sku(parent.get_text(" ", strip=True)) if parent else ""
                priority = 0 if sku in parent_text else 1 if parent is not None else 2
                if href not in {item[1] for item in links}:
                    links.append((priority, href, title))
            for _priority, href, title in sorted(links)[:80]:
                if self._page_contains_sku(href, sku):
                    return href, title
        return self._find_product_url_in_browser(sku)

    @staticmethod
    def _first_text(soup: BeautifulSoup, selectors: Sequence[str]) -> str:
        for selector in selectors:
            element = soup.select_one(selector)
            if element is not None:
                value = _clean(element.get_text(" ", strip=True))
                if value:
                    return value
        return ""

    @staticmethod
    def _html_fragment(element: Any) -> str:
        if element is None:
            return ""
        for unwanted in element.select("script, style, noscript"):
            unwanted.decompose()
        return str(element).strip()

    @staticmethod
    def _product_image_asset_key(image_url: str) -> str:
        """Collapse Magento full/thumbnail cache variants of the same asset."""

        path = urlparse(image_url).path
        match = re.search(
            r"/media/catalog/product/cache/[^/]+/(.+)$",
            path,
            flags=re.IGNORECASE,
        )
        return (match.group(1) if match else path).casefold()

    def _valid_product_image_urls(
        self,
        page_url: str,
        raw_urls: Iterable[str],
    ) -> list[str]:
        images: list[str] = []
        seen_assets: set[str] = set()
        for raw_url in raw_urls:
            image_url = self._absolute(page_url, raw_url)
            path = urlparse(image_url).path.casefold()
            asset_key = self._product_image_asset_key(image_url)
            if (
                self._hosted_by_kross(image_url)
                and path.endswith(IMAGE_SUFFIXES)
                and not path.endswith("/view.png")
                and asset_key not in seen_assets
            ):
                seen_assets.add(asset_key)
                images.append(image_url)
        return images

    def _product_gallery_images(self, soup: BeautifulSoup, page_url: str) -> list[str]:
        """Return only full-resolution product gallery sources, in display order."""

        gallery_sources = (
            (".kross-gallery-slide[data-large-src]", "data-large-src"),
            ("a.orbitvu-gallery-item-link[data-big_src]", "data-big_src"),
            ("[data-zoom-image]", "data-zoom-image"),
        )
        for selector, attribute in gallery_sources:
            images = self._valid_product_image_urls(
                page_url,
                (element.get(attribute) or "" for element in soup.select(selector)),
            )
            if images:
                return images

        # A single social-preview image is safer than treating carousel
        # thumbnail <img> elements as uploadable product photos.
        preview = soup.select_one("meta[property='og:image'][content]")
        return self._valid_product_image_urls(
            page_url,
            (preview.get("content") if preview is not None else "",),
        )

    def fetch_product(self, url: str) -> KrossProductData:
        if not self._hosted_by_kross(url):
            raise ValueError("Only public https://kross.pl product URLs are supported")
        try:
            response = self._get(url)
            page_url = response.url
            page_html = response.text
        except requests.RequestException:
            driver = self.browser_driver
            if driver is None:
                raise
            driver.get(url)
            deadline = time.monotonic() + self.timeout
            while time.monotonic() < deadline:
                try:
                    if str(driver.execute_script("return document.readyState")) == "complete":
                        break
                except Exception:
                    break
                time.sleep(0.1)
            page_url = driver.current_url
            page_html = driver.page_source
        soup = BeautifulSoup(page_html, "html.parser")
        title = self._first_text(soup, ("main h1", "h1", "meta[property='og:title']"))
        if not title:
            title = _clean(soup.title.string if soup.title else "")

        description = None
        for selector in (
            "#description", "[data-role='description']", ".product-description",
            ".product.info.detailed .description", ".description",
        ):
            candidate = soup.select_one(selector)
            if candidate is not None and _clean(candidate.get_text(" ", strip=True)):
                description = candidate
                break
        description_html = self._html_fragment(description)

        specs: list[str] = []
        seen_spec_rows: set[str] = set()
        for row in soup.select(
            "#additional tr, [id*='additional'] tr, .additional-attributes-table tr, "
            ".product-specifications tr, .specifications tr, dl"
        ):
            if getattr(row, "name", "") == "dl":
                pairs = zip(row.select("dt"), row.select("dd"))
            else:
                cells = row.select("th, td")
                pairs = [(cells[0], cells[1])] if len(cells) >= 2 else []
            for key_cell, value_cell in pairs:
                key = _clean(key_cell.get_text(" ", strip=True))
                value = _clean(value_cell.get_text(" ", strip=True))
                line = f"{key}: {value}" if key and value else ""
                if line and line not in seen_spec_rows:
                    seen_spec_rows.add(line)
                    specs.append(line)

        images = self._product_gallery_images(soup, page_url)
        variant_skus: list[str] = []
        for element in soup.select("[itemprop='sku'], [data-sku], meta[itemprop='sku']"):
            raw = (
                element.get("content")
                or element.get("data-sku")
                or element.get_text(" ", strip=True)
            )
            candidate = normalize_sku(raw)
            if candidate and candidate not in variant_skus:
                variant_skus.append(candidate)
        for raw in re.findall(
            r'''["'](?:sku|simple_sku|product_sku)["']\s*:\s*["']([^"']+)["']''',
            page_html,
            flags=re.IGNORECASE,
        ):
            candidate = normalize_sku(html.unescape(raw))
            if candidate and candidate not in variant_skus:
                variant_skus.append(candidate)
        for raw in re.findall(r"\bKR[A-Z0-9]{10,28}\b", page_html, flags=re.IGNORECASE):
            candidate = normalize_sku(raw)
            if candidate not in variant_skus:
                variant_skus.append(candidate)
        variant_skus.sort(key=lambda candidate: (not candidate.startswith("KR"), candidate))
        return KrossProductData(
            url=page_url,
            name=title,
            description_html=description_html,
            specification_text="\n".join(specs),
            image_urls=tuple(images),
            variant_skus=tuple(variant_skus),
        )

    def download_images(
        self,
        product: KrossProductData,
        destination: Path,
        *,
        log: Callable[[str], None] | None = None,
    ) -> tuple[Path, ...]:
        destination.mkdir(parents=True, exist_ok=True)
        downloaded: list[Path] = []
        for index, image_url in enumerate(product.image_urls, start=1):
            suffix = Path(urlparse(image_url).path).suffix.casefold()
            suffix = suffix if suffix in IMAGE_SUFFIXES else ".jpg"
            target = destination / f"{index:02d}{suffix}"
            try:
                response = self._get(image_url)
                content_type = (response.headers.get("content-type") or "").casefold()
                if content_type and "image" not in content_type:
                    raise ValueError(f"unexpected content type {content_type}")
                from PIL import Image

                with Image.open(BytesIO(response.content)) as image:
                    width, height = image.size
                    image.load()
                if max(width, height) < MIN_KROSS_PRODUCT_PHOTO_LONG_EDGE:
                    raise ValueError(
                        f"thumbnail-sized image ({width}x{height}px)"
                    )
                target.write_bytes(response.content)
                if target.stat().st_size:
                    downloaded.append(target)
                    if log:
                        log(f"Downloaded photo {index}/{len(product.image_urls)}")
            except Exception as error:
                if log:
                    log(f"Photo {index} skipped: {error}")
        return tuple(downloaded)

    def capture_dimensions(
        self,
        product: KrossProductData,
        destination: Path,
        *,
        log: Callable[[str], None] | None = None,
    ) -> Path | None:
        """Capture the full-width English geometry table when one is available."""

        if self.browser_driver is None:
            if log:
                log("Dimensions table skipped: no browser is connected")
            return None
        from .dimensions import (
            KrossDimensionsNotAvailable,
            SIZE_CHART_IMAGE_NAME,
            capture_kross_dimensions_table,
        )

        try:
            dimensions = capture_kross_dimensions_table(
                self.browser_driver,
                product.url,
                destination,
                timeout=self.timeout,
            )
        except KrossDimensionsNotAvailable:
            if log:
                log("KROSS product has no dimensions table; continuing without it")
            return None
        if log:
            size_chart = Path(destination).with_name(SIZE_CHART_IMAGE_NAME)
            suffix = " and separate SIZE/HEIGHT image" if size_chart.is_file() else ""
            log(
                f"Captured full dimensions table ({dimensions[0]}x{dimensions[1]} px){suffix}"
            )
        return Path(destination)


class KrossPimboScanner(PimboBrowserClient):
    """Scan filtered KROSS products in PIMBO and retain every variant SKU."""

    def __init__(self, driver: Any, *, cancellation: Any = None) -> None:
        super().__init__(
            driver,
            cancellation=cancellation,
            search_term="kross",
            expected_brand="kross",
            run_name="KROSS",
        )

    def _variant_sku_snapshot(self) -> tuple[str, ...] | None:
        By = self._by()
        try:
            rows = self.driver.find_elements(
                By.CSS_SELECTOR,
                "div[role='tabpanel'] table tbody tr[data-slot='table-row']",
            )
            if not rows:
                return None
            values: list[str] = []
            for row in rows:
                cells = row.find_elements(By.CSS_SELECTOR, "td")
                if not cells:
                    continue
                links = cells[0].find_elements(
                    By.CSS_SELECTOR, "a[href*='/dashboard/variants/']"
                )
                sku = normalize_sku(links[0].text if links else cells[0].text)
                if sku and sku not in values:
                    values.append(sku)
            return tuple(values) or None
        except Exception:
            return None

    def _open_product(self, row_index: int) -> KrossPimboProduct:
        snapshot: dict[str, Any] | None = None
        last_error: BaseException | None = None
        for _attempt in range(8):
            self._check_cancelled()
            try:
                row, snapshot = self._row_snapshot(row_index)
                href = str(snapshot.get("row_href") or "")
                if href:
                    self.driver.get(href)
                else:
                    self.driver.execute_script(
                        "arguments[0].scrollIntoView({block:'center'}); arguments[0].click();",
                        row,
                    )
                self._wait_until(
                    lambda: bool(re.search(
                        r"/dashboard/products/[^/?#]+",
                        str(self.driver.current_url or ""),
                    )),
                    15.0,
                    "The PIMBO product did not open",
                )
                break
            except Exception as error:
                last_error = error
                time.sleep(0.15)
        else:
            raise RuntimeError(f"The PIMBO product row kept refreshing: {last_error}")

        def open_variants() -> PimboProductEditor | None:
            try:
                editor = PimboProductEditor(self.driver)
                editor.open_section("variants")
                return editor
            except Exception:
                return None

        self._wait_until(open_variants, 10.0, "The PIMBO Variants section did not open")
        variants = self._wait_until(
            self._variant_sku_snapshot,
            10.0,
            "The PIMBO variant SKUs did not load",
        )
        product_url = str(self.driver.current_url or "")
        product_id = product_url.rstrip("/").split("/")[-1]
        return KrossPimboProduct(
            product_id=product_id,
            product_name=_clean((snapshot or {}).get("title")),
            product_url=product_url,
            visible_code=normalize_sku((snapshot or {}).get("visible_code", "")),
            variant_skus=unique_skus(variants),
        )

    def scan_products(
        self,
        filters: PimboFilterSpec,
        *,
        progress: Callable[[int, int, str], None] | None = None,
        log: Callable[[str], None] | None = None,
    ) -> tuple[KrossPimboProduct, ...]:
        self.apply_filters(filters)
        product_total, pages = self._totals()
        found: list[KrossPimboProduct] = []
        processed = 0
        if log:
            log(f"Filtered PIMBO list: {product_total or 'unknown'} KROSS products across {pages} page(s)")
        for page in range(1, pages + 1):
            self._check_cancelled()
            if product_total is not None and processed >= product_total:
                break
            self.go_to_page(page)
            row_count = len(self._wait_for_rows(allow_empty=True))
            if product_total is not None:
                # The page input updates before the React table. On the final
                # page, _wait_for_rows can momentarily see the preceding page's
                # full row set. Never scan beyond the confirmed filtered total.
                row_count = min(row_count, max(product_total - processed, 0))
            for row_index in range(row_count):
                self._check_cancelled()
                if progress:
                    progress(
                        processed,
                        product_total or max(processed + row_count, 1),
                        f"Reading all variants for PIMBO product {processed + 1}",
                    )
                try:
                    product = self._open_product(row_index)
                    found.append(product)
                    if log:
                        log(
                            f"{product.product_name or product.product_id}: "
                            f"{len(product.variant_skus)} variant(s)"
                        )
                except Exception as error:
                    try:
                        _row, snapshot = self._row_snapshot(row_index)
                    except Exception:
                        snapshot = {}
                    failed = KrossPimboProduct(
                        product_id="",
                        product_name=_clean(snapshot.get("title")),
                        product_url="",
                        visible_code=normalize_sku(snapshot.get("visible_code", "")),
                        variant_skus=(),
                        error=str(error),
                    )
                    found.append(failed)
                    if log:
                        log(f"PIMBO product {processed + 1} skipped: {error}")
                finally:
                    self._restore_list(page, filters)
                processed += 1
                if progress:
                    progress(
                        processed,
                        product_total or processed,
                        f"Read variants for {processed} PIMBO product(s)",
                    )
        return tuple(found)


class KrossPimboClient:
    """Find a PIMBO product by one of its variant SKUs without altering it."""

    def __init__(self, driver: Any, *, timeout: float = 15.0) -> None:
        self.driver = driver
        self.timeout = timeout

    def _wait(self, predicate: Callable[[], Any], message: str, timeout: float | None = None) -> Any:
        deadline = time.monotonic() + (timeout or self.timeout)
        error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                value = predicate()
                if value:
                    return value
            except Exception as caught:
                error = caught
            time.sleep(0.15)
        detail = f": {error}" if error else ""
        raise RuntimeError(f"{message}{detail}")

    def _safe_click(
        self,
        target: Any | Callable[[], Any],
        message: str,
        *,
        attempts: int = 5,
    ) -> Any:
        """Retry PIMBO controls replaced or covered by its fixed toolbar."""

        resolve = target if callable(target) else lambda: target
        last_error: BaseException | None = None
        for _attempt in range(max(1, attempts)):
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
                    pass
                try:
                    element.click()
                except Exception:
                    self.driver.execute_script("arguments[0].click();", element)
                return element
            except Exception as error:
                last_error = error
                time.sleep(0.15)
        detail = f": {last_error}" if last_error else ""
        raise RuntimeError(f"{message}{detail}")

    @staticmethod
    def _visible(elements: Iterable[Any]) -> list[Any]:
        result: list[Any] = []
        for element in elements:
            try:
                if element.is_displayed():
                    result.append(element)
            except Exception:
                continue
        return result

    def _ensure_list(self) -> None:
        from selenium.webdriver.common.by import By

        if "/dashboard/products/" in (self.driver.current_url or ""):
            if PimboProductEditor(self.driver).is_dirty():
                raise RuntimeError("The open PIMBO product has unsaved changes")
        if "/dashboard/products" not in (self.driver.current_url or "") or "/dashboard/products/" in (self.driver.current_url or ""):
            self.driver.get(PIMBO_PRODUCTS_URL)
        self._wait(
            lambda: self._visible(
                self.driver.find_elements(By.CSS_SELECTOR, "main input[placeholder='Search...']")
            ),
            "PIMBO Products did not become ready. Log in and open Products first",
        )

    def _search_field(self) -> Any | None:
        from selenium.webdriver.common.by import By

        return next(
            iter(self._visible(self.driver.find_elements(
                By.CSS_SELECTOR, "main input[placeholder='Search...']"
            ))),
            None,
        )

    def _set_search(self, sku: str) -> None:
        from selenium.webdriver.common.keys import Keys

        field = self._wait(
            lambda: self._search_field(),
            "PIMBO search field was not found",
        )
        first_field = [field]

        def current_field() -> Any:
            if first_field:
                return first_field.pop()
            return self._search_field()

        field = self._safe_click(
            current_field,
            "The PIMBO SKU search field remained covered",
        )
        field.send_keys(Keys.CONTROL, "a")
        field.send_keys(sku)
        field.send_keys(Keys.ENTER)
        self._wait(
            lambda: _clean(self._search_field().get_attribute("value")).casefold() == sku.casefold(),
            "PIMBO SKU search was not applied",
            6.0,
        )
        time.sleep(0.35)

    def _rows(self) -> list[Any]:
        from selenium.webdriver.common.by import By

        return self._visible(self.driver.find_elements(
            By.CSS_SELECTOR, "main table tbody tr[data-slot='table-row']"
        ))

    def _row_info(self, row: Any) -> tuple[str, str, str]:
        from selenium.webdriver.common.by import By

        links = row.find_elements(By.CSS_SELECTOR, "a[href*='/dashboard/products/']")
        href = links[0].get_attribute("href") if links else ""
        titles = row.find_elements(By.CSS_SELECTOR, "span.font-medium[title]")
        title = _clean(titles[0].get_attribute("title") if titles else "")
        code = _clean((row.find_elements(By.CSS_SELECTOR, "span.font-mono") or [row])[0].text)
        return href, title, code

    def _open_product_row(
        self,
        row_index: int,
        href: str,
        title: str,
        code: str,
    ) -> None:
        """Open a PIMBO result whose current UI may not contain an anchor."""

        if href:
            self.driver.get(href)
            return

        normalized_code = normalize_sku(code)
        normalized_title = _clean(title).casefold()
        deadline = time.monotonic() + max(1.0, min(self.timeout, 6.0))
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                rows = self._rows()
                target = None
                for row in rows:
                    _href, row_title, row_code = self._row_info(row)
                    if normalized_code and normalize_sku(row_code) == normalized_code:
                        target = row
                        break
                    if normalized_title and _clean(row_title).casefold() == normalized_title:
                        target = row
                        break
                if (
                    target is None
                    and not normalized_code
                    and not normalized_title
                    and row_index < len(rows)
                ):
                    target = rows[row_index]
                if target is None:
                    raise RuntimeError("The matching PIMBO product row disappeared")
                self.driver.execute_script(
                    "arguments[0].scrollIntoView({block:'center'}); arguments[0].click();",
                    target,
                )
                return
            except Exception as error:
                # PIMBO replaces search rows while React applies the query. A
                # failed reference must be discarded, not clicked again.
                last_error = error
                time.sleep(0.15)
        detail = f": {last_error}" if last_error else ""
        raise RuntimeError(f"The matching PIMBO product row could not be opened{detail}")

    def _candidate_snapshots(self) -> list[tuple[int, str, str, str]]:
        deadline = time.monotonic() + max(1.0, min(self.timeout, 6.0))
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                return [
                    (index, *self._row_info(row))
                    for index, row in enumerate(self._rows())
                ]
            except Exception as error:
                last_error = error
                time.sleep(0.15)
        detail = f": {last_error}" if last_error else ""
        raise RuntimeError(f"PIMBO search results kept refreshing{detail}")

    @staticmethod
    def _candidate_signature(
        candidates: Iterable[tuple[int, str, str, str]],
    ) -> tuple[tuple[str, str, str], ...]:
        return tuple(
            (str(href or ""), _clean(title), normalize_sku(code))
            for _index, href, title, code in candidates
        )

    def _wait_for_fresh_candidates(
        self,
        previous_signature: tuple[tuple[str, str, str], ...] | None,
    ) -> list[tuple[int, str, str, str]]:
        """Wait past React's previous-query rows before opening a result."""

        deadline = time.monotonic() + max(1.5, min(self.timeout, 6.0))
        started = time.monotonic()
        last_signature: tuple[tuple[str, str, str], ...] | None = None
        stable_since = started
        latest: list[tuple[int, str, str, str]] = []
        while time.monotonic() < deadline:
            latest = self._candidate_snapshots()
            signature = self._candidate_signature(latest)
            now = time.monotonic()
            if signature != last_signature:
                last_signature = signature
                stable_since = now
            changed_from_previous = (
                previous_signature is None or signature != previous_signature
            )
            if changed_from_previous and now - stable_since >= 0.3:
                return latest
            # The same PIMBO product can legitimately match two of its variant
            # SKUs, so unchanged rows are allowed after a short refresh window.
            if now - started >= 1.5 and now - stable_since >= 0.3:
                return latest
            time.sleep(0.15)
        return latest

    def _variant_skus(self, expected_sku: str = "") -> set[str] | None:
        from selenium.webdriver.common.by import By

        try:
            values: set[str] = set()
            expected = normalize_sku(expected_sku)
            rows = self.driver.find_elements(
                By.CSS_SELECTOR,
                "div[role='tabpanel'] table tbody tr[data-slot='table-row']",
            )
            for row in rows:
                if not row.is_displayed():
                    continue
                cells = row.find_elements(By.CSS_SELECTOR, "td")
                if not cells:
                    continue
                links = cells[0].find_elements(
                    By.CSS_SELECTOR, "a[href*='/dashboard/variants/']"
                )
                raw = str(links[0].text if links else cells[0].text).replace("\xa0", " ")
                normalized = normalize_sku(raw)
                if expected and expected in normalized:
                    values.add(expected)
                for line in raw.splitlines():
                    value = normalize_sku(line)
                    if value:
                        values.add(value)
            for item in self.driver.find_elements(
                By.CSS_SELECTOR, "main a[href*='/dashboard/variants/']"
            ):
                if item.is_displayed():
                    raw = str(item.text or "").replace("\xa0", " ")
                    normalized = normalize_sku(raw)
                    if expected and expected in normalized:
                        values.add(expected)
                    for line in raw.splitlines():
                        value = normalize_sku(line)
                        if value:
                            values.add(value)
            return values or None
        except Exception:
            # Never expose a stale WebElement to the next poll.
            return None

    def find_by_variant_sku(self, sku: str) -> KrossMatch:
        from selenium.webdriver.common.by import By

        sku = normalize_sku(sku)
        self._ensure_list()
        saw_candidates = False
        for _search_attempt in range(3):
            try:
                previous_field = self._search_field()
                previous_value = _clean(
                    previous_field.get_attribute("value") if previous_field else ""
                )
            except Exception:
                previous_value = ""
            previous_candidates = self._candidate_snapshots()
            previous_signature = (
                self._candidate_signature(previous_candidates)
                if previous_value.casefold() != sku.casefold()
                else None
            )
            self._set_search(sku)
            candidates = self._wait_for_fresh_candidates(previous_signature)
            if not candidates:
                continue
            saw_candidates = True
            candidates.sort(key=lambda item: normalize_sku(item[3]) != sku)
            for candidate_index, (row_index, href, title, code) in enumerate(candidates):
                matched_product = False
                try:
                    self._open_product_row(row_index, href, title, code)
                    self._wait(
                        lambda: "/dashboard/products/" in (self.driver.current_url or ""),
                        "PIMBO product did not open",
                    )

                    def open_variants() -> PimboProductEditor:
                        editor = PimboProductEditor(self.driver)
                        editor.open_section("variants")
                        return editor

                    editor = self._wait(
                        open_variants,
                        "PIMBO Variants did not become ready",
                        8.0,
                    )
                    try:
                        variant_skus = self._wait(
                            lambda: (
                                values
                                if (values := self._variant_skus(sku)) is not None
                                and sku in values
                                else None
                            ),
                            f"PIMBO variant SKU {sku} did not become ready",
                            8.0,
                        )
                    except RuntimeError:
                        variant_skus = set()
                    if sku in variant_skus:
                        product_url = str(self.driver.current_url or "")
                        product_match = re.search(
                            r"/dashboard/products/([^/?#]+)", product_url
                        )
                        product_id = product_match.group(1) if product_match else ""
                        # Keep the verified product open. The upload service can
                        # continue in this same editor without an unnecessary
                        # round-trip to Products and back into the product.
                        matched_product = True
                        return KrossMatch(
                            sku=sku,
                            status="pimbo_found",
                            pimbo_product_id=product_id,
                            pimbo_product_name=title or editor.product_name(),
                            pimbo_product_url=product_url,
                        )
                finally:
                    if (
                        not matched_product
                        and "/dashboard/products/" in (self.driver.current_url or "")
                    ):
                        self.driver.get(PIMBO_PRODUCTS_URL)
                        self._wait(
                            lambda: self._visible(self.driver.find_elements(
                                By.CSS_SELECTOR, "main input[placeholder='Search...']"
                            )),
                            "PIMBO did not return to Products",
                        )
                        if candidate_index < len(candidates) - 1:
                            self._set_search(sku)
                            self._wait_for_fresh_candidates(None)
            self._ensure_list()
        if not saw_candidates:
            return KrossMatch(sku, "pimbo_not_found", note="No PIMBO product matches this SKU")
        return KrossMatch(sku, "pimbo_not_found", note="SKU was not found in the PIMBO product variants")


class KrossAutomationService:
    """Collect filtered KROSS products locally, then prepare PIMBO from disk."""

    def __init__(
        self,
        pimbo_driver: Any,
        *,
        public_catalog: KrossPublicCatalog | None = None,
        pimbo_client_factory: Callable[[Any], KrossPimboClient] = KrossPimboClient,
        pimbo_scanner_factory: Callable[[Any], KrossPimboScanner] = KrossPimboScanner,
        editor_factory: Callable[[Any], PimboProductEditor] = PimboProductEditor,
    ) -> None:
        self.pimbo_driver = pimbo_driver
        self.public_catalog = public_catalog or KrossPublicCatalog(
            browser_driver=pimbo_driver,
        )
        self.pimbo_client_factory = pimbo_client_factory
        self.pimbo_scanner_factory = pimbo_scanner_factory
        self.editor_factory = editor_factory

    def discover_filter_options(self) -> PimboFilterOptions:
        return self.pimbo_scanner_factory(self.pimbo_driver).discover_filter_options()

    @staticmethod
    def _package_folder(output_root: Path, sku: str) -> Path:
        return Path(output_root) / normalize_sku(sku)

    @staticmethod
    def _local_product_photo_is_uploadable(path: Path) -> bool:
        """Keep old local packages from uploading cached 110px thumbnails."""

        try:
            from PIL import Image

            with Image.open(path) as image:
                width, height = image.size
            return max(width, height) >= MIN_KROSS_PRODUCT_PHOTO_LONG_EDGE
        except Exception:
            # Preserve compatibility with manually supplied image formats that
            # Pillow cannot inspect; PIMBO remains the final format validator.
            return True

    @staticmethod
    def _write_package(
        folder: Path,
        match: KrossMatch,
        product: KrossProductData,
        options: KrossCollectionOptions,
        warnings: Sequence[str],
    ) -> Path:
        folder.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1,
            "match": asdict(match),
            "product": asdict(product),
            "collection_stages": list(
                name for name in options.STAGES if getattr(options, name)
            ),
            "warnings": list(warnings),
        }
        target = folder / KROSS_METADATA_NAME
        target.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if product.description_html:
            (folder / KROSS_DESCRIPTION_NAME).write_text(
                product.description_html,
                encoding="utf-8",
            )
        if product.specification_text:
            (folder / KROSS_SPECIFICATIONS_NAME).write_text(
                product.specification_text,
                encoding="utf-8",
            )
        return target

    @staticmethod
    def _read_package(folder: Path) -> tuple[KrossMatch | None, KrossProductData | None]:
        target = Path(folder) / KROSS_METADATA_NAME
        if not target.is_file():
            return None, None
        payload = json.loads(target.read_text(encoding="utf-8"))
        match_data = dict(payload.get("match") or {})
        product_data = dict(payload.get("product") or {})
        description_file = Path(folder) / KROSS_DESCRIPTION_NAME
        specifications_file = Path(folder) / KROSS_SPECIFICATIONS_NAME
        if not product_data.get("description_html") and description_file.is_file():
            product_data["description_html"] = description_file.read_text(encoding="utf-8")
        if not product_data.get("specification_text") and specifications_file.is_file():
            product_data["specification_text"] = specifications_file.read_text(encoding="utf-8")
        if "variant_skus" in match_data:
            match_data["variant_skus"] = tuple(match_data.get("variant_skus") or ())
        for tuple_field in ("image_urls", "variant_skus"):
            if tuple_field in product_data:
                product_data[tuple_field] = tuple(product_data.get(tuple_field) or ())
        match = KrossMatch(**{
            name: match_data[name]
            for name in KrossMatch.__dataclass_fields__
            if name in match_data
        }) if match_data else None
        product = KrossProductData(**{
            name: product_data.get(
                name, () if name in {"image_urls", "variant_skus"} else ""
            )
            for name in KrossProductData.__dataclass_fields__
        }) if product_data else None
        return match, product

    @classmethod
    def load_local_packages(cls, output_root: Path) -> KrossDiscoveryResult:
        root = Path(output_root)
        if not root.is_dir():
            return KrossDiscoveryResult(())
        matches: list[KrossMatch] = []
        for folder in sorted((item for item in root.iterdir() if item.is_dir()), key=lambda item: item.name):
            sku = normalize_sku(folder.name)
            if not sku:
                continue
            try:
                saved, _product = cls._read_package(folder)
            except Exception as error:
                matches.append(KrossMatch(
                    sku=sku,
                    status="local_ready",
                    variant_skus=(sku,),
                    local_folder=str(folder),
                    note=(
                        f"Loaded local SKU folder, but {KROSS_METADATA_NAME} is invalid: {error}. "
                        "Photo/brand/family stages can still run."
                    ),
                ))
                continue
            if saved is None:
                matches.append(KrossMatch(
                    sku=sku,
                    status="local_ready",
                    variant_skus=(sku,),
                    local_folder=str(folder),
                    note="Loaded local SKU folder; source metadata is not available",
                ))
                continue
            matches.append(replace(
                saved,
                sku=sku,
                status="local_ready",
                local_folder=str(folder),
                note="Loaded from the local KROSS package",
            ))
        return KrossDiscoveryResult(tuple(matches))

    def collect_filtered(
        self,
        filters: PimboFilterSpec,
        output_root: Path,
        *,
        options: KrossCollectionOptions | None = None,
        progress: Callable[[int, int, str], None] | None = None,
        log: Callable[[str], None] | None = None,
    ) -> KrossDiscoveryResult:
        """Scan filtered PIMBO products, try every SKU, and save local packages."""

        selected = options or KrossCollectionOptions()
        root = Path(output_root)
        root.mkdir(parents=True, exist_ok=True)
        scanner = self.pimbo_scanner_factory(self.pimbo_driver)
        products = scanner.scan_products(filters, progress=progress, log=log)
        return self._collect_products(
            products,
            root,
            selected,
            progress=progress,
            log=log,
        )

    def collect_skus(
        self,
        skus: Iterable[str],
        output_root: Path,
        *,
        options: KrossCollectionOptions | None = None,
        progress: Callable[[int, int, str], None] | None = None,
        log: Callable[[str], None] | None = None,
    ) -> KrossDiscoveryResult:
        """Collect packages from pasted SKUs without scanning PIMBO variants."""

        return self.collect_inputs(
            skus,
            output_root,
            options=options,
            progress=progress,
            log=log,
        )

    def collect_inputs(
        self,
        values: Iterable[str | KrossCollectionTarget],
        output_root: Path,
        *,
        options: KrossCollectionOptions | None = None,
        progress: Callable[[int, int, str], None] | None = None,
        log: Callable[[str], None] | None = None,
    ) -> KrossDiscoveryResult:
        """Collect pasted SKUs and direct KROSS URLs without scanning PIMBO."""

        targets = parse_collection_targets(values)
        selected = options or KrossCollectionOptions()
        root = Path(output_root)
        root.mkdir(parents=True, exist_ok=True)
        matches: list[KrossMatch] = []
        total = len(targets)
        for index, target in enumerate(targets, start=1):
            if progress:
                progress(index - 1, total, f"Collecting KROSS data for {target.label}")
            try:
                if target.url and not KrossPublicCatalog._hosted_by_kross(target.url):
                    raise ValueError("Only public https://kross.pl product URLs are supported")
                product: KrossProductData | None = None
                kross_url = target.url
                kross_name = ""
                matched_sku = target.sku
                if kross_url:
                    if log:
                        log(f"Opening direct KROSS URL: {kross_url}")
                    # URL-only entries need the page metadata to derive the SKU.
                    # Explicit SKU/URL pairs can skip this fetch when only the
                    # dimensions stage is requested.
                    if not matched_sku or any((
                        selected.product_photos,
                        selected.description_source,
                        selected.specifications_source,
                    )):
                        product = self.public_catalog.fetch_product(kross_url)
                        kross_url = product.url
                        kross_name = product.name
                    page_variant_skus = tuple(
                        sku for sku in (product.variant_skus if product is not None else ())
                        if is_kross_variant_sku(sku)
                    )
                    if not matched_sku and page_variant_skus:
                        matched_sku = page_variant_skus[0]
                    if not matched_sku:
                        raise ValueError(
                            "The KROSS page did not expose a real variant SKU; "
                            "paste it as SKU | URL"
                        )
                else:
                    if log:
                        log(f"Searching KROSS for pasted SKU {matched_sku}")
                    kross_url, kross_name = self.public_catalog.find_product_url(matched_sku)
                    if not kross_url:
                        matches.append(KrossMatch(
                            sku=matched_sku,
                            status="kross_not_found",
                            variant_skus=(matched_sku,),
                            note="Pasted SKU was not found on kross.pl",
                        ))
                        if progress:
                            progress(index, total, f"No KROSS page for {matched_sku}")
                        continue

                variants = unique_skus((
                    matched_sku,
                    *(page_variant_skus if kross_url and product is not None else ()),
                ))
                pimbo = KrossPimboProduct(
                    product_id="",
                    product_name="",
                    product_url="",
                    visible_code=matched_sku,
                    variant_skus=variants or (matched_sku,),
                )
                match = self._collect_resolved_product(
                    pimbo,
                    matched_sku,
                    kross_url,
                    kross_name,
                    root,
                    selected,
                    log=log,
                    fetched_product=product,
                )
                matches.append(match)
                if progress:
                    progress(index, total, f"Collected {matched_sku}")
            except Exception as error:
                matches.append(KrossMatch(
                    sku=matched_sku or target.url,
                    status="error",
                    kross_url=target.url,
                    variant_skus=(matched_sku,) if matched_sku else (),
                    note=str(error),
                ))
                if progress:
                    progress(index, total, f"Could not collect {target.label}")
        return KrossDiscoveryResult(tuple(matches))

    def _collect_products(
        self,
        products: Iterable[KrossPimboProduct],
        root: Path,
        selected: KrossCollectionOptions,
        *,
        progress: Callable[[int, int, str], None] | None = None,
        log: Callable[[str], None] | None = None,
    ) -> KrossDiscoveryResult:
        products = tuple(products)
        matches: list[KrossMatch] = []
        total = len(products)
        for index, pimbo in enumerate(products, start=1):
            product_label = pimbo.product_name or pimbo.product_id or pimbo.visible_code
            if progress:
                progress(index - 1, total, f"Searching KROSS variants for {product_label}")
            if pimbo.error:
                matches.append(KrossMatch(
                    sku=pimbo.visible_code,
                    status="error",
                    pimbo_product_name=pimbo.product_name,
                    variant_skus=pimbo.variant_skus,
                    note=pimbo.error,
                ))
                continue
            matched_sku = ""
            kross_url = ""
            kross_name = ""
            for variant_index, sku in enumerate(pimbo.variant_skus, start=1):
                if log:
                    log(
                        f"{product_label}: checking variant "
                        f"{variant_index}/{len(pimbo.variant_skus)} — {sku}"
                    )
                kross_url, kross_name = self.public_catalog.find_product_url(sku)
                if kross_url:
                    matched_sku = sku
                    break
            if not matched_sku:
                matches.append(KrossMatch(
                    sku=pimbo.variant_skus[0] if pimbo.variant_skus else pimbo.visible_code,
                    status="kross_not_found",
                    pimbo_product_id=pimbo.product_id,
                    pimbo_product_name=pimbo.product_name,
                    pimbo_product_url=pimbo.product_url,
                    variant_skus=pimbo.variant_skus,
                    note=f"None of {len(pimbo.variant_skus)} variant SKU(s) was found on kross.pl",
                ))
                if progress:
                    progress(index, total, f"No KROSS page for {product_label}")
                continue
            match = self._collect_resolved_product(
                pimbo, matched_sku, kross_url, kross_name, root, selected, log=log
            )
            matches.append(match)
            if progress:
                progress(index, total, f"Collected {matched_sku}")
        return KrossDiscoveryResult(tuple(matches))

    def _collect_resolved_product(
        self,
        pimbo: KrossPimboProduct,
        matched_sku: str,
        kross_url: str,
        kross_name: str,
        root: Path,
        selected: KrossCollectionOptions,
        *,
        log: Callable[[str], None] | None = None,
        fetched_product: KrossProductData | None = None,
    ) -> KrossMatch:
        folder = self._package_folder(root, matched_sku)
        folder.mkdir(parents=True, exist_ok=True)
        warnings: list[str] = []
        needs_page_data = any((
            selected.product_photos,
            selected.description_source,
            selected.specifications_source,
        ))
        product = KrossProductData(kross_url, kross_name, "", "", ())
        if fetched_product is not None:
            product = replace(
                fetched_product,
                description_html=(
                    fetched_product.description_html if selected.description_source else ""
                ),
                specification_text=(
                    fetched_product.specification_text
                    if selected.specifications_source else ""
                ),
                image_urls=fetched_product.image_urls if selected.product_photos else (),
            )
        elif needs_page_data:
            try:
                fetched = self.public_catalog.fetch_product(kross_url)
                product = replace(
                    fetched,
                    description_html=(
                        fetched.description_html if selected.description_source else ""
                    ),
                    specification_text=(
                        fetched.specification_text if selected.specifications_source else ""
                    ),
                    image_urls=fetched.image_urls if selected.product_photos else (),
                )
            except Exception as error:
                warnings.append(f"KROSS product data: {error}")
        if selected.product_photos:
            try:
                downloaded = self.public_catalog.download_images(product, folder, log=log)
                if not downloaded:
                    warnings.append("No KROSS product photos were downloaded")
            except Exception as error:
                warnings.append(f"Photos: {error}")
        if selected.dimensions:
            try:
                captured = self.public_catalog.capture_dimensions(
                    product,
                    folder / "dimensions-table.png",
                    log=log,
                )
                if captured is None:
                    warnings.append("KROSS product has no dimensions table")
            except Exception as error:
                warnings.append(f"Dimensions: {error}")

        status = "collected_with_warnings" if warnings else "collected"
        match = KrossMatch(
            sku=matched_sku,
            status=status,
            pimbo_product_id=pimbo.product_id,
            pimbo_product_name=pimbo.product_name,
            pimbo_product_url=pimbo.product_url,
            kross_product_name=product.name or kross_name,
            kross_url=kross_url,
            note="; ".join(warnings) if warnings else "KROSS data saved locally",
            variant_skus=pimbo.variant_skus,
            local_folder=str(folder),
        )
        self._write_package(folder, match, product, selected, warnings)
        return match

    def discover(
        self,
        skus: Iterable[str],
        *,
        progress: Callable[[int, int, str], None] | None = None,
        log: Callable[[str], None] | None = None,
    ) -> KrossDiscoveryResult:
        normalized = unique_skus(skus)
        client = self.pimbo_client_factory(self.pimbo_driver)
        matches: list[KrossMatch] = []
        for index, sku in enumerate(normalized, start=1):
            if progress:
                progress(index - 1, len(normalized), f"Finding {sku} in PIMBO")
            try:
                pimbo = client.find_by_variant_sku(sku)
                if pimbo.status != "pimbo_found":
                    matches.append(pimbo)
                    continue
                kross_url, kross_name = self.public_catalog.find_product_url(sku)
                if not kross_url:
                    matches.append(replace(
                        pimbo,
                        status="kross_not_found",
                        note="SKU was found in PIMBO but is not sold on kross.pl",
                    ))
                    continue
                matches.append(replace(
                    pimbo,
                    status="found",
                    kross_product_name=kross_name,
                    kross_url=kross_url,
                    note="Ready to prepare",
                ))
            except Exception as error:
                matches.append(KrossMatch(sku, "error", note=str(error)))
            finally:
                if progress:
                    progress(index, len(normalized), f"Checked {sku}")
        return KrossDiscoveryResult(tuple(matches))

    @staticmethod
    def _description_html(product: KrossProductData) -> str:
        if product.description_html:
            return product.description_html
        if product.name:
            return f"<p>{html.escape(product.name)}</p>"
        raise PimAutomationError("KROSS product has no usable description")

    @staticmethod
    def _pimbo_product_id(url: str) -> str:
        match = re.search(r"/dashboard/products/([^/?#]+)", str(url or ""))
        return match.group(1) if match else ""

    def _open_editor(self, match: KrossMatch) -> PimboProductEditor:
        """Open the target without reloading an already-open partial run."""

        current_url = str(getattr(self.pimbo_driver, "current_url", "") or "")
        current_id = self._pimbo_product_id(current_url)
        target_id = match.pimbo_product_id or self._pimbo_product_id(match.pimbo_product_url)
        if current_id and current_id == target_id:
            return self.editor_factory(self.pimbo_driver)
        if current_id:
            current_editor = self.editor_factory(self.pimbo_driver)
            if current_editor.is_dirty():
                raise PimAutomationError(
                    "A different PIMBO product has unsaved changes; switch or save it manually first"
                )
        self.pimbo_driver.get(match.pimbo_product_url)
        return self.editor_factory(self.pimbo_driver)

    def upload_and_save(
        self,
        match: KrossMatch,
        output_root: Path | None,
        *,
        options: KrossWorkflowOptions | None = None,
        progress: Callable[[str], None] | None = None,
    ) -> KrossUploadResult:
        """Run any selected KROSS stages, together or independently."""

        if not match.ready:
            raise ValueError(f"SKU {match.sku} is not ready for upload")
        selected = options or KrossWorkflowOptions()
        if not selected.any_selected:
            raise ValueError("Select at least one KROSS workflow stage")
        if selected.needs_output_folder and output_root is None and not match.local_folder:
            raise ValueError("The selected image stages require an output folder")

        completed_stages: list[str] = []
        warnings: list[str] = []

        def add_warning(stage: str, detail: Any) -> None:
            message = f"{stage}: {_clean(detail)}"
            warnings.append(message)
            if progress:
                progress(f"Warning — {message}")

        product: KrossProductData | None = None
        image_root = Path(match.local_folder) if match.local_folder else (
            Path(output_root) / normalize_sku(match.sku) if output_root is not None else None
        )
        using_local_package = bool(image_root and image_root.is_dir())
        resolved_match = match
        if using_local_package:
            if progress:
                progress(f"Finding PIMBO product by local package SKU {match.sku}")
            pimbo = self.pimbo_client_factory(self.pimbo_driver).find_by_variant_sku(match.sku)
            if pimbo.status != "pimbo_found":
                raise PimAutomationError(
                    pimbo.note or f"SKU {match.sku} was not found in PIMBO"
                )
            resolved_match = replace(
                match,
                pimbo_product_id=pimbo.pimbo_product_id,
                pimbo_product_name=pimbo.pimbo_product_name or match.pimbo_product_name,
                pimbo_product_url=pimbo.pimbo_product_url,
            )
            if progress:
                progress(
                    "Verified PIMBO product — "
                    f"{resolved_match.pimbo_product_name or resolved_match.pimbo_product_id}"
                )
            try:
                _saved_match, product = self._read_package(image_root)
            except Exception as error:
                raise PimAutomationError(f"Could not read local KROSS package: {error}") from error
        elif selected.needs_catalogue:
            if progress:
                progress(f"Reading KROSS source data for {match.sku}")
            product = self.public_catalog.fetch_product(match.kross_url)

        photo_paths: tuple[Path, ...] = ()
        if selected.product_photos:
            if using_local_package:
                if progress:
                    progress(f"Loading local KROSS product photos for {match.sku}")
                local_photo_candidates = tuple(sorted(
                    path
                    for path in image_root.iterdir()
                    if path.is_file()
                    and path.suffix.casefold() in IMAGE_SUFFIXES
                    and path.name.casefold() not in {
                        "dimensions-table.png", "size-height-table.png",
                    }
                ))
                photo_paths = tuple(
                    path for path in local_photo_candidates
                    if self._local_product_photo_is_uploadable(path)
                )
                skipped_thumbnails = len(local_photo_candidates) - len(photo_paths)
                if skipped_thumbnails and progress:
                    progress(
                        f"Ignored {skipped_thumbnails} thumbnail-sized local KROSS photo(s)"
                    )
            else:
                if progress:
                    progress(f"Downloading KROSS product photos for {match.sku}")
                photo_paths = self.public_catalog.download_images(
                    product,
                    image_root,
                    log=progress,
                )
            if not photo_paths:
                add_warning(
                    "Product photos",
                    f"No product photos were found in {image_root}"
                    if using_local_package
                    else "No KROSS product photos could be downloaded",
                )

        dimensions_image: Path | None = None
        size_chart_image: Path | None = None
        if selected.size_tables or selected.geometry:
            if using_local_package:
                if selected.geometry:
                    candidate = image_root / "dimensions-table.png"
                    dimensions_image = candidate if candidate.is_file() else None
                if selected.size_tables:
                    size_candidate = image_root / "size-height-table.png"
                    size_chart_image = size_candidate if size_candidate.is_file() else None
                if progress:
                    progress(f"Loading selected local KROSS table images for {match.sku}")
            else:
                if progress:
                    progress(f"Capturing the full KROSS dimensions table for {match.sku}")
                captured_dimensions = self.public_catalog.capture_dimensions(
                    product,
                    image_root / "dimensions-table.png",
                    log=progress,
                )
                if selected.geometry:
                    dimensions_image = captured_dimensions
                if selected.size_tables:
                    size_candidate = image_root / "size-height-table.png"
                    size_chart_image = size_candidate if size_candidate.is_file() else None
            if selected.geometry and dimensions_image is None:
                add_warning("Geometry", f"No dimensions table was found in {image_root}")
            if selected.size_tables and size_chart_image is None:
                add_warning("Size tables", f"No SIZE/HEIGHT table was found in {image_root}")
        table_paths = tuple(
            path for path in (dimensions_image, size_chart_image) if path is not None
        )
        downloaded_image_paths = photo_paths + table_paths

        if using_local_package and progress:
            progress(
                "Local package preflight — "
                f"photos: {len(photo_paths)}; "
                f"Geometry: {'yes' if dimensions_image else 'no'}; "
                f"Size tables: {'yes' if size_chart_image else 'no'}; "
                f"description: {len(product.description_html) if product else 0} chars; "
                f"specifications: {len(product.specification_text) if product else 0} chars"
            )

        if progress:
            progress("Preparing the verified PIMBO Draft product")
        editor = self._open_editor(resolved_match)
        base = editor.begin("")
        base = replace(base, product_code=resolved_match.sku)
        if base.status == PimPreparationStatus.BLOCKED_NON_DRAFT:
            return KrossUploadResult(
                match=resolved_match,
                preparation=base,
                downloaded_images=downloaded_image_paths,
                product=product,
                dimensions_image=dimensions_image,
                size_chart_image=size_chart_image,
                options=selected,
                completed_stages=tuple(completed_stages),
            )

        changed_fields: list[str] = []
        ai_steps: list[PimAiStepResult] = []
        family_ready: bool | None = None
        description_ready: bool | None = None
        unsafe_phase_one = False
        specification_source = (
            product.specification_text
            if selected.specifications_magic_ai and product
            else ""
        )
        if selected.specifications_magic_ai and not specification_source:
            add_warning(
                "Specifications MagicAI",
                f"{KROSS_METADATA_NAME} has no saved KROSS specifications",
            )

        def ordered_completed_stages() -> tuple[str, ...]:
            return tuple(
                stage for stage in KrossWorkflowOptions.STAGES
                if stage in completed_stages
            )

        def normalize_preparation(preparation: PimPreparationResult) -> PimPreparationResult:
            if (
                preparation.status == PimPreparationStatus.FAILED
                and preparation.error == "PIMBO form has no reviewable unsaved changes"
            ):
                return replace(
                    preparation,
                    status=PimPreparationStatus.NO_CHANGES,
                    error="",
                    warnings=tuple(warnings),
                )
            return replace(preparation, warnings=tuple(warnings))

        def make_result(preparation: PimPreparationResult) -> KrossUploadResult:
            return KrossUploadResult(
                match=resolved_match,
                preparation=preparation,
                downloaded_images=downloaded_image_paths,
                product=product,
                dimensions_image=dimensions_image,
                size_chart_image=size_chart_image,
                options=selected,
                completed_stages=ordered_completed_stages(),
            )

        # Phase 1 follows the operator workflow exactly: ordinary photos,
        # Size tables, Geometry, description, family, brand, category, Save.
        if photo_paths:
            try:
                uploaded_photo_count = 0
                total_photos = len(photo_paths)
                batches = tuple(
                    photo_paths[index:index + PRODUCT_PHOTO_UPLOAD_BATCH_SIZE]
                    for index in range(0, total_photos, PRODUCT_PHOTO_UPLOAD_BATCH_SIZE)
                )
                for batch_index, batch in enumerate(batches):
                    first = batch_index * PRODUCT_PHOTO_UPLOAD_BATCH_SIZE + 1
                    last = first + len(batch) - 1
                    if progress:
                        progress(
                            f"Uploading KROSS product photos {first}–{last} of {total_photos}"
                        )
                    uploaded_photo_count += editor.upload_product_images(
                        batch,
                        skip_if_present=False,
                    )
                    if batch_index < len(batches) - 1:
                        if progress:
                            progress("Waiting for PIMBO to register the photo batch")
                        time.sleep(PRODUCT_PHOTO_UPLOAD_BATCH_PAUSE_SECONDS)
                if uploaded_photo_count:
                    changed_fields.append("images")
                completed_stages.append("product_photos")
            except Exception as error:
                add_warning("Product photos", error)

        if size_chart_image is not None:
            try:
                if progress:
                    progress("Uploading the KROSS SIZE/HEIGHT crop to Size tables")
                if editor.upload_size_table_images(
                    (size_chart_image,), skip_if_present=False
                ):
                    changed_fields.append("size_table_images")
                completed_stages.append("size_tables")
            except Exception as error:
                add_warning("Size tables", error)
        if dimensions_image is not None:
            try:
                if progress:
                    progress("Uploading the full KROSS table to Geometry")
                if editor.upload_geometry_images(
                    (dimensions_image,), skip_if_present=False
                ):
                    changed_fields.append("geometry_images")
                completed_stages.append("geometry")
            except Exception as error:
                add_warning("Geometry", error)

        if selected.description_source:
            if not product or not product.description_html:
                description_ready = False
                add_warning(
                    "Description source",
                    f"{KROSS_METADATA_NAME} has no saved KROSS description",
                )
            else:
                try:
                    if progress:
                        progress("Pasting and verifying the KROSS source description")
                    if editor.set_description_html(self._description_html(product)):
                        changed_fields.append("description_lt_source")
                    description_ready = True
                    completed_stages.append("description_source")
                except Exception as error:
                    description_ready = False
                    add_warning("Description source", error)
        if selected.description_magic_ai:
            if description_ready is False:
                unsafe_phase_one = True
                add_warning(
                    "Description MagicAI",
                    "Skipped because the KROSS description was not pasted successfully",
                )
            else:
                try:
                    if progress:
                        progress("Running MagicAI for the verified non-empty description")
                    description_step = editor.generate_description()
                    ai_steps.append(description_step)
                    if progress and description_step.detail:
                        progress(description_step.detail)
                    completed_stages.append("description_magic_ai")
                except Exception as error:
                    unsafe_phase_one = True
                    add_warning("Description MagicAI", error)

        if selected.product_family:
            try:
                if progress:
                    progress("Setting and verifying product family Dviračiai")
                if editor.ensure_product_family("Dviračiai"):
                    changed_fields.append("product_family")
                completed_stages.append("product_family")
                family_ready = True
            except Exception as error:
                family_ready = False
                if selected.save:
                    unsafe_phase_one = True
                add_warning("Product family", error)
        if selected.brand:
            try:
                if progress:
                    progress("Setting brand to KROSS")
                if editor.set_brand("KROSS"):
                    changed_fields.append("brand")
                completed_stages.append("brand")
            except Exception as error:
                if selected.save:
                    unsafe_phase_one = True
                add_warning("Brand", error)
        if selected.category_magic_ai:
            try:
                if family_ready is False:
                    raise PimAutomationError(
                        "Product family Dviračiai could not be prepared"
                    )
                if not selected.product_family:
                    current_family = editor.product_family()
                    if current_family.casefold() != "dviračiai".casefold():
                        raise PimAutomationError(
                            f"Product family is {current_family or 'empty'}, expected Dviračiai"
                        )
                if progress:
                    progress("Running MagicAI for the Dviračiai category")
                category_step = editor.suggest_category("Dviračiai")
                ai_steps.append(category_step)
                if progress and category_step.detail:
                    progress(f"Category selected — {category_step.detail}")
                completed_stages.append("category_magic_ai")
            except Exception as error:
                unsafe_phase_one = True
                add_warning("Category MagicAI", error)

        # Translation remains independently selectable, but validation never
        # opens or reads SEO. It belongs to the first persisted phase.
        if selected.translations:
            try:
                if progress:
                    progress("Checking the Lithuanian product name before translation")
                if editor.ensure_lithuanian_name_from_english():
                    changed_fields.append("product_name_lt_from_en")
                    if progress:
                        progress(
                            "Lithuanian name was empty — copied the English name as the translation source"
                        )
                if progress:
                    progress(
                        "Translating product copy with overwrite existing translations enabled"
                    )
                ai_steps.append(editor.translate_lt_to_all(overwrite=True))
                completed_stages.append("translations")
            except Exception as error:
                unsafe_phase_one = True
                add_warning("Translations", error)

        # Specifications can be run independently only when the product already
        # has the Dviračiai family. In a full run, the family selected above is
        # persisted by the first Save before the Specifications panel is opened.
        if (
            selected.specifications_magic_ai
            and specification_source
            and family_ready is None
        ):
            try:
                current_family = editor.product_family()
                family_ready = current_family.casefold() == "dviračiai".casefold()
                if not family_ready:
                    add_warning(
                        "Specifications MagicAI",
                        f"Product family is {current_family or 'empty'}, expected Dviračiai",
                    )
                    if selected.save:
                        unsafe_phase_one = True
            except Exception as error:
                family_ready = False
                add_warning("Specifications MagicAI family check", error)
                if selected.save:
                    unsafe_phase_one = True

        # A specifications-only partial run may intentionally remain unsaved.
        # In a full run, specifications are deferred until after the first Save
        # so the Dviračiai family schema is present.
        if (
            selected.specifications_magic_ai
            and specification_source
            and family_ready is not False
            and not selected.save
        ):
            try:
                if progress:
                    progress("Opening Specifications and running MagicAI")
                specification_step = editor.fill_empty_specifications_with_ai(
                    specification_source
                )
                ai_steps.append(specification_step)
                if specification_step.changed:
                    changed_fields.append("specifications")
                completed_stages.append("specifications_magic_ai")
            except Exception as error:
                add_warning("Specifications MagicAI", error)

        if any(stage in completed_stages for stage in (
            "description_source",
            "description_magic_ai",
            "category_magic_ai",
            "translations",
        )):
            try:
                editor.switch_locale("lt")
            except Exception as error:
                add_warning("Return to LT locale", error)

        prepared = normalize_preparation(editor.finish(
            base,
            changed_fields=changed_fields,
            ai_steps=ai_steps,
            warnings=warnings,
        ))
        if not selected.save:
            return make_result(prepared)
        if unsafe_phase_one:
            prepared = replace(
                prepared,
                status=PimPreparationStatus.FAILED,
                warnings=tuple(warnings),
                error=(
                    "Automatic Save was blocked because a MagicAI stage failed; "
                    "the product was left unsaved"
                ),
            )
            return make_result(prepared)
        if prepared.status == PimPreparationStatus.READY_FOR_REVIEW:
            if progress:
                progress("Saving photos, tables, description, family, brand, and category")
            try:
                prepared = normalize_preparation(editor.save_and_verify(prepared))
            except Exception as error:
                add_warning("First save", error)
                prepared = replace(
                    prepared,
                    status=PimPreparationStatus.FAILED,
                    warnings=tuple(warnings),
                    error=f"First save: {_clean(error)}",
                )
            if prepared.status == PimPreparationStatus.SAVED_AUTOMATICALLY:
                completed_stages.append("save")
        if prepared.status not in {
            PimPreparationStatus.SAVED_AUTOMATICALLY,
            PimPreparationStatus.NO_CHANGES,
        }:
            return make_result(prepared)

        # Phase 2: after the first Save, wait for PIMBO to rebuild the family
        # schema, then open Specifications, run MagicAI, and Save again.
        if selected.specifications_magic_ai and specification_source:
            if prepared.status == PimPreparationStatus.SAVED_AUTOMATICALLY:
                if progress:
                    progress("Waiting 1 second for the Dviračiai specification schema")
                time.sleep(1.0)
            if progress:
                progress("Opening Specifications after Save")
            specifications_base = replace(
                editor.begin(""), product_code=resolved_match.sku
            )
            if specifications_base.status == PimPreparationStatus.BLOCKED_NON_DRAFT:
                return make_result(specifications_base)
            specification_ai_steps: list[PimAiStepResult] = []
            specification_changes: list[str] = []
            try:
                if progress:
                    progress("Running MagicAI for Specifications")
                specification_step = editor.fill_empty_specifications_with_ai(
                    specification_source
                )
                specification_ai_steps.append(specification_step)
                if specification_step.changed:
                    specification_changes.append("specifications")
                completed_stages.append("specifications_magic_ai")
            except Exception as error:
                add_warning("Specifications MagicAI", error)
                return make_result(replace(prepared, warnings=tuple(warnings)))

            specifications_prepared = normalize_preparation(editor.finish(
                specifications_base,
                changed_fields=specification_changes,
                ai_steps=specification_ai_steps,
                warnings=warnings,
            ))
            if specifications_prepared.status == PimPreparationStatus.READY_FOR_REVIEW:
                if progress:
                    progress("Saving MagicAI specifications")
                try:
                    specifications_prepared = normalize_preparation(
                        editor.save_and_verify(specifications_prepared)
                    )
                except Exception as error:
                    add_warning("Specifications save", error)
                    specifications_prepared = replace(
                        specifications_prepared,
                        status=PimPreparationStatus.FAILED,
                        warnings=tuple(warnings),
                        error=f"Specifications save: {_clean(error)}",
                    )
            combined_status = specifications_prepared.status
            if (
                combined_status == PimPreparationStatus.NO_CHANGES
                and prepared.status == PimPreparationStatus.SAVED_AUTOMATICALLY
            ):
                combined_status = prepared.status
            prepared = replace(
                specifications_prepared,
                product_code=resolved_match.sku,
                initial_version=base.initial_version,
                initial_fields=base.initial_fields,
                status=combined_status,
                changed_fields=tuple(dict.fromkeys(
                    (*prepared.changed_fields, *specifications_prepared.changed_fields)
                )),
                ai_steps=tuple((*prepared.ai_steps, *specifications_prepared.ai_steps)),
                warnings=tuple(warnings),
            )
            if prepared.status == PimPreparationStatus.SAVED_AUTOMATICALLY:
                completed_stages.append("save")

        if progress:
            progress(
                "Completed stages — "
                f"{', '.join(ordered_completed_stages()) or 'none'}; "
                f"warnings: {len(warnings)}"
            )
        return make_result(prepared)
