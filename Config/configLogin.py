import json
import stdiomask
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from Config.config import resource_path

# Generate and save the key somewhere secure; only once needed
def issaugotiLoginInfo(email, password):
    loginPath = resource_path("loginInfo.json")

    credentials = jsonLoginInfoLoad()

    credentials[email] = password

    with open(loginPath, 'w') as f:
        json.dump(credentials, f)

def jsonLoginInfoLoad():
    loginPath = resource_path("loginInfo.json")
    try:
        with open(loginPath, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def gautiLoginInfoJSON():
    credentials = jsonLoginInfoLoad()
    if credentials:

        if len(credentials) > 1:
            for i, email in enumerate(credentials.keys()):
                print(f"{i + 1}. {email}")
            choice = int(input("Pasirinkite prisijungimo duomenis (?veskite numer?): ")) - 1
            email = list(credentials.keys())[choice]
            return email, credentials[email]
        else:
            email = next(iter(credentials))
            return email, credentials[email]
    return None, None

def login(driver):
    driver.maximize_window()
    driver.get("https://ultrabike.lt/admin-ultro/")

    saved_email, saved_password = gautiLoginInfoJSON()

    while True:
        try:
            email_field = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "email"))
            )
            password_field = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "passwd"))
            )

            password_field.clear()
            email_field.clear()

            if saved_email and saved_password:
                use_saved = input(f"Ar norite naudoti išsaugotus prisijungimo duomenis ({saved_email})? (T/N): ").lower()
                if use_saved == 't':
                    email = saved_email
                    password = saved_password
                else:
                    email = input("Įrašykite emailą: ")
                    password = stdiomask.getpass("Įveskite savo slaptažodį: ", mask="*")
                    issaugotiLoginInfo(email, password)
            else:
                email = input("Įrašykite emailą: ")
                password = stdiomask.getpass("Įveskite savo slaptažodį: ", mask="*")
                issaugotiLoginInfo(email, password)

            email_field.send_keys(email)
            password_field.send_keys(password)

            submit_button = driver.find_element(By.ID, "submit_login")
            submit_button.click()

            print("Tikrinamas prisijungimas")
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "quick_select"))
            )

            print("Sėkmingai prisijungėt!")
            break

        except TimeoutException:
            print("Prisijungti nepavyko.")
            saved_email, saved_password = None, None  # Reset saved credentials on failure
            while True:
                try_again = input("Ar norėtumėt bandyti vėl? (T/N): ").lower()
                if try_again == "t":
                    break
                elif try_again == "n":
                    print("Darbas baigiamas.")
                    driver.quit()
                    exit()
                    return
                else:
                    print("Prašome įvesti 'T' arba 'N'.")

