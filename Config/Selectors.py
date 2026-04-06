"""
Config/Selectors.py

Central registry of all browser element selectors used for admin UI automation.

When migrating to a new platform, only this file needs to be updated —
no changes required in the automation logic files.

Selectors are grouped by page/context. Dynamic selectors (those that depend
on an index or language ID) are implemented as static methods.

Dynamic selectors (those that depend on an index or value) are implemented
as static methods.
"""

from selenium.webdriver.common.by import By


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

class LoginSelectors:
    """Selectors for the admin login page."""

    URL = "https://pim.bo.ultrabike.lt/admin/login"

    EMAIL    = (By.ID, "field-email")
    PASSWORD = (By.ID, "field-password")
    SUBMIT   = (By.CSS_SELECTOR, "button[type='submit']")



# ---------------------------------------------------------------------------
# Product List (catalog / search results)
# ---------------------------------------------------------------------------

class ProductListSelectors:
    """Selectors for the product list / catalog page."""

    # Sidebar navigation
    NAV_MENU_COLLAPSE = (By.CSS_SELECTOR, "div.hamburger__open-icon")
    NAV_CATALOG       = (By.CSS_SELECTOR, "button.nav-group__toggle")
    NAV_PRODUCTS      = (By.ID, "nav-products")

    # Name search bar (always visible at top of list)
    SEARCH_NAME       = (By.ID, "search-filter-input")

    # Filter panel controls (used for External Id / code search)
    TOGGLE_FILTERS    = (By.ID, "toggle-list-filters")
    ADD_FILTER_BUTTON = (By.CSS_SELECTOR, "button.where-builder__add-first-filter")
    FILTER_VALUE      = (By.CSS_SELECTOR, "input.condition-value-text")

    # Product results table — waited on to confirm the page has loaded
    PRODUCT_TABLE    = (By.CSS_SELECTOR, "div.collection-list__tables table")

    # First row in the results table (used when there is only one match)
    PRODUCT_ROW      = (By.CSS_SELECTOR, "tbody tr.row-1")

    @staticmethod
    def product_row_by_code(code: str):
        """Locate the External Id cell whose text exactly matches the product code."""
        return (By.XPATH,
            f"//td[contains(@class,'cell-externalId')]"
            f"//span[normalize-space()='{code}']")

    @staticmethod
    def product_link_by_brand(brand: str):
        """
        Within a product row, locate the name-cell anchor whose text contains
        the brand name (case-insensitive via XPath translate()).
        """
        brand_lower = brand.lower()
        return (
            By.XPATH,
            f".//td[contains(@class,'cell-name')]//a[contains("
            f"translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), "
            f"'{brand_lower}')]",
        )


# ---------------------------------------------------------------------------
# Product Editor (single product edit page)
# ---------------------------------------------------------------------------

