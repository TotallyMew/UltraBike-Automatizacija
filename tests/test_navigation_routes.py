import unittest
from unittest.mock import patch

from PySide6.QtCore import QMargins
from qfluentwidgets import FluentIcon, NavigationItemPosition

from GUI_Qt.MainWindow import MainWindow
from GUI_Qt.routes import NAV_GROUPS, ROUTES


class _Signal:
    def connect(self, callback):
        self.callback = callback


class _Font:
    def setWeight(self, _weight):
        pass


class _Icon:
    def isNull(self):
        return False


class _Item:
    def __init__(self, text="", parent_route=None, is_group=False):
        self.isSelected = False
        self.selectedChanged = _Signal()
        self._text = text
        self._parent_route = parent_route
        self._is_group = is_group
        self._properties = {}
        self.tooltip = ""
        self.accessible_name = ""

    def setTextColor(self, *_args):
        pass

    def setIndicatorColor(self, *_args):
        pass

    def font(self):
        return _Font()

    def setFont(self, _font):
        pass

    def update(self):
        pass

    def setText(self, text):
        self._text = text

    def text(self):
        return self._text

    def setToolTip(self, text):
        self.tooltip = text

    def setAccessibleName(self, text):
        self.accessible_name = text

    def setProperty(self, key, value):
        self._properties[key] = value

    def property(self, key):
        return self._properties.get(key)

    def _margins(self):
        return QMargins(28 if self._parent_route else 0, 0, 20 if self._is_group else 0, 0)

    def icon(self):
        return _Icon()


class _Navigation:
    def __init__(self):
        self.callbacks = {}
        self.positions = {}
        self.parents = {}
        self.icons = {}
        self.items = {}

    def addItem(
        self,
        *,
        routeKey,
        onClick=None,
        position=None,
        parentRouteKey=None,
        icon=None,
        text="",
        selectable=True,
        **_kwargs,
    ):
        self.positions[routeKey] = position
        self.parents[routeKey] = parentRouteKey
        self.icons[routeKey] = icon
        item = _Item(text, parentRouteKey, is_group=not selectable)
        self.items[routeKey] = item
        if onClick is not None:
            self.callbacks[routeKey] = onClick
        return item

    def addSeparator(self, *_args, **_kwargs):
        # Skip construction of the decorative Qt footer in this unit test.
        raise RuntimeError("footer not needed")


class _I18n:
    def tr(self, key):
        return key


class _Window:
    NAVIGATION_EXPAND_WIDTH = MainWindow.NAVIGATION_EXPAND_WIDTH
    _apply_nav_item_text = MainWindow._apply_nav_item_text
    _refresh_nav_item_text = MainWindow._refresh_nav_item_text
    _set_nav_item_text = MainWindow._set_nav_item_text
    _retranslate_navigation = MainWindow._retranslate_navigation

    def __init__(self):
        self.navigationInterface = _Navigation()
        self.i18n = _I18n()
        self.opened = []

    def open_route(self, key):
        self.opened.append(key)


class _Metrics:
    def elidedText(self, text, _mode, width):
        return text if len(text) * 10 <= width else text[:8] + "…"


