"""Shared selectors for login, product lists, and supplier websites.

Product-page selectors intentionally live only in ``PimboProductEditor`` so
the current PIMBO write boundary cannot drift across multiple registries.
"""

from selenium.webdriver.common.by import By


class LoginSelectors:
    """Current PIMBO dashboard login page."""

    URL = "https://pim.bo.ultrabike.lt/dashboard/login"
    EMAIL = (By.ID, "email")
    PASSWORD = (By.ID, "password")
    SUBMIT = (By.CSS_SELECTOR, "button[type='submit']")


class ProductListSelectors:
    """Current PIMBO product search and result list."""

    URL = "https://pim.bo.ultrabike.lt/dashboard/products"
    NAV_PRODUCTS = (By.CSS_SELECTOR, "a[href='/dashboard/products']")
    SEARCH_NAME = (By.CSS_SELECTOR, "input[placeholder='Search...']")
    PRODUCT_TABLE = (By.CSS_SELECTOR, "table")
    PRODUCT_ROW = (By.CSS_SELECTOR, "tbody tr[data-slot='table-row']")
    PRODUCT_ROWS = PRODUCT_ROW
    NEXT_PAGE = (
        By.XPATH,
        "//button[normalize-space()='Next' and not(@disabled) and not(@data-disabled)]",
    )

    @staticmethod
    def _xpath_literal(value: str) -> str:
        if "'" not in value:
            return f"'{value}'"
        if '"' not in value:
            return f'"{value}"'
        parts = value.split("'")
        return "concat(" + ', "\'", '.join(f"'{part}'" for part in parts) + ")"

    @staticmethod
    def product_row_by_code(code: str):
        """Locate a result row by its exact External ID/SKU text."""

        clean_code = code.strip()
        code_literal = ProductListSelectors._xpath_literal(clean_code)
        code_with_space = ProductListSelectors._xpath_literal(f"{clean_code} ")
        return (
            By.XPATH,
            "//tr[@data-slot='table-row' and ("
            ".//span[contains(concat(' ', normalize-space(@class), ' '), ' font-mono ')"
            f" and (normalize-space()={code_literal} or starts-with(normalize-space(), {code_with_space}))]"
            f" or contains(normalize-space(.), {code_literal})"
            ")]",
        )

    @staticmethod
    def product_link_by_brand(brand: str):
        """Locate the visible product title within a result row."""

        brand_lower = brand.lower()
        literal = ProductListSelectors._xpath_literal(brand_lower)
        return (
            By.XPATH,
            ".//span[contains(concat(' ', normalize-space(@class), ' '), ' font-medium ')"
            f" and (not(string-length({literal}))"
            " or contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', "
            f"'abcdefghijklmnopqrstuvwxyz'), {literal}))]",
        )


class CastelliSelectors:
    """Selectors for castelli-cycling.com product URL lookup."""

    BASE_URL = "https://www.castelli-cycling.com/LT/en/#"
    SEARCH_URL = "https://www.castelli-cycling.com/LT/en/search?text={query}"
    SEARCH_INPUT = (By.CSS_SELECTOR, "input.js-site-search-input[name='text']")
    SEARCH_ARROW = (By.CSS_SELECTOR, ".search-button-arrow")
    PRODUCT_LINK = (
        By.CSS_SELECTOR,
        "a[href*='/p/'][onclick*='productClick'], .carousel-item.active a[href*='/p/']",
    )
    NO_RESULTS = (
        By.XPATH,
        "//*[contains(normalize-space(), 'No results found for keyword')]",
    )
    COUNTRY_SELECT = (By.ID, "kl-md-choose-country")
    LANGUAGE_SELECT = (By.ID, "kl-md-choose-lang")
    COUNTRY_CHOOSE_BUTTON = (
        By.CSS_SELECTOR,
        ".kl-modal-content button[type='submit'], .kl-modal-content button.cta",
    )
    SEARCH_OPEN_CANDIDATES = [
        (By.CSS_SELECTOR, "li.nav-item.nav-icon.search-icon > a.nav-link"),
        (By.CSS_SELECTOR, "li.search-icon a"),
        (By.CSS_SELECTOR, "i[title='Search']"),
        (By.CSS_SELECTOR, ".js-search-open"),
        (By.CSS_SELECTOR, ".search-button"),
        (By.CSS_SELECTOR, ".search-icon"),
        (By.CSS_SELECTOR, "button[aria-label*='Search']"),
        (By.CSS_SELECTOR, "a[aria-label*='Search']"),
        (By.XPATH, "//button[contains(normalize-space(), 'Search')]"),
    ]
    COOKIE_BUTTON_CANDIDATES = [
        (By.ID, "onetrust-accept-btn-handler"),
        (By.ID, "CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll"),
        (By.CSS_SELECTOR, "button#acceptCookie, button.accept-cookie, button.cookie-accept, button.cookie-accept-all"),
        (By.CSS_SELECTOR, ".cookie button.primary, .cookies button.primary, .cookie-banner button.primary, .cookie-consent button.primary"),
        (By.CSS_SELECTOR, "[data-testid='uc-accept-all-button'], [data-testid='accept-all-button']"),
        (By.XPATH, "//button[contains(translate(normalize-space(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'accept')]"),
        (By.XPATH, "//button[contains(translate(normalize-space(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'allow all')]"),
        (By.XPATH, "//button[contains(translate(normalize-space(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'agree')]"),
        (By.XPATH, "//button[contains(translate(normalize-space(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'continue')]"),
        (By.XPATH, "//button[normalize-space()='OK' or normalize-space()='Ok' or normalize-space()='ok']"),
        (By.XPATH, "//button[contains(translate(normalize-space(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'accetta')]"),
        (By.XPATH, "//button[contains(translate(normalize-space(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'sutinku')]"),
    ]


