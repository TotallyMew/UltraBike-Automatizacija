from unittest import skip
from scrapeUtilities import *
from generalUtilities import *
import requests
from bs4 import BeautifulSoup
from config import settings

def scrapeAndTranslateToFileOctaneOne(url, output_file):
    # Load translation dictionaries
    key_translations = loadTranslations(resource_path("OctaneENG-LT.txt"))
    value_translations = loadValueTranslations(resource_path("vertimasSavybesENG-LT.txt"))

    # Initialize storage for all data and unique keys
    all_data = []
    unique_keys = set()

    try:
        # Fetch the page content
        response = requests.get(url)
        response.raise_for_status()  # Check for HTTP errors

        # Parse the page content with BeautifulSoup
        soup = BeautifulSoup(response.text, "html.parser")
        spec_items = soup.find_all("div", class_="div-spec-item")

        if not spec_items:
            print("Octane One puslapio struktura pasikeitė, atnaujinkite programą")
            return "Program update required: Octane One page structure has changed."

        # Iterate over all found specification items
        for item in spec_items:
            
            key = item.find("div", class_="tb-spec-type").get_text(strip=True).title()
            value = item.find("div", class_="tb-spec-text").get_text(strip=True)
            if key.lower() == "derailleurs":
    # Create two entries for front and rear derailleur
                key = "front derailleur"            
                translated_key = "priekinis pavarų perjungėjas"
                translated_value = value_translations.get(value, value)
                translated_value = verstTikPirmaZodi(translated_value, value_translations)
                all_data.append((translated_key, translated_value))
                unique_keys.add(translated_key)
                
                key = "rear derailleur"
                translated_key = "galinis pavarų perjungejas"
                translated_value = value_translations.get(value, value)
                translated_value = verstTikPirmaZodi(translated_value, value_translations)
                all_data.append((translated_key, translated_value))
                unique_keys.add(translated_key)
                continue
            if key.lower() == "levers/shifters":
# Create two entries for front and rear derailleur
                key = "levers"            
                translated_key = "stabdžių rankenėlės"
                translated_value = value_translations.get(value, value)
                translated_value = verstTikPirmaZodi(translated_value, value_translations)
                all_data.append((translated_key, translated_value))
                unique_keys.add(translated_key)
                
                key = "shifters"
                translated_key = "pavarų perjungimo rankenėlės"
                translated_value = value_translations.get(value, value)
                translated_value = verstTikPirmaZodi(translated_value, value_translations)
                all_data.append((translated_key, translated_value))
                unique_keys.add(translated_key)
                continue


            translated_key = key_translations.get(key, key)
            translated_value = value_translations.get(value, value)
            translated_value = verstTikPirmaZodi(translated_value, value_translations)
            all_data.append((translated_key, translated_value))
            unique_keys.add(translated_key)

        # Write the translated data to a file
        with open(output_file, "w", encoding="utf-8") as file:
            for key, value in all_data:
                file.write(f"{key}: {value}\n")
            file.write("\n")

        uniqueKeysTotal = len(unique_keys)
    except requests.HTTPError as http_err:
        print(f"HTTP Error: {http_err}")
        return "Klaida: Nepavyko gauti duomenų iš svetainės. Patikrinkite URL arba bandykite vėliau."
    except requests.RequestException as req_err:
        print(f"Request Error: {req_err}")
        return "Klaida: Problema su tinklo užklausa. Bandykite vėliau."
    except Exception as e:
        print(f"Error: {e}")
        return f"Nepavyko apdoroti duomenų dėl klaidos: {e}"

    return f"Total unique keys: {uniqueKeysTotal}"

def automatizacija(
    table_class, pirminisVertimas_I_Lietuviu, galutinisVertimas_I_ANGLU, driver, brandName
):
    global settings
    code = getCode()
    url = getURL(brandName)
    scrapeAndTranslateToFileOctaneOne(url, pirminisVertimas_I_Lietuviu)
    versti_I_Anglu(pirminisVertimas_I_Lietuviu, galutinisVertimas_I_ANGLU, resource_path("vertimasSavybesLT-ENG.txt"))
    tables_data = nuskaitytIsverstasFailasLietuviu(pirminisVertimas_I_Lietuviu)
    tables_data_eng = nuskaitytIsverstasFailasAnglu(galutinisVertimas_I_ANGLU)
    prekesPaspaudimas(driver, brandName,code)
    prekiuSavybiuSuvedimas(driver, code, tables_data, tables_data_eng, brandName)
    addBrandName(driver,brandName)

def mainOctaneFunction(driver, brandName):

    table_class = "c-table is-specification"

    pirminisVertimas_I_Lietuviu = resource_path("pabaigtaOLT.txt")
    galutinisVertimas_I_ANGLU = resource_path("pabaigtaOENG.txt")

    automatizacija(
            table_class, pirminisVertimas_I_Lietuviu, galutinisVertimas_I_ANGLU, driver, brandName
        )



