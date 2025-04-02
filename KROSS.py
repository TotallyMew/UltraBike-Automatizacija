import LentelesVertimas
from scrapeUtilities import *
from generalUtilities import *
from LentelesVertimas import lentelesVertimas
import requests
from bs4 import BeautifulSoup
from config import settings

import requests
from bs4 import BeautifulSoup

def scrapeAndTranslateToFileKROSS(url, output_file):
    key_translations = loadTranslations(resource_path("vertimasDetalesPL-LT.txt"))
    value_translations = loadValueTranslations(resource_path("vertimasSavybesPL-LT.txt"))

    all_data = []
    unique_keys = set()

    try:
        response = requests.get(url)
        response.raise_for_status()  # HTTP error check

        soup = BeautifulSoup(response.text, "html.parser")
        additional_section = soup.find("div", id="additional")

        if not additional_section:
            print("KROSS puslapio struktūra pasikeitė, atnaujinkite programą")
            exit()

        tables = additional_section.find_all("table", class_="additional-attributes-table")

        if not tables:
            print("Nerasta duomenų lentelių. Patikrinkite struktūrą.")
            exit()

        for table in tables:
            rows = table.find_all("tr")
            table_data = {}
            
            for row in rows:
                cells = row.find_all("td")
                if len(cells) >= 2:
                    key = cells[0].get_text(strip=True).title()
                    value = cells[1].get_text(strip=True)
                    
                    if value.upper() != "BRAK":
                        translated_key = key_translations.get(key, key)
                        translated_value = value_translations.get(value, value)
                        translated_value = verstTikPirmaZodi(translated_value, value_translations)
                        
                        table_data[translated_key] = translated_value
                        unique_keys.add(translated_key)

            all_data.append(table_data)

        with open(output_file, "w", encoding="utf-8") as file:
            for table_data in all_data:
                for key, value in table_data.items():
                    file.write(f"{key}: {value}\n")
                file.write("\n")

        uniqueKeysTotal = len(unique_keys)

    except requests.HTTPError as e:
        print(f"HTTP Error: {e}")
        return "Klaida: Nepavyko gauti duomenų iš svetainės. Patikrinkite URL arba bandykite vėliau."
    except Exception as e:
        print(f"Error: {e}")
        return f"Nepavyko apdoroti duomenų dėl klaidos: {e}"

    return f"Total unique keys: {uniqueKeysTotal}"  
 

def automatizacija(
    pirminisVertimas_I_Lietuviu, galutinisVertimas_I_ANGLU, driver, brandName, description
):
    global settings
    code = getCode()
    url = getURL(brandName)
    scrapeAndTranslateToFileKROSS(url, pirminisVertimas_I_Lietuviu)
    versti_I_Anglu(pirminisVertimas_I_Lietuviu, galutinisVertimas_I_ANGLU, resource_path("vertimasSavybesLT-ENG.txt"))
    tables_data = nuskaitytIsverstasFailasLietuviu(pirminisVertimas_I_Lietuviu)
    tables_data_eng = nuskaitytIsverstasFailasAnglu(galutinisVertimas_I_ANGLU)
    
    prekesPaspaudimas(driver, brandName,code)
    if settings and settings [4] is True:
        lentelesVertimas()
    else:
        print("Lentelių vertimas praleistas, tai galite pakeisti nustatymuose (settings.txt).")
    if settings and settings[2] is True:
        siustiNuotraukasKROSS(url, driver)
        sukeltiNuotraukasKROSS(driver)
    filteriuPridejimas(driver)
    prekiuSavybiuSuvedimas(driver, code, tables_data, tables_data_eng, brandName)
    addBrandName(driver,brandName)


   # addDescriptionFromWord(driver, description) # add description from word file

def mainKrossFunction(driver, brandName):

    description = "testas.docx"
    pirminisVertimas_I_Lietuviu = resource_path("pabaigtaLT.txt")
    galutinisVertimas_I_ANGLU = resource_path("pabaigtaENG.txt")

    automatizacija(
            pirminisVertimas_I_Lietuviu, galutinisVertimas_I_ANGLU, driver, brandName, description
        )

