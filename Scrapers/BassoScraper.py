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
    resource_path
)

def scrapeAndTranslateToFileBasso(target_code, outputFile, driver):
    keyTranslations = loadTranslations(resource_path("Resources/PinarelloENG-LT.txt"))
    valueTranslations = loadValueTranslations(resource_path("Resources/vertimasSavybesENG-LT.txt"))
    
    
    wait = WebDriverWait(driver, 15)
    original_tab = driver.current_window_handle
    
    try:
        # STEP 1: Open a new tab
        driver.execute_script("window.open('');")
        driver.switch_to.window(driver.window_handles[-1])  # Switch to new tab
        
        # STEP 2: Navigate to the login page
        driver.get("https://bassobikes.com/en/login")
        wait.until(EC.presence_of_element_located((By.ID, "basic_username")))
        
        # STEP 3: Login with credentials
        username_field = driver.find_element(By.ID, "basic_username")
        password_field = driver.find_element(By.ID, "basic_password")
        
        username_field.send_keys("augustas.koko@gmail.com") 
        password_field.send_keys("spanguole10") 
        
        login_button = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
        login_button.click()
        
        # Wait for login to complete
        wait.until(EC.presence_of_element_located((By.CLASS_NAME, "account")))
        
        # STEP 4: Navigate to the account dashboard
        account_link = driver.find_element(By.CSS_SELECTOR, "div.account a")
        account_link.click()
        
        # Handle cookie consent banner if present
        try:
            cookie_button = wait.until(EC.element_to_be_clickable((By.ID, "rcc-confirm-button")))
            cookie_button.click()
        except (TimeoutException, NoSuchElementException):
            # Cookie banner may not appear if cookies are already accepted
            pass
        
        # STEP 5: Navigate to saved configurations
        saved_configs_link = wait.until(EC.element_to_be_clickable(
            (By.XPATH, "//h4[normalize-space()='Saved configurations']/ancestor::a")
        ))
        saved_configs_link.click()
        
        # STEP 6: Wait for the grid to load and find the specific bicycle by code
        wait.until(EC.presence_of_element_located((By.CLASS_NAME, "ConfigurationSavedItem")))
        
        bike_elements = driver.find_elements(By.CLASS_NAME, "ConfigurationSavedItem")
        target_bike = None
        
        for bike in bike_elements:
            try:
                code_element = bike.find_element(By.CLASS_NAME, "Pro-Grid-number")
                if target_code in code_element.text:
                    target_bike = bike
                    break
            except (NoSuchElementException, StaleElementReferenceException):
                continue
        
        if not target_bike:
            return f"[ERROR] Bicycle with code {target_code} not found"
        
        # STEP 7: Click the action button and then Details
        dropdown_trigger = target_bike.find_element(By.CLASS_NAME, "dropdown-configurationSaved-trigger")
        dropdown_trigger.click()
        time.sleep(1)  # Wait for dropdown to appear
        
        details_option = wait.until(EC.element_to_be_clickable(
            (By.XPATH, "//nav[@class='nav-option-configurationSaved']//a[normalize-space()='Details']")
        ))
        details_option.click()
        
        # STEP 8: Wait for the modal to load
        wait.until(EC.presence_of_element_located((By.CLASS_NAME, "ant-modal-body")))
        time.sleep(2)  # Give it a moment to fully load
        
        # STEP 9: Extract all the bike parts and their descriptions
        allData = []
        uniqueKeys = set()
        
        # Find all section rows using BeautifulSoup parsing
        soup = BeautifulSoup(driver.page_source, "html.parser")
        modal_body = soup.select_one(".ant-modal-body")
        sections = modal_body.select(".Config-del-row")
        
        for section in sections:
            tableData = {}
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
                    
                translatedKey = keyTranslations.get(rawKey, rawKey)
                translatedVal = valueTranslations.get(rawVal, rawVal)
                translatedVal = verstTikPirmaZodi(translatedVal, valueTranslations)
                
                tableData[translatedKey] = translatedVal
                uniqueKeys.add(translatedKey)
            
            if tableData:
                allData.append(tableData)
        
        # STEP 10: Write to file
        with open(outputFile, "w", encoding="utf-8") as f:
            for table in allData:
                for key, val in table.items():
                    f.write(f"{key}: {val}\n")
                f.write("\n")
        
        return f"✔ Successfully scraped bike with code {target_code}. Total unique keys: {len(uniqueKeys)}"
    
    except Exception as e:
        return f"[ERROR] {e}"
    
    finally:
        # STEP 11: Close the current tab and return to the original
        driver.close()
        driver.switch_to.window(original_tab)
        
