from ast import Try
import time
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    ElementClickInterceptedException,
)
from Utilities.scrapeUtilities import *
from Config.config import settings, resizeWindow, resource_path
import pypandoc


def loadCredentials(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()
        if len(lines) < 2:
            raise ValueError("Credentials file must have at least 2 lines (username and password)")
        return lines[0], lines[1]


def getCode():
    code = input("Įveskite prekės unikalų kodą: ")
    return code

def getBrandName():
    brandName = input("Pasirinkite prekės tiekėją (KROSS, Rondo, Pinarello, Le Grand):")
    return brandName



def convert_docx_to_html(file_path):
    html = pypandoc.convert_file(file_path, 'html')
    return html


def addDescription(driver, file_path):
    try:
        # Step 1: Click the code button
        code_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.ID, "mceu_105-button"))
        )
        code_button.click()
        print("Clicked code button")

        # Step 2: Find the textarea and paste text from .txt file
        textarea = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "mceu_235"))
        )
        
        # Read the text file
        with open(file_path, 'r', encoding='utf-8') as file:
            text_content = file.read()
        
        # Clear any existing content and paste the new text
        textarea.clear()
        textarea.send_keys(text_content)
        print("Text pasted into textarea")

        # Step 3: Press the confirmation button (Gerai)
        confirm_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.ID, "mceu_237-button"))
        )
        confirm_button.click()
        print("Clicked confirmation button")

    except FileNotFoundError:
        print(f"File not found: {file_path}")
    except Exception as e:
        print(f"Failed to add description from text file: {e}")


def addBrandName(driver, brandName):  
    try:
        addBrandName = WebDriverWait(driver, 10).until( #prideti add or try, kai brnadName jau parinktas
            EC.element_to_be_clickable((By.ID, "add_brand_button"))
        )
        driver.execute_script("arguments[0].scrollIntoView();", addBrandName)
        addBrandName.click()

        selectBrand = driver.find_element(By.ID, "select2-form_step1_id_manufacturer-container")
        driver.execute_script("arguments[0].scrollIntoView();", selectBrand)
        selectBrand.click()

        ieskotiSavybes = driver.find_element(By.CLASS_NAME, "select2-search__field")
        driver.execute_script("arguments[0].scrollIntoView();", ieskotiSavybes)
        ieskotiSavybes.send_keys(brandName)

        brandNameTopMatch = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, "select2-results__option"))
        )
        driver.execute_script("arguments[0].scrollIntoView();", brandNameTopMatch)
        brandNameTopMatch.click()
        print("Prekės ženklas pridėtas")
    except:
        print("Prekės žėnklas jau yra pridėtas")

def spaustiSuPilnuKodu(unique_code, driver, brandName):
    
    try:
        paspaustiPreke = WebDriverWait(driver, 2).until(
                            EC.element_to_be_clickable((By.CLASS_NAME, "odd"))
                        )
        driver.execute_script("arguments[0].scrollIntoView();", paspaustiPreke)
        paspaustiPreke.click()
        return True
    

    except NoSuchElementException:
        print(f"Prekė su kodu '{unique_code}' nerasta.")
    except ElementClickInterceptedException:
        print(f"Negalima paspausti ant prekės su kodu '{unique_code}'.")
    except Exception as e:
        print(f"Ivyko klaida: {e}")

def spausPrekesLink(unique_code, driver, brandName):
    if brandName.lower() == "krosstxt":
        brandName = "KROSS"
    try:
        code_element = WebDriverWait(driver, 2).until(
            EC.presence_of_element_located(
                (By.XPATH, f"//td[normalize-space()='{unique_code}']")
            )
        )
        driver.execute_script("arguments[0].scrollIntoView();", code_element)

        row_element = code_element.find_element(By.XPATH, "./ancestor::tr")
        link_element = row_element.find_element(
            By.XPATH,
            f".//a[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{brandName.lower()}')]"
        )
        driver.execute_script("arguments[0].scrollIntoView();", link_element)
        WebDriverWait(driver, 2).until(EC.element_to_be_clickable(link_element))
        link_element.click()

        return True

    except NoSuchElementException:
        print(f"Prekė su kodu '{unique_code}' nerasta.")
    except ElementClickInterceptedException:
        print(f"Negalima paspausti ant prekės su kodu '{unique_code}'.")
    except Exception as e:
        print(f"Ivyko klaida: {e}")

    return False

