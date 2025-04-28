from selenium.webdriver.common import keys
from scrapeUtilities import *
from generalUtilities import *
import requests
from bs4 import BeautifulSoup
from config import settings

def scrapeAndTranslateToFileRascal(url, output_file):
    key_translations = loadTranslations(resource_path("RascalENG-LT.txt"))
    value_translations = loadValueTranslations(resource_path("vertimasSavybesENG-LT.txt"))

    all_data = []
    unique_keys = set()
    selected_option_index = None  # Variable to store the user's choice

    try:
        response = requests.get(url)
        response.raise_for_status()  # HTTP error check 

        soup = BeautifulSoup(response.text, "html.parser")
        if soup.find("ul", class_="list-unstyled product-params split-params"):
            product_params = soup.find("ul", class_="list-unstyled product-params split-params")
        else:
            product_params = soup.find("ul", class_="list-unstyled product-params")

        if not product_params:
            print("Rascal puslapio struktura pasikeitė, atnaujinkite programą")
            exit()

        for li in product_params.find_all("li"):
            key_span = li.find("span")
            value_spans = key_span.find_next_siblings("span")  

            if key_span and value_spans:
                key = key_span.get_text(strip=True).title()
               
                if len(value_spans) > 1:
                    if selected_option_index is None: 
                        while True:  
                            print(f"Rasta daugiau nei vienas prekės variantas puslapyje.")
                            for index, value_span in enumerate(value_spans, start=1):
                                value = value_span.get_text(strip=True)
                                print(f"{index}: {value}")

                            try:
                                selected_option_index = int(input(". Pasirinkite pagal kurį rašyti: ")) - 1
                                if 0 <= selected_option_index < len(value_spans):
                                    break  
                                else:
                                    print("Neteisingas pasirinkimas.")
                            except ValueError:
                                print("Neteisingas pasirinkimas. Pasirinkite per naują.")

                    selected_value = value_spans[selected_option_index].get_text(strip=True)
                else:
                    selected_value = value_spans[0].get_text(strip=True)
                
                if key.lower() == "brakes":
                    keys_to_check = ["Front Brakes", "Rear Brakes"]
                    for sub_key in keys_to_check:
                        translated_key = key_translations.get(sub_key, sub_key)
                        translated_value = value_translations.get(selected_value, selected_value)
                        translated_value = verstTikPirmaZodi(translated_value, value_translations)
                        all_data.append({translated_key: translated_value})
                else:
                    translated_key = key_translations.get(key, key)
                    translated_value = value_translations.get(selected_value, selected_value)
                    translated_value = verstTikPirmaZodi(translated_value, value_translations)
                    all_data.append({translated_key: translated_value})

        # Write the data to the output file
        with open(output_file, "w", encoding="utf-8") as file:
            for table_data in all_data:
                for key, value in table_data.items():
                    if key and value:
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
    pirminisVertimas_I_Lietuviu, galutinisVertimas_I_ANGLU, driver, brandName
):

    code = getCode()
    url = getURL(brandName)
    scrapeAndTranslateToFileRascal(url, pirminisVertimas_I_Lietuviu)
    versti_I_Anglu(pirminisVertimas_I_Lietuviu, galutinisVertimas_I_ANGLU, resource_path("vertimasSavybesLT-ENG.txt"))
    tables_data = nuskaitytIsverstasFailasLietuviu(pirminisVertimas_I_Lietuviu)
    tables_data_eng = nuskaitytIsverstasFailasAnglu(galutinisVertimas_I_ANGLU)
    prekesPaspaudimas(driver, brandName,code)
    filteriuPridejimas(driver)
    prekiuSavybiuSuvedimas(driver, code, tables_data, tables_data_eng, brandName)
    addBrandName(driver,brandName)


def mainRascalFunction(driver, brandName):
    pirminisVertimas_I_Lietuviu = resource_path("pabaigtaRasLT.txt")
    galutinisVertimas_I_ANGLU = resource_path("pabaigtaRasENG.txt")

    automatizacija(
            pirminisVertimas_I_Lietuviu, galutinisVertimas_I_ANGLU, driver, brandName
        )



