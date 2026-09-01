from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import call, patch

from Managers.PimboProductEditor import (
    PIMBO_PRODUCTS_URL,
    PimAiStepResult,
    PimPreparationResult,
    PimPreparationStatus,
)
from tools.kross_automation import (
    KrossAutomationService,
    KrossCollectionOptions,
    KrossMatch,
    KrossPimboProduct,
    KrossProductData,
    KrossWorkflowOptions,
    capture_kross_dimensions_table,
    normalize_label,
    normalize_sku,
    parse_collection_targets,
    unique_skus,
)
from tools.kross_automation.dimensions import _validate_capture_metrics
from tools.kross_automation.service import (
    KROSS_DESCRIPTION_NAME,
    KROSS_METADATA_NAME,
    KROSS_SPECIFICATIONS_NAME,
    KrossPimboClient,
    KrossPimboScanner,
    KrossPublicCatalog,
)
from tools.orbea_automation import PimboFilterSpec


class _Response:
    def __init__(self, url: str, text: str = "", content: bytes = b"", content_type: str = "text/html"):
        self.url = url
        self.text = text
        self.content = content or text.encode("utf-8")
        self.headers = {"content-type": content_type}

    def raise_for_status(self):
        return None


class _Session:
    def __init__(self, pages):
        self.pages = pages
        self.headers = {}

    def get(self, url, timeout):
        return self.pages[url]


class _Driver:
    def __init__(self):
        self.visited = []
        self.current_url = ""

    def get(self, url):
        self.visited.append(url)
        self.current_url = url


class _Catalog:
    def __init__(self, product: KrossProductData, image_path: Path):
        self.product = product
        self.image_path = image_path
        self.calls = []

    def fetch_product(self, url):
        self.calls.append(("fetch", url))
        return self.product

    def download_images(self, product, destination, *, log=None):
        self.calls.append(("images", destination))
        if log:
            log("downloaded image")
        return (self.image_path,)

    def capture_dimensions(self, product, destination, *, log=None):
        self.calls.append(("dimensions", destination))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"dimensions")
        destination.with_name("size-height-table.png").write_bytes(b"size chart")
        if log:
            log("captured dimensions")
        return destination


class _Editor:
    def __init__(self):
        self.calls = []

    def begin(self, _product_code):
        self.calls.append("begin")
        return PimPreparationResult(product_code="", product_id="p-1", initial_version=7)

    def set_brand(self, value):
        self.calls.append(f"brand:{value}")
        return True

    def ensure_product_family(self, value):
        self.calls.append(f"family:{value}")
        return True

    def product_family(self):
        self.calls.append("read_family")
        return "Dviračiai"

    def upload_product_images(self, paths, *, skip_if_present):
        self.calls.append(f"product_images:{len(tuple(paths))}")
        return 1

    def upload_geometry_images(self, paths, *, skip_if_present):
        self.calls.append(f"geometry_images:{len(tuple(paths))}")
        return 1

    def upload_size_table_images(self, paths, *, skip_if_present):
        self.calls.append(f"size_table_images:{len(tuple(paths))}")
        return 1

    def set_description_html(self, value):
        self.calls.append(f"description:{bool(value)}")
        return True

    def generate_description(self):
        self.calls.append("description_magic")
        return PimAiStepResult("description", True, True)

    def suggest_category(self, family):
        self.calls.append(f"category:{family}")
        return PimAiStepResult("category", True, True)

    def fill_empty_specifications_with_ai(self, source):
        self.calls.append(f"specs:{source}")
        return PimAiStepResult("specifications", True, True)

    def ensure_lithuanian_name_from_english(self):
        self.calls.append("name_lt_from_en")
        return True

    def translate_lt_to_all(self, *, overwrite):
        self.calls.append(f"translate:{overwrite}")
        return PimAiStepResult("translation", True, True)

    def switch_locale(self, locale):
        self.calls.append(f"locale:{locale}")

    def finish(self, result, **_kwargs):
        self.calls.append("finish")
        return replace(
            result,
            status=PimPreparationStatus.READY_FOR_REVIEW,
            changed_fields=tuple(_kwargs.get("changed_fields") or ()),
            ai_steps=tuple(_kwargs.get("ai_steps") or ()),
            warnings=tuple(_kwargs.get("warnings") or ()),
        )

    def save_and_verify(self, result):
        self.calls.append("save")
        return result.with_status(PimPreparationStatus.SAVED_AUTOMATICALLY)