def tikrintiArSavybeRasta(driver):
    try:
        no_results_message = driver.find_element(By.XPATH, "//*[contains(text(), 'No results found')]")
        driver.execute_script("arguments[0].scrollIntoView();", no_results_message)
        if no_results_message:
            return True
    except NoSuchElementException:
        return False
    return False

def perSkydeliPrekesNematomos(driver):
    prekesKodoElementID = "filter_column_name_category"
    prekesMygtukas = "subtab-AdminProducts"
    katalogasMygtukas = "subtab-AdminCatalog"
    sutraukimoIsskleidimoMygtuka = "menu-collapse"

    try:
        prekesElement = WebDriverWait(driver, 3).until(
            EC.element_to_be_clickable((By.NAME, prekesKodoElementID))
        )
        driver.execute_script("arguments[0].scrollIntoView();", prekesElement)
        prekesElement.click()
    except TimeoutException:
        print("Prekės mygtukas nerastas")
        try:
            prekesMygtukasElement = WebDriverWait(driver, 3).until(
                EC.element_to_be_clickable((By.ID, prekesMygtukas))
            )
            driver.execute_script("arguments[0].scrollIntoView();", prekesMygtukasElement)
            prekesMygtukasElement.click()
            return
        except TimeoutException:
            try:
                katalogasMygtukasElement = WebDriverWait(driver, 3).until(
                    EC.element_to_be_clickable((By.ID, katalogasMygtukas))
                )
                driver.execute_script("arguments[0].scrollIntoView();", katalogasMygtukasElement)
                katalogasMygtukasElement.click()
                prekesMygtukasElement = WebDriverWait(driver, 3).until(
                    EC.element_to_be_clickable((By.ID, prekesMygtukas))
                )
                driver.execute_script("arguments[0].scrollIntoView();", prekesMygtukasElement)
                prekesMygtukasElement.click()
            except TimeoutException:
                try:
                    sutraukimoIsskleidimoMygtukasElement = WebDriverWait(driver, 3).until(
                        EC.element_to_be_clickable((By.CLASS_NAME, sutraukimoIsskleidimoMygtuka))
                    )
                    driver.execute_script("arguments[0].scrollIntoView();", sutraukimoIsskleidimoMygtukasElement)
                    sutraukimoIsskleidimoMygtukasElement.click()
                    time.sleep(3)
                    katalogasMygtukasElement = WebDriverWait(driver, 3).until(
                        EC.element_to_be_clickable((By.ID, katalogasMygtukas))
                    )
                    driver.execute_script("arguments[0].scrollIntoView();", katalogasMygtukasElement)
                    katalogasMygtukasElement.click()
                    katalogasMygtukasElement.click()
                    prekesMygtukasElement = WebDriverWait(driver, 3).until(
                        EC.element_to_be_clickable((By.ID, prekesMygtukas))
                    )
                    driver.execute_script("arguments[0].scrollIntoView();", prekesMygtukasElement)
                    prekesMygtukasElement.click()
                except TimeoutException:
                    print("Nepavyko rasti PrestaShop logo, tikslinkit programos kodą")
    print("Problema sutvarkyta, darbas tęsiamas")
    


filteriuSkaicius = 0

