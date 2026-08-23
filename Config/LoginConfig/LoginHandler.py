from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from Config.LoginConfig.CredentialManager import CredentialManager
from Config.Selectors import LoginSelectors
from Utilities.ErrorManager import ErrorManager


class LoginCancelled(Exception):
    """Internal control flow used to leave Selenium waits during shutdown."""


class LoginHandler:
    def __init__(self, driver, credential_manager: CredentialManager, logger=None):
        self.driver = driver
        self.credential_manager = credential_manager
        self.logger = logger
        self.saved_email = None
        self.saved_password = None
    
    def _log(self, message, **context):
        if self.logger:
            self.logger.log("LoginHandler", message, **context)
    
    def _log_error(self, message, exception=None, **context):
        if self.logger:
            self.logger.error("LoginHandler", message, exception=exception, **context)
    
    @staticmethod
    def _raise_if_cancelled(cancel_callback=None) -> None:
        if cancel_callback is not None and cancel_callback():
            raise LoginCancelled()

    def _wait_for_element(self, locator, timeout: int, cancel_callback=None):
        condition = EC.presence_of_element_located(locator)

        def cancellable_condition(driver):
            self._raise_if_cancelled(cancel_callback)
            return condition(driver)

        return WebDriverWait(self.driver, timeout).until(cancellable_condition)

    def attempt_login(self, email: str, password: str, cancel_callback=None) -> bool:
        """
        Attempt to login with given credentials
        Returns True if successful, False otherwise
        """
        self._log("Attempting login", email=email)
        try:
            self._raise_if_cancelled(cancel_callback)
            email_field = self._wait_for_element(
                LoginSelectors.EMAIL, 10, cancel_callback
            )
            password_field = self._wait_for_element(
                LoginSelectors.PASSWORD, 10, cancel_callback
            )

            self._raise_if_cancelled(cancel_callback)
            email_field.clear()
            password_field.clear()

            email_field.send_keys(email)
            password_field.send_keys(password)

            submit_button = self.driver.find_element(*LoginSelectors.SUBMIT)
            submit_button.click()

            self._log("Login form submitted")

            WebDriverWait(self.driver, 15).until(
                lambda d: self._login_complete_condition(d, cancel_callback)
            )
            
            self._log("Login successful", email=email)
            return True
            
        except LoginCancelled:
            self._log("Login cancelled")
            raise
        except TimeoutException:
            self._log_error("Login failed - timeout", email=email)
            return False
        except Exception as e:
            self._log_error("Login failed - unexpected error", exception=e, email=email)
            return False
    
    def _login_complete_condition(self, driver, cancel_callback=None) -> bool:
        self._raise_if_cancelled(cancel_callback)
        return (
            "/dashboard/login" not in driver.current_url
            or len(driver.find_elements(*LoginSelectors.EMAIL)) == 0
        )

    def login(self, credentials_callback, retry_callback, max_attempts=3, cancel_callback=None):
        """Main login method.

        This project is GUI-only. Callers must provide:
        - credentials_callback() -> (email, password)
        - retry_callback() -> bool
        """
        self._log("Starting login process")
        if credentials_callback is None:
            raise ValueError("credentials_callback is required")

        if retry_callback is None:
            raise ValueError("retry_callback is required")

        try:
            self._raise_if_cancelled(cancel_callback)
            self.driver.maximize_window()
            self.driver.get(LoginSelectors.URL)
            self._raise_if_cancelled(cancel_callback)

            attempts = 0

            while attempts < max_attempts:
                self._raise_if_cancelled(cancel_callback)
                email, password = credentials_callback()

                if email is None or password is None:
                    self._log("Login cancelled by user")
                    self.driver.quit()
                    return False

                if self.attempt_login(email, password, cancel_callback):
                    return True

                attempts += 1
                self.saved_email, self.saved_password = None, None

                self._raise_if_cancelled(cancel_callback)
                ErrorManager.show_error("LOGIN_FAILED")

                if attempts < max_attempts:
                    if not retry_callback():
                        self._log("Login cancelled by user")
                        self.driver.quit()
                        return False
                else:
                    self._log("Max login attempts reached")
                    self.driver.quit()
                    return False
        except LoginCancelled:
            self._log("Login cancelled during application shutdown")
            return False

        return False
    
    def _is_valid_email(self, email: str) -> bool:
        """Basic email validation"""
        import re
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, email) is not None
