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
        self.assertFalse(self.screen._table_images_check.isChecked())
        self.assertFalse(self.screen._product_photos_check.isChecked())
        self.assertTrue(self.screen._table_images_check.isHidden())
        self.assertTrue(self.screen._product_photos_check.isHidden())
        self.assertTrue(self.screen._photo_card.isHidden())

    def test_catalogue_scan_never_starts_image_downloads(self):
        self.screen._table_images_check.setChecked(True)
        self.screen._product_photos_check.setChecked(True)

        config = self.screen._create_run_config()

        self.assertFalse(config.download_images)
        self.assertFalse(config.download_product_photos)
        self.assertFalse(self.settings.values["orbea_download_table_images"])
        self.assertFalse(self.settings.values["orbea_download_product_photos"])

    def test_task_sections_show_one_workflow_at_a_time(self):
        expected = {
            "setup": self.screen._setup_page,
            "progress": self.screen._progress_page,
            "photos": self.screen._photos_page,
            "descriptions": self.screen._descriptions_page,
            "results": self.screen._results_page,
        }
        for index, (route, active_page) in enumerate(expected.items()):
            self.screen._switch_section(route)
            self.app.processEvents()
            self.assertEqual(self.screen._section_tabs.currentIndex(), index)
            for page in expected.values():
                self.assertEqual(page.isHidden(), page is not active_page)

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

    def test_activation_refreshes_once_after_login_time_preload(self):
        driver = object()
        self.main.driver = driver
        calls = []
        self.screen.refresh_filter_options = lambda **kwargs: calls.append(kwargs)

        self.screen.on_activated()
        self.screen.on_activated()

        self.assertEqual(calls, [{"show_errors": False}])

    def test_worker_module_does_not_eagerly_import_spreadsheet_or_widget_stacks(self):
        import GUI_Qt.orbea.workers as workers

        self.assertNotIn("openpyxl", workers.__dict__)
        self.assertNotIn("QWidget", workers.__dict__)


if __name__ == "__main__":
    unittest.main()
