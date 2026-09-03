from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QWidget

from GUI_Qt.kross.workers import (
    KrossDiscoveryWorker, KrossSkuCollectionWorker, KrossUploadWorker,
)
from GUI_Qt.screens.KrossScreen import KrossScreen
from Managers.PimboProductEditor import PimPreparationResult, PimPreparationStatus
from tools.kross_automation import (
    KrossAutomationService, KrossCollectionOptions, KrossDiscoveryResult,
    KrossMatch, KrossUploadResult, KrossWorkflowOptions,
)


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


class KrossScreenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.settings = _Settings({"kross_download_path": self.temp.name})
        self.main = _Main(self.settings)
        self.screen = KrossScreen(self.main)
        self.app.processEvents()

    def tearDown(self):
        self.assertTrue(self.screen.shutdown())
        self.screen.deleteLater()
        self.main.deleteLater()
        self.app.processEvents()
        self.temp.cleanup()

    def test_collection_starts_from_filters_and_local_output(self):
        self.assertTrue(self.screen._collect_button.isEnabled())
        self.assertEqual(("Draft",), self.screen._filter_spec().statuses)
        self.assertEqual(
            ("product_photos", "dimensions", "description_source", "specifications_source"),
            tuple(
                name
                for name, checkbox in self.screen._collection_checks.items()
                if checkbox.isChecked()
            ),
        )

    def test_pasted_skus_are_normalized_and_enable_manual_collection(self):
        self.assertFalse(self.screen._collect_skus_button.isEnabled())

        self.screen._manual_skus_input.setPlainText(
            "krtr1z28x17m003989, KRTR1Z28X17M003989\nKRAL2Z28X58M009346"
        )
        self.app.processEvents()

        self.assertEqual(
            ("KRTR1Z28X17M003989", "KRAL2Z28X58M009346"),
            self.screen._manual_skus(),
        )
        self.assertTrue(self.screen._collect_skus_button.isEnabled())
        self.assertTrue(self.screen._load_pasted_local_button.isEnabled())

    def test_pasted_sku_can_load_an_existing_local_package_without_collection(self):
        local_match = KrossMatch(
            "KRIX3Z29X18W009542",
            "local_ready",
            kross_url="https://kross.pl/influx-hybrid-3-0",
            variant_skus=(
                "KRIX3Z29X18W009542",
                "KRIX3Z29X19W009543",
            ),
            local_folder=str(Path(self.temp.name) / "KRIX3Z29X18W009542"),
        )
        self.screen._manual_skus_input.setPlainText(
            "KRIX3Z29X19W009543\nMISSING-SKU"
        )

        with patch.object(
            KrossAutomationService,
            "load_local_packages",
            return_value=KrossDiscoveryResult((local_match,)),
        ):
            self.screen._load_pasted_local_packages()

        self.assertEqual(1, self.screen._table.rowCount())
        self.assertEqual(
            "KRIX3Z29X18W009542",
            self.screen._table.item(0, 3).text(),
        )
        self.assertIn("kross.manual.loaded_local", self.screen._log.toPlainText())
        self.assertIn("kross.manual.local_missing", self.screen._log.toPlainText())

    def test_successful_upload_row_is_unchecked_for_resume(self):
        match = KrossMatch(
            "SKU-1",
            "local_ready",
            pimbo_product_id="p-1",
            local_folder=self.temp.name,
        )
        self.screen._populate_table((match,))
        self.screen._active_upload_total = 1
        result = KrossUploadResult(
            match,
            PimPreparationResult(
                product_code=match.sku,
                product_id=match.pimbo_product_id,
                status=PimPreparationStatus.SAVED_AUTOMATICALLY,
            ),
        )

        self.screen._on_upload_result(result)

        self.assertEqual(
            Qt.CheckState.Unchecked,
            self.screen._table.item(0, 0).checkState(),
        )

    def test_only_complete_matches_are_selected_for_save(self):
        matches = (
            KrossMatch(
                "SKU-1", "found", pimbo_product_url="https://pim.bo.ultrabike.lt/dashboard/products/p-1",
                kross_url="https://kross.pl/example",
            ),
            KrossMatch("SKU-2", "kross_not_found"),
        )
        self.screen._matches = {match.sku: match for match in matches}
        self.screen._populate_table(matches)
        self.assertEqual((matches[0],), self.screen._selected_ready_matches())
        self.assertTrue(self.screen._upload_button.isEnabled())
        self.assertEqual(Path(self.temp.name), Path(self.screen._output_input.text()))

    def test_stages_can_be_selected_individually_or_all_together(self):
        match = KrossMatch(
            "SKU-1",
            "found",
            pimbo_product_url="https://pim.bo.ultrabike.lt/dashboard/products/p-1",
            kross_url="https://kross.pl/example",
        )
        self.screen._matches = {match.sku: match}
        self.screen._populate_table((match,))

        self.assertEqual(
            KrossWorkflowOptions.STAGES,
            self.screen._workflow_options().selected_stages,
        )
        self.assertTrue(self.screen._output_input.isEnabled())

        self.screen._set_all_stages(False)
        self.assertFalse(self.screen._workflow_options().any_selected)
        self.assertFalse(self.screen._upload_button.isEnabled())
        self.assertTrue(self.screen._output_input.isEnabled())

        self.screen._stage_checks["brand"].setChecked(True)
        self.app.processEvents()
        self.assertEqual(("brand",), self.screen._workflow_options().selected_stages)
        self.assertTrue(self.screen._upload_button.isEnabled())
        self.assertTrue(self.screen._output_input.isEnabled())

        self.screen._stage_checks["product_photos"].setChecked(True)
        self.app.processEvents()
        self.assertTrue(self.screen._output_input.isEnabled())

    def test_results_table_has_readable_product_columns(self):
        match = KrossMatch(
            "SKU-2",
            "collected",
            pimbo_product_name="KROSS Alta 2.0",
            pimbo_product_url="https://pim.bo.ultrabike.lt/dashboard/products/p-2",
            kross_product_name="Alta 2.0",
            kross_url="https://kross.pl/alta-2-0",
            variant_skus=("SKU-1", "SKU-2", "SKU-3"),
            local_folder=self.temp.name,
        )

        self.screen._populate_table((match,))

        self.assertGreaterEqual(self.screen._table.minimumHeight(), 360)
        self.assertEqual("KROSS Alta 2.0", self.screen._table.item(0, 1).text())
        self.assertEqual("SKU-1, SKU-2, SKU-3", self.screen._table.item(0, 2).text())
        self.assertEqual("SKU-2", self.screen._table.item(0, 3).text())

    def test_multi_product_partial_run_requires_save(self):
        matches = tuple(
            KrossMatch(
                f"SKU-{index}",
                "found",
                pimbo_product_url=f"https://pim.bo.ultrabike.lt/dashboard/products/p-{index}",
                kross_url=f"https://kross.pl/example-{index}",
            )
            for index in (1, 2)
        )
        self.screen._matches = {match.sku: match for match in matches}
        self.screen._populate_table(matches)
        self.screen._set_all_stages(False)
        self.screen._stage_checks["brand"].setChecked(True)
        errors = []
        self.screen._show_error = errors.append

        self.screen._start_upload()

        self.assertEqual(["kross.stages.multi_requires_save"], errors)
        self.assertIsNone(self.screen._upload_worker)

    def test_discovery_worker_does_not_require_upload_state(self):
        result = KrossDiscoveryResult((KrossMatch("SKU-1", "kross_not_found"),))

        class _Service:
            def discover(self, skus, *, progress):
                self.skus = tuple(skus)
                progress(1, 1, "Checked SKU-1")
                return result

        service = _Service()
        worker = KrossDiscoveryWorker(lambda: service, ("SKU-1",))
        successes = []
        failures = []
        worker.succeeded.connect(successes.append)
        worker.failed.connect(failures.append)

        worker.run()

        self.assertEqual(("SKU-1",), service.skus)
        self.assertEqual([result], successes)
        self.assertEqual([], failures)

    def test_manual_collection_worker_calls_direct_sku_pipeline(self):
        result = KrossDiscoveryResult((KrossMatch("SKU-1", "kross_not_found"),))

        class _Service:
            def collect_inputs(self, inputs, output_root, *, options, progress, log):
                self.inputs = tuple(inputs)
                self.output_root = output_root
                self.options = options
                log("manual collection")
                progress(1, 1, "Checked SKU-1")
                return result

        service = _Service()
        worker = KrossSkuCollectionWorker(
            lambda: service,
            ("SKU-1",),
            Path(self.temp.name),
            KrossCollectionOptions.only("description_source"),
        )
        successes = []
        failures = []
        logs = []
        worker.succeeded.connect(successes.append)
        worker.failed.connect(failures.append)
        worker.log_message.connect(logs.append)

        worker.run()

        self.assertEqual(("SKU-1",), service.inputs)
        self.assertEqual([result], successes)
        self.assertEqual([], failures)
        self.assertEqual(["manual collection"], logs)

    def test_upload_worker_rejects_multi_product_run_without_save(self):
        matches = tuple(
            KrossMatch(
                f"SKU-{index}",
                "found",
                pimbo_product_url=f"https://pim.bo.ultrabike.lt/dashboard/products/p-{index}",
                kross_url=f"https://kross.pl/example-{index}",
            )
            for index in (1, 2)
        )
        service_created = []
        worker = KrossUploadWorker(
            lambda: service_created.append(True),
            matches,
            None,
            KrossWorkflowOptions.only("brand"),
        )
        failures = []
        completions = []
        worker.failed.connect(failures.append)
        worker.completed.connect(lambda: completions.append(True))

        worker.run()

        self.assertEqual([], service_created)
        self.assertEqual(
            ["A run without Save can target only one PIMBO product at a time"],
            failures,
        )
        self.assertEqual([True], completions)

    def test_upload_worker_recovers_one_failed_product_and_continues(self):
        matches = tuple(
            KrossMatch(
                f"SKU-{index}",
                "found",
                pimbo_product_id=f"p-{index}",
                pimbo_product_url=(
                    f"https://pim.bo.ultrabike.lt/dashboard/products/p-{index}"
                ),
            )
            for index in (1, 2)
        )

        class _Service:
            def __init__(self):
                self.uploaded = []
                self.recovered = []

            def upload_and_save(self, match, _output, *, options, progress):
                self.uploaded.append(match.sku)
                status = (
                    PimPreparationStatus.FAILED
                    if match.sku == "SKU-1"
                    else PimPreparationStatus.SAVED_AUTOMATICALLY
                )
                return KrossUploadResult(
                    match,
                    PimPreparationResult(
                        product_code=match.sku,
                        product_id=match.pimbo_product_id,
                        status=status,
                        error="first product failed" if status == PimPreparationStatus.FAILED else "",
                    ),
                )

            def recover_after_failed_upload(self, match, *, progress):
                self.recovered.append(match.sku)
                progress("recovered")
                return True

        service = _Service()
        worker = KrossUploadWorker(
            lambda: service,
            matches,
            Path(self.temp.name),
            KrossWorkflowOptions(),
        )
        results = []
        failures = []
        logs = []
        worker.item_finished.connect(results.append)
        worker.failed.connect(failures.append)
        worker.progress_changed.connect(logs.append)

        worker.run()

        self.assertEqual(["SKU-1", "SKU-2"], service.uploaded)
        self.assertEqual(["SKU-1"], service.recovered)
        self.assertEqual(2, len(results))
        self.assertEqual([], failures)
        self.assertIn("recovered", logs)

    def test_upload_worker_stops_before_cascading_when_recovery_is_unsafe(self):
        matches = tuple(
            KrossMatch(
                f"SKU-{index}",
                "found",
                pimbo_product_id=f"p-{index}",
                pimbo_product_url=(
                    f"https://pim.bo.ultrabike.lt/dashboard/products/p-{index}"
                ),
            )
            for index in (1, 2)
        )

        class _Service:
            def __init__(self):
                self.uploaded = []

            def upload_and_save(self, match, _output, *, options, progress):
                self.uploaded.append(match.sku)
                return KrossUploadResult(
                    match,
                    PimPreparationResult(
                        product_code=match.sku,
                        product_id=match.pimbo_product_id,
                        status=PimPreparationStatus.FAILED,
                        error="first product failed",
                    ),
                )

            def recover_after_failed_upload(self, _match, *, progress):
                return False

        service = _Service()
        worker = KrossUploadWorker(
            lambda: service,
            matches,
            Path(self.temp.name),
            KrossWorkflowOptions(),
        )
        failures = []
        worker.failed.connect(failures.append)

        worker.run()

        self.assertEqual(["SKU-1"], service.uploaded)
        self.assertEqual(1, len(failures))
        self.assertIn("Batch stopped after SKU-1", failures[0])


if __name__ == "__main__":
    unittest.main()
