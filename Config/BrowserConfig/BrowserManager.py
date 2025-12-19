import os
import time
import requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.edge.options import Options as EdgeOptions
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.firefox import GeckoDriverManager
from webdriver_manager.microsoft import EdgeChromiumDriverManager
from selenium.webdriver.common.by import By

class InternetChecker:
    @staticmethod
    def check_connection(url='http://www.google.com'):
        try:
            requests.get(url, timeout=5)
            return True
        except requests.ConnectionError:
            return False

class BrowserManager:
    def __init__(self):
        self.internet_checker = InternetChecker()

    def setup_browser(self, browser_choice, retry_callback=None):
        """
        Setup browser with optional retry callback for GUI compatibility

        Args:
            browser_choice: Browser to use (chrome, firefox, edge)
            retry_callback: Optional callback for internet retry. If None, uses CLI prompts.
                          Should return True to retry, False to cancel.
        """
        while True:
            if not self.internet_checker.check_connection():
                if retry_callback is not None:
                    # GUI mode - use callback
                    if not retry_callback():
                        return None
                else:
                    # CLI mode - use prompts
                    if not self._prompt_retry_internet():
                        return None
                continue

            try:
                browser_choice = browser_choice.lower()
                if browser_choice == "chrome":
                    return self._setup_chrome()
                elif browser_choice == "firefox":
                    return self._setup_firefox()
                elif browser_choice == "edge":
                    return self._setup_edge()
                else:
                    browser_choice = self._handle_unsupported_browser()
                    if browser_choice is None:
                        return None
                    continue
            except Exception as e:
                # Error: Error setting up browser: {e}
                # Error: Closing program, browser not found.
                return None

    def _setup_chrome(self):
        options = ChromeOptions()
        options.add_experimental_option('excludeSwitches', ['enable-logging'])
        return webdriver.Chrome(
            service=ChromeService(ChromeDriverManager().install()),
            options=options
        )

    def _setup_firefox(self):
        options = FirefoxOptions()
        options.set_preference('browser.log.file', '/dev/null')
        return webdriver.Firefox(
            service=FirefoxService(GeckoDriverManager().install()),
            options=options
        )

    def _setup_edge(self):
        options = EdgeOptions()
        options.use_chromium = True
        options.add_experimental_option('excludeSwitches', ['enable-logging'])
        return webdriver.Edge(
            service=EdgeService(EdgeChromiumDriverManager().install()),
            options=options
        )

    def _handle_unsupported_browser(self):
        raise RuntimeError("CLI browser selection disabled: provide a valid 'browser_choice' or a GUI retry_callback.")

    def _prompt_retry_internet(self):
        raise RuntimeError("CLI internet retry prompt disabled: provide a 'retry_callback' from GUI.")