class ProductEditorSelectors:
    """Selectors for the product detail / edit page."""

    # Language switcher — trigger button that opens the locale popup
    LANGUAGE_SWITCH = (By.CSS_SELECTOR, "button.popup-button.popup-button--background")

    # Product name field (same ID for all languages; locale set via switcher)
    NAME_FIELD = (By.ID, "field-name")

    # Save controls
    SAVE_BUTTON     = (By.ID, "action-save")
    SAVE_BUTTON_ALT = (By.ID, "action-save")

    # Feedback indicators after save (pim.bo uses Sonner toasts)
    SAVE_SUCCESS       = (By.CSS_SELECTOR, "li.payload-toast-item[data-type='success']")
    SAVE_ERROR         = (By.CSS_SELECTOR, "li.payload-toast-item[data-type='error']")
    SAVE_ERROR_MESSAGE = (By.CSS_SELECTOR, "li.payload-toast-item[data-type='error'] div.toast-title")

    # Loading overlay — waited on to disappear after language switch
    LOADING_OVERLAY = (By.CSS_SELECTOR, ".loading, .spinner, .overlay")

    # HugeRTE editor body (inside the description iframe)
    # HugeRTE is a TinyMCE fork — body id changed from "tinymce" to "hugerte"
    TINYMCE_BODY = (By.ID, "hugerte")

    # The HugeRTE edit iframe (ID is dynamic; matched by class instead)
    DESCRIPTION_IFRAME = (By.CSS_SELECTOR, "iframe.tox-edit-area__iframe")

    # Hidden textarea backing the HugeRTE editor (ID is dynamic; matched by attribute)
    DESCRIPTION_TEXTAREA = (By.CSS_SELECTOR, "textarea[aria-hidden='true']")

    @staticmethod
    def language_option(lang_code: str):
        """The popup button for a specific locale (e.g. 'lt', 'en', 'lv').

        The currently-selected locale is a <div> (disabled); other locales
        are <button> elements — we only ever need to click a non-selected one.
        """
        return (By.XPATH,
            f"//button[contains(@class,'popup-button-list__button')]"
            f"[.//span[@data-locale='{lang_code}']]")

    @staticmethod
    def name_field(lang_id: str = None):
        """Product name input — same element for all languages in pim.bo."""
        return ProductEditorSelectors.NAME_FIELD

    @staticmethod
    def description_iframe(lang_id: str = None):
        """HugeRTE iframe for the description field (lang_id unused in pim.bo)."""
        return ProductEditorSelectors.DESCRIPTION_IFRAME

    @staticmethod
    def description_textarea(lang_id: str = None):
        """Hidden textarea backing the HugeRTE editor (lang_id unused in pim.bo)."""
        return ProductEditorSelectors.DESCRIPTION_TEXTAREA


# ---------------------------------------------------------------------------
# Brand / Manufacturer
# ---------------------------------------------------------------------------

class BrandSelectors:
    """Selectors for the manufacturer/brand field on the product editor."""

    # Container wrapping the React Select — click to open the dropdown
    BRAND_DROPDOWN   = (By.CSS_SELECTOR, "#field-manufacturer .rs__control")
    # Text input inside the React Select for searching
    BRAND_SEARCH     = (By.CSS_SELECTOR, "#field-manufacturer input.rs__input")
    # Options that appear in the dropdown after typing
    BRAND_RESULT     = (By.CSS_SELECTOR, ".rs__option")
    # "Add new Manufacturer" button next to the dropdown
    ADD_BRAND_BUTTON = (By.CSS_SELECTOR, "#manufacturer-add-new button")


# ---------------------------------------------------------------------------
# Product Features / Specifications
# ---------------------------------------------------------------------------

class FeatureSelectors:
    """Selectors for the product specifications section (pim.bo template-based).

    pim.bo flow:
      1. Click SPECS_TAB to reveal the specifications block.
      2. Choose the "Dviračiai" template via TEMPLATE_DROPDOWN / TEMPLATE_INPUT.
      3. Click APPLY_TEMPLATE_BUTTON — this pre-creates all spec rows.
      4. Fill each spec's value input, found either by index (spec_value_field) or
         by matching the visible spec-name text (spec_value_by_name).

    Spec rows follow this DOM pattern:
        id="specifications-row-{index}"
          └── id="field-specifications__{index}__specification"  ← React Select (read-only)
                └── div.relationship--single-value__text          ← visible name text
          └── id="field-specifications__{index}__value"           ← plain text input
    """

    # -- Navigation ----------------------------------------------------------

    # Specifications tab: <button class="tabs-field__tab-button">Specifications</button>
    SPECS_TAB = (By.XPATH,
        "//button[contains(@class,'tabs-field__tab-button')"
        " and normalize-space()='Specifications']")

    # -- Template application ------------------------------------------------

    # Native <select> — contains <option value="1">Dviračiai</option>
    TEMPLATE_SELECT = (By.XPATH,
        "//select[.//option[normalize-space()='Dviračiai']]")

    # Apply Template: <button class="btn btn--style-secondary ..."><span class="btn__label">Apply Template</span>
    APPLY_TEMPLATE_BUTTON = (By.XPATH,
        "//button[.//span[contains(@class,'btn__label')"
        " and normalize-space()='Apply Template']]")

    # -- Spec rows -----------------------------------------------------------

    # Used to detect whether the template has already been applied
    FIRST_SPEC_VALUE = (By.ID, "field-specifications__0__value")

    @staticmethod
    def spec_value_field(index: int):
        """Value input for a spec row by zero-based index."""
        return (By.ID, f"field-specifications__{index}__value")

    @staticmethod
    def spec_value_by_name(spec_name: str):
        """
        Locate the value input for a spec by matching the spec name text.

        The name text lives in div.relationship--single-value__text inside each
        specifications-row-N container, and the value input is a sibling input
        with an id ending in __value.

        Matches both exact names (e.g. "Rėmas") and categorized names
        (e.g. "Rėmo komplektacija > Rėmas") by also checking for a
        "> spec_name" suffix.
        """
        return (By.XPATH,
            f"//div[contains(@class,'relationship--single-value__text')"
            f" and (normalize-space()='{spec_name}'"
            f" or contains(normalize-space(), '> {spec_name}'))]"
            f"/ancestor::*[starts-with(@id,'specifications-row-')]"
            f"//input[contains(@id,'__value')]")


