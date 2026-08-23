import tempfile
import threading
import unittest
from pathlib import Path

from Database.DatabaseManager import DatabaseManager
from Managers.OperationTracker import OperationKind, OperationStatus, OperationTracker


class OperationTrackerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database = DatabaseManager(Path(self.temp.name) / "activity.db")
        self.tracker = OperationTracker(self.database)

    def tearDown(self):
        self.database.close()
        self.temp.cleanup()

    def test_lifecycle_cancel_diagnostics_and_crash_recovery(self):
        cancelled = []
        record = self.tracker.create(
            OperationKind.ORBEA,
            "orbea",
            total=10,
            output_path=self.temp.name,
            resume_kind="orbea_checkpoint",
            resume_ref="checkpoint.json",
            cancel=lambda: cancelled.append(True),
        )
        self.tracker.start(record.id, stage="scan")
        self.tracker.progress(record.id, 4, 10, message="four")
        self.assertTrue(self.tracker.request_cancel(record.id))
        self.assertEqual(cancelled, [True])
        self.tracker.finish(record.id, OperationStatus.CANCELLED)
        final = self.tracker.get(record.id)
        self.assertEqual(final.status, OperationStatus.CANCELLED)
        self.assertEqual(final.progress_percent, 40)
        self.assertIn('"resume"', self.tracker.diagnostics(record.id))

        abandoned = self.tracker.create(OperationKind.UPLOAD, "upload")
        self.tracker.start(abandoned.id)
        restarted = OperationTracker(self.database)
        self.assertEqual(
            restarted.get(abandoned.id).status, OperationStatus.INTERRUPTED
        )

    def test_concurrent_progress_writes_are_serialized(self):
        record = self.tracker.create(OperationKind.URL_SCANNER, "castelli_url_getter", total=100)
        self.tracker.start(record.id)
        errors = []

        def update(value):
            try:
                self.tracker.progress(record.id, value, 100)
            except Exception as error:  # pragma: no cover - captured for assertion
                errors.append(error)

        threads = [threading.Thread(target=update, args=(value,)) for value in range(1, 41)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])
        self.tracker.finish(record.id)
        self.assertEqual(self.tracker.get(record.id).status, OperationStatus.SUCCEEDED)


if __name__ == "__main__":
    unittest.main()
