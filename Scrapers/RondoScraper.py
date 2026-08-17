import requests
from bs4 import BeautifulSoup
from Utilities.TranslationHandler import TranslationHandler

def scrapeAndTranslateToFileRondo(url, outputFile, db_manager=None):
    translation_handler = TranslationHandler(db_manager)
    
    # Component names (keys)
    keyTranslations = translation_handler.get_translations_by_category("EN", "LT", "component")
    
    # Materials, colors, properties (values)
    valueTranslations = {}
    valueTranslations.update(translation_handler.get_translations_by_category("EN", "LT", "material"))
    valueTranslations.update(translation_handler.get_translations_by_category("EN", "LT", "color"))
    valueTranslations.update(translation_handler.get_translations_by_category("EN", "LT", "property"))
    
    allData = []
    tableData = {}
    uniqueKeys = set()

    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:52.0) Gecko/20100101 Firefox/52.0',
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')
        rows = soup.find_all('tr') or soup.select('table[border="1"] tr')

        for row in rows:
            cells = row.find_all('td')
            if len(cells) != 2:
                continue

            key = cells[0].get_text(strip=True).replace(':', '').upper()  # ← .upper()
            value = cells[1].get_text(strip=True)

            if not value or value == '-':
                continue

            specialKeys = {
                "BRAKES": ["FRONT BRAKES", "REAR BRAKES"],
                "ROTORS": ["FRONT ROTORS", "REAR ROTORS"],
                "HUBS": ["FRONT HUB", "REAR HUB"]
            }

            if key in specialKeys:
                for subKey in specialKeys[key]:
                    translatedKey = keyTranslations.get(subKey, subKey)
                    translatedValue = translation_handler.translate_first_word(valueTranslations.get(value, value), valueTranslations)
                    tableData[translatedKey] = translatedValue
                    uniqueKeys.add(translatedKey)
            else:
                translatedKey = keyTranslations.get(key, key)
                translatedValue = translation_handler.translate_first_word(valueTranslations.get(value, value), valueTranslations)
                tableData[translatedKey] = translatedValue
                uniqueKeys.add(translatedKey)

        allData.append(tableData)

        with open((outputFile), "w", encoding="utf-8") as file:
            for table in allData:
                for key, val in table.items():
                    if key and val:
                        file.write(f"{key}: {val}\n")
                file.write("\n")

        return f"Total unique keys: {len(uniqueKeys)}"

    except requests.HTTPError as e:
        return f"HTTP klaida: {e}"
    except Exception as e:
        return f"Klaida apdorojant Rondo duomenis: {e}"
