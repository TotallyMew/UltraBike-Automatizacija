import stdiomask
import re
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from Config.LoginConfig.CredentialManager import CredentialManager
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
    
    def _is_valid_email(self, email):
        """Basic email validation"""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, email) is not None
    
    def attempt_login(self, email: str, password: str) -> bool:
        self._log("Attempting login", email=email)
        try:
            email_field = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "email")))
            password_field = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "passwd")))
            
            email_field.clear()
            password_field.clear()
            
            email_field.send_keys(email)
            password_field.send_keys(password)
            
            submit_button = self.driver.find_element(By.ID, "submit_login")
            submit_button.click()
            
            self._log("Login form submitted")
            
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "quick_select"))
            )
            
            self._log("Login successful", email=email)
            ErrorManager.show_success("Sėkmingai prisijungėt!")
            return True
            
        except TimeoutException:
            self._log_error("Login failed - timeout", email=email)
            ErrorManager.show_error("LOGIN_FAILED")
            return False
        except Exception as e:
            self._log_error("Login failed - unexpected error", exception=e, email=email)
            ErrorManager.show_error("LOGIN_FAILED")
            return False
    
    def prompt_for_credentials(self) -> tuple:
        self.saved_email, self.saved_password = self.credential_manager.get_saved_credentials()
        
        if self.saved_email and self.saved_password:
            use_saved = input(f"Naudoti esamus duomenis prisijungimui ({self.saved_email})? (T/N): ").lower()
            if use_saved == 't':
                self._log("Using saved credentials", email=self.saved_email)
                return self.saved_email, self.saved_password
        
        while True:
            email = input("Įveskite el. paštą: ").strip()
            if self._is_valid_email(email):
                break
            else:
                ErrorManager.show_warning("Neteisingas el. pašto formatas. Bandykite dar kartą.")
        
        password = stdiomask.getpass("Įveskite slaptažodį: ", mask="*")
        self.credential_manager.save_credentials(email, password)
        self._log("New credentials entered", email=email)
        return email, password
    
    def handle_login_retry(self) -> bool:
        return ErrorManager.prompt_retry("prisijungimą")
    
    def login(self) -> None:
        self._log("Starting login process")
        self.driver.maximize_window()
        self.driver.get("https://ultrabike.lt/admin-ultro/")
        
        max_attempts = 3
        attempts = 0
        
        while attempts < max_attempts:
            email, password = self.prompt_for_credentials()
            
            if self.attempt_login(email, password):
                return
            
            attempts += 1
            self.saved_email, self.saved_password = None, None
            
            if attempts < max_attempts:
                if not self.handle_login_retry():
                    self._log("Login cancelled by user")
                    self.driver.quit()
                    exit()
            else:
                ErrorManager.show_error("LOGIN_FAILED")
                self._log("Max login attempts reached")
                self.driver.quit()
                exit()