class CastelliImageSelectors:
    """Selectors for castelli-cycling.com product image downloads."""

    PRODUCT_IMAGE = "#colLeft.mosaic img[src], .mosaic#colLeft img[src], #colLeft img[src]"


class AbusSelectors:
    """Selectors for abus.com product URL lookup."""

    BASE_URL = "https://www.abus.com/int"
    SEARCH_URL = "https://www.abus.com/int/find?search={query}"
    DIRECT_PRODUCT_URL = "https://www.abus.com/int/product/{query}"
    SEARCH_URL_CANDIDATES = [SEARCH_URL]
    SEARCH_INPUT_CANDIDATES = [
        (By.CSS_SELECTOR, "input[type='search']"),
        (By.CSS_SELECTOR, "input[name='q']"),
        (By.CSS_SELECTOR, "input[name='query']"),
        (By.CSS_SELECTOR, "input[name='search']"),
        (By.CSS_SELECTOR, "input[placeholder*='Search']"),
        (By.CSS_SELECTOR, "input[placeholder*='What are you looking for']"),
        (By.XPATH, "//input[contains(translate(@placeholder, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'search')]"),
        (By.XPATH, "//input[contains(translate(@placeholder, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'looking for')]"),
    ]
    SEARCH_OPEN_CANDIDATES = [
        (By.CSS_SELECTOR, "button[aria-label*='Search']"),
        (By.CSS_SELECTOR, "a[aria-label*='Search']"),
        (By.CSS_SELECTOR, "button[title*='Search']"),
        (By.CSS_SELECTOR, "a[title*='Search']"),
        (By.CSS_SELECTOR, ".search button, .search a, .search-toggle, .search-icon"),
        (By.XPATH, "//button[contains(translate(normalize-space(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'search')]"),
        (By.XPATH, "//a[contains(translate(normalize-space(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'search')]"),
    ]
    SHOW_ALL_RESULTS = [
        (By.XPATH, "//button[contains(translate(normalize-space(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'show all results')]"),
        (By.XPATH, "//a[contains(translate(normalize-space(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'show all results')]"),
    ]
    PRODUCT_CARD = (
        By.CSS_SELECTOR,
        ".column--card-search-result a.card[href], a.card[href*='/int/Consumer/']",
    )
    PRODUCT_LINK = (
        By.CSS_SELECTOR,
        ".column--card-search-result a.card[href], a.card[href*='/int/Consumer/'], a[href*='/int/product/'], a[href*='/int/Consumer/']",
    )
    NESTED_VARIANT_LINK = (By.CSS_SELECTOR, "[data-nested-link]")
    NO_RESULTS = (
        By.XPATH,
        "//*[contains(translate(normalize-space(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'no results') or contains(translate(normalize-space(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'not found')]",
    )
    COOKIE_BUTTON_CANDIDATES = [
        (By.ID, "onetrust-accept-btn-handler"),
        (By.ID, "CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll"),
        (By.CSS_SELECTOR, "button#acceptCookie, button.accept-cookie, button.cookie-accept, button.cookie-accept-all"),
        (By.CSS_SELECTOR, ".cookie button.primary, .cookies button.primary, .cookie-banner button.primary, .cookie-consent button.primary"),
        (By.CSS_SELECTOR, "[data-testid='uc-accept-all-button'], [data-testid='accept-all-button']"),
        (By.XPATH, "//button[contains(translate(normalize-space(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'accept')]"),
        (By.XPATH, "//button[contains(translate(normalize-space(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'allow all')]"),
        (By.XPATH, "//button[contains(translate(normalize-space(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'agree')]"),
        (By.XPATH, "//button[normalize-space()='OK' or normalize-space()='Ok' or normalize-space()='ok']"),
    ]


class OakleySelectors:
    """Selectors for oakley.com product URL lookup."""

    BASE_URL = "https://www.oakley.com"
    SEARCH_URL = "https://www.oakley.com/en-eu/search?text={query}"
    SEARCH_OPEN = (
        By.CSS_SELECTOR,
        ".oo-hdr-search a[aria-label='Search'], .oo-open-hdr-search a, [data-element-id='MainNav_Search'] a",
    )
    SEARCH_INPUT = (
        By.CSS_SELECTOR,
        "input.search-text.search-input-modal[name='text']",
    )
    SEARCH_SUBMIT = (
        By.CSS_SELECTOR,
        "form.search-box button[type='submit'], .search-submit-btn",
    )
    PRODUCT_LINK = (
        By.CSS_SELECTOR,
        "#so-search-result .so-item a[href*='/product/'], #so-search-result-mobile a[href*='/product/']",
    )
    NO_RESULTS = (
        By.XPATH,
        "//*[contains(concat(' ', normalize-space(@class), ' '), ' results-noMatch ')"
        " and not(contains(concat(' ', normalize-space(@class), ' '), ' hide '))]",
    )
    COOKIE_BUTTON_CANDIDATES = [
        (By.ID, "onetrust-accept-btn-handler"),
        (By.CSS_SELECTOR, "button#acceptCookie, button.accept-cookie, button.cookie-accept, button.cookie-accept-all"),
        (By.CSS_SELECTOR, "[data-testid='uc-accept-all-button'], [data-testid='accept-all-button']"),
        (By.XPATH, "//button[contains(translate(normalize-space(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'accept')]"),
        (By.XPATH, "//button[contains(translate(normalize-space(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'allow all')]"),
        (By.XPATH, "//button[contains(translate(normalize-space(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'agree')]"),
        (By.XPATH, "//button[normalize-space()='OK' or normalize-space()='Ok' or normalize-space()='ok']"),
    ]
