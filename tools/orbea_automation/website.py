"""Read the public Orbea site in an owned browser, independently of Pimbo."""
from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass, replace
from typing import Any, Callable
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import ElementClickInterceptedException, TimeoutException, WebDriverException

from .catalogue import CatalogueEntry, MatchResult, model_key, normalize_code
from .component_values import normalize_component_specifications
from .features import feature_description_html, read_feature_description
from .models import RunCancelled
from .photos import _json_assignment, normalize_orbea_product_url

SPECIFICATIONS_CAPTURE_VERSION = 2
WEBSITE_LOOKUP_VERSION = 2


def template_code(sku: str) -> str:
    """Orbea model reference + TTCC, with size/colour removed from a variant."""
    code = normalize_code(sku)
    if re.fullmatch(r"[A-Z][A-Z0-9]{3}(?:[A-Z0-9]{4})?", code) and any(c.isdigit() for c in code[:4]):
        return code[:4] + "TTCC"
    return ""


@dataclass(frozen=True)
class SearchProduct:
    code: str
    name: str
    url: str


def parse_region_homes(page_html: str, url: str) -> tuple[str, ...]:
    """Discover every advertised country/language site, including International."""
    soup = BeautifulSoup(page_html, "html.parser")
    _check_access(soup)
    regions = []
    for anchor in soup.select('#zone-lang-show-all a[href]'):
        parts = urlsplit(urljoin(url, anchor['href']))
        if parts.scheme != "https" or parts.hostname != "www.orbea.com" or not re.fullmatch(r"/[a-z]{2}-(?:[a-z]{2}|int)/?", parts.path):
            continue
        home = f"https://www.orbea.com{parts.path.rstrip('/')}/"
        if home not in regions:
            regions.append(home)
    # Try the local, international and major English shops first. This only
    # orders discovered links; it never substitutes a fixed coverage list.
    preferred = ('en-be', 'en-lt', 'en-int', 'en-au', 'en-gb', 'en-us')
    def priority(home):
        locale = urlsplit(home).path.strip('/')
        return preferred.index(locale) if locale in preferred else len(preferred) + (not locale.startswith('en-'))
    return tuple(sorted(regions, key=priority))


def parse_search_popup(page_html: str, url: str) -> tuple[SearchProduct, ...] | None:
    """Read code and link from the same rendered autocomplete row."""
    soup = BeautifulSoup(page_html, "html.parser")
    _check_access(soup)
    form = soup.select_one('form[role="search"]')
    if form is None:
        return None
    scope = form.select_one('[x-ref="searchScrollable"]')
    waiting = form.select_one('[x-show="waiting"]')
    if scope is None or waiting is None or 'display:none' not in str(waiting.get('style', '')).replace(' ', ''):
        return None
    if 'display:none' in str(scope.get('style', '')).replace(' ', ''):
        return None
    results = []
    for anchor in scope.select('a[href]'):
        model = anchor.select_one('[x-text="result.model"]')
        name = anchor.select_one('[x-text="result.name"]')
        if model is None:
            continue
        code = normalize_code(model.get_text(strip=True))
        if not re.fullmatch(r'[A-Z][A-Z0-9]{3}TTCC', code):
            continue
        try:
            link = normalize_orbea_product_url(urljoin(url, anchor['href']))
        except ValueError:
            continue
        results.append(SearchProduct(code, name.get_text(' ', strip=True) if name else '', link))
    empty = form.select_one('[x-show="!waiting && total === 0"]')
    if results:
        return tuple(results)
    if empty is not None and 'display:none' not in str(empty.get('style', '')).replace(' ', ''):
        return ()
    return None


@dataclass(frozen=True)
class WebsiteProduct:
    url: str
    name: str
    codes: tuple[str, ...]
    description_html: str
    specifications_text: str
    page_html: str
    description_error: str = ""
    description_source: str = "page"
    specifications_error: str = ""
    specifications_source: str = "legacy_components"


class OrbeaAccessError(RuntimeError):
    """The public site returned an access check instead of a product page."""