class NavigationRouteTests(unittest.TestCase):
    def test_sidebar_click_boolean_does_not_replace_captured_route(self):
        window = _Window()
        MainWindow._init_navigation(window)

        for route in ROUTES:
            window.navigationInterface.callbacks[route.key](True)

        self.assertEqual(window.opened, [route.key for route in ROUTES])

    def test_sidebar_group_membership_and_order(self):
        expected = {
            "operations": ["upload", "batch", "descriptions", "folders", "translations"],
            "insights": ["history", "earnings", "spotify", "activity"],
            "product_tools": ["name_getter", "code_getter", "product_name_getter", "spec_checker"],
            "brand_tools": [
                "basso_images",
                "pinarello_images",
                "castelli_url_getter",
                "castelli_images",
                "abus_url_getter",
                "oakley_url_getter",
                "orbea",
            ],
            "system": ["account", "settings", "info"],
        }

        for group, route_keys in expected.items():
            self.assertEqual([route.key for route in ROUTES if route.group == group], route_keys)

    def test_functional_groups_scroll_and_system_routes_are_standalone_bottom_items(self):
        window = _Window()
        MainWindow._init_navigation(window)

        for group in NAV_GROUPS:
            key = f"nav_group_{group.key}"
            self.assertEqual(window.navigationInterface.positions[key], NavigationItemPosition.SCROLL)
            self.assertIsNone(window.navigationInterface.parents[key])

        self.assertNotIn("nav_group_system", window.navigationInterface.positions)
        for route in (route for route in ROUTES if route.group == "system"):
            self.assertEqual(
                window.navigationInterface.positions[route.key],
                NavigationItemPosition.BOTTOM,
            )
            self.assertIsNone(window.navigationInterface.parents[route.key])

    def test_sidebar_uses_semantic_group_and_route_icons(self):
        self.assertEqual(
            {group.key: group.icon for group in NAV_GROUPS},
            {
                "operations": FluentIcon.TILES,
                "insights": FluentIcon.VIEW,
                "product_tools": FluentIcon.DEVELOPER_TOOLS,
                "brand_tools": FluentIcon.TAG,
            },
        )
        route_icons = {route.key: route.icon for route in ROUTES}
        self.assertEqual(route_icons["earnings"], FluentIcon.STOP_WATCH)
        self.assertEqual(route_icons["spotify"], FluentIcon.CONNECT)
        self.assertEqual(route_icons["activity"], FluentIcon.HISTORY)
        self.assertEqual(route_icons["folders"], FluentIcon.FOLDER_ADD)
        self.assertEqual(route_icons["code_getter"], FluentIcon.CODE)
        self.assertEqual(route_icons["orbea"], FluentIcon.ROBOT)
        for key in ("castelli_url_getter", "abus_url_getter", "oakley_url_getter"):
            self.assertEqual(route_icons[key], FluentIcon.LINK)
        for key in ("basso_images", "pinarello_images", "castelli_images"):
            self.assertEqual(route_icons[key], FluentIcon.IMAGE_EXPORT)

    def test_navigation_refresh_covers_every_group_and_route(self):
        window = _Window()
        window._nav_items = {
            **{f"nav_group_{group.key}": _Item() for group in NAV_GROUPS},
            **{route.key: _Item() for route in ROUTES},
        }

        MainWindow._retranslate_navigation(window)

        expected_keys = {
            *(f"nav_group_{group.key}" for group in NAV_GROUPS),
            *(route.key for route in ROUTES),
        }
        self.assertEqual(set(window._nav_items), expected_keys)
        for group in NAV_GROUPS:
            self.assertEqual(window._nav_items[f"nav_group_{group.key}"].text(), group.label_key)
        for route in ROUTES:
            self.assertEqual(window._nav_items[route.key].text(), route.label_key)

        MainWindow._retranslate_navigation(window, "lt")
        self.assertEqual(window._nav_items["nav_group_insights"].text(), "Įžvalgos")
        self.assertEqual(
            window._nav_items["product_name_getter"].text(),
            "Eksportuoti produktų pavadinimus",
        )

    def test_long_labels_elide_but_keep_full_tooltip_and_accessible_name(self):
        window = _Window()
        item = _Item(parent_route="nav_group_product_tools")
        full_text = "Eksportuoti produktų pavadinimus"

        with patch("GUI_Qt.MainWindow.QFontMetrics", return_value=_Metrics()):
            MainWindow._apply_nav_item_text(window, item, full_text)

        self.assertTrue(item.text().endswith("…"))
        self.assertEqual(item.tooltip, full_text)
        self.assertEqual(item.accessible_name, full_text)
        self.assertEqual(item.property("fullNavigationText"), full_text)


if __name__ == "__main__":
    unittest.main()
