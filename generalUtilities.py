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




def getCode():
    code = input("Įveskite prekės unikalų kodą: ")
    return code

def getBrandName():
    brandName = input("Pasirinkite prekės tiekėją (KROSS, Rondo, Pinarello, Le Grand):")
    return brandName



def convert_docx_to_html(file_path):
    html = pypandoc.convert_file(file_path, 'html')
    return html


def addDescriptionFromWord(driver, file_path):
    try:
        # Convert Word document to HTML
        html_content = convert_docx_to_html(file_path)

        # Wait for the iframe to load and switch to it
        iframe = WebDriverWait(driver, 10).until(
            EC.frame_to_be_available_and_switch_to_it((By.ID, "form_step1_description_2_ifr"))
        )

        # Inject the HTML content into the body of the TinyMCE editor
        script = """
        var body = document.body;
        body.innerHTML = arguments[0];
        """
        driver.execute_script(script, html_content)

        # Switch back to the main document after finishing interaction
        driver.switch_to.default_content()

    except Exception as e:
        print(f"Failed to add description from Word file: {e}")


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
            




   


def prekiuSavybiuSuvedimas(driver, unique_code, tables_data, tables_data_eng, brandName):
    global filteriuSkaicius
    kelintaSavybe = filteriuSkaicius

    global settings


    time.sleep(1)
    print("Ruošiamasi pildyti lietuvišką versiją puslapio")
    for table in tables_data: #kazkada padaryti kad jeigu prekiu savybe yra pradeta pildyti, kad programa neluztu, bet nlb zinau kaip ta padaryt
        for feature_key, feature_value in table.items():
            pridetiSavybe = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.ID, "add_feature_button"))
            )
            driver.execute_script("arguments[0].scrollIntoView();", pridetiSavybe)
            #time.sleep(0.5)  # Small delay to ensure element is fully interactable

            try:
                # Attempt to click using JavaScript
                driver.execute_script("arguments[0].click();", pridetiSavybe)
            except Exception as e:
                print(f"JavaScript click failed: {e}")
                # Fall back to normal click
                pridetiSavybe.click()

            pasirinktiSavybe = driver.find_element(
                By.ID,
                "select2-form_step1_features_"
                + str(kelintaSavybe)
                + "_feature-container",
            )
            pasirinktiSavybe.click()
            #print("Renkama savybė")
            ieskotiSavybes = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CLASS_NAME, "select2-search__field"))
            )
            ieskotiSavybes.send_keys(feature_key)
            feature_key = feature_key.capitalize()
            
            try:
                WebDriverWait(driver, 2).until(EC.presence_of_element_located((By.CLASS_NAME, "select2-results__option"))) 
                if tikrintiArSavybeRasta(driver):
                   # print(f"Nerasta '{feature_key}', bet informaija supildyta.") 
                    pasirinktiSavybe.click()
                    savybesAprasymas = driver.find_element(
                    By.ID, "form_step1_features_" + str(kelintaSavybe) + "_custom_value_2"
                    )
                    savybesAprasymas.send_keys(feature_value + Keys.TAB)
                    kelintaSavybe+=1
                    continue    
                
                if feature_key == "Padangos - padangos plotis (mm / col.)":
                    print("PAKEICIAU")
                    feature_key = "Padangos - Padangos plotis (mm / col.)"

                xpath_expression = f"//li[. = '{feature_key}']" 
                poPaieskosVirstutinisElementas = WebDriverWait(driver, 1).until(
                    EC.presence_of_element_located((By.XPATH, xpath_expression))
                )
                poPaieskosVirstutinisElementas.click()
                

            except TimeoutException:
                print(f"Nerasta '{feature_key}'.") #galima biski geriau padaryt
                continue
            savybesAprasymas = driver.find_element(
                By.ID, "form_step1_features_" + str(kelintaSavybe) + "_custom_value_2"
            )
            savybesAprasymas.send_keys(feature_value + Keys.TAB)
            #print(feature_key + "  :  " + feature_value)

            kelintaSavybe += 1
        # suletinti irasyma
        # time.sleep(1)

    # savybiu surasymas anglu kalbai

    

    kelintaSavybe = filteriuSkaicius
    print("Lietuviškai užpildyta")
    print("Ruošiamasi pildyti anglišką versiją puslapio")
    time.sleep(1)

    for table in tables_data_eng:
        for feature_key, feature_value in table.items():

            wait = WebDriverWait(driver, 10)
            language_dropdown_element = wait.until(
                EC.element_to_be_clickable((By.ID, "form_switch_language"))
            )

            driver.execute_script("arguments[0].click();", language_dropdown_element)

            language_dropdown = Select(language_dropdown_element)
            language_dropdown.select_by_value("en")

            savybesAprasymas = driver.find_element(
                By.ID, "form_step1_features_" + str(kelintaSavybe) + "_custom_value_1"
            )
            savybesAprasymas.send_keys(
                feature_value + Keys.TAB
            )  # Use the feature value here
            #print(feature_key + " savybė aprašyta:  " + feature_value)
            
            kelintaSavybe += 1

    print("Prekė angliškai užpildyta")
    
    # if settings and settings[0] is True:
    kelintaSavybe = filteriuSkaicius
    print("Ruošiamasi pildyti latvišką versiją puslapio")
    time.sleep(1)

    for table in tables_data_eng:
        for feature_key, feature_value in table.items():
            # Switch to the Latvian language
            wait = WebDriverWait(driver, 10)
            language_dropdown_element = wait.until(
                EC.element_to_be_clickable((By.ID, "form_switch_language"))
            )
            driver.execute_script("arguments[0].click();", language_dropdown_element)
            language_dropdown = Select(language_dropdown_element)
            language_dropdown.select_by_value("lv")

            # Locate all feature containers dynamically
            feature_containers = driver.find_elements(
                By.XPATH, "//span[contains(@id, 'select2-form_step1_features_')]"
            )

            feature_filled = False  # Flag to check if the feature has been filled

            for element in feature_containers:
                container_id = element.get_attribute("id")

                # Validate the ID format and skip if it's unexpected
                if not container_id or len(container_id.split("_")) < 4:
                    print(f"Unexpected ID format: {container_id}. Skipping.")
                    continue

                feature_number = container_id.split("_")[3]
                current_feature = element.get_attribute("title")

                # Case-insensitive comparison
                if current_feature.lower() == feature_key.lower():
                    try:
                        # Locate the input field using the feature number
                        input_element = driver.find_element(
                            By.ID, f"form_step1_features_{feature_number}_custom_value_3"
                        )
                        input_element.clear()  # Clear any existing value
                        input_element.send_keys(feature_value + Keys.TAB)
                        feature_filled = True  # Mark as filled
                    except Exception as e:
                        print(f"Error filling {feature_key}: {e}")
                    break  # Exit the loop once the correct feature is filled

            if not feature_filled:
                print(f"Ypatybė {feature_key} nerasta ir neužpildyta. Pasitikrinkite vertimą ir ar iš vis yra prestashope.")

    print("Prekė latviškai užpildyta")





