import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
from bs4 import BeautifulSoup
from Utilities.TranslationHandler import TranslationHandler, load_translations, load_value_translations
from Utilities.WebIntercationHandler import WebInteractionHandler

def loadCredentials(driver):
    web_handler = WebInteractionHandler(driver)
    username, password = web_handler.load_credentials("Assets/credentials.txt")
    return username, password

def scrapeAndTranslateToFileLeeCougan(target_code, outputFile, driver, db_manager=None):
    translation_handler = TranslationHandler(db_manager)
    
    # Component names (keys)
    keyTranslations = translation_handler.get_translations_by_category("EN", "LT", "component")
    
    # Materials, colors, properties (values)
    valueTranslations = {}
    valueTranslations.update(translation_handler.get_translations_by_category("EN", "LT", "material"))
    valueTranslations.update(translation_handler.get_translations_by_category("EN", "LT", "color"))
    valueTranslations.update(translation_handler.get_translations_by_category("EN", "LT", "property"))

    username, password = loadCredentials(driver)

    close_driver_at_end = False
    if driver is None:
        close_driver_at_end = True
        options = webdriver.ChromeOptions()
        driver = webdriver.Chrome(options=options)
        driver.maximize_window()

    wait = WebDriverWait(driver, 15)
    original_tab = driver.current_window_handle

    try:
        # STEP 1: Open new tab
        driver.execute_script("window.open('');")
        driver.switch_to.window(driver.window_handles[-1])

        # STEP 2: Go to login
        driver.get("https://leecougan.com/en/login")
        wait.until(EC.presence_of_element_located((By.ID, "basic_username")))

        # STEP 3: Login
        username_field = driver.find_element(By.ID, "basic_username")
        password_field = driver.find_element(By.ID, "basic_password")
        username_field.send_keys(username)
        password_field.send_keys(password)
        login_button = driver.find_element(By.XPATH, "//button[@type='submit']")
        login_button.click()
        wait.until(EC.presence_of_element_located((By.CLASS_NAME, "account")))

        # STEP 4: Navigate to dashboard
        account_link = driver.find_element(By.XPATH, "//div[@class='account']/a")
        account_link.click()

        # STEP 5: Handle cookie banner
        try:
            cookie_banner = wait.until(EC.presence_of_element_located((By.CLASS_NAME, "cookie-banner")))
            cookie_button = cookie_banner.find_element(By.ID, "rcc-confirm-button")
            cookie_button.click()
        except (TimeoutException, NoSuchElementException):
            pass

        # STEP 6: Go to saved configurations
        wait.until(EC.element_to_be_clickable(
            (By.XPATH, "//a[contains(@href, '/dashboard/configurator')]")
        )).click()

        wait.until(EC.presence_of_element_located((By.CLASS_NAME, "ConfigurationSavedItem")))
        bike_elements = driver.find_elements(By.CLASS_NAME, "ConfigurationSavedItem")

        target_bike = None
        for bike in bike_elements:
            try:
                code_element = bike.find_element(By.XPATH, ".//div[@class='Pro-Grid-number']/span[@class='value']")
                if code_element.text == target_code:
                    target_bike = bike
                    break
            except (NoSuchElementException, StaleElementReferenceException):
                continue

        if not target_bike:
            return f"[ERROR] Bicycle with code {target_code} not found"

        # STEP 7: Open dropdown and click "Details"
        action_dropdown = target_bike.find_element(By.XPATH, ".//a[@class='ant-dropdown-link']")
        action_dropdown.click()
        time.sleep(1)

        details_option = wait.until(EC.element_to_be_clickable(
            (By.XPATH, "//ul/li/a[text()='Details']")
        ))
        details_option.click()

        # STEP 8: Wait for modal
        wait.until(EC.presence_of_element_located(
            (By.XPATH, "//div[@class='Modal-header']/h2[text()='Configuration Summary']")
        ))
        time.sleep(2)

        # STEP 9: Parse details
        allData = []
        uniqueKeys = set()
        soup = BeautifulSoup(driver.page_source, "html.parser")
        sections = soup.select(".Config-del-row")

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

                rawKey = keyElem.get_text(strip=True).replace(":", "").upper()
                rawVal = valElem.get_text(strip=True)

                if not rawKey or not rawVal:
                    continue

                rawTable[rawKey] = rawVal

            # Merge Crank + Crank Arm
            if "Crank" in rawTable and "Crank Arm" in rawTable:
                combined_val = f"{rawTable['Crank']} + {rawTable['Crank Arm']}"
                rawTable["Crank"] = combined_val
                del rawTable["Crank Arm"]
            elif "Crank Arm" in rawTable:
                rawTable["Crank"] = rawTable.pop("Crank Arm")

            for rawKey, rawVal in rawTable.items():
                keyLower = rawKey.lower()
                if keyLower in specialKeys:
                    for subKey in specialKeys[keyLower]:
                        translatedKey = keyTranslations.get(subKey, subKey)
                        translatedVal = valueTranslations.get(rawVal, rawVal)
                        translatedVal = translation_handler.translate_first_word(translatedVal, valueTranslations)
                        tableData[translatedKey] = translatedVal
                        uniqueKeys.add(translatedKey)
                else:
                    translatedKey = keyTranslations.get(rawKey, rawKey)
                    translatedVal = valueTranslations.get(rawVal, rawVal)
                    translatedVal = translation_handler.translate_first_word(translatedVal, valueTranslations)
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
        driver.close()
        driver.switch_to.window(original_tab)
        if close_driver_at_end:
            driver.quit()