import queue
import threading
import unittest

from Utilities.ErrorManager import ErrorManager


class _Logger:
    def __init__(self):
        self.entries = []

    def log(self, module, message, **context):
        self.entries.append(("log", module, message, context))

    def error(self, module, message, exception=None, **context):
        self.entries.append(("error", module, message, context))


class ErrorManagerTests(unittest.TestCase):
    def tearDown(self):
        ErrorManager.configure()
        ErrorManager._prompt_queue = None

    def test_worker_notification_is_localized_logged_and_queued(self):
        notifications = queue.Queue()
        logger = _Logger()
        ErrorManager.configure(
            notification_queue=notifications,
            logger=logger,
            translator=lambda key, **values: f"localized:{key}:{values['code']}",
        )

        worker = threading.Thread(
            target=lambda: ErrorManager.show_error("UPLOAD_PRODUCT_NOT_FOUND", code="X-1")
        )
        worker.start()
        worker.join()

        self.assertEqual(
            notifications.get_nowait(),
            (
                "notification",
                "error",
                "localized:error.UPLOAD_PRODUCT_NOT_FOUND:X-1",
                "UPLOAD_PRODUCT_NOT_FOUND",
            ),
        )
        self.assertEqual(logger.entries[0][0], "error")
        self.assertEqual(logger.entries[0][3]["code"], "UPLOAD_PRODUCT_NOT_FOUND")

    def test_retry_prompt_round_trip_is_thread_safe(self):
        prompts = queue.Queue()
        ErrorManager.set_prompt_queue(prompts)
        result = []
        worker = threading.Thread(target=lambda: result.append(ErrorManager.prompt_retry("upload")))
        worker.start()
        prompt_type, operation, response = prompts.get(timeout=1)
        self.assertEqual((prompt_type, operation), ("retry", "upload"))
        response.put("NEW-CODE")
        worker.join(timeout=1)
        self.assertEqual(result, ["NEW-CODE"])


if __name__ == "__main__":
    unittest.main()