class KrossAutomationTests(unittest.TestCase):
    def test_filtered_scanner_never_reads_past_confirmed_product_total(self):
        class _Scanner(KrossPimboScanner):
            def __init__(self):
                super().__init__(object())
                self.page = 0
                self.opened = []

            def apply_filters(self, _filters):
                return None

            def _totals(self):
                return 3, 2

            def go_to_page(self, page_number):
                self.page = page_number

            def _wait_for_rows(self, allow_empty=False):
                # Page 2 temporarily exposes both rows from the preceding page,
                # even though only one confirmed product remains.
                return [object(), object()]

            def _open_product(self, row_index):
                self.opened.append((self.page, row_index))
                number = len(self.opened)
                return KrossPimboProduct(
                    product_id=f"p-{number}",
                    product_name=f"Product {number}",
                    product_url=f"https://pim.bo.ultrabike.lt/dashboard/products/p-{number}",
                    visible_code=f"P-{number}",
                    variant_skus=(f"SKU-{number}",),
                )

            def _restore_list(self, _page, _filters):
                return None

        scanner = _Scanner()
        products = scanner.scan_products(PimboFilterSpec())

        self.assertEqual(3, len(products))
        self.assertEqual([(1, 0), (1, 1), (2, 0)], scanner.opened)

    def test_upload_search_click_survives_pimbo_toolbar_overlap(self):
        class _Element:
            def __init__(self):
                self.native_clicks = 0

            def click(self):
                self.native_clicks += 1
                raise RuntimeError("element click intercepted")

        class _ClickDriver:
            def __init__(self):
                self.dom_clicks = 0

            def execute_script(self, script, _element):
                if "arguments[0].click" in script:
                    self.dom_clicks += 1

        driver = _ClickDriver()
        element = _Element()
        clicked = KrossPimboClient(driver)._safe_click(
            lambda: element,
            "covered SKU field",
        )

        self.assertIs(element, clicked)
        self.assertEqual(1, element.native_clicks)
        self.assertEqual(1, driver.dom_clicks)

    def _match(self, product_url="https://kross.pl/rowery/example-bike"):
        return KrossMatch(
            sku="SKU-1",
            status="found",
            pimbo_product_id="p-1",
            pimbo_product_url="https://pim.bo.ultrabike.lt/dashboard/products/p-1",
            kross_url=product_url,
        )

    def test_dimension_labels_are_normalized_like_the_browser_script(self):
        self.assertEqual(
            "tt - efektywna dlugosc gornej rury",
            normalize_label("  TT - efektywna długość górnej rury "),
        )

    def test_clipped_dimensions_metrics_are_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "preparation failed"):
            _validate_capture_metrics({
                "ok": False,
                "reason": "capture target is still clipped",
                "tableWidth": 1236,
                "captureWidth": 839,
            })

    def test_dimensions_capture_saves_the_expanded_full_width_png(self):
        from PIL import Image

        class _Element:
            def is_displayed(self):
                return True

            def find_element(self, _by, _selector):
                return self

            def screenshot(self, path):
                Image.new("RGB", (1236, 500), "white").save(path, "PNG")
                return True

        class _CaptureDriver:
            def __init__(self):
                self.element = _Element()
                self.visited = []
                self.scripts = []
                self.current_url = "https://kross.pl/alta-4-0-czarny-grafitowy-matowy"

            def set_page_load_timeout(self, timeout):
                self.timeout = timeout

            def get(self, url):
                self.visited.append(url)

            def find_elements(self, _by, selector):
                if "dimensions-table" in selector:
                    return [self.element]
                return []

            def execute_script(self, script, *args):
                self.scripts.append((script, args))
                if "const tableWidth" in script:
                    return {
                        "ok": True,
                        "rows": 19,
                        "columns": 7,
                        "tableWidth": 1236,
                        "captureWidth": 1236,
                        "sizeChartHeight": 96,
                    }
                return None

            def execute_async_script(self, _script):
                return None

        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "dimensions-table.png"
            driver = _CaptureDriver()
            dimensions = capture_kross_dimensions_table(
                driver,
                "https://kross.pl/alta-4-0-czarny-grafitowy-matowy",
                destination,
                timeout=0.2,
            )

            self.assertEqual((1236, 500), dimensions)
            self.assertTrue(destination.is_file())
            size_chart = destination.with_name("size-height-table.png")
            self.assertTrue(size_chart.is_file())
            with Image.open(size_chart) as image:
                self.assertEqual((1236, 96), image.size)
            self.assertIn("scrollWidth", driver.scripts[0][0])
            self.assertEqual([], driver.visited)

    def test_pimbo_search_requeries_the_field_after_dom_refresh(self):
        class _Field:
            def __init__(self, value="", *, stale=False):
                self.value = value
                self.stale = stale

            def is_displayed(self):
                return True

            def click(self):
                return None

            def send_keys(self, *keys):
                if "\ue007" in keys:
                    self.stale = True
                self.value = "SKU-1"

            def get_attribute(self, name):
                if self.stale:
                    raise RuntimeError("stale element reference")
                return self.value if name == "value" else ""

        field_old = _Field()
        field_new = _Field("SKU-1")

        class _Driver:
            current_url = "https://pim.bo.ultrabike.lt/dashboard/products"

            def __init__(self):
                self.calls = 0

            def find_elements(self, by, selector):
                self.calls += 1
                if self.calls == 1:
                    return [field_old]
                return [field_new]

        driver = _Driver()
        client = KrossPimboClient(driver)

        client._set_search("SKU-1")

        self.assertEqual(2, driver.calls)

    def test_pimbo_search_opens_clickable_row_when_it_has_no_product_link(self):
        sku = "KRAL2Z28X58M009346"

        class _Text:
            def __init__(self, text):
                self.text = text

            def get_attribute(self, name):
                return self.text if name == "title" else ""

        class _Row:
            def is_displayed(self):
                return True

            def find_elements(self, _by, selector):
                if "dashboard/products" in selector:
                    return []
                if "font-medium" in selector:
                    return [_Text("KROSS Alta")]
                if "font-mono" in selector:
                    return [_Text("ALTA-4-0")]
                return []

        class _Variant(_Text):
            def is_displayed(self):
                return True

        class _StaleVariant(_Variant):
            @property
            def text(self):
                raise RuntimeError("stale element reference")

            @text.setter
            def text(self, value):
                self._text = value

        class _Visible:
            def is_displayed(self):
                return True

        class _PimboDriver:
            def __init__(self):
                self.current_url = "https://pim.bo.ultrabike.lt/dashboard/products"
                self.row = _Row()
                self.clicked = False
                self.click_attempts = 0
                self.variant_queries = 0

            def execute_script(self, _script, row):
                self.click_attempts += 1
                if self.click_attempts == 1:
                    raise RuntimeError("stale element reference")
                self.clicked = row is self.row
                self.current_url = "https://pim.bo.ultrabike.lt/dashboard/products/p-1"

            def find_elements(self, _by, selector):
                if "dashboard/variants" in selector:
                    self.variant_queries += 1
                    if self.variant_queries == 1:
                        return [_StaleVariant(sku)]
                    if self.variant_queries == 2:
                        return [_Variant("PREVIOUS-PRODUCT-SKU")]
                    return [_Variant(sku)]
                if "Search..." in selector:
                    return [_Visible()]
                return []

            def get(self, url):
                self.current_url = url

        class _Client(KrossPimboClient):
            def _ensure_list(self):
                return None

            def _set_search(self, _sku):
                return None

            def _rows(self):
                return [self.driver.row]

        class _PimboEditor:
            def __init__(self, _driver):
                pass

            def open_section(self, section):
                self.section = section

            def product_name(self):
                return "KROSS Alta"

        driver = _PimboDriver()
        with patch("tools.kross_automation.service.PimboProductEditor", _PimboEditor):
            result = _Client(driver, timeout=0.1).find_by_variant_sku(sku)

        self.assertTrue(driver.clicked)
        self.assertEqual(2, driver.click_attempts)
        self.assertEqual(3, driver.variant_queries)
        self.assertEqual("pimbo_found", result.status)
        self.assertEqual("p-1", result.pimbo_product_id)
        self.assertEqual(
            "https://pim.bo.ultrabike.lt/dashboard/products/p-1",
            result.pimbo_product_url,
        )
        self.assertEqual(result.pimbo_product_url, driver.current_url)

    def test_pimbo_lookup_retries_when_first_search_snapshot_is_previous_product(self):
        sku = "KREX2Z28X17W008492"

        class _Driver:
            def __init__(self):
                self.current_url = PIMBO_PRODUCTS_URL
                self.visited = []

            def get(self, url):
                self.visited.append(url)
                self.current_url = url

            def find_elements(self, _by, selector):
                return [self] if "Search..." in selector else []

            def is_displayed(self):
                return True

        class _Client(KrossPimboClient):
            def __init__(self, driver):
                super().__init__(driver, timeout=0.1)
                self.searches = 0
                self.result_passes = 0

            def _ensure_list(self):
                return None

            def _search_field(self):
                return None

            def _set_search(self, _sku):
                self.searches += 1

            def _candidate_snapshots(self):
                return []

            def _wait_for_fresh_candidates(self, _previous_signature):
                self.result_passes += 1
                product_id = "p-old" if self.result_passes == 1 else "p-new"
                return [(
                    0,
                    f"https://pim.bo.ultrabike.lt/dashboard/products/{product_id}",
                    "KROSS bike",
                    "MODEL",
                )]

            def _open_product_row(self, _row_index, href, _title, _code):
                self.driver.get(href)

            def _variant_skus(self, expected_sku=""):
                if self.driver.current_url.endswith("/p-new"):
                    return {expected_sku}
                return {"PREVIOUS-PRODUCT-SKU"}

            def _wait(self, predicate, message, timeout=None):
                value = predicate()
                if value:
                    return value
                raise RuntimeError(message)

        class _PimboEditor:
            def __init__(self, _driver):
                pass

            def open_section(self, _section):
                return None

            def product_name(self):
                return "KROSS bike"

        driver = _Driver()
        client = _Client(driver)
        with patch("tools.kross_automation.service.PimboProductEditor", _PimboEditor):
            result = client.find_by_variant_sku(sku)

        self.assertEqual("pimbo_found", result.status)
        self.assertEqual("p-new", result.pimbo_product_id)
        self.assertEqual(2, client.searches)
        self.assertIn(
            "https://pim.bo.ultrabike.lt/dashboard/products/p-old",
            driver.visited,
        )
        self.assertEqual(result.pimbo_product_url, driver.current_url)

    def test_sku_normalization_is_stable_and_deduplicates(self):
        self.assertEqual("KRTR1Z28X17M003989", normalize_sku(" krtr1 z28x17m003989 "))
        self.assertEqual(
            ("SKU-1", "SKU-2"),
            unique_skus(["sku-1", " SKU-1 ", "sku-2", ""]),
        )

    def test_manual_inputs_accept_skus_urls_and_explicit_pairs(self):
        url_one = "https://kross.pl/alta-4-0"
        url_two = "https://kross.pl/sentio-hybrid"

        targets = parse_collection_targets((
            "sku-1",
            url_one,
            f"sku-2 | {url_two}",
        ))

        self.assertEqual(
            (
                ("SKU-1", ""),
                ("", url_one),
                ("SKU-2", url_two),
            ),
            tuple((target.sku, target.url) for target in targets),
        )

    def test_public_catalog_validates_search_candidate_and_extracts_content(self):
        sku = "KRTR1Z28X17M003989"
        search_url = f"https://kross.pl/catalogsearch/result/?q={sku}"
        product_url = "https://kross.pl/rowery/example-bike"
        pages = {
            search_url: _Response(search_url, '<a href="/rowery/example-bike">Example bike</a>'),
            product_url: _Response(
                product_url,
                f'''<main><h1>Example Bike</h1><div id="description"><p>Supplier copy</p></div>
                <div id="additional"><table><tr><td>RAMA</td><td>Aluminium</td></tr></table></div>
                <a class="orbitvu-gallery-item-link" data-big_src="/media/bike.jpg"></a>{sku}</main>''',
            ),
        }
        catalog = KrossPublicCatalog(_Session(pages))

        found_url, name = catalog.find_product_url(sku)
        self.assertEqual(product_url, found_url)
        self.assertEqual("Example bike", name)

        product = catalog.fetch_product(product_url)
        self.assertEqual("Example Bike", product.name)
        self.assertIn("Supplier copy", product.description_html)
        self.assertEqual("RAMA: Aluminium", product.specification_text)
        self.assertEqual(("https://kross.pl/media/bike.jpg",), product.image_urls)

    def test_public_catalog_uses_large_carousel_sources_and_ignores_thumbnails(self):
        product_url = "https://kross.pl/alta-4-0"
        pages = {
            product_url: _Response(
                product_url,
                '''<main><h1>Alta 4.0</h1>
                <div class="kross-gallery-slide"
                     data-large-src="/media/catalog/product/cache/full/K/R/bike-1.jpg"></div>
                <div class="kross-gallery-slide"
                     data-large-src="/media/catalog/product/cache/full/K/R/bike-2.jpg"></div>
                <div class="gallery">
                  <img src="/media/catalog/product/cache/thumb/K/R/bike-1.jpg">
                  <img src="/media/catalog/product/cache/thumb/K/R/bike-2.jpg">
                </div></main>''',
            ),
        }

        product = KrossPublicCatalog(_Session(pages)).fetch_product(product_url)

        self.assertEqual(
            (
                "https://kross.pl/media/catalog/product/cache/full/K/R/bike-1.jpg",
                "https://kross.pl/media/catalog/product/cache/full/K/R/bike-2.jpg",
            ),
            product.image_urls,
        )

    def test_download_images_rejects_thumbnail_sized_assets(self):
        from PIL import Image

        def image_bytes(size):
            from io import BytesIO

            buffer = BytesIO()
            Image.new("RGB", size, "white").save(buffer, "JPEG")
            return buffer.getvalue()

        full_url = "https://kross.pl/media/full.jpg"
        thumb_url = "https://kross.pl/media/thumb.jpg"
        catalog = KrossPublicCatalog(_Session({
            full_url: _Response(
                full_url, content=image_bytes((950, 720)), content_type="image/jpeg"
            ),
            thumb_url: _Response(
                thumb_url, content=image_bytes((110, 110)), content_type="image/jpeg"
            ),
        }))
        product = KrossProductData(
            "https://kross.pl/alta-4-0", "Alta 4.0", "", "", (full_url, thumb_url)
        )
        log = []

        with tempfile.TemporaryDirectory() as temporary:
            downloaded = catalog.download_images(product, Path(temporary), log=log.append)
            files = tuple(path.name for path in Path(temporary).iterdir())

        self.assertEqual(("01.jpg",), tuple(path.name for path in downloaded))
        self.assertEqual(("01.jpg",), files)
        self.assertTrue(any("thumbnail-sized image (110x110px)" in item for item in log))

    def test_product_page_extracts_variant_skus_for_url_only_collection(self):
        product_url = "https://kross.pl/alta-4-0"
        pages = {
            product_url: _Response(
                product_url,
                '''<main><h1>Alta 4.0</h1><script type="application/json">
                {"sku":"ALTA-4-0","variants":[
                  {"simple_sku":"KRAL2Z28X58M009346"},
                  {"simple_sku":"KRAL2Z28X58M009347"}
                ]}</script></main>''',
            ),
        }

        product = KrossPublicCatalog(_Session(pages)).fetch_product(product_url)

        self.assertEqual(
            ("KRAL2Z28X58M009346", "KRAL2Z28X58M009347", "ALTA-4-0"),
            product.variant_skus,
        )

    def test_browser_search_uses_direct_magento_url_and_redirect(self):
        sku = "KRAL2Z28X58M009346"

        class _Browser:
            def __init__(self):
                self.current_url = ""
                self.page_source = ""
                self.title = "KROSS Alta 2.0"
                self.visited = []

            def get(self, url):
                self.visited.append(url)
                self.current_url = "https://kross.pl/alta-2-0"
                self.page_source = f"<main>{sku}</main>"

            def find_elements(self, _by, _selector):
                return []

            def execute_script(self, _script, *_args):
                return None

        browser = _Browser()
        catalog = KrossPublicCatalog(browser_driver=browser, timeout=0.2)

        url, title = catalog._find_product_url_in_browser(sku)

        self.assertEqual("https://kross.pl/alta-2-0", url)
        self.assertEqual("KROSS Alta 2.0", title)
        self.assertEqual(
            [f"https://kross.pl/catalogsearch/result/?q={sku}"],
            browser.visited,
        )

    def test_browser_search_opens_and_validates_a_result_tile_without_http_waits(self):
        sku = "KRAL2Z28X58M009346"
        search_url = f"https://kross.pl/catalogsearch/result/?q={sku}"
        product_url = "https://kross.pl/alta-2-0"

        class _FailingSession:
            def __init__(self):
                self.headers = {}

            def get(self, *_args, **_kwargs):
                raise AssertionError("browser-backed lookup must not wait on HTTP fallbacks")

        class _Browser:
            title = "Alta 2.0"

            def __init__(self):
                self.current_url = ""
                self.page_source = ""
                self.visited = []

            def set_page_load_timeout(self, timeout):
                self.timeout = timeout

            def get(self, url):
                self.visited.append(url)
                self.current_url = url
                if url == search_url:
                    self.page_source = (
                        '<div class="product-item"><a href="/alta-2-0">Alta 2.0</a>'
                        f'<span>{sku}</span></div>'
                    )
                else:
                    self.page_source = f"<main><h1>Alta 2.0</h1>{sku}</main>"

            def find_elements(self, _by, _selector):
                return []

            def execute_script(self, _script, *_args):
                return None

        browser = _Browser()
        catalog = KrossPublicCatalog(
            _FailingSession(), browser_driver=browser, timeout=30.0
        )

        url, title = catalog.find_product_url(sku)

        self.assertEqual(product_url, url)
        self.assertEqual("Alta 2.0", title)
        self.assertEqual([search_url, product_url], browser.visited)
        self.assertEqual(12.0, browser.timeout)

    def test_filtered_collection_tries_all_variants_until_one_matches_and_saves_package(self):
        pimbo = KrossPimboProduct(
            product_id="p-1",
            product_name="KROSS Alta 2.0",
            product_url="https://pim.bo.ultrabike.lt/dashboard/products/p-1",
            visible_code="ALTA-2-0",
            variant_skus=("MISSING-1", "FOUND-2", "UNUSED-3"),
        )

        class _Scanner:
            def scan_products(self, _filters, *, progress, log):
                if log:
                    log("read all variants")
                return (pimbo,)

        class _CollectionCatalog:
            def __init__(self):
                self.searches = []

            def find_product_url(self, sku):
                self.searches.append(sku)
                if sku == "FOUND-2":
                    return "https://kross.pl/alta-2-0", "Alta 2.0"
                return "", ""

            def fetch_product(self, url):
                return KrossProductData(
                    url, "Alta 2.0", "<p>Description</p>", "Frame: Aluminium", ()
                )

        catalog = _CollectionCatalog()
        service = KrossAutomationService(
            object(),
            public_catalog=catalog,
            pimbo_scanner_factory=lambda _driver: _Scanner(),
        )
        with tempfile.TemporaryDirectory() as temporary:
            result = service.collect_filtered(
                PimboFilterSpec(),
                Path(temporary),
                options=KrossCollectionOptions.only(
                    "description_source", "specifications_source"
                ),
            )
            match = result.matches[0]
            metadata = Path(match.local_folder) / KROSS_METADATA_NAME
            description = Path(match.local_folder) / KROSS_DESCRIPTION_NAME
            specifications = Path(match.local_folder) / KROSS_SPECIFICATIONS_NAME
            loaded = KrossAutomationService.load_local_packages(Path(temporary))
            description_text = description.read_text(encoding="utf-8")
            specifications_text = specifications.read_text(encoding="utf-8")

        self.assertEqual(["MISSING-1", "FOUND-2"], catalog.searches)
        self.assertEqual("FOUND-2", match.sku)
        self.assertEqual(pimbo.variant_skus, match.variant_skus)
        self.assertTrue(metadata.name == KROSS_METADATA_NAME)
        self.assertEqual("<p>Description</p>", description_text)
        self.assertEqual("Frame: Aluminium", specifications_text)
        self.assertEqual("local_ready", loaded.matches[0].status)
        self.assertEqual("FOUND-2", loaded.matches[0].sku)

    def test_pasted_skus_collect_full_local_packages_without_pimbo_scan(self):
        class _ManualCatalog:
            def __init__(self):
                self.searches = []

            def find_product_url(self, sku):
                self.searches.append(sku)
                return f"https://kross.pl/{sku.casefold()}", f"Bike {sku}"

            def fetch_product(self, url):
                return KrossProductData(
                    url, "Manual bike", "<p>Description</p>", "Frame: Aluminium", ()
                )

        def scanner_must_not_run(_driver):
            raise AssertionError("manual SKU collection must not scan PIMBO")

        catalog = _ManualCatalog()
        progress = []
        service = KrossAutomationService(
            object(),
            public_catalog=catalog,
            pimbo_scanner_factory=scanner_must_not_run,
        )
        with tempfile.TemporaryDirectory() as temporary:
            result = service.collect_skus(
                (" sku-1 ", "SKU-1", "sku-2"),
                Path(temporary),
                options=KrossCollectionOptions.only(
                    "description_source", "specifications_source"
                ),
                progress=lambda current, total, message: progress.append(
                    (current, total, message)
                ),
            )
            folders = [Path(match.local_folder) for match in result.matches]
            loaded = KrossAutomationService.load_local_packages(Path(temporary))
            package_files_exist = all(
                (folder / KROSS_METADATA_NAME).is_file() for folder in folders
            )

        self.assertEqual(["SKU-1", "SKU-2"], catalog.searches)
        self.assertEqual(("SKU-1", "SKU-2"), tuple(match.sku for match in result.matches))
        self.assertTrue(all(not match.pimbo_product_url for match in result.matches))
        self.assertTrue(all(match.variant_skus == (match.sku,) for match in result.matches))
        self.assertTrue(package_files_exist)
        self.assertEqual((2, 2), progress[-1][:2])
        self.assertEqual(2, len(loaded.matches))

    def test_direct_url_collection_skips_search_and_uses_extracted_variant_sku(self):
        url = "https://kross.pl/alta-4-0"
        sku = "KRAL2Z28X58M009346"

        class _UrlCatalog:
            def __init__(self):
                self.fetches = []

            def find_product_url(self, _sku):
                raise AssertionError("a direct URL must skip KROSS search")

            def fetch_product(self, product_url):
                self.fetches.append(product_url)
                return KrossProductData(
                    product_url,
                    "Alta 4.0",
                    "<p>Description</p>",
                    "Frame: Aluminium",
                    (),
                    (sku, "KRAL2Z28X58M009347"),
                )

        catalog = _UrlCatalog()
        service = KrossAutomationService(object(), public_catalog=catalog)
        with tempfile.TemporaryDirectory() as temporary:
            result = service.collect_inputs(
                (url,),
                Path(temporary),
                options=KrossCollectionOptions.only(
                    "description_source", "specifications_source"
                ),
            )
            match = result.matches[0]
            package_exists = (Path(match.local_folder) / KROSS_METADATA_NAME).is_file()

        self.assertEqual([url], catalog.fetches)
        self.assertEqual(sku, match.sku)
        self.assertEqual((sku, "KRAL2Z28X58M009347"), match.variant_skus)
        self.assertEqual(url, match.kross_url)
        self.assertTrue(package_exists)

    def test_upload_reads_existing_local_sku_folder_without_visiting_kross(self):
        from PIL import Image

        class _PimboLookup:
            def find_by_variant_sku(self, sku):
                return KrossMatch(
                    sku,
                    "pimbo_found",
                    pimbo_product_id="p-9",
                    pimbo_product_name="KROSS Alta",
                    pimbo_product_url="https://pim.bo.ultrabike.lt/dashboard/products/p-9",
                )

        class _NoKrossCatalog:
            def fetch_product(self, _url):
                raise AssertionError("upload must not revisit KROSS")

            def download_images(self, *_args, **_kwargs):
                raise AssertionError("upload must not download KROSS photos")

        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary) / "FOUND-2"
            folder.mkdir()
            Image.new("RGB", (950, 720), "white").save(folder / "01.jpg", "JPEG")
            Image.new("RGB", (110, 110), "white").save(folder / "02.jpg", "JPEG")
            editor = _Editor()
            driver = _Driver()
            service = KrossAutomationService(
                driver,
                public_catalog=_NoKrossCatalog(),
                pimbo_client_factory=lambda _driver: _PimboLookup(),
                editor_factory=lambda _driver: editor,
            )
            match = KrossMatch(
                "FOUND-2",
                "local_ready",
                local_folder=str(folder),
                variant_skus=("FOUND-2",),
            )

            result = service.upload_and_save(
                match,
                Path(temporary),
                options=KrossWorkflowOptions.only("product_photos"),
            )

        self.assertTrue(result.succeeded)
        self.assertEqual("p-9", result.match.pimbo_product_id)
        self.assertEqual(["begin", "product_images:1", "finish"], editor.calls)

    def test_missing_local_assets_warn_and_other_selected_stages_still_run(self):
        class _PimboLookup:
            def find_by_variant_sku(self, sku):
                return KrossMatch(
                    sku,
                    "pimbo_found",
                    pimbo_product_id="p-9",
                    pimbo_product_url="https://pim.bo.ultrabike.lt/dashboard/products/p-9",
                )

        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary) / "FOUND-2"
            folder.mkdir()
            (folder / "dimensions-table.png").write_bytes(b"geometry")
            (folder / "size-height-table.png").write_bytes(b"size")
            saved_match = KrossMatch(
                "FOUND-2",
                "collected",
                kross_url="https://kross.pl/found-2",
                local_folder=str(folder),
            )
            KrossAutomationService._write_package(
                folder,
                saved_match,
                KrossProductData(
                    "https://kross.pl/found-2", "Found 2", "", "", ()
                ),
                KrossCollectionOptions.only("dimensions"),
                (),
            )
            editor = _Editor()
            progress = []
            service = KrossAutomationService(
                _Driver(),
                pimbo_client_factory=lambda _driver: _PimboLookup(),
                editor_factory=lambda _driver: editor,
            )

            result = service.upload_and_save(
                replace(saved_match, status="local_ready"),
                Path(temporary),
                options=KrossWorkflowOptions.only(
                    "product_photos",
                    "size_tables",
                    "geometry",
                    "brand",
                    "description_source",
                    "specifications_magic_ai",
                ),
                progress=progress.append,
            )

        self.assertTrue(result.succeeded)
        self.assertEqual(
            ["begin", "size_table_images:1", "geometry_images:1", "brand:KROSS", "finish"],
            editor.calls,
        )
        self.assertEqual(("size_tables", "geometry", "brand"), result.completed_stages)
        self.assertEqual(3, len(result.preparation.warnings))
        self.assertTrue(any("No product photos" in warning for warning in progress))
        self.assertTrue(any("no saved KROSS description" in warning for warning in progress))
        self.assertTrue(any("no saved KROSS specifications" in warning for warning in progress))

    def test_one_stage_can_run_without_fetching_unused_kross_data_or_saving(self):
        with tempfile.TemporaryDirectory() as temporary:
            image = Path(temporary) / "bike.jpg"
            product = KrossProductData(
                url="https://kross.pl/rowery/example-bike",
                name="Example",
                description_html="<p>Source</p>",
                specification_text="Frame: Carbon",
                image_urls=(),
            )
            catalog = _Catalog(product, image)
            editor = _Editor()
            driver = _Driver()
            service = KrossAutomationService(
                driver,
                public_catalog=catalog,
                editor_factory=lambda _driver: editor,
            )

            result = service.upload_and_save(
                self._match(),
                None,
                options=KrossWorkflowOptions.only("brand"),
            )

        self.assertTrue(result.succeeded)
        self.assertEqual(PimPreparationStatus.READY_FOR_REVIEW, result.preparation.status)
        self.assertIsNone(result.product)
        self.assertEqual((), result.downloaded_images)
        self.assertEqual(("brand",), result.completed_stages)
        self.assertEqual([], catalog.calls)
        self.assertEqual(["begin", "brand:KROSS", "finish"], editor.calls)
        self.assertEqual([self._match().pimbo_product_url], driver.visited)

    def test_size_tables_and_geometry_can_be_uploaded_independently(self):
        product = KrossProductData(
            url="https://kross.pl/rowery/example-bike",
            name="Example",
            description_html="",
            specification_text="",
            image_urls=(),
        )
        expected = {
            "size_tables": ("size_table_images:1", "size_tables"),
            "geometry": ("geometry_images:1", "geometry"),
        }

        for stage, (upload_call, completed_stage) in expected.items():
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as temporary:
                image = Path(temporary) / "bike.jpg"
                catalog = _Catalog(product, image)
                editor = _Editor()
                service = KrossAutomationService(
                    _Driver(),
                    public_catalog=catalog,
                    editor_factory=lambda _driver: editor,
                )

                result = service.upload_and_save(
                    self._match(product.url),
                    Path(temporary) / "downloads",
                    options=KrossWorkflowOptions.only(stage),
                )

                self.assertTrue(result.succeeded)
                self.assertIn(upload_call, editor.calls)
                other_call = (
                    "geometry_images:1"
                    if stage == "size_tables"
                    else "size_table_images:1"
                )
                self.assertNotIn(other_call, editor.calls)
                self.assertEqual((completed_stage,), result.completed_stages)

    def test_many_product_photos_are_uploaded_in_re_resolved_batches(self):
        class _ManyPhotoCatalog(_Catalog):
            def download_images(self, product, destination, *, log=None):
                return tuple(Path(destination) / f"photo-{index:02d}.jpg" for index in range(23))

        with tempfile.TemporaryDirectory() as temporary:
            product = KrossProductData(
                url="https://kross.pl/rowery/example-bike",
                name="Example",
                description_html="",
                specification_text="",
                image_urls=tuple(f"https://kross.pl/photo-{index}.jpg" for index in range(23)),
            )
            image = Path(temporary) / "bike.jpg"
            catalog = _ManyPhotoCatalog(product, image)
            editor = _Editor()
            progress = []
            service = KrossAutomationService(
                _Driver(),
                public_catalog=catalog,
                editor_factory=lambda _driver: editor,
            )

            with patch("tools.kross_automation.service.time.sleep") as batch_pause:
                result = service.upload_and_save(
                    self._match(product.url),
                    Path(temporary) / "downloads",
                    options=KrossWorkflowOptions.only("product_photos"),
                    progress=progress.append,
                )

        self.assertTrue(result.succeeded)
        self.assertEqual(
            ["begin", "product_images:10", "product_images:10", "product_images:3", "finish"],
            editor.calls,
        )
        self.assertEqual(
            [call(1.0), call(1.0)],
            batch_pause.call_args_list,
        )
        self.assertTrue(any("1–10 of 23" in message for message in progress))
        self.assertTrue(any("21–23 of 23" in message for message in progress))

    def test_save_only_preserves_the_already_open_product_without_reloading(self):
        with tempfile.TemporaryDirectory() as temporary:
            image = Path(temporary) / "bike.jpg"
            product = KrossProductData("", "", "", "", ())
            catalog = _Catalog(product, image)
            editor = _Editor()
            driver = _Driver()
            driver.current_url = self._match().pimbo_product_url + "?tab=specifications"
            service = KrossAutomationService(
                driver,
                public_catalog=catalog,
                editor_factory=lambda _driver: editor,
            )

            result = service.upload_and_save(
                self._match(),
                None,
                options=KrossWorkflowOptions.only("save"),
            )

        self.assertTrue(result.succeeded)
        self.assertEqual(PimPreparationStatus.SAVED_AUTOMATICALLY, result.preparation.status)
        self.assertEqual([], driver.visited)
        self.assertEqual([], catalog.calls)
        self.assertEqual(["begin", "finish", "save"], editor.calls)
        self.assertEqual(("save",), result.completed_stages)

    def test_idempotent_stage_reports_no_changes_instead_of_failure(self):
        class _NoChangeEditor(_Editor):
            def set_brand(self, value):
                self.calls.append(f"brand:{value}")
                return False

            def finish(self, result, **_kwargs):
                self.calls.append("finish")
                return result.with_status(
                    PimPreparationStatus.FAILED,
                    error="PIMBO form has no reviewable unsaved changes",
                )

        with tempfile.TemporaryDirectory() as temporary:
            image = Path(temporary) / "bike.jpg"
            catalog = _Catalog(KrossProductData("", "", "", "", ()), image)
            editor = _NoChangeEditor()
            service = KrossAutomationService(
                _Driver(),
                public_catalog=catalog,
                editor_factory=lambda _driver: editor,
            )
            result = service.upload_and_save(
                self._match(),
                None,
                options=KrossWorkflowOptions.only("brand", "save"),
            )

        self.assertTrue(result.succeeded)
        self.assertEqual(PimPreparationStatus.NO_CHANGES, result.preparation.status)
        self.assertNotIn("save", editor.calls)

    def test_upload_runs_the_requested_order_and_saves_only_after_enrichment(self):
        with tempfile.TemporaryDirectory() as temporary:
            image = Path(temporary) / "bike.jpg"
            image.write_bytes(b"image")
            product = KrossProductData(
                url="https://kross.pl/rowery/example-bike",
                name="Example",
                description_html="<p>Source description</p>",
                specification_text="Frame: Carbon",
                image_urls=("https://kross.pl/media/bike.jpg",),
            )
            catalog = _Catalog(product, image)
            editor = _Editor()
            driver = _Driver()
            service = KrossAutomationService(
                driver,
                public_catalog=catalog,
                editor_factory=lambda _driver: editor,
            )
            match = self._match(product.url)

            with patch("tools.kross_automation.service.time.sleep") as wait_after_save:
                result = service.upload_and_save(match, Path(temporary) / "downloads")

        self.assertTrue(result.succeeded)
        self.assertEqual("dimensions-table.png", result.dimensions_image.name)
        self.assertEqual("size-height-table.png", result.size_chart_image.name)
        self.assertEqual(3, len(result.downloaded_images))
        self.assertEqual(KrossWorkflowOptions.STAGES, result.completed_stages)
        self.assertEqual([match.pimbo_product_url], driver.visited)
        self.assertEqual(
            [
                "begin", "product_images:1", "size_table_images:1",
                "geometry_images:1", "description:True", "description_magic",
                "family:Dviračiai", "brand:KROSS", "category:Dviračiai",
                "name_lt_from_en", "translate:True", "locale:lt", "finish", "save", "begin",
                "specs:Frame: Carbon", "finish", "save",
            ],
            editor.calls,
        )
        wait_after_save.assert_called_once_with(1.0)

    def test_failed_category_magicai_blocks_the_first_save(self):
        class _FailingCategoryEditor(_Editor):
            def suggest_category(self, family):
                self.calls.append(f"category:{family}")
                raise RuntimeError("category service unavailable")

        editor = _FailingCategoryEditor()
        driver = _Driver()
        service = KrossAutomationService(
            driver,
            editor_factory=lambda _driver: editor,
        )

        result = service.upload_and_save(
            self._match(),
            None,
            options=KrossWorkflowOptions.only(
                "product_family", "brand", "category_magic_ai", "save"
            ),
        )

        self.assertFalse(result.succeeded)
        self.assertEqual(PimPreparationStatus.FAILED, result.preparation.status)
        self.assertIn("Automatic Save was blocked", result.preparation.error)
        self.assertEqual(
            [
                "begin",
                "family:Dviračiai",
                "brand:KROSS",
                "category:Dviračiai",
                "finish",
            ],
            editor.calls,
        )
        self.assertNotIn("save", editor.calls)

    def test_missing_description_source_blocks_description_magicai_and_save(self):
        with tempfile.TemporaryDirectory() as temporary:
            image = Path(temporary) / "bike.jpg"
            catalog = _Catalog(
                KrossProductData(
                    "https://kross.pl/example", "Example", "", "", ()
                ),
                image,
            )
            editor = _Editor()
            service = KrossAutomationService(
                _Driver(),
                public_catalog=catalog,
                editor_factory=lambda _driver: editor,
            )

            result = service.upload_and_save(
                self._match("https://kross.pl/example"),
                None,
                options=KrossWorkflowOptions.only(
                    "description_source", "description_magic_ai", "save"
                ),
            )

        self.assertFalse(result.succeeded)
        self.assertIn("Automatic Save was blocked", result.preparation.error)
        self.assertEqual(["begin", "finish"], editor.calls)
        self.assertNotIn("description_magic", editor.calls)
        self.assertNotIn("save", editor.calls)

    def test_specifications_only_requires_existing_dviraciai_family(self):
        class _WrongFamilyEditor(_Editor):
            def product_family(self):
                self.calls.append("read_family")
                return "Draft"

        with tempfile.TemporaryDirectory() as temporary:
            image = Path(temporary) / "bike.jpg"
            catalog = _Catalog(
                KrossProductData(
                    "https://kross.pl/example",
                    "Example",
                    "",
                    "Frame: Carbon",
                    (),
                ),
                image,
            )
            editor = _WrongFamilyEditor()
            service = KrossAutomationService(
                _Driver(),
                public_catalog=catalog,
                editor_factory=lambda _driver: editor,
            )

            result = service.upload_and_save(
                self._match("https://kross.pl/example"),
                None,
                options=KrossWorkflowOptions.only(
                    "specifications_magic_ai", "save"
                ),
            )

        self.assertFalse(result.succeeded)
        self.assertEqual(["begin", "read_family", "finish"], editor.calls)
        self.assertTrue(any(
            "expected Dviračiai" in warning
            for warning in result.preparation.warnings
        ))
        self.assertNotIn("specs:Frame: Carbon", editor.calls)
        self.assertNotIn("save", editor.calls)


if __name__ == "__main__":
    unittest.main()
