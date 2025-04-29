import requests
from bs4 import BeautifulSoup
from scrapeUtilities import *
from generalUtilities import *
import urllib3
import certifi
from bs4 import BeautifulSoup
import requests
import urllib3
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import time

def scrapeAndTranslateToFileRondo(url, output_file):
    headers = {
        'User-Agent': 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:52.0) Gecko/20100101 Firefox/52.0',
    }
    response = requests.get(url, headers=headers, verify=False)
    response.raise_for_status()

    soup = BeautifulSoup(response.content, 'html.parser')
    
    # Try the first method
    rows = soup.find_all('tr')
    if not rows:
        # If the first method didn't find anything, try the alternative structure
        rows = soup.select('table[border="1"] tr')  # Adjust the selector based on your alternative HTML structure

    key_translations = loadTranslations(resource_path("RondoENG-LT.txt"))
    value_translations = loadValueTranslations(resource_path("vertimasSavybesENG-LT.txt"))
    all_data = []

    for row in rows:
        cells = row.find_all('td')
        if len(cells) == 2:
            key = cells[0].get_text(strip=True).replace(':', '').strip().title()
            value = cells[1].get_text(strip=True).strip()
            if value == '-' or not value:
                continue
            
            # Handling special cases
            if key.lower() == "brakes":
                keys_to_check = ["Front Brakes", "Rear Brakes"]
                for sub_key in keys_to_check:
                    translated_key = key_translations.get(sub_key, sub_key)
                    translated_value = value_translations.get(value, value)
                    translated_value = verstTikPirmaZodi(translated_value, value_translations)
                    all_data.append({translated_key: translated_value})
            elif key.lower() == "rotors":
                keys_to_check = ["Front Rotors", "Rear Rotors"]
                for sub_key in keys_to_check:
                    translated_key = key_translations.get(sub_key, sub_key)
                    translated_value = value_translations.get(value, value)
                    translated_value = verstTikPirmaZodi(translated_value, value_translations)
                    all_data.append({translated_key: translated_value})
            elif key.lower() == "hubs":
                keys_to_check = ["Front Hub", "Rear Hub"]
                for sub_key in keys_to_check:
                    translated_key = key_translations.get(sub_key, sub_key)
                    translated_value = value_translations.get(value, value)
                    translated_value = verstTikPirmaZodi(translated_value, value_translations)
                    all_data.append({translated_key: translated_value})
            else:
                translated_key = key_translations.get(key, key)
                translated_value = value_translations.get(value, value)
                translated_value = verstTikPirmaZodi(translated_value, value_translations)
                all_data.append({translated_key: translated_value})

    # Writing to file
    with open(resource_path(output_file), "w", encoding="utf-8") as file:
        for data in all_data:
            for key, value in data.items():
                file.write(f"{key}: {value}\n")
            file.write("\n")





def automatizacija(
    pirminisVertimas_I_Lietuviu, galutinisVertimas_I_ANGLU, driver, brandName
):

    code = getCode()
    url = getURL(brandName)
    scrapeAndTranslateToFileRondo(url, pirminisVertimas_I_Lietuviu)
    versti_I_Anglu(pirminisVertimas_I_Lietuviu, galutinisVertimas_I_ANGLU, resource_path("vertimasSavybesLT-ENG.txt"))
    tables_data = nuskaitytIsverstasFailasLietuviu(pirminisVertimas_I_Lietuviu)
    tables_data_eng = nuskaitytIsverstasFailasAnglu(galutinisVertimas_I_ANGLU)
    prekesPaspaudimas(driver, brandName,code)
    filteriuPridejimas(driver)
    prekiuSavybiuSuvedimas(driver, code, tables_data, tables_data_eng, brandName)
    addBrandName(driver,brandName)


def mainRondoFunction(driver, brandName):
    pirminisVertimas_I_Lietuviu = resource_path("pabaigtaRLT.txt")
    galutinisVertimas_I_ANGLU = resource_path("pabaigtaRENG.txt")

    automatizacija(
            pirminisVertimas_I_Lietuviu, galutinisVertimas_I_ANGLU, driver, brandName
        )

