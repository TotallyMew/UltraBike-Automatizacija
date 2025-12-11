import requests
from bs4 import BeautifulSoup
from Utilities.TranslationHandler import TranslationHandler

def scrapeAndTranslateToFileOctaneOne(url, outputFile, db_manager=None):
    translation_handler = TranslationHandler(db_manager)
    
    # Component names (keys)
    keyTranslations = translation_handler.get_translations_by_category("EN", "LT", "component")
    
    # Materials, colors, properties (values)
    valueTranslations = {}
    valueTranslations.update(translation_handler.get_translations_by_category("EN", "LT", "material"))
    valueTranslations.update(translation_handler.get_translations_by_category("EN", "LT", "color"))
    valueTranslations.update(translation_handler.get_translations_by_category("EN", "LT", "property"))

    allData = []
    uniqueKeys = set()

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        specItems = soup.find_all("div", class_="div-spec-item")
        if not specItems:
            raise ValueError("Octane One puslapio struktūra pasikeitė, atnaujinkite programą.")

        tableData = {}
        for item in specItems:
            keyElem = item.find("div", class_="tb-spec-type")
            valueElem = item.find("div", class_="tb-spec-text")
            if not keyElem or not valueElem:
                continue

            key = keyElem.get_text(strip=True).upper()  # ← .upper()
            value = valueElem.get_text(strip=True)

            if key == "DERAILLEURS":
                frontKey = "FRONT DERAILLEUR"
                rearKey = "REAR DERAILLEUR"
                frontTranslated = keyTranslations.get(frontKey, "Priekinis pavarų perjungėjas")
                rearTranslated = keyTranslations.get(rearKey, "Galinis pavarų perjungejas")
                translatedValue = translation_handler.translate_first_word(value, valueTranslations)

                tableData[frontTranslated] = translatedValue
                tableData[rearTranslated] = translatedValue
                uniqueKeys.update([frontTranslated, rearTranslated])
                continue

            if key == "LEVERS/SHIFTERS":
                leversKey = "LEVERS"
                shiftersKey = "SHIFTERS"
                leversTranslated = keyTranslations.get(leversKey, "Stabdžių rankenėlės")
                shiftersTranslated = keyTranslations.get(shiftersKey, "Pavarų perjungimo rankenėlės")
                translatedValue = translation_handler.translate_first_word(value, valueTranslations)

                tableData[leversTranslated] = translatedValue
                tableData[shiftersTranslated] = translatedValue
                uniqueKeys.update([leversTranslated, shiftersTranslated])
                continue

            translatedKey = keyTranslations.get(key, key)
            translatedValue = translation_handler.translate_first_word(value, valueTranslations)

            tableData[translatedKey] = translatedValue
            uniqueKeys.add(translatedKey)

        allData.append(tableData)

        with open(outputFile, "w", encoding="utf-8") as f:
            for table in allData:
                for key, val in table.items():
                    f.write(f"{key}: {val}\n")
                f.write("\n")

        return f"Total unique keys: {len(uniqueKeys)}"

    except requests.HTTPError as e:
        return f"HTTP klaida: {e}"
    except Exception as e:
        return f"Klaida apdorojant Octane One duomenis: {e}"