def _check_access(soup: BeautifulSoup) -> None:
    heading = soup.find("h1")
    name = heading.get_text(" ", strip=True).casefold() if heading else ""
    title = soup.title.get_text(" ", strip=True).casefold() if soup.title else ""
    text = soup.get_text(" ", strip=True).casefold()
    if name in {"www.orbea.com", "orbea.com", "just a moment...", "access denied"} or (
        not soup.select_one("#product-bike-detail")
        and (title in {"just a moment...", "access denied"}
             or any(value in text for value in ("verify you are human", "checking your browser", "enable javascript and cookies", "performing security verification")))
    ):
        raise OrbeaAccessError("Orbea still requires a website security check. Scanned codes, completed downloads and the partial Excel are saved. Choose Resume interrupted collection and complete any check in the Orbea browser window; collection will continue automatically when the shop opens.")


def _product_objects(value: Any):
    if isinstance(value, list):
        for item in value:
            yield from _product_objects(item)
    elif isinstance(value, dict):
        kinds = value.get("@type", [])
        if "Product" in ([kinds] if isinstance(kinds, str) else kinds or []):
            yield value
        yield from _product_objects(value.get("@graph", []))


COMPONENT_LABELS = frozenset((
    "frame", "fork", "shock", "rear shock", "crankset", "crank", "headset", "handlebar", "stem", "shifters",
    "brakes", "front brake", "rear brake", "front derailleur", "rear derailleur", "cassette", "chain", "wheels",
    "tyres", "tires", "saddle", "seatpost", "grips", "bar tape", "bottom bracket", "pedals", "motor", "battery",
    "display", "charger", "wheel size", "weight", "cuadro", "horquilla", "amortiguador", "bielas", "dirección",
    "manillar", "potencia", "manetas", "frenos", "desviador", "cambio", "cadena", "ruedas", "cubiertas",
    "sillín", "tija sillín", "tija", "cinta", "pedales", "batería", "peso",
))


STANDARD_CONFIGURATION = "#standard-configuration-dialog"
STANDARD_CONFIGURATION_BUTTON = 'button[aria-controls="standard-configuration-dialog"]'


def standard_configuration_rows(soup):
    """Read the published articles, including text directly after their h3."""
    dialog = soup.select_one(STANDARD_CONFIGURATION)
    if dialog is None:
        return ()
    rows = {}
    for article in dialog.select("article"):
        heading = article.find("h3")
        if heading is None:
            continue
        label = heading.get_text(" ", strip=True)
        if not label:
            continue
        content = BeautifulSoup(str(article), "html.parser")
        for unwanted in content.select("h3, button, script, style, svg, template"):
            unwanted.decompose()
        value = content.get_text(" ", strip=True)
        value = re.sub(r"\s+", " ", value).strip()
        if value:
            key = label.casefold()
            name, values = rows.setdefault(key, (label, []))
            if value not in values:
                values.append(value)
    # Published front/rear tyre entries can share a heading. Keep every value
    # instead of interpreting the second fitted component as a variant choice.
    return tuple(f"{name}: {'; '.join(values)}" for name, values in rows.values())


def component_specification_rows(soup):
    """Read heading, definition-list, table, and paired-label component layouts."""
    standard = standard_configuration_rows(soup)
    if standard or soup.select_one(STANDARD_CONFIGURATION):
        return standard
    containers = soup.select('[id*="specification"], [id*="component"], [class*="specification"], [data-section="specifications"]')
    main = soup.select_one('#product-bike-detail[x-init]') or soup.select_one("#product-bike-detail") or soup.find("main")
    if main:
        containers.append(main)
    rows = []
    for container in containers:
        for label in container.find_all(["h3", "h4", "dt", "p", "span", "label"]):
            if label.find_parent(["nav", "header", "footer", "form", "template"]) or label.find(["p", "span", "h3", "dt"]):
                continue
            if any(str(parent.get("id", "")).startswith(("sidebar-", "component-", "components-base")) for parent in label.parents):
                continue
            name = label.get_text(" ", strip=True)
            known = name.casefold() in COMPONENT_LABELS
            if not known and (container is main or label.name not in {"h3", "h4", "dt"}):
                continue
            value = label.find_next_sibling()
            if value is None and known and label.parent and len(label.parent.find_all(recursive=False)) == 1:
                value = label.parent.find_next_sibling()
            if value and value.name not in {"h2", "h3", "h4", "dt", "button", "select", "input"} and not value.find(["h3", "h4", "dt"]):
                text = value.get_text(" ", strip=True)
                if text and text.casefold() not in COMPONENT_LABELS:
                    rows.append(f"{name}: {text}")
        for row in container.select("tr"):
            if row.find_parent("template") or any(str(parent.get("id", "")).startswith(("sidebar-", "component-")) for parent in row.parents):
                continue
            cells = row.find_all(["th", "td"], recursive=False)
            if len(cells) == 2 and (container is not main or cells[0].get_text(" ", strip=True).casefold() in COMPONENT_LABELS):
                rows.append(": ".join(cell.get_text(" ", strip=True) for cell in cells))
    return tuple(normalize_component_specifications("\n".join(rows)).splitlines())


