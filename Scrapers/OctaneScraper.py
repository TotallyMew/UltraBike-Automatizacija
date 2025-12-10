import requests
from bs4 import BeautifulSoup
from Utilities.TranslationHandler import TranslationHandler, load_translations, load_value_translations

def scrapeAndTranslateToFileOctaneOne(url, outputFile):
    translation_handler = TranslationHandler()
    keyTranslations = load_translations("Assets/Translations/OctaneENG-LT.txt")
    valueTranslations = load_value_translations("Assets/Translations/vertimasSavybesENG-LT.txt")

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

            key = keyElem.get_text(strip=True).title()
            value = valueElem.get_text(strip=True)

            if key.lower() == "derailleurs":
                frontKey = "Front Derailleur"
                rearKey = "Rear Derailleur"
                frontTranslated = "Priekinis pavarų perjungėjas"
                rearTranslated = "Galinis pavarų perjungejas"
                translatedValue = translation_handler.translate_first_word(value, valueTranslations)

                tableData[frontTranslated] = translatedValue
                tableData[rearTranslated] = translatedValue
                uniqueKeys.update([frontTranslated, rearTranslated])
                continue

            if key.lower() == "levers/shifters":
                leversKey = "Levers"
                shiftersKey = "Shifters"
                leversTranslated = "Stabdžių rankenėlės"
                shiftersTranslated = "Pavarų perjungimo rankenėlės"
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