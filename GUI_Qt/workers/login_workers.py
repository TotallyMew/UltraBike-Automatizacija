"""Cancellable workers for PIMBO browser authentication."""

from __future__ import annotations

import threading

from PySide6.QtCore import QThread, Signal

from Config.BrowserConfig.BrowserManager import BrowserManager
from Config.LoginConfig.LoginHandler import LoginHandler


class PimboLoginWorker(QThread):
    """Own a temporary Selenium driver until login succeeds or is cancelled."""

    result = Signal(bool, str, object)
    is_login_worker = True

    def __init__(self, email, password, browser_choice, credential_manager, tr):
        super().__init__()
        self.email = email
        self.password = password
        self.browser_choice = browser_choice or "Chrome"
        self.credential_manager = credential_manager
        self.tr = tr
        self.driver = None
        self._stop_event = threading.Event()

    def is_cancelled(self) -> bool:
        return self._stop_event.is_set() or self.isInterruptionRequested()

    def request_stop(self) -> None:
        self._stop_event.set()
        self.requestInterruption()

    def _quit_driver(self) -> None:
        driver, self.driver = self.driver, None
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass

    def run(self) -> None:
        try:
            if self.is_cancelled():
                return
            browser_manager = BrowserManager()
            self.driver = browser_manager.setup_browser(
                self.browser_choice,
                retry_callback=lambda: False,
                cancel_callback=self.is_cancelled,
            )
            if self.is_cancelled():
                return
            if self.driver is None:
                self.result.emit(False, self.tr("login.browser_init_failed"), None)
                return

            login_handler = LoginHandler(self.driver, self.credential_manager)
            success = login_handler.login(
                credentials_callback=lambda: (self.email, self.password),
                retry_callback=lambda: False,
                max_attempts=1,
                cancel_callback=self.is_cancelled,
            )
            if self.is_cancelled():
                return
            if success:
                authenticated_driver, self.driver = self.driver, None
                self.result.emit(True, self.tr("login.ok"), authenticated_driver)
            else:
                self.result.emit(False, self.tr("login.invalid_credentials"), None)
        except Exception as error:
            if not self.is_cancelled():
                self.result.emit(False, str(error), None)
        finally:
            self._quit_driver()
