import requests
from bs4 import BeautifulSoup
from scrapeUtilities import loadTranslations, loadValueTranslations, verstTikPirmaZodi
from config import resource_path

def scrapeAndTranslateToFileTREK(url, output_file):
    key_translations = loadTranslations(resource_path("vertimasDetalesPL-LT.txt"))
    value_translations = loadValueTranslations(resource_path("vertimasSavybesENG-LT.txt"))

    all_data = []
    unique_keys = set()

    try:
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        # Locate the entire specifications component
        spec_section = soup.find("section", id="trekProductSpecificationsComponentBOM")
        if not spec_section:
            print("Specifikacijų sekcija nerasta. Patikrinkite struktūrą.")
            return

        # Find all spec tables within collapsible sections
        tables = spec_section.find_all("table", class_="sprocket__table spec")
        if not tables:
            print("Specifikacijų lentelės nerastos. Patikrinkite HTML struktūrą.")
            return

        for table in tables:
            rows = table.find_all("tr")
            table_data = {}

            for row in rows:
                # Extract the <th> as the key and <td> as the value
                key_element = row.find("th")
                value_element = row.find("td")

                if key_element and value_element:
                    key = key_element.get_text(strip=True).title()
                    value = value_element.get_text(separator=" ", strip=True)  # Handle <br>, <a>, etc.

                    if value.upper() != "BRAK":
                        translated_key = key_translations.get(key, key)
                        translated_value = value_translations.get(value, value)
                        translated_value = verstTikPirmaZodi(translated_value, value_translations)

                        table_data[translated_key] = translated_value
                        unique_keys.add(translated_key)

            if table_data:
                all_data.append(table_data)

        # Write translated specs to file
        with open(output_file, "w", encoding="utf-8") as file:
            for table_data in all_data:
                for key, value in table_data.items():
                    file.write(f"{key}: {value}\n")
                file.write("\n")

        return f"Total unique keys: {len(unique_keys)}"

    except requests.HTTPError as e:
        return f"HTTP klaida: {e}"
    except Exception as e:
        return f"Nepavyko apdoroti duomenų: {e}"


def automatizacija(
    pirminisVertimas_I_Lietuviu, galutinisVertimas_I_ANGLU, driver, brandName, description
):
    global settings
    code = getCode()
    url = getURL(brandName)
    scrapeAndTranslateToFileTREK(url, pirminisVertimas_I_Lietuviu)
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