def read_component_dialog(driver, *, timeout, check):
    """Open a component/specification dialog when its rows are loaded on demand."""
    buttons = driver.find_elements(By.CSS_SELECTOR, STANDARD_CONFIGURATION_BUTTON)
    if not buttons:
        buttons = driver.find_elements(By.CSS_SELECTOR, 'button[aria-controls*="component"], button[aria-controls*="specification"]')
    button = next((item for item in buttons if item.is_displayed() and item.is_enabled()), None)
    if button is None:
        return None
    dialog_id = str(button.get_attribute("aria-controls") or "")
    if not re.fullmatch(r"[A-Za-z][\w-]*", dialog_id):
        return None
    def loaded(_driver):
        check()
        dialogs = driver.find_elements(By.CSS_SELECTOR, f'#{dialog_id}')
        visible = next((item for item in dialogs if item.is_displayed()), None)
        if visible is None:
            return False
        rows = component_specification_rows(BeautifulSoup(visible.get_attribute("outerHTML") or "", "html.parser"))
        return "\n".join(rows) if rows else False
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", button)
        try:
            button.click()
        except ElementClickInterceptedException:
            driver.execute_script("arguments[0].click();", button)
        return WebDriverWait(driver, timeout).until(loaded, message="The Orbea component specifications did not load")
    finally:
        try:
            closes = driver.find_elements(By.CSS_SELECTOR, f'#{dialog_id} button[\\@click*="close-dialog"], #{dialog_id} button[aria-label="Close"]')
            close = next((item for item in closes if item.is_displayed()), None)
            if close:
                close.click()
            else:
                driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
        except WebDriverException:
            pass


