from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from Config.LoginConfig.CredentialManager import CredentialManager
from Config.Selectors import LoginSelectors
from Utilities.ErrorManager import ErrorManager

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
    
    def attempt_login(self, email: str, password: str) -> bool:
        """
        Attempt to login with given credentials
        Returns True if successful, False otherwise
        """
        self._log("Attempting login", email=email)
        try:
            email_field = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located(LoginSelectors.EMAIL))
            password_field = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located(LoginSelectors.PASSWORD))

            email_field.clear()
            password_field.clear()

            email_field.send_keys(email)
            password_field.send_keys(password)

            submit_button = self.driver.find_element(*LoginSelectors.SUBMIT)
            submit_button.click()

            self._log("Login form submitted")

            WebDriverWait(self.driver, 15).until(
                lambda d: "/dashboard/login" not in d.current_url
                or len(d.find_elements(*LoginSelectors.EMAIL)) == 0
            )
            
            self._log("Login successful", email=email)
            return True
            
        except TimeoutException:
            self._log_error("Login failed - timeout", email=email)
            return False
        except Exception as e:
            self._log_error("Login failed - unexpected error", exception=e, email=email)
            return False
    
    def login(self, credentials_callback, retry_callback, max_attempts=3):
        """Main login method.

        This project is GUI-only. Callers must provide:
        - credentials_callback() -> (email, password)
        - retry_callback() -> bool
        """
        self._log("Starting login process")
        self.driver.maximize_window()
        self.driver.get(LoginSelectors.URL)
        
        if credentials_callback is None:
            raise ValueError("credentials_callback is required")

        if retry_callback is None:
            raise ValueError("retry_callback is required")
        
        attempts = 0
        
        while attempts < max_attempts:
            # Get credentials from callback
            email, password = credentials_callback()
            
            if email is None or password is None:
                self._log("Login cancelled by user")
                self.driver.quit()
                return False
            
            # Try to login
            if self.attempt_login(email, password):
                # Success - persistence handled by GUI (encrypted with master password)
                return True
            
            attempts += 1
            self.saved_email, self.saved_password = None, None
            
            # Show error
            ErrorManager.show_error("LOGIN_FAILED")
            
            # Ask if retry
            if attempts < max_attempts:
                if not retry_callback():
                    self._log("Login cancelled by user")
                    self.driver.quit()
                    return False
            else:
                self._log("Max login attempts reached")
                self.driver.quit()
                return False
        
        return False
    
    def _is_valid_email(self, email: str) -> bool:
        """Basic email validation"""
        import re
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, email) is not None
