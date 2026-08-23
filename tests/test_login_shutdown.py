from __future__ import annotations

from Config.BrowserConfig.BrowserManager import BrowserManager
from Config.LoginConfig.LoginHandler import LoginHandler
from GUI_Qt.services.shutdown import ShutdownService
from GUI_Qt.workers.login_workers import PimboLoginWorker


class _Logger:
    def __init__(self):
        self.messages = []

    def log(self, component, message, **context):
        self.messages.append((component, message, context))


class _Main:
    def __init__(self):
        self.logger = _Logger()


class _StuckLoginWorker:
    is_login_worker = True

    def __init__(self):
        self.running = True
        self.stop_requested = False
        self.terminated = False
        self.waits = []

    def request_stop(self):
        self.stop_requested = True

    def isRunning(self):
        return self.running

    def wait(self, milliseconds):
        self.waits.append(milliseconds)
        return not self.running

    def terminate(self):
        self.terminated = True
        self.running = False


class _DriverThatMustNotStart:
    def __init__(self):
        self.calls = []

    def maximize_window(self):
        self.calls.append("maximize")

    def get(self, _url):
        self.calls.append("get")


def test_shutdown_forces_only_a_blocked_login_check_after_cooperative_wait():
    main = _Main()
    service = ShutdownService(main)
    worker = _StuckLoginWorker()
    service.iter_workers = lambda include_orbea=False: iter(((object(), worker),))

    assert service.stop_workers(wait_ms=5_000) is True
    assert worker.stop_requested is True
    assert worker.terminated is True
    assert worker.waits == [1_500, 1_500]
    assert "PIMBO login check" in main.logger.messages[0][1]


def test_browser_setup_honors_cancellation_before_network_or_driver_work():
    manager = BrowserManager()

    class _Internet:
        def check_connection(self):
            raise AssertionError("network should not be checked after cancellation")

    manager.internet_checker = _Internet()

    assert manager.setup_browser(
        "Chrome",
        retry_callback=lambda: False,
        cancel_callback=lambda: True,
    ) is None


def test_login_handler_honors_cancellation_before_opening_pimbo():
    driver = _DriverThatMustNotStart()
    handler = LoginHandler(driver, credential_manager=None)

    assert handler.login(
        credentials_callback=lambda: ("person@example.com", "secret"),
        retry_callback=lambda: False,
        max_attempts=1,
        cancel_callback=lambda: True,
    ) is False
    assert driver.calls == []


def test_pimbo_worker_exposes_cooperative_shutdown_contract():
    worker = PimboLoginWorker(
        "person@example.com", "secret", "Chrome", None, lambda key: key
    )

    worker.request_stop()

    assert worker.is_login_worker is True
    assert worker.is_cancelled() is True