def parse_website_product(page_html: str, url: str) -> WebsiteProduct:
    """Use product-scoped identifiers, never a search echo or navigation code."""
    url = normalize_orbea_product_url(url)
    soup = BeautifulSoup(page_html, "html.parser")
    _check_access(soup)
    heading = soup.find("h1")
    name = heading.get_text(" ", strip=True) if heading else ""
    codes: list[str] = []
    descriptions: list[str] = []
    specifications: list[str] = []

    def add_code(value: Any) -> None:
        code = normalize_code(value)
        if re.fullmatch(r"[A-Z][A-Z0-9]{3,}", code) and any(c.isdigit() for c in code) and code not in codes:
            codes.append(code)

    for script in soup.select('script[type="application/ld+json"]'):
        try:
            objects = list(_product_objects(json.loads(script.string or script.get_text())))
        except (ValueError, TypeError):
            continue
        for product in objects:
            # A recommendation widget can contain other Product objects.
            if name and model_key(product.get("name")) != model_key(name):
                continue
            name = name or str(product.get("name") or "")
            for key in ("sku", "mpn", "productID"):
                add_code(product.get(key))
            if product.get("description"):
                descriptions.append(BeautifulSoup(str(product["description"]), "html.parser").get_text(" ", strip=True))
            properties = product.get("additionalProperty") or []
            if isinstance(properties, dict):
                properties = [properties]
            for item in properties:
                if isinstance(item, dict) and item.get("name") and item.get("value"):
                    specifications.append(f"{item['name']}: {item['value']}")

    root = soup.select_one('#product-bike-detail[x-init]') or soup.select_one("#product-bike-detail")
    if root:
        for node in [root, *root.select('[itemprop="sku"], [data-sku], [data-product-code]')]:
            for key in ("data-sku", "data-product-code", "content"):
                add_code(node.get(key))
            if node.get("itemprop") == "sku":
                add_code(node.get_text(" ", strip=True))
        initializer = str(root.get("x-init") or "")
        selected_code = re.search(r'''(?:^|;)\s*code\s*=\s*(['"])([A-Z][A-Z0-9]{3,})\1\s*;''', initializer)
        if selected_code:
            add_code(selected_code[2])
        template = _json_assignment(initializer, "currentTemplate")
        if not isinstance(template, dict):
            templates = _json_assignment(initializer, "templates")
            selected = re.search(r"\btemplate\s*=\s*(\d+)\s*;", initializer)
            if selected and isinstance(templates, list):
                template = next((item for item in templates if isinstance(item, dict) and str(item.get("id")) == selected[1]), None)
        if isinstance(template, dict):
            for key in ("sku", "code", "reference", "identifier", "model_code", "product_code"):
                add_code(template.get(key))

    main = soup.find("main") or soup.body or soup
    # Keep component sections out of the legacy paragraph description fallback.
    containers = main.select('[id*="specification"], [id*="component"], [class*="specification"], [data-section="specifications"]')
    if not containers:
        for h in main.find_all(["h2", "h3"]):
            if h.get_text(" ", strip=True).casefold() in {"components", "specifications", "frameset", "drivetrain"}:
                container = h.find_parent("section")
                if container and container not in containers:
                    containers.append(container)
    standard_rows = standard_configuration_rows(soup)
    if standard_rows or soup.select_one(STANDARD_CONFIGURATION_BUTTON):
        specifications = list(standard_rows)
    else:
        specifications.extend(component_specification_rows(soup))

    if not descriptions and not soup.select_one(STANDARD_CONFIGURATION_BUTTON):
        for paragraph in main.find_all("p"):
            if paragraph.find_parent(["nav", "footer", "header", "form", "table"]) or any(parent in containers for parent in paragraph.parents):
                continue
            text = paragraph.get_text(" ", strip=True)
            if len(text) >= 40 and not paragraph.find("input"):
                descriptions.append(text)
    if not name:
        raise ValueError("The Orbea page has no product heading; it may be unavailable or blocked")
    feature_html = feature_description_html(page_html)
    return WebsiteProduct(
        url=url, name=name, codes=tuple(codes),
        description_html=feature_html or "\n".join(f"<p>{html.escape(text)}</p>" for text in dict.fromkeys(descriptions)),
        specifications_text=normalize_component_specifications("\n".join(specifications)), page_html=page_html,
        description_source="feature_dialog" if feature_html else "page",
        specifications_source="standard_configuration" if standard_rows else "legacy_components",
    )


def product_matches(product: WebsiteProduct, sku: str, title: str) -> bool:
    expected = template_code(sku)
    return bool(expected and any(template_code(value) == expected for value in product.codes))


def website_code_match(product: WebsiteProduct, sku: str, title: str) -> MatchResult | None:
    """Confirm the published product code before trusting a candidate link."""
    if not product_matches(product, sku, title):
        return None
    code = normalize_code(sku)
    template = template_code(sku)
    entry = CatalogueEntry(prefix=template[:-4] if template.endswith("TTCC") else code,
                           template_code=template, model=product.name, product_link=product.url)
    return MatchResult("code_match", "Orbea website code", entry)


