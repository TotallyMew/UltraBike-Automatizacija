from types import SimpleNamespace
from pathlib import Path

import pytest

from tools.orbea_automation.component_values import normalize_component_specifications
from tools.orbea_automation.specifications import build_orbea_specification_plan
from tools.orbea_automation.website import parse_website_product, read_component_dialog, STANDARD_CONFIGURATION_BUTTON


@pytest.mark.parametrize("price", ["€\u00a00", "0\u00a0€", "$ 0", "£ 0"])
def test_configurator_and_included_rows_resolve_to_one_clean_component(price):
    source = f"Crankset: Shimano Cues U6030 34x50T {price} More information\nCrankset: Shimano Cues U6030 34x50T Incl."
    plan = build_orbea_specification_plan("Orbea AVANT H50 Nickel-Acid Gum (Matt)", ("51", "45", "63"),
        source, product=SimpleNamespace(name="Avant H50"))
    assert "Švaistikliai" not in dict(plan.values)
    assert "Crankset: Shimano Cues U6030 34x50T" in plan.magic_ai_source
    assert "More information" not in plan.magic_ai_source and "Incl." not in plan.magic_ai_source


def test_included_component_wins_over_options_with_equal_prices():
    text = "Crankset: Shimano 36x52T € 0 More information Shimano 34x50T € 0 More information\nCrankset: Shimano 34x50T Incl."
    assert normalize_component_specifications(text) == "Crankset: Shimano 34x50T"


def test_unselected_options_and_add_delete_controls_are_omitted():
    text = "Rotors: 140mm € 0 160mm € 0\nFront light: Add Delete Supernova € 89 More information\nFork: Fox 36 Incl."
    assert normalize_component_specifications(text) == "Fork: Fox 36"


def test_included_na_is_preserved_and_information_buttons_are_ignored():
    text = "Display: Add Delete Shimano EN600 € 149 More information\nDisplay: N/A Incl.\nBattery: More information More information\nBattery: Avinox 800 Wh Incl."
    assert normalize_component_specifications(text) == "Display: N/A\nBattery: Avinox 800 Wh"


def test_single_published_component_price_is_removed_without_truncating_part_numbers():
    assert normalize_component_specifications("Stem: OC Mountain Control 21, 0º € 0") == "Stem: OC Mountain Control 21, 0º"


@pytest.mark.parametrize("source", ["Fork: Fox 36\nFork: Fox 38", "Fork: Fox 36 Incl.\nFork: Fox 38 Incl."])
def test_component_rows_are_retained_for_ai_without_mapping_or_choosing_a_value(source):
    plan = build_orbea_specification_plan("Orbea RISE 2027 Custom", (), source)
    assert dict(plan.values) == {"Modelis": "Orbea RISE 2027"}
    assert "Fork: Fox 36" in plan.magic_ai_source and "Fork: Fox 38" in plan.magic_ai_source


def test_collection_reads_clean_included_rows_and_not_the_option_menu():
    page = '''<main><h1>AVANT H50</h1><div id="product-bike-detail">
        <div><p>Crankset</p><p>Shimano Cues U6030 34x50T € 0 More information</p></div>
        <table><tr><td>Crankset</td><td>Shimano Cues U6030 34x50T Incl.</td></tr></table>
        </div></main>'''
    product = parse_website_product(page, "https://www.orbea.com/en-be/avant-h50")
    assert product.specifications_text == "Crankset: Shimano Cues U6030 34x50T"


def test_complete_standard_configuration_including_raw_article_text_and_repeated_tyres():
    page = (Path(__file__).parent / "fixtures/orbea_standard_configuration.html").read_text(encoding="utf-8")
    product = parse_website_product(page, "https://www.orbea.com/en-be/wild-lt-m20")
    assert product.specifications_source == "standard_configuration"
    assert len(product.specifications_text.splitlines()) == 30
    assert "Fork: RockShox ZEB - Select Rush RC 170 mm" in product.specifications_text
    assert "Motor: Avinox M2S" in product.specifications_text and "Battery: Avinox 800 Wh" in product.specifications_text
    assert "Unnamed" not in product.specifications_text and "Wrong" not in product.specifications_text
    plan = build_orbea_specification_plan("Orbea WILD LT M20 2027 Custom", ("S", "M"), product.specifications_text,
        product=SimpleNamespace(name=product.name))
    values = dict(plan.values)
    assert set(values) == {"Modelis", "Galimi rėmo dydžiai"}
    assert "Fork: RockShox ZEB - Select Rush RC 170 mm" in plan.magic_ai_source
    assert "Motor: Avinox M2S" in plan.magic_ai_source and "Battery: Avinox 800 Wh" in plan.magic_ai_source
    assert "Maxxis Assegai" in plan.magic_ai_source and "Maxxis Minion 2.40" in plan.magic_ai_source
    assert "Ratų dydis" not in values and "Lako užbaigimas" not in values
    assert "Remote: Avinox BC100" in plan.magic_ai_source


def test_empty_standard_dialog_does_not_fall_back_to_configurator_choices():
    page = '<main><h1>Orbea</h1><button aria-controls="standard-configuration-dialog">Standard configuration</button><div id="sidebar-components"><h3>Fork</h3><p>Wrong fork € 0</p></div></main><dialog id="standard-configuration-dialog"></dialog>'
    product = parse_website_product(page, "https://www.orbea.com/en-be/avant-h50")
    assert product.specifications_text == "" and product.description_html == ""


def test_on_demand_reader_opens_standard_configuration_button():
    page = '<dialog id="standard-configuration-dialog"><article><h3>Fork</h3>Orbea carbon</article></dialog>'
    class Element:
        def __init__(self, driver, dialog=False):
            self.driver, self.dialog = driver, dialog
        def is_displayed(self):
            return self.driver.open if self.dialog else True
        def is_enabled(self):
            return True
        def get_attribute(self, name):
            return page if name == "outerHTML" else "standard-configuration-dialog"
        def click(self):
            self.driver.open = True
        def send_keys(self, keys):
            self.driver.open = False
    class Driver:
        open = False
        def find_elements(self, by, selector):
            if selector == STANDARD_CONFIGURATION_BUTTON:
                return [Element(self)]
            if selector == "#standard-configuration-dialog":
                return [Element(self, dialog=True)]
            return []
        def find_element(self, *args):
            return Element(self)
        def execute_script(self, *args):
            pass
    driver = Driver()
    assert read_component_dialog(driver, timeout=.05, check=lambda: None) == "Fork: Orbea carbon"
    assert not driver.open