# ---------------------------------------------------------------------------
# Product Attributes (pim.bo array field)
# ---------------------------------------------------------------------------

class AttributeSelectors:
    """Selectors for the product-level Attributes section.

    pim.bo flow:
      1. Click ATTRIBUTES_TAB to reveal the attributes block.
      2. Choose the "Dviračiai" template from the select and click Apply Template.
      3. Each attribute row has: Attribute (react-select), Value Text, Value Number,
         Value Boolean, Value Options (multi-select), Measurement Value/Unit.

    DOM pattern:
        id="attributes-row-{index}"
          └── id="field-attributes__{index}__attribute"     ← React Select
                └── div.relationship--single-value__text     ← visible name
          └── id="field-attributes__{index}__valueText"      ← text input (localized)
          └── id="field-attributes__{index}__valueNumber"    ← number input
          └── id="field-attributes__{index}__valueBoolean"   ← checkbox
          └── id="field-attributes__{index}__valueOptions"   ← React Select multi
          └── id="field-attributes__{index}__measurementValue" ← number input
          └── id="field-attributes__{index}__measurementUnit"  ← text input
    """

    # -- Navigation ----------------------------------------------------------

    ATTRIBUTES_TAB = (By.XPATH,
        "//button[contains(@class,'tabs-field__tab-button')"
        " and normalize-space()='Attributes']")

    # -- Template application ------------------------------------------------
    # The template section sits just before the #field-attributes div.

    TEMPLATE_SELECT = (By.XPATH,
        "//div[@id='field-attributes']"
        "/preceding-sibling::div[1]//select")

    APPLY_TEMPLATE_BUTTON = (By.XPATH,
        "//div[@id='field-attributes']"
        "/preceding-sibling::div[1]"
        "//button[.//span[normalize-space()='Apply Template']]")

    # -- Detect existing rows ------------------------------------------------

    FIRST_ATTRIBUTE_ROW = (By.ID, "attributes-row-0")

    ALL_ATTRIBUTE_ROWS = (By.CSS_SELECTOR,
        "div[id^='attributes-row-']")

    # -- Per-row fields by index ---------------------------------------------

    @staticmethod
    def attribute_row(index: int):
        return (By.ID, f"attributes-row-{index}")

    @staticmethod
    def attribute_name(index: int):
        """Visible attribute name text inside the row's react-select."""
        return (By.CSS_SELECTOR,
            f"#attributes-row-{index} .relationship--single-value__text")

    @staticmethod
    def value_text(index: int):
        return (By.ID, f"field-attributes__{index}__valueText")

    @staticmethod
    def value_number(index: int):
        return (By.ID, f"field-attributes__{index}__valueNumber")

    @staticmethod
    def value_boolean(index: int):
        return (By.ID, f"field-attributes__{index}__valueBoolean")

    @staticmethod
    def value_options_control(index: int):
        """React-select control for multi-select Value Options."""
        return (By.CSS_SELECTOR,
            f"#field-attributes__{index}__valueOptions .rs__control")

    @staticmethod
    def value_options_input(index: int):
        """Text input inside the Value Options react-select."""
        return (By.CSS_SELECTOR,
            f"#field-attributes__{index}__valueOptions input.rs__input")

    @staticmethod
    def measurement_value(index: int):
        return (By.ID, f"field-attributes__{index}__measurementValue")

    @staticmethod
    def measurement_unit(index: int):
        return (By.ID, f"field-attributes__{index}__measurementUnit")

    # -- By-name lookups (find row index by attribute name) ------------------

    @staticmethod
    def value_text_by_name(attr_name: str):
        """Locate the Value Text input for an attribute by its display name."""
        return (By.XPATH,
            f"//div[contains(@class,'relationship--single-value__text')"
            f" and normalize-space()='{attr_name}']"
            f"/ancestor::div[starts-with(@id,'attributes-row-')]"
            f"//input[contains(@id,'__valueText')]")

    @staticmethod
    def value_options_input_by_name(attr_name: str):
        """Locate the Value Options react-select input for an attribute by name."""
        return (By.XPATH,
            f"//div[contains(@class,'relationship--single-value__text')"
            f" and normalize-space()='{attr_name}']"
            f"/ancestor::div[starts-with(@id,'attributes-row-')]"
            f"//div[contains(@id,'__valueOptions')]//input[contains(@class,'rs__input')]")

    @staticmethod
    def value_number_by_name(attr_name: str):
        """Locate the Value Number input for an attribute by name."""
        return (By.XPATH,
            f"//div[contains(@class,'relationship--single-value__text')"
            f" and normalize-space()='{attr_name}']"
            f"/ancestor::div[starts-with(@id,'attributes-row-')]"
            f"//input[contains(@id,'__valueNumber')]")

    @staticmethod
    def measurement_value_by_name(attr_name: str):
        return (By.XPATH,
            f"//div[contains(@class,'relationship--single-value__text')"
            f" and normalize-space()='{attr_name}']"
            f"/ancestor::div[starts-with(@id,'attributes-row-')]"
            f"//input[contains(@id,'__measurementValue')]")

    @staticmethod
    def measurement_unit_by_name(attr_name: str):
        return (By.XPATH,
            f"//div[contains(@class,'relationship--single-value__text')"
            f" and normalize-space()='{attr_name}']"
            f"/ancestor::div[starts-with(@id,'attributes-row-')]"
            f"//input[contains(@id,'__measurementUnit')]")


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Variants
# ---------------------------------------------------------------------------

class VariantSelectors:
    """Selectors for the product variants section."""

    # Variants tab button
    VARIANTS_TAB = (By.XPATH,
        "//button[contains(@class,'tabs-field__tab-button')"
        " and normalize-space()='Variants']")

    # All variant option values (the size text inside each variant's Option field).
    # Each variant row (variants-row-N) has a variantAttributes sub-section
    # where the Option relationship shows the size in a single-value__text div.
    VARIANT_OPTION_VALUES = (By.CSS_SELECTOR,
        "#field-variants [id*='variantAttributes'][id*='option'] "
        "div.relationship--single-value__text")


class ImageSelectors:
    """Selectors for the product image upload area."""

    DROPZONE       = (By.ID, "product-images-dropzone")
    EXISTING_IMAGE = (By.CLASS_NAME,
        "dz-preview.disabled.openfilemanager.dz-clickable")

    # Lithuanian name field (lang_id=2) — used to derive the local image folder name
    NAME_FIELD_LT = (By.ID, "form_step1_name_2")
