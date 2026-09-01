from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QWidget

from GUI_Qt.kross.workers import (
    KrossDiscoveryWorker, KrossSkuCollectionWorker, KrossUploadWorker,
)
from GUI_Qt.screens.KrossScreen import KrossScreen
from tools.kross_automation import (
    KrossCollectionOptions, KrossDiscoveryResult, KrossMatch, KrossWorkflowOptions,
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


if __name__ == "__main__":
    unittest.main()
