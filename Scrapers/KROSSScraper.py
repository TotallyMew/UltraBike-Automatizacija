# scrapers/KROSSScraper.py

import requests
from bs4 import BeautifulSoup
from Utilities.TranslationHandler import TranslationHandler

def scrapeAndTranslateToFileKROSS(bicycleUrlOrCode, outputFile):
    translation_handler = TranslationHandler()
    keyTranslations = translation_handler.load_translations("Assets/Translations\\vertimasDetalesPL-LT.txt")
    valueTranslations = translation_handler.load_value_translations("Assets/Translations\\vertimasSavybesPL-LT.txt")

    allData = []
    uniqueKeys = set()

    try:
        response = requests.get(bicycleUrlOrCode)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        additionalSection = soup.find("div", id="additional")
        if not additionalSection:
            raise ValueError("KROSS puslapio struktūra pasikeitė, atnaujinkite programą.")

        tables = additionalSection.find_all("table", class_="additional-attributes-table")
        if not tables:
            raise ValueError("Nerasta duomenų lentelių. Patikrinkite struktūrą.")

        for table in tables:
            rows = table.find_all("tr")
            tableData = {}

            for row in rows:
                cells = row.find_all("td")
                if len(cells) >= 2:
                    key = cells[0].get_text(strip=True).title()
                    value = cells[1].get_text(strip=True)

                    if value.upper() == "BRAK" or value.upper() == "NIE" or value.upper() == "TAK":
                        continue
                    if key.upper() == "KOLOR BAZOWY" or key.upper() == "PRODUCENT" or key.upper() == "OSOBA ODPOWIEDZIALNA W UE":
                        continue

                    translatedKey = keyTranslations.get(key, key)
                    translatedValue = valueTranslations.get(value, value)
                    translatedValue = translation_handler.translate_first_word(translatedValue, valueTranslations)

                    tableData[translatedKey] = translatedValue
                    uniqueKeys.add(translatedKey)

            allData.append(tableData)

        # Extract main and secondary color if present
        colorBlock = soup.select_one(".product-related-colors .block-title.title")
        if colorBlock:
            colorText = colorBlock.get_text(strip=True).replace("Kolor bazowy:", "").strip()
            colors = colorText.split()

            if len(colors) >= 1:
                mainColor = colors[0]
                translated = translation_handler.translate_first_word(valueTranslations.get(mainColor, mainColor), valueTranslations)
                allData[0]["Pagrindinė spalva"] = translated
                uniqueKeys.add("Pagrindinė spalva")

            if len(colors) >= 2:
                secondaryColor = colors[1]
                translated = translation_handler.translate_first_word(valueTranslations.get(secondaryColor, secondaryColor), valueTranslations)
                allData[0]["Papildoma spalva (antra)"] = translated
                uniqueKeys.add("Papildoma spalva (antra)")

        # Write result to file
        with open(outputFile, "w", encoding="utf-8") as f:
            for table in allData:
                for key, val in table.items():
                    f.write(f"{key}: {val}\n")
                f.write("\n")

        return f"Total unique keys: {len(uniqueKeys)}"

    except requests.HTTPError as e:
        return f"HTTP klaida: {e}"
    except Exception as e:
        return f"Klaida apdorojant KROSS duomenis: {e}"