def filteriuPridejimas(driver):
    global settings
    if settings and settings[2] is False:
        with open(resource_path("filtrai.txt"), 'r', encoding='utf-8') as file:
            filteriuMasyvas = [line.strip() for line in file.readlines()]
        kelintaSavybe = 0
        global filteriuSkaicius 
        filteriuSkaicius = len(filteriuMasyvas)
        time.sleep(1)

        for feature_key in filteriuMasyvas:
            pridetiSavybe = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.ID, "add_feature_button"))
            )
            driver.execute_script("arguments[0].scrollIntoView();", pridetiSavybe)
           # time.sleep(0.5)  # Small delay to ensure element is fully interactable

            try:
                # Attempt to click using JavaScript
                driver.execute_script("arguments[0].click();", pridetiSavybe)
            except Exception as e:
                print(f"JavaScript click failed: {e}")
                # Fall back to normal click
                pridetiSavybe.click()

            pasirinktiSavybe = driver.find_element(
                By.ID,
                "select2-form_step1_features_" + str(kelintaSavybe) + "_feature-container"
            )
            pasirinktiSavybe.click()

            ieskotiSavybes = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CLASS_NAME, "select2-search__field"))
            )
            ieskotiSavybes.send_keys(feature_key)

            try:
                WebDriverWait(driver, 2).until(EC.presence_of_element_located((By.CLASS_NAME, "select2-results__option")))
                if tikrintiArSavybeRasta(driver):
                    pasirinktiSavybe.click()
                    kelintaSavybe += 1
                    continue

                xpath_expression = f"//li[. = '{feature_key}']" 
                poPaieskosVirstutinisElementas = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, xpath_expression))
                )
                poPaieskosVirstutinisElementas.click()

            except TimeoutException:
                print(f"Nerasta '{feature_key}'.")
                continue

            kelintaSavybe += 1


def prekesPaspaudimas(driver, brandName, unique_code):
    

    if unique_code.startswith("UB-"):
        try:
            WebDriverWait(driver, 3).until(EC.element_to_be_clickable((By.NAME, "filter_column_name_category")))
        
        except TimeoutException:      
            perSkydeliPrekesNematomos(driver)


        while True:
            try:
                ieskotiPavadinimas = driver.find_element(By.NAME, "filter_column_name")
                ieskotiPavadinimas.clear()
                ieskotiKategorija = driver.find_element(By.NAME, "filter_column_name_category")
                ieskotiKategorija.clear()
                ieskotiPrekes = driver.find_element(By.NAME, "filter_column_reference")
                ieskotiPrekes.clear() 
                ieskotiPrekes.send_keys(unique_code + Keys.ENTER)


                if spausPrekesLink(unique_code, driver, brandName):
                    print("Prekė sėkmingai paspausta.")
                    break  
                else:
                    print("Prekė su nurodytu kodu nerasta arba negali būti paspausta.")
            except Exception as e:
                print(f"Ivyko klaida: {e}")

      
            while True:
                retry = input("Bandyti dar kartą? (t/n): ")
                if retry.lower() == "t":
                    unique_code = input(
                        "Įveskite naują prekės kodą: "
                    )
                    break
                elif retry.lower() == "n":
                    print("Darbas baigiamas.")
                    driver.quit()
                    exit()
                else:
                    print("Įveskite T arba N")
    else:
        while True:
            try:
                ieskotiPrekes = driver.find_element(By.ID, "bo_query")
                ieskotiPrekes.clear() 
                ieskotiPrekes.send_keys(unique_code + Keys.ENTER)
                
                if spaustiSuPilnuKodu(unique_code, driver, brandName):
                    print("Prekė sėkmingai paspausta.")
                    break
                else:
                    print("Prekė su norodytu kodu nerasta")
            except Exception as e:
                print(f"Ivyko klaida, prekė nerasta")

            while True:
                retry = input("Bandyti dar kartą? (t/n): ")
                if retry.lower() == "t":
                    unique_code = input(
                        "Įveskite naują prekės kodą: "
                    )
                    break
                elif retry.lower() == "n":
                    print("Darbas baigiamas.")
                    driver.quit()
                    exit()
                else:
                    print("Įveskite T arba N")
            





