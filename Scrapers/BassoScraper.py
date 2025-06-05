import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
from bs4 import BeautifulSoup
from Utilities.scrapeUtilities import (
    loadTranslations,
    loadValueTranslations,
    verstTikPirmaZodi,
)
from generalUtilities import loadCredentials
import re

internalCounter = 0
username, password = loadCredentials("Assets/credentials.txt")

def process_special_values(raw_key: str, raw_val: str, target_language: str = 'lt') -> str:
    """Process special value cases with language-specific handling"""
    processed_val = raw_val
    
    # # 1. Handle (if compatible) replacement only for Lithuanian
    # if target_language.lower() == 'lt' and "(if compatible)" in processed_val:
    #     processed_val = processed_val.replace("(if compatible)", "(jeigu suderinama)")
    
    # 2. Handle rotor values splitting
    if raw_key.lower() in ["front rotors", "rear rotors"]:
        if "Front:" in processed_val and "Rear:" in processed_val:
            if "front" in raw_key.lower():
                processed_val = processed_val.split("Front:")[1].split(";")[0].strip()
            else:
                processed_val = processed_val.split("Rear:")[1].strip()
            processed_val = processed_val.replace(" mm", "mm").replace("  ", " ")
    
    # 3. Handle spacer values formatting
    if raw_key.lower() == "spacers":
        matches = re.findall(r'(\d+\s*[xX]\s*\d+)', processed_val)
        if matches:
            processed_val = matches[0].lower().replace(" ", "").replace("x", "x")
    
    return processed_val

def scrapeAndTranslateToFileBasso(bicycleUrlOrCode, outputFile, driver):
    global internalCounter, username, password

    keyTranslations = loadTranslations("Assets/Translations/BassoENG-LT.txt")
    valueTranslations = loadValueTranslations("Assets/Translations/vertimasSavybesENG-LT.txt")
    
    wait = WebDriverWait(driver, 15)
    original_tab = driver.current_window_handle

    try:
        # Open new tab
        driver.execute_script("window.open('');")
        driver.switch_to.window(driver.window_handles[-1])
        
        # Navigate to login
        driver.get("https://bassobikes.com/en/login")
        if internalCounter == 0:
            wait.until(EC.presence_of_element_located((By.ID, "basic_username")))
        
        if internalCounter == 0:
            internalCounter += 1
            # Login process
            username_field = driver.find_element(By.ID, "basic_username")
            password_field = driver.find_element(By.ID, "basic_password")
            username_field.send_keys(username)
            password_field.send_keys(password)
            login_button = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
            login_button.click()
            wait.until(EC.presence_of_element_located((By.CLASS_NAME, "account")))
            
            # Navigate to account
            account_link = driver.find_element(By.CSS_SELECTOR, "div.account a")
            account_link.click()
            
            try:
                cookie_button = wait.until(EC.element_to_be_clickable((By.ID, "rcc-confirm-button")))
                cookie_button.click()
            except (TimeoutException, NoSuchElementException):
                pass
        
        # Navigate to saved configurations
        saved_configs_link = wait.until(EC.element_to_be_clickable(
            (By.XPATH, "//h4[normalize-space()='Saved configurations']/ancestor::a")
        ))
        saved_configs_link.click()
        
        # Find target bike
        wait.until(EC.presence_of_element_located((By.CLASS_NAME, "ConfigurationSavedItem")))
        bike_elements = driver.find_elements(By.CLASS_NAME, "ConfigurationSavedItem")
        target_bike = None
        
        for bike in bike_elements:
            try:
                code_element = bike.find_element(By.CLASS_NAME, "Pro-Grid-number")
                if bicycleUrlOrCode in code_element.text:
                    target_bike = bike
                    break
            except (NoSuchElementException, StaleElementReferenceException):
                continue
        
        if not target_bike:
            return f"[ERROR] Bicycle with code {bicycleUrlOrCode} not found"
        
        # Open bike details
        dropdown_trigger = target_bike.find_element(By.CLASS_NAME, "dropdown-configurationSaved-trigger")
        dropdown_trigger.click()
        time.sleep(1)
        
        details_option = wait.until(EC.element_to_be_clickable(
            (By.XPATH, "//nav[@class='nav-option-configurationSaved']//a[normalize-space()='Details']")
        ))
        details_option.click()
        
        # Extract data
        wait.until(EC.presence_of_element_located((By.CLASS_NAME, "ant-modal-body")))
        time.sleep(2)
        
        allData = []
        uniqueKeys = set()
        
        soup = BeautifulSoup(driver.page_source, "html.parser")
        modal_body = soup.select_one(".ant-modal-body")
        sections = modal_body.select(".Config-del-row")
        
        specialKeys = {
            "brakes": ["Front Brakes", "Rear Brakes"],
            "rotors": ["Front Rotors", "Rear Rotors"],
            "hubs": ["Front Hub", "Rear Hub"]
        }

        for section in sections:
            tableData = {}
            rawTable = {}
            entries = section.select(".ant-col")

            for entry in entries:
                keyElem = entry.find("h3")
                valElem = entry.find("span")

                if not keyElem or not valElem:
                    continue

                rawKey = keyElem.get_text(strip=True).replace(":", "").title()
                rawVal = valElem.get_text(strip=True)

                if not rawKey or not rawVal:
                    continue

                rawTable[rawKey] = rawVal

            # Merge Crank and Crank Arm
            if "Crank" in rawTable and "Crank Arm" in rawTable:
                rawTable["Crank"] = f"{rawTable['Crank']} {rawTable['Crank Arm']}"
                del rawTable["Crank Arm"]
            elif "Crank Arm" in rawTable:
                rawTable["Crank"] = rawTable.pop("Crank Arm")

            for rawKey, rawVal in rawTable.items():
                keyLower = rawKey.lower()

                if keyLower in specialKeys:
                    for subKey in specialKeys[keyLower]:
                        translatedKey = keyTranslations.get(subKey, subKey)
                        translatedRawVal = valueTranslations.get(rawVal, rawVal)
                        translatedRawVal = process_special_values(subKey, translatedRawVal, 'lt')
                        translatedValue = verstTikPirmaZodi(translatedRawVal, valueTranslations)
                        tableData[translatedKey] = translatedValue
                        uniqueKeys.add(translatedKey)
                else:
                    translatedKey = keyTranslations.get(rawKey, rawKey)
                    translatedRawVal = valueTranslations.get(rawVal, rawVal)
                    translatedRawVal = process_special_values(rawKey, translatedRawVal, 'lt')
                    translatedVal = verstTikPirmaZodi(translatedRawVal, valueTranslations)
                    tableData[translatedKey] = translatedVal
                    uniqueKeys.add(translatedKey)

            if tableData:
                allData.append(tableData)

        # Write to file
        with open(outputFile, "w", encoding="utf-8") as f:
            for table in allData:
                for key, val in table.items():
                    f.write(f"{key}: {val}\n")
                f.write("\n")
        
        return f"✔ Successfully scraped bike with code {bicycleUrlOrCode}. Total unique keys: {len(uniqueKeys)}"
    
    except Exception as e:
        return f"[ERROR] {e}"
    
    finally:
        driver.close()
        driver.switch_to.window(original_tab)