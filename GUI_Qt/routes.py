"""Declarative authenticated-page route registry."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Callable

from qfluentwidgets import FluentIcon, NavigationItemPosition


@dataclass(frozen=True)
class RouteSpec:
    key: str
    label_key: str
    group: str
    icon: object
    screen_factory: Callable[[object], object]


@dataclass(frozen=True)
class NavigationGroupSpec:
    """Presentation metadata for a scrolling navigation section."""

    key: str
    label_key: str
    icon: object
    position: NavigationItemPosition = NavigationItemPosition.SCROLL


NAV_GROUPS = (
    NavigationGroupSpec("operations", "nav.group.operations", FluentIcon.TILES),
    NavigationGroupSpec("insights", "nav.group.insights", FluentIcon.VIEW),
    NavigationGroupSpec("product_tools", "nav.group.product_tools", FluentIcon.DEVELOPER_TOOLS),
    NavigationGroupSpec("brand_tools", "nav.group.brand_tools", FluentIcon.TAG),
)


def _lazy(module_name: str, class_name: str, attribute: str):
    def factory(main_window):
        screen = getattr(main_window, attribute, None)
        if screen is None:
            screen_class = getattr(importlib.import_module(module_name), class_name)
            screen = screen_class(main_window)
            setattr(main_window, attribute, screen)
        return screen

    return factory


ROUTES = (
    RouteSpec("product_lookup", "nav.product_lookup", "product_tools", FluentIcon.SEARCH,
              _lazy("GUI_Qt.screens.ProductLookupScreen", "ProductLookupScreen", "product_lookup_screen")),
    RouteSpec("history", "nav.history", "insights", FluentIcon.HISTORY,
              _lazy("GUI_Qt.screens.FullHistoryScreen", "FullHistoryScreen", "full_history_screen")),
    RouteSpec("translations", "nav.translations", "product_tools", FluentIcon.LANGUAGE,
              _lazy("GUI_Qt.screens.TranslationsScreen", "TranslationsScreen", "translations_screen")),
    RouteSpec("earnings", "nav.earnings", "insights", FluentIcon.STOP_WATCH,
              _lazy("GUI_Qt.screens.EarningsScreen", "EarningsScreen", "earnings_screen")),
    RouteSpec("spotify", "nav.spotify", "insights", FluentIcon.CONNECT,
              _lazy("GUI_Qt.screens.SpotifyScreen", "SpotifyScreen", "spotify_screen")),
    RouteSpec("activity", "nav.activity", "insights", FluentIcon.HISTORY,
              _lazy("GUI_Qt.screens.ActivityScreen", "ActivityScreen", "activity_screen")),
    RouteSpec("brand_urls", "layout.url_finder", "brand_tools", FluentIcon.LINK,
              _lazy("GUI_Qt.screens.BrandToolsScreen", "BrandUrlFinderScreen", "brand_url_screen")),
    RouteSpec("brand_images", "layout.image_downloader", "brand_tools", FluentIcon.IMAGE_EXPORT,
              _lazy("GUI_Qt.screens.BrandToolsScreen", "BrandImageDownloaderScreen", "brand_image_screen")),
    RouteSpec("orbea", "nav.orbea", "operations", FluentIcon.ROBOT,
              _lazy("GUI_Qt.screens.OrbeaScreen", "OrbeaScreen", "orbea_screen")),
    RouteSpec("kross", "nav.kross", "operations", FluentIcon.ROBOT,
              _lazy("GUI_Qt.screens.KrossScreen", "KrossScreen", "kross_screen")),
    RouteSpec("account", "nav.account", "system", FluentIcon.PEOPLE,
              _lazy("GUI_Qt.screens.AccountScreen", "AccountScreen", "account_screen")),
    RouteSpec("settings", "nav.settings", "system", FluentIcon.SETTING,
              _lazy("GUI_Qt.screens.SettingsScreen", "SettingsScreen", "settings_screen")),
    RouteSpec("info", "nav.info", "system", FluentIcon.INFO,
              _lazy("GUI_Qt.screens.InfoScreen", "InfoScreen", "info_screen")),
)

ROUTE_REGISTRY = {route.key: route for route in ROUTES}

DEFAULT_ROUTE = "earnings"
ROUTE_ALIASES = {
    "name_getter": "product_lookup",
    "code_getter": "product_lookup",
    "product_name_getter": "product_lookup",
    "spec_checker": "product_lookup",
    "abus_url_getter": "brand_urls",
    "castelli_url_getter": "brand_urls",
    "oakley_url_getter": "brand_urls",
    "basso_images": "brand_images",
    "pinarello_images": "brand_images",
    "castelli_images": "brand_images",
}

# Saved activity links still open the correct brand or lookup tab.
ROUTE_MODES = {
    "name_getter": 0, "code_getter": 1, "product_name_getter": 2, "spec_checker": 3,
    "abus_url_getter": 0, "castelli_url_getter": 1, "oakley_url_getter": 2,
    "basso_images": 0, "pinarello_images": 1, "castelli_images": 2,
}


def resolve_route_key(key: str) -> str:
    return ROUTE_ALIASES.get(str(key or ""), str(key or ""))
