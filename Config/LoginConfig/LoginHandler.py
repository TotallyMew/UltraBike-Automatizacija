import stdiomask
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from Config.LoginConfig.CredentialManager import CredentialManager

class LoginHandler:    
    def __init__(self, driver, credential_manager: CredentialManager):
        self.driver = driver
        self.credential_manager = credential_manager
        self.saved_email = None
        self.saved_password = None
    
    def attempt_login(self, email: str, password: str) -> bool:
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
            print("Bandoma prisijungt...")
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "quick_select")))
            
            print("Sėkmingai prisijungėt!")
            return True
            
        except TimeoutException:
            print("Prisijungti nepavyko.")
            return False
    
    def prompt_for_credentials(self) -> tuple:
        self.saved_email, self.saved_password = self.credential_manager.get_saved_credentials()
        
        if self.saved_email and self.saved_password:
            use_saved = input(f"Naudoti esamus duomenis prisijungimui ({self.saved_email})? (T/N): ").lower()
            if use_saved == 't':
                return self.saved_email, self.saved_password
        
        email = input("Įveskite el. paštą: ")
        password = stdiomask.getpass("Įveskite slaptažodį: ", mask="*")
        self.credential_manager.save_credentials(email, password)
        return email, password
    
    def handle_login_retry(self) -> bool:
        while True:
            try_again = input("Bandyti dar kartą? (T/N): ").lower()
            if try_again == "t":
                return True
            elif try_again == "n":
                print("Darbas baigiamas...")
                return False
            else:
                print("Įveskite 'T' arba 'N'.")
    
    def login(self) -> None:
        self.driver.maximize_window()
        self.driver.get("https://ultrabike.lt/admin-ultro/")
        
        while True:
            email, password = self.prompt_for_credentials()
            
            if self.attempt_login(email, password):
                break
                
            self.saved_email, self.saved_password = None, None  # Reset on failure
            
            if not self.handle_login_retry():
                self.driver.quit()
                exit()
