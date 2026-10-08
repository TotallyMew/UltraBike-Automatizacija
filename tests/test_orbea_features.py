from __future__ import annotations

import html
import json

import pytest
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By

from tools.orbea_automation.features import FEATURE_BUTTON, FEATURE_DIALOG, feature_description_html, read_feature_description
from tools.orbea_automation.models import CancellationToken
from tools.orbea_automation.website import OrbeaWebsiteClient, parse_website_product
from tools.orbea_description_extractor import extract_description, render_document


URL = "https://www.orbea.com/es-es/orca-m11eltd-pwr"
MODEL = "ORCA M11eLTD PWR"
SKU = "U10707SV"
CARDS = [
    {"subheading": "Carbono OMX", "text": "Nuestro cuadro de alta gama OMX cuenta con menos láminas de carbono."},
    {"subheading": "Rigidez optimizada para cada talla", "text": "Todas las Orca se comportan de la misma manera."},
    {"subheading": "Powerspine", "text": "La parte inferior del cuadro soporta las cargas torsionales y laterales."},
    {"subheading": "ICR Plus", "text": "El cableado interno va guiado por debajo de la potencia."},
    {"subheading": "Paso de rueda de 32 mm", "text": "Cubiertas más anchas en superficies irregulares."},
]


def dialog_html(*, mounted_cards=5, embedded=True):
    data = ' data="' + html.escape(json.dumps({"cards": CARDS, "heading": None}, ensure_ascii=False), quote=True) + '"' if embedded else ""
    cards = "".join(f'<article class="swiper-slide"><h3>{card["subheading"]}</h3><div>{card["text"]}</div></article>' for card in CARDS[:mounted_cards])
    return ('<div id="feature-modules-dialog" role="dialog"><div class="dialog__content">'
        '<div><h2 id="dialog-heading-feature-modules-dialog">Características</h2>'
        '<button x-on:click="closeDialog;" title="Cerrar"><span class="sr-only">Cerrar</span></button></div>'
        '<section><picture><img src="feature.webp"></picture><div><h2>Praise the Light</h2>'
        '<div>Esa sensación que transmite una bici ligera y eficiente es insuperable.</div></div></section>'
        f'<section{data}><nav><button>Anterior</button><button>Siguiente</button></nav>{cards}'
        '<div class="sr-only">1 / 5</div><script>alert("unwanted")</script></section></div></div>')


def product_html(extra=""):
    product = {"@type": "Product", "name": MODEL, "sku": SKU, "description": "SHORT SUMMARY"}
    return f'<html><body><main><h1>{MODEL}</h1><p>Price, delivery, and unrelated store information.</p><script type="application/ld+json">{json.dumps(product)}</script></main>{extra}</body></html>'


def test_dialog_extracts_intro_and_all_cards_without_controls_or_store_text():
    source = product_html(dialog_html()) + '<footer>Newsletter, unrelated accessories</footer>'
    result = feature_description_html(source)
    soup = BeautifulSoup(result, "html.parser")
    assert [node.get_text() for node in soup.select("h2,h3")] == ["Praise the Light", *[card["subheading"] for card in CARDS]]
    assert len(soup.select("p")) == 6
    assert not soup.select("button,nav,script,img")
    for noise in ("Características", "Cerrar", "Anterior", "Siguiente", "1 / 5", "SHORT SUMMARY", "Price", "Newsletter"):
        assert noise not in result
    product = parse_website_product(source, URL)
    assert product.description_html == result and product.description_source == "feature_dialog"


def test_embedded_cards_include_unmounted_slides_and_do_not_duplicate_dom_cards():
    result = feature_description_html(dialog_html(mounted_cards=1))
    assert result.count("<h3>") == 5
    for card in CARDS:
        assert result.count(card["subheading"]) == 1
        assert card["text"] in result


def test_pasted_inner_content_is_supported_and_dom_only_cards_are_collected():
    soup = BeautifulSoup(dialog_html(embedded=False), "html.parser")
    fragment = str(soup.select_one(".dialog__content"))
    assert feature_description_html(fragment).count("<h3>") == 5
    # An enclosing product section must not hide the dialog's own sections.
    assert feature_description_html('<section id="product">' + fragment + '</section>').count("<h3>") == 5
    assert feature_description_html('<main><h1>Bike</h1><p>Unrelated copy</p></main>') == ""


