import time
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
)
import time

from selenium.webdriver.common.by import By
from Utilities.WebIntercationHandler import WebInteractionHandler



class ProductNavigationHandler:
    def __init__(self, driver):
        self.driver = driver
        self.web_interaction = WebInteractionHandler(driver)

    def fix_invisible_products(self):
        prekesKodoElementID = "filter_column_name_category"

        try:
            prekesElement = WebDriverWait(self.driver, 3).until(
                EC.element_to_be_clickable((By.NAME, prekesKodoElementID))
            )
            self.driver.execute_script("arguments[0].scrollIntoView();", prekesElement)
            prekesElement.click()
        except TimeoutException:
            print("Prekės mygtukas nerastas")
            try:
                self._navigate_via_products_button()
            except TimeoutException:
                try:
                    self._navigate_via_catalog_button()
                except TimeoutException:
                    try:
                        self._expand_menu_and_navigate()
                    except TimeoutException:
                        print("Nepavyko rasti PrestaShop logo, tikslinkit programos kodą")
        print("Problema sutvarkyta, darbas tęsiamas")

    def _navigate_via_products_button(self):
        prekesMygtukasElement = WebDriverWait(self.driver, 3).until(
            EC.element_to_be_clickable((By.ID, "subtab-AdminProducts")) #"Prekės" mygtukas PrestaShop administravimo skydelyje
        )
        self.driver.execute_script("arguments[0].scrollIntoView();", prekesMygtukasElement)
        prekesMygtukasElement.click()

    def _navigate_via_catalog_button(self):
        katalogasMygtukasElement = WebDriverWait(self.driver, 3).until(#"Katalogas" mygtukas
            EC.element_to_be_clickable((By.ID, "subtab-AdminCatalog"))
        )
        self.driver.execute_script("arguments[0].scrollIntoView();", katalogasMygtukasElement)
        katalogasMygtukasElement.click()
        prekesMygtukasElement = WebDriverWait(self.driver, 3).until(
            EC.element_to_be_clickable((By.ID, "subtab-AdminProducts"))
        )
        self.driver.execute_script("arguments[0].scrollIntoView();", prekesMygtukasElement)
        prekesMygtukasElement.click()

    def _expand_menu_and_navigate(self):
        sutraukimoIsskleidimoMygtukasElement = WebDriverWait(self.driver, 3).until(
            EC.element_to_be_clickable((By.CLASS_NAME, "menu-collapse"))#"<< arba >>" mygtukas kur sutrumpina arba išplečia meniu PrestaShop administravimo skydelyje
        )
        self.driver.execute_script("arguments[0].scrollIntoView();", sutraukimoIsskleidimoMygtukasElement)
        sutraukimoIsskleidimoMygtukasElement.click()
        time.sleep(3)
        self._navigate_via_catalog_button()

    def navigate_to_product(self, brand_name, unique_code):
        if unique_code.startswith("UB-"):
            try:
                WebDriverWait(self.driver, 3).until(
                    EC.element_to_be_clickable((By.NAME, "filter_column_name_category"))
                )
            except TimeoutException:      
                self.fix_invisible_products()

            while True:
                try:
                    self._search_product(unique_code)
                    if self.web_interaction.click_product_by_link(unique_code, brand_name):
                        print("Prekė sėkmingai paspausta.")
                        break  
                    else:
                        print("Prekė su nurodytu kodu nerasta arba negali būti paspausta.")
                except Exception as e:
                    print(f"Ivyko klaida: {e}")

                if not self._retry_search():
                    return
        else:
            while True:
                try:
                    self._search_product_simple(unique_code)
                    if self.web_interaction.click_product_by_code(unique_code):
                        print("Prekė sėkmingai paspausta.")
                        break
                    else:
                        print("Prekė su norodytu kodu nerasta")
                except Exception as e:
                    print(f"Ivyko klaida, prekė nerasta")

                if not self._retry_search():
                    return

    def _search_product(self, unique_code): #UB code
        search_name = self.driver.find_element(By.NAME, "filter_column_name")
        search_name.clear()
        search_category = self.driver.find_element(By.NAME, "filter_column_name_category")
        search_category.clear()
        search_product = self.driver.find_element(By.NAME, "filter_column_reference")
        search_product.clear() 
        search_product.send_keys(unique_code + Keys.ENTER)

    def _search_product_simple(self, unique_code): #SKU
        search_product = self.driver.find_element(By.ID, "bo_query")
        search_product.clear() 
        search_product.send_keys(unique_code + Keys.ENTER)

    def _retry_search(self):
        while True:
            retry = input("Bandyti dar kartą? (t/n): ")
            if retry.lower() == "t":
                return True
            elif retry.lower() == "n":
                print("Darbas baigiamas.")
                self.driver.quit()
                exit()
            else:
                print("Įveskite T arba N")
