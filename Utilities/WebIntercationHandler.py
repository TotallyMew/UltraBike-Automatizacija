import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    NoSuchElementException,
    ElementClickInterceptedException,
                                        )
import time
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException




class WebInteractionHandler:
    def __init__(self, driver):
        self.driver = driver

    def load_credentials(self, file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
            if len(lines) < 2:
                raise ValueError("Credentials file must have at least 2 lines (username and password)")
            return lines[0], lines[1]

    def add_brand_name(self, brand_name):
        try:
            add_brand = WebDriverWait(self.driver, 2).until(
                EC.element_to_be_clickable((By.ID, "add_brand_button"))
            )
            self.driver.execute_script("arguments[0].scrollIntoView();", add_brand)
            add_brand.click()

            select_brand = self.driver.find_element(By.ID, "select2-form_step1_id_manufacturer-container")
            self.driver.execute_script("arguments[0].scrollIntoView();", select_brand)
            select_brand.click()

            search_field = self.driver.find_element(By.CLASS_NAME, "select2-search__field")
            self.driver.execute_script("arguments[0].scrollIntoView();", search_field)
            search_field.send_keys(brand_name)

            brand_match = WebDriverWait(self.driver, 2).until(
                EC.presence_of_element_located((By.CLASS_NAME, "select2-results__option"))
            )
            self.driver.execute_script("arguments[0].scrollIntoView();", brand_match)
            brand_match.click()
            print("Prekės ženklas pridėtas")       
        except:     
            print("Prekės žėnklas jau yra pridėtas")

    def save_information(self):
        try:
            save_button = WebDriverWait(self.driver, 2).until(  
                EC.element_to_be_clickable((By.CSS_SELECTOR, "input.btn.btn-primary.save.uppercase.ml-3"))
            )
            self.driver.execute_script("arguments[0].click();", save_button)
            print("Prekės pakeitimai išsaugoti.")
        except:
            print("Prekės atnaujinimai nebuvo išsaugoti!")
        time.sleep(3)

    def click_product_by_code(self, unique_code):
        try:
            product = WebDriverWait(self.driver, 2).until(
                EC.element_to_be_clickable((By.CLASS_NAME, "odd"))
            )
            self.driver.execute_script("arguments[0].scrollIntoView();", product)
            product.click()
            return True
        except NoSuchElementException:
            print(f"Prekė su kodu '{unique_code}' nerasta.")
        except ElementClickInterceptedException:
            print(f"Negalima paspausti ant prekės su kodu '{unique_code}'.")
        except Exception as e:
            print(f"Ivyko netikėta klaida: {e}")
        return False

    def click_product_by_link(self, unique_code, brand_name):
        if brand_name.lower() == "krosstxt":
            brand_name = "KROSS"
        try:
            code_element = WebDriverWait(self.driver, 2).until(
                EC.presence_of_element_located(
                    (By.XPATH, f"//td[normalize-space()='{unique_code}']")
                )
            )
            self.driver.execute_script("arguments[0].scrollIntoView();", code_element)

            row_element = code_element.find_element(By.XPATH, "./ancestor::tr")
            link_element = row_element.find_element(
                By.XPATH,
                f".//a[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{brand_name.lower()}')]"
            )
            self.driver.execute_script("arguments[0].scrollIntoView();", link_element)
            WebDriverWait(self.driver, 2).until(EC.element_to_be_clickable(link_element))
            link_element.click()
            return True
        except Exception as e:
            print(f"Ivyko klaida: {e}")
        return False

    def is_feature_found(self):
        try:
            no_results = self.driver.find_element(By.XPATH, "//*[contains(text(), 'No results found')]")
            self.driver.execute_script("arguments[0].scrollIntoView();", no_results)
            return True
        except NoSuchElementException:
            print("NX")
            return False