class Element:
    def __init__(self, driver, kind):
        self.driver, self.kind = driver, kind
        self.text = MODEL if kind == "heading" else "Características principales"

    def is_displayed(self):
        return self.kind != "dialog" or self.driver.opened

    def is_enabled(self):
        return True

    def click(self):
        if self.kind == "button":
            self.driver.open_calls += 1
            self.driver.opened = True
        elif self.kind == "close":
            self.driver.close_calls += 1
            self.driver.opened = False

    def get_attribute(self, name):
        if name == "outerHTML":
            return dialog_html(mounted_cards=1) if self.driver.loaded else '<div id="feature-modules-dialog"></div>'
        if name == "innerText":
            return MODEL + " Price and unrelated store information"
        return None

    def find_elements(self, by, selector):
        # Check the real escaped Alpine-attribute selector as well as behavior.
        return [Element(self.driver, "close")] if BeautifulSoup(dialog_html(), "html.parser").select(selector) else []

    def send_keys(self, keys):
        self.driver.opened = False


class Driver:
    def __init__(self, *, has_features=True, loaded=True):
        self.has_features, self.loaded = has_features, loaded
        self.opened = False
        self.open_calls = self.close_calls = 0
        self.current_url = URL
        self.navigations = []

    def set_page_load_timeout(self, timeout):
        pass

    def get(self, url):
        self.current_url = url
        self.navigations.append(url)

    @property
    def page_source(self):
        return product_html(dialog_html() if self.opened and self.loaded else "")

    def find_elements(self, by, selector):
        if by == By.TAG_NAME and selector == "h1":
            return [Element(self, "heading")]
        if selector == FEATURE_BUTTON:
            return [Element(self, "button")] if self.has_features else []
        if selector == FEATURE_DIALOG:
            return [Element(self, "dialog")] if self.opened else []
        if selector == "main":
            return [Element(self, "main")]
        if selector == "main h1, h1":
            return [Element(self, "heading")]
        return []

    def execute_script(self, script, *args):
        if ".click()" in script:
            args[0].click()
        return None


def test_public_website_client_opens_spanish_features_and_caches_full_copy():
    driver = Driver()
    client = OrbeaWebsiteClient(lambda: driver, CancellationToken(), timeout=1)
    product = client.fetch(URL)
    assert product.description_source == "feature_dialog" and not product.description_error
    assert product.description_html.count("<h3>") == 5
    assert driver.open_calls == driver.close_calls == 1 and not driver.opened
    assert client.fetch(URL) is product and driver.open_calls == 1


def test_standalone_extractor_uses_the_same_features_copy():
    driver = Driver()
    document = extract_description(driver, URL)
    result = render_document(document)
    assert document.model == MODEL and document.expanded_sections == []
    for card in CARDS:
        assert card["subheading"] in result and card["text"] in result
    assert "SHORT SUMMARY" not in result and "Price" not in result
    assert driver.open_calls == driver.close_calls == 1


def test_disabled_description_selection_does_not_click_the_features_button():
    driver = Driver()
    client = OrbeaWebsiteClient(lambda: driver, CancellationToken(), timeout=1)
    client.collect_description = False
    product = client.fetch(URL)
    assert driver.open_calls == 0 and product.description_html == "<p>SHORT SUMMARY</p>"


def test_missing_features_opener_returns_legacy_fallback():
    assert read_feature_description(Driver(has_features=False), timeout=0.05) is None


@pytest.mark.parametrize("initializer", ["microsite = null;", "microsite = JSON.parse('{\"modules\":[]}');"])
def test_confirmed_absence_of_feature_content_is_not_an_extraction_error(initializer):
    class NoDescriptionDriver(Driver):
        @property
        def page_source(self):
            return product_html() + '<div id="product-bike-detail" x-init="' + html.escape(initializer, quote=True) + '"></div>'
    driver = NoDescriptionDriver(loaded=False)
    product = OrbeaWebsiteClient(lambda: driver, CancellationToken(), timeout=.05).fetch(URL)
    assert not product.description_html and not product.description_error
    assert product.description_source == "not_available"
    assert driver.open_calls == 0


def test_unloaded_features_are_an_error_instead_of_a_successful_short_summary():
    driver = Driver(loaded=False)
    client = OrbeaWebsiteClient(lambda: driver, CancellationToken(), timeout=0.05)
    product = client.fetch(URL)
    assert product.description_html == "" and "Features dialog" in product.description_error
    assert "TimeoutException" in product.description_error
    assert product.codes == (SKU,) and driver.close_calls == 1
