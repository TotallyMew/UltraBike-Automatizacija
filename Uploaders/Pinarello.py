import requests
from bs4 import BeautifulSoup
from Utilities.scrapeUtilities import *
from generalUtilities import *



def scrapeAndTranslateToFilePinarello(url, output_file_path):
    headers = {'User-Agent': 'Mozilla/5.0'}
    response = requests.get(url, headers=headers)
    response.raise_for_status()  # Ensure we handle HTTP errors

    soup = BeautifulSoup(response.content, 'html.parser')
    parts_divs = soup.find_all('div', class_='col-lg-4 p-3')

    key_translations = loadTranslations(resource_path("PinarelloENG-LT.txt"))
    value_translations = loadValueTranslations(resource_path("vertimasSavybesENG-LT.txt"))
    all_data = []

    with open(output_file_path, 'w', encoding='utf-8') as file:
        for part_div in parts_divs:
            title_div = part_div.find('div', class_='text--small color--mid-dark-gray mb-2')
            spec_div = part_div.find('div', class_='color--dark-gray')
            if title_div is not None and title_div.text.strip() != "" and spec_div is not None and spec_div.text.strip() != "":
                title = title_div.get_text(strip=True).replace(':', '').strip().title()
                spec = spec_div.get_text(strip=True).strip()
                if title.lower() == "axles disc":
                    titles_to_check = ["Front Hub", "Rear Hub"]
                    for sub_title in titles_to_check:
                        translated_title = key_translations.get(sub_title, sub_title)  # Translate the key
                        translated_spec = value_translations.get(spec, spec)  # Translate the value
                        file.write(f"{translated_title}: {translated_spec}\n")
                        all_data.append({translated_title: translated_spec})
                else:
                    translated_title = key_translations.get(title, title)  # Translate the key
                    translated_spec = value_translations.get(spec, spec)  # Translate the value
                    file.write(f"{translated_title}: {translated_spec}\n")
                    all_data.append({translated_title: translated_spec})

        
        file.write("\n")

    return f"Data from all parts saved to {output_file_path}. Total unique entries: {len(all_data)}"

def automatizacija(
    pirminisVertimas_I_Lietuviu, galutinisVertimas_I_ANGLU, driver, brandName
):

    code = getCode()
    url = getURL(brandName)
    scrapeAndTranslateToFilePinarello(url, pirminisVertimas_I_Lietuviu)
    versti_I_Anglu(pirminisVertimas_I_Lietuviu, galutinisVertimas_I_ANGLU, resource_path("vertimasSavybesLT-ENG.txt"))
    tables_data = nuskaitytIsverstasFailasLietuviu(pirminisVertimas_I_Lietuviu)
    prekesPaspaudimas(driver, brandName,code)
    filteriuPridejimas(driver)
    tables_data_eng = nuskaitytIsverstasFailasAnglu(galutinisVertimas_I_ANGLU)
    prekiuSavybiuSuvedimas(driver, code, tables_data, tables_data_eng, "Pinarello")
    addBrandName(driver,brandName)


def mainPinarelloFunction(driver, brandName):
    pirminisVertimas_I_Lietuviu = resource_path("pabaigtaPLT.txt")
    galutinisVertimas_I_ANGLU = resource_path("pabaigtaPENG.txt")

    automatizacija(
            pirminisVertimas_I_Lietuviu, galutinisVertimas_I_ANGLU, driver, brandName
        )
