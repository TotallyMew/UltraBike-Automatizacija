from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


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
        self.assertEqual(state["product_code_prefix"], "")
        self.assertEqual(self.screen._search_edit.text(), "orbea")
        self.assertTrue(self.screen._search_edit.isReadOnly())
        self.assertEqual(self.screen._excel_sort_btn.text(), "Sort existing Excel")
        self.assertTrue(self.screen._table_images_check.isChecked())
        self.assertTrue(self.screen._product_photos_check.isChecked())
        self.assertFalse(self.screen._table_images_check.isHidden())
        self.assertFalse(self.screen._product_photos_check.isHidden())
        self.assertTrue(self.screen._photo_card.isHidden())

    def test_collection_uses_selected_download_options(self):
        self.screen._table_images_check.setChecked(True)
        self.screen._product_photos_check.setChecked(True)

        config = self.screen._create_run_config()

        self.assertTrue(config.collect_product_data)
        self.assertTrue(config.download_images)
        self.assertTrue(config.download_product_photos)
        self.assertTrue(config.download_description)
        self.assertTrue(config.download_specifications)
        self.screen._table_images_check.setChecked(False)
        self.screen._product_photos_check.setChecked(False)
        self.screen._description_check.setChecked(False)
        self.screen._specifications_check.setChecked(False)
        config = self.screen._create_run_config()
        self.assertFalse(config.download_images)
        self.assertFalse(config.download_product_photos)
        self.assertFalse(config.download_description)
        self.assertFalse(config.download_specifications)
        self.assertEqual(json.loads(self.settings.values["orbea_collection_options"]), dict.fromkeys(("tables", "photos", "description", "specifications"), False))

    def test_missing_saved_optional_catalogue_does_not_block_fresh_scan(self):
        self.main.driver = object()
        self.settings.values["orbea_catalogue_path"] = str(Path(self.temp.name) / "removed.xlsx")
        with patch.object(self.screen, "_detect_catalogue", return_value=""):
            self.screen._load_paths()
        self.screen._update_action_states()
        self.assertEqual(self.screen._catalogue_edit.text(), "")
        self.assertEqual(self.settings.values["orbea_catalogue_path"], "")
        self.assertTrue(self.screen._start_btn.isEnabled())
        self.assertIsNone(self.screen._create_run_config().catalogue_path)

    def test_invalid_catalogue_explains_why_scan_is_disabled(self):
        self.main.driver = object()
        self.screen._catalogue_edit.setText(str(Path(self.temp.name) / "missing.xlsx"))
        self.screen._update_action_states()
        self.assertFalse(self.screen._start_btn.isEnabled())
        self.assertIn("clear this field", self.screen._start_btn.toolTip())

    def test_missing_output_explains_why_scan_is_disabled(self):
        self.main.driver = object()
        self.screen._output_edit.clear()
        self.screen._update_action_states()
        self.assertFalse(self.screen._start_btn.isEnabled())
        self.assertIn("output folder", self.screen._start_btn.toolTip())

    def test_collection_can_start_without_excel_catalogue(self):
        self.main.driver = object()
        self.screen._catalogue_edit.clear()
        self.screen._update_action_states()
        self.assertTrue(self.screen._start_btn.isEnabled())
        self.assertTrue(self.screen._validate_inputs())
        self.assertIsNone(self.screen._create_run_config().catalogue_path)

    def test_primary_scan_reads_current_pimbo_products_instead_of_reusing_saved_scan(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from tools.orbea_automation import OrbeaAutomationService, RunCheckpoint, create_run_directory

        self.screen._catalogue_edit.clear()
        for checkbox in (self.screen._table_images_check, self.screen._product_photos_check,
                         self.screen._description_check, self.screen._specifications_check):
            checkbox.setChecked(False)
        config = self.screen._create_run_config()
        saved = RunCheckpoint.create(create_run_directory(config.output_root), config)
        saved.data["scan_completed"] = True
        saved.save()
        scanned_folders = []

        def collect(_client, _catalogue, checkpoint, _config, **_kwargs):
            scanned_folders.append(checkpoint.run_dir)
            checkpoint.data["scan_completed"] = True
            checkpoint.save()

        self.screen.workflow_controller.service_factory = lambda driver: OrbeaAutomationService(
            driver, website_client_factory=lambda *_args: SimpleNamespace(close=lambda: None)
        )
        self.main.driver = object()
        self.screen._update_action_states()
        with patch("tools.orbea_automation.service.PimboBrowserClient.collect", collect):
            self.screen._start_btn.click()
            self.assertIsNotNone(self.screen._worker)
            self.assertTrue(self.screen._worker.wait(5000))
            self.app.processEvents()

        self.assertEqual(scanned_folders, [self.screen._run_dir])
        self.assertNotEqual(self.screen._run_dir, saved.run_dir)
        self.assertTrue(saved.path.is_file())

    def test_collection_choices_are_restored(self):
        self.settings.values["orbea_collection_options"] = {"tables": False, "photos": True, "description": False, "specifications": True}
        self.screen._load_paths()
        self.assertFalse(self.screen._table_images_check.isChecked())
        self.assertTrue(self.screen._product_photos_check.isChecked())
        self.assertFalse(self.screen._description_check.isChecked())
        self.assertTrue(self.screen._specifications_check.isChecked())

    def test_collection_choices_persist_through_database_settings(self):
        from Database.DatabaseManager import DatabaseManager
        from Database.SettingsManager import SettingsManager

        database = DatabaseManager(Path(self.temp.name) / "settings.db")
        settings = SettingsManager(database)
        self.screen.settings = settings
        restored_main = _Main(settings)
        restored = None
        try:
            self.screen._description_check.setChecked(False)
            self.screen._table_images_check.setChecked(False)
            self.assertFalse(json.loads(settings.get("orbea_collection_options"))["description"])
            restored = OrbeaScreen(restored_main)
            self.assertFalse(restored._description_check.isChecked())
            self.assertFalse(restored._table_images_check.isChecked())
            self.assertTrue(restored._product_photos_check.isChecked())
        finally:
            if restored is not None:
                restored.shutdown()
                restored.deleteLater()
            restored_main.deleteLater()
            self.screen.settings = self.settings
            self.app.processEvents()
            database.close()

    def test_failed_run_keeps_saved_excel_and_folder_available(self):
        from types import SimpleNamespace
        from openpyxl import Workbook

        root = Path(self.temp.name)
        report = root / "orbea_matches.xlsx"
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Matches"
        sheet.append(("Variant SKU", "Pimbo Product", "Catalogue Code", "Year", "Orbea URL"))
        sheet.append(("U10701AA", "Orbea ORCA M30i", "U107TTCC", 2026, "https://www.orbea.com/en-be/orca-m30i"))
        workbook.save(report)
        workbook.close()
        self.screen._closing = True  # Avoid showing an interactive error dialog.
        self.screen._on_partial_result(SimpleNamespace(workbook_path=report, run_dir=root, counts={"scanned": 1}))
        self.screen._on_run_error("Pimbo product row 20 disappeared")
        self.screen._run_thread_finished()
        self.assertEqual(self.screen._workbook_path, report)
        self.assertTrue(self.screen._open_excel_btn.isEnabled())
        self.assertTrue(self.screen._open_folder_btn.isEnabled())
        self.assertEqual(self.screen._table.rowCount(), 1)
        self.assertIn("failed", self.screen._stage_label.text().lower())

    def test_collection_results_and_upload_stay_in_one_automation_page(self):
        self.assertEqual(self.screen._section_tabs.count(), 2)
        for route in ("automation", "setup", "progress", "results", "upload"):
            self.screen._switch_section(route)
            self.app.processEvents()
            self.assertEqual(self.screen._section_tabs.currentIndex(), 0)
            self.assertFalse(self.screen._automation_page.isHidden())
            self.assertTrue(self.screen._tools_page.isHidden())
        self.screen._switch_section("photos")
        self.assertEqual(self.screen._section_tabs.currentIndex(), 1)
        self.assertFalse(self.screen._image_tool.body.isHidden())
        self.assertTrue(self.screen._description_tool.body.isHidden())

    def test_website_verification_is_partial_with_wrapped_instructions(self):
        from unittest.mock import MagicMock

        tracker = MagicMock()
        self.main.operation_tracker = tracker
        self.screen._run_operation_id = "orbea-run"
        self.screen._run_dir = Path(self.temp.name)
        self.screen._on_website_blocked("Complete verification in the Orbea browser; saved Excel is ready.")
        self.assertIn("Orbea", self.screen._stage_label.text())
        self.assertNotIn("failed", self.screen._stage_label.text().lower())
        self.assertTrue(self.screen._progress_label.wordWrap())
        self.assertIn("verification", self.screen._progress_label.text())
        tracker.finish.assert_called_once_with("orbea-run", "partial", output_path=str(self.screen._run_dir), error_summary=self.screen._progress_label.text())

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

    def test_code_prefix_is_saved_restored_and_passed_to_run(self):
        self.screen._code_prefix_edit.setText(" u107 ")
        saved = json.loads(self.settings.values["orbea_filter_preset"])
        self.assertEqual(saved["product_code_prefix"], "u107")
        self.assertEqual(self.screen._create_run_config().product_code_prefix, "U107")

        self.screen._apply_filter_options(PimboFilterOptions())
        self.assertEqual(self.screen._code_prefix_edit.text(), "u107")
        restored = OrbeaScreen(self.main)
        try:
            self.assertEqual(restored._code_prefix_edit.text(), "u107")
            self.screen._set_busy(True)
            self.assertFalse(self.screen._code_prefix_edit.isEnabled())
            self.screen._set_busy(False)
            self.screen._code_prefix_edit.clear()
            self.assertEqual(self.screen._create_run_config().product_code_prefix, "")
        finally:
            restored.shutdown()
            restored.deleteLater()

    def test_activation_refreshes_once_after_login_time_preload(self):
        driver = object()
        self.main.driver = driver
        calls = []
        self.screen.refresh_filter_options = lambda **kwargs: calls.append(kwargs)

        self.screen.on_activated()
        self.screen.on_activated()

        self.assertEqual(calls, [{"show_errors": False}])

    def test_resume_is_clickable_without_pimbo_and_restores_saved_settings(self):
        from dataclasses import replace
        from types import SimpleNamespace
        from unittest.mock import MagicMock, patch
        from tools.orbea_automation import OrbeaAutomationService, RunCheckpoint, create_run_directory, PimboFilterSpec
        from tools.orbea_automation.website import parse_website_product

        config = replace(self.screen._create_run_config(), product_code_prefix="U", filters=PimboFilterSpec(stock="Any"),
            download_images=False, download_product_photos=False, download_description=False, download_specifications=False)
        saved = RunCheckpoint.create(create_run_directory(config.output_root), config)
        url = "https://www.orbea.com/en-be/orca-m30i"
        saved.upsert_result({"row_key": "p1", "product_id": "p1", "sku": "U10707SV", "title": "Orbea ORCA M30i Black",
            "status": "code_match", "catalogue_url": url, "catalogue_model": "ORCA M30i", "website_lookup_status": "done"})
        saved.data["scan_completed"] = True
        saved.save()
        self.screen._catalogue_edit.setText(str(Path(self.temp.name) / "missing.xlsx"))
        self.screen._code_prefix_edit.setText("T")
        self.main.driver = None
        self.main.try_acquire_browser_lease = MagicMock(return_value=False)
        product = parse_website_product('<main><h1>ORCA M30i</h1><script type="application/ld+json">{"@type":"Product","name":"ORCA M30i","sku":"U10707SV"}</script></main>', url)
        website = SimpleNamespace(fetch=lambda _: product, close=lambda: None)
        drivers = []
        def service(driver):
            drivers.append(driver)
            return OrbeaAutomationService(driver, website_client_factory=lambda *_: website)
        self.screen.workflow_controller.service_factory = service
        self.screen._update_action_states()
        self.assertTrue(self.screen._resume_btn.isEnabled())
        self.assertFalse(self.screen._start_btn.isEnabled())
        with patch("tools.orbea_automation.service.PimboBrowserClient.collect", side_effect=AssertionError("must not rescan")):
            self.screen._resume_btn.click()
            self.assertIsNotNone(self.screen._worker)
            self.assertTrue(self.screen._worker.wait(5000))
            self.app.processEvents()
        self.assertEqual(drivers, [None])
        self.main.try_acquire_browser_lease.assert_not_called()
        self.assertEqual(self.screen._run_dir, saved.run_dir)
        self.assertEqual(self.screen._code_prefix_edit.text(), "U")
        self.assertEqual(self.screen._collect_filter_state()["stock"], "Any")
        self.assertFalse(self.screen._table_images_check.isChecked())
        self.assertTrue(self.screen._workbook_path.is_file())

    def test_saved_scan_does_not_start_filter_discovery_or_disable_resume(self):
        from unittest.mock import MagicMock
        from tools.orbea_automation import RunCheckpoint, create_run_directory
        config = self.screen._create_run_config()
        saved = RunCheckpoint.create(create_run_directory(config.output_root), config)
        saved.data["scan_completed"] = True
        saved.save()
        self.main.driver = object()
        self.screen.refresh_filter_options = MagicMock()
        self.screen.on_activated()
        self.screen.refresh_filter_options.assert_not_called()
        self.assertTrue(self.screen._resume_btn.isEnabled())

    def test_retry_matched_reopens_completed_run_without_pimbo_and_refreshes_specs(self):
        from dataclasses import replace
        from types import SimpleNamespace
        from unittest.mock import MagicMock
        from tools.orbea_automation import OrbeaAutomationService, RunCheckpoint, create_run_directory
        from tools.orbea_automation.website import parse_website_product, SPECIFICATIONS_CAPTURE_VERSION

        config = replace(self.screen._create_run_config(), catalogue_path=None,
            download_images=False, download_product_photos=False, download_description=False, download_specifications=True)
        saved = RunCheckpoint.create(create_run_directory(config.output_root), config)
        url = "https://www.orbea.com/en-be/orca-m30i"
        folder = saved.run_dir / "products" / "U10707SV"
        folder.mkdir(parents=True)
        specs = folder / "specifications.txt"
        specs.write_text("Frame: Bad old data")
        saved.upsert_result({"row_key": "p1", "product_id": "p1", "sku": "U10707SV", "title": "Orbea ORCA M30i Black",
            "status": "code_match", "catalogue_url": url, "catalogue_model": "ORCA M30i", "website_lookup_status": "done",
            "collection_stages": {"specifications": {"status": "downloaded", "capture_version": SPECIFICATIONS_CAPTURE_VERSION,
                                                       "files": [str(specs)]}}})
        saved.data.update(scan_completed=True, website_lookup_completed=True)
        saved.mark_completed()
        self.main.try_acquire_browser_lease = MagicMock(return_value=False)
        product = parse_website_product('<main><h1>ORCA M30i</h1><script type="application/ld+json">'
            '{"@type":"Product","name":"ORCA M30i","sku":"U10707SV",'
            '"additionalProperty":[{"name":"Frame","value":"Correct configuration"}]}</script></main>', url)
        website = SimpleNamespace(fetch=lambda _: product, close=lambda: None)
        self.screen.workflow_controller.service_factory = lambda driver: OrbeaAutomationService(driver, website_client_factory=lambda *_: website)
        self.screen._update_action_states()
        self.assertFalse(self.screen._resume_btn.isEnabled())
        self.assertFalse(self.screen._retry_btn.isEnabled())
        self.assertTrue(self.screen._retry_matched_btn.isEnabled())
        self.assertIn("successful", self.screen._retry_matched_btn.toolTip())
        with patch("tools.orbea_automation.service.PimboBrowserClient.collect", side_effect=AssertionError("must not rescan")):
            self.screen._retry_matched_btn.click()
            self.assertTrue(self.screen._worker.retry_matched)
            self.assertFalse(self.screen._retry_matched_btn.isEnabled())
            self.assertTrue(self.screen._worker.wait(5000))
            self.app.processEvents()
        self.main.try_acquire_browser_lease.assert_not_called()
        self.assertEqual(self.screen._run_dir, saved.run_dir)
        self.assertEqual(specs.read_text().strip(), "Frame: Correct configuration")
        self.assertTrue(self.screen._retry_matched_btn.isEnabled())

    def test_retry_matched_chooses_latest_run_with_matches_and_ignores_empty_run(self):
        from tools.orbea_automation import RunCheckpoint, create_run_directory
        config = self.screen._create_run_config()
        saved = RunCheckpoint.create(create_run_directory(config.output_root), config)
        saved.upsert_result({"row_key": "p1", "product_id": "p1", "sku": "U10707SV",
            "status": "code_match", "catalogue_url": "https://www.orbea.com/en-be/orca-m30i"})
        saved.mark_completed()
        empty = RunCheckpoint.create(create_run_directory(config.output_root), config)
        self.screen._update_action_states()
        self.assertEqual(self.screen._saved_resume_config(retry_matched=True).resume_run_dir, saved.run_dir)
        self.assertEqual(self.screen._saved_resume_config().resume_run_dir, empty.run_dir)
        self.assertTrue(self.screen._retry_matched_btn.isEnabled())

    def test_resume_requires_login_only_for_unfinished_pimbo_scan(self):
        from tools.orbea_automation import RunCheckpoint, create_run_directory
        config = self.screen._create_run_config()
        saved = RunCheckpoint.create(create_run_directory(config.output_root), config)
        self.screen._update_action_states()
        self.assertFalse(self.screen._resume_btn.isEnabled())
        self.assertIn("Log in to Pimbo", self.screen._resume_hint.text())
        self.main.driver = object()
        self.screen.on_activated = lambda: None
        self.screen._update_action_states()
        self.assertTrue(self.screen._resume_btn.isEnabled())

    def test_no_saved_run_displays_reason_below_disabled_resume(self):
        self.screen._update_action_states()
        self.assertFalse(self.screen._resume_btn.isEnabled())
        self.assertIn("output folder", self.screen._resume_hint.text())
        self.assertFalse(self.screen._retry_matched_btn.isEnabled())
        self.assertIn("matched products", self.screen._retry_matched_btn.toolTip())

    def test_worker_module_does_not_eagerly_import_spreadsheet_or_widget_stacks(self):
        import GUI_Qt.orbea.workers as workers

        self.assertNotIn("openpyxl", workers.__dict__)
        self.assertNotIn("QWidget", workers.__dict__)


if __name__ == "__main__":
    unittest.main()
