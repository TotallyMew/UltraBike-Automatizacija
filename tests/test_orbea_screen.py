from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QWidget

from GUI_Qt.screens.OrbeaScreen import OrbeaScreen
from tools.orbea_automation import FilterOption, PimboFilterOptions


class _Settings:
    def __init__(self, values):
        self.values = dict(values)

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value):
        self.values[key] = value


class _I18n:
    @staticmethod
    def tr(key, **_kwargs):
        return key


class _Main(QWidget):
    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.i18n = _I18n()
        self.driver = None


class OrbeaScreenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        catalogue = root / "catalogue.xlsx"
        catalogue.touch()
        self.settings = _Settings(
            {
                "orbea_catalogue_path": str(catalogue),
                "orbea_output_root": str(root / "runs"),
                "browser_choice": "Edge",
            }
        )
        self.main = _Main(self.settings)
        self.screen = OrbeaScreen(self.main)
        self.app.processEvents()

    def tearDown(self):
        self.assertTrue(self.screen.shutdown())
        self.screen.deleteLater()
        self.main.deleteLater()
        self.app.processEvents()
        self.temp.cleanup()

    def test_defaults_are_draft_and_in_stock(self):
        state = self.screen._collect_filter_state()
        self.assertEqual(state["statuses"], ["Draft"])
        self.assertEqual(state["stock"], "In stock")
        self.assertEqual(self.screen._search_edit.text(), "orbea")
        self.assertTrue(self.screen._search_edit.isReadOnly())
        self.assertEqual(self.screen._excel_sort_btn.text(), "Sort existing Excel")

    def test_dynamic_ids_and_multi_completeness_reach_typed_config(self):
        options = PimboFilterOptions(
            statuses=(FilterOption("Draft", "Draft"),),
            families=(FilterOption("family-7", "Bicycles"),),
            categories=(
                FilterOption("category-1", "Mountain"),
                FilterOption("category-2", "Mountain"),
            ),
            sources=(FilterOption("source-9", "ERP"),),
            stock=(FilterOption("In stock", "In stock"),),
            completeness_locales=(FilterOption("en", "English"),),
            completeness_buckets=(
                FilterOption("<40%", "<40%"),
                FilterOption("100%", "100%"),
            ),
            sort=(FilterOption("Recent", "Recent"),),
        )
        self.screen._apply_filter_options(options)
        self.screen._family_combo.setCurrentIndex(1)
        self.screen._category_combo.setCurrentIndex(2)
        self.screen._source_combo.setCurrentIndex(1)
        self.screen._locale_combo.setCurrentIndex(0)
        self.screen._bucket_buttons["<40%"].setChecked(True)
        self.screen._bucket_buttons["100%"].setChecked(True)

        config = self.screen._create_run_config()

        self.assertEqual(config.filters.family_id, "family-7")
        self.assertEqual(config.filters.category_id, "category-2")
        self.assertEqual(config.filters.source_id, "source-9")
        self.assertEqual(config.filters.completeness_locale, "en")
        self.assertEqual(config.filters.completeness_buckets, ("<40%", "100%"))
        self.assertEqual(config.browser_name, "edge")
        self.assertEqual(
            (
                config.navigation_timeout,
                config.control_discovery_timeout,
                config.table_render_timeout,
                config.selector_timeout,
                config.image_retry_limit,
            ),
            (25.0, 3.0, 8.0, 5.0, 1),
        )

    def test_shutdown_screen_can_be_reused_after_logout(self):
        self.assertTrue(self.screen.shutdown())
        self.assertTrue(self.screen._closing)
        self.screen.refresh_filter_options(show_errors=False)
        self.assertFalse(self.screen._closing)


if __name__ == "__main__":
    unittest.main()