class OrbeaWebsiteClient:
    HOME = "https://www.orbea.com/en-be/"

    def __init__(self, driver_factory: Callable[[], Any], cancellation: Any, timeout: float = 25, *, access_timeout: float = 300):
        self.driver_factory = driver_factory
        self.cancellation = cancellation
        self.timeout = timeout
        self.access_timeout = access_timeout
        self.access_progress: Callable[[bool, str], None] | None = None
        self.collect_description = True
        self.collect_specifications = True
        self._driver = None
        self._products: dict[str, WebsiteProduct] = {}
        self.regions: tuple[str, ...] = ()
        self._matches: dict[str, MatchResult] = {}
        self._searched = False

    def _check(self):
        cancelled = getattr(self.cancellation, "is_cancelled", None) or getattr(self.cancellation, "is_set", None)
        if cancelled and cancelled():
            raise RunCancelled("The Orbea website collection was stopped")

    @property
    def driver(self):
        self._check()
        if self._driver is None:
            self._driver = self.driver_factory()
            self._driver.set_page_load_timeout(self.timeout)
        return self._driver

    def close(self):
        driver, self._driver = self._driver, None
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass

    cancel = close

    def _notify_access(self, waiting: bool, message: str) -> None:
        if self.access_progress is not None:
            try:
                self.access_progress(waiting, message)
            except Exception:
                pass

    def _source(self) -> str:
        self._check()
        try:
            return self.driver.page_source
        except WebDriverException:
            # Stop can close the owned browser while a source read is in flight.
            self._check()
            raise

    def _page_soup(self) -> BeautifulSoup:
        """Wait in the same visible browser while normal verification finishes.

        The user handles any human check. No challenge is clicked or solved.
        """
        self._check()
        soup = BeautifulSoup(self._source(), "html.parser")
        try:
            _check_access(soup)
            return soup
        except OrbeaAccessError as error:
            access_error = error
        self._notify_access(True, "Orbea is checking website access. Complete any verification in the Orbea browser window. Collection will continue automatically; you can also press Stop. Saved work is safe.")

        def accessible(driver):
            self._check()
            current = BeautifulSoup(self._source(), "html.parser")
            try:
                _check_access(current)
            except OrbeaAccessError:
                return False
            # The challenge can briefly disappear into an empty loading page.
            return current if current.select_one('main, #main-content, #product-bike-detail[x-init]') else False

        try:
            soup = WebDriverWait(self.driver, self.access_timeout).until(accessible)
        except TimeoutException:
            self._check()
            raise access_error from None
        self._notify_access(False, "Orbea website access is ready. Continuing collection.")
        return soup

    def _navigate(self, url: str) -> None:
        try:
            self.driver.get(url)
        except TimeoutException:
            # An eager navigation may time out while a check is still running.
            soup = BeautifulSoup(self._source(), "html.parser")
            try:
                _check_access(soup)
            except OrbeaAccessError:
                self._page_soup()
            else:
                raise

    def _read_product_page(self, url: str) -> WebsiteProduct:
        self._navigate(url)
        return self.wait_for_product()

    def wait_for_product(self) -> WebsiteProduct:
        def product_heading(driver):
            self._check()
            self._page_soup()
            return driver.find_elements(By.TAG_NAME, "h1")

        WebDriverWait(self.driver, self.timeout).until(product_heading, message="The Orbea product heading did not load")
        current = normalize_orbea_product_url(self.driver.current_url)
        return parse_website_product(self._source(), current)

    def fetch(self, url: str) -> WebsiteProduct:
        self._check()
        url = normalize_orbea_product_url(url)
        if url not in self._products:
            product = self._read_product_page(url)
            if self.collect_description:
                def check():
                    self._check()
                    self._page_soup()
                try:
                    description = read_feature_description(self.driver, timeout=self.timeout, check=check)
                    if description is not None:
                        product = replace(product, description_html=description,
                            description_source="feature_dialog" if description else "not_available", page_html=self.driver.page_source)
                except (RunCancelled, OrbeaAccessError):
                    raise
                except Exception as error:
                    product = replace(product, description_html="", description_error=f"Features dialog: {type(error).__name__}: {error}")
            if self.collect_specifications and not product.specifications_text:
                def check_components():
                    self._check()
                    self._page_soup()
                try:
                    specifications = read_component_dialog(self.driver, timeout=self.timeout, check=check_components)
                    if specifications is not None:
                        product = replace(product, specifications_text=specifications,
                            specifications_source="standard_configuration" if self.driver.find_elements(By.CSS_SELECTOR, STANDARD_CONFIGURATION_BUTTON) else "legacy_components")
                except (RunCancelled, OrbeaAccessError):
                    raise
                except Exception as error:
                    product = replace(product, specifications_error=f"Components dialog: {type(error).__name__}: {error}")
            self._products[url] = product
        return self._products[url]

    def read_default_custom_photos(self, url, output_dir, *, asset_root=None, log=None):
        from .custom_photos import CustomDesignAlreadySelected, CustomDesignNotReady, capture_default_design, save_default_design
        self._check()
        url = normalize_orbea_product_url(url)
        try:
            current = normalize_orbea_product_url(self.driver.current_url)
        except ValueError:
            current = ''
        if current != url:
            self._read_product_page(url)
        def check():
            self._check()
            self._page_soup()
        try:
            snapshot = capture_default_design(self.driver, timeout=self.timeout, check=check)
        except (CustomDesignAlreadySelected, CustomDesignNotReady):
            # Restore canonical defaults and retry a stalled page once. A
            # reload also removes any prior interactive paint changes.
            self._read_product_page(url)
            snapshot = capture_default_design(self.driver, timeout=self.timeout, check=check, allow_selected_default=True)
        return save_default_design(snapshot, output_dir, asset_root=asset_root, log=log, check=self._check)

    def discover_regions(self) -> tuple[str, ...]:
        if not self.regions:
            self._navigate(self.HOME)

            def regions_ready(driver):
                soup = self._page_soup()
                return parse_region_homes(str(soup), driver.current_url) or False

            regions = WebDriverWait(self.driver, self.timeout).until(
                regions_ready, message="Orbea's country/language list did not load; regional coverage cannot be confirmed")
            self.regions = (self.HOME, *[home for home in regions if home != self.HOME])
        return self.regions

    def _search_results(self, query: str, home: str) -> tuple[SearchProduct, ...]:
        """Use autocomplete only; no candidate product pages or feature dialogs."""
        if query != template_code(query):
            raise ValueError("Orbea searches must use a model code ending in TTCC")
        # A fresh document prevents a previous query's delayed results being
        # mistaken for this query. Region discovery supplies the first home.
        if self._searched or self.driver.current_url.rstrip('/') != home.rstrip('/'):
            self._navigate(home)
        self._searched = True

        def search_ready(driver):
            self._page_soup()
            fields = driver.find_elements(By.CSS_SELECTOR, 'form[role="search"] input[name="query"]')
            if not fields:
                return False
            for close in driver.find_elements(By.CSS_SELECTOR, 'dialog[open] button[x-on\\:click*="closeDialog"], dialog[open] button[title="Close"]'):
                if close.is_displayed():
                    close.click()
            field = fields[0]
            if not field.is_displayed():
                buttons = driver.find_elements(By.CSS_SELECTOR, 'button[\\@click*="toggle-form"]')
                button = next((item for item in buttons if item.is_displayed()), None)
                if button is None:
                    return False
                try:
                    button.click()
                except ElementClickInterceptedException:
                    driver.execute_script("arguments[0].click();", button)
            return field if field.is_displayed() else False

        field = WebDriverWait(self.driver, self.timeout).until(search_ready, message="The Orbea search popup did not open")
        field.clear()
        field.send_keys(query)

        def results_ready(driver):
            soup = self._page_soup()
            result = parse_search_popup(str(soup), driver.current_url)
            # An empty tuple is a completed search, not a waiting signal.
            return {"results": result} if result is not None else False

        return WebDriverWait(self.driver, self.timeout, poll_frequency=0.1).until(
            results_ready, message=f"Orbea search results for {query} did not load")['results']

    def lookup(self, sku: str, title: str = "") -> MatchResult:
        query = template_code(sku)
        if not query:
            return MatchResult("unmatched", "Orbea TTCC search", None, "The Pimbo SKU is not a recognised Orbea model/variant code")
        if query in self._matches:
            return self._matches[query]
        errors = []
        for home in self.discover_regions():
            self._check()
            try:
                results = self._search_results(query, home)
            except (RunCancelled, OrbeaAccessError):
                raise
            except Exception as error:
                errors.append(f"{home}: {type(error).__name__}: {error}")
                continue
            # Search can include fuzzy matches. Only the first exact code row
            # qualifies; product titles and URL slugs have no matching role.
            result = next((item for item in results if item.code == query), None)
            if result is not None:
                entry = CatalogueEntry(query[:-4], query, result.name, product_link=result.url)
                match = MatchResult("code_match", "Orbea TTCC search", entry)
                self._matches[query] = match
                return match
        if errors:
            raise RuntimeError("Regional lookup is incomplete: " + " | ".join(errors)[:1800])
        match = MatchResult("unmatched", "Orbea TTCC search", None,
                            f"No exact {query} result in {len(self.regions)} Orbea country/language sites")
        self._matches[query] = match
        return match
