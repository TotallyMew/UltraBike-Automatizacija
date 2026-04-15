# scrapers/KROSSScraper.py

import requests
from bs4 import BeautifulSoup
from Utilities.TranslationHandler import TranslationHandler, load_translations, load_value_translations

def scrapeAndTranslateToFileKROSS(bicycleUrlOrCode, outputFile, db_manager=None):
    translation_handler = TranslationHandler(db_manager)
    
    # Component names (keys)
    keyTranslations = translation_handler.get_translations_by_category("PL", "LT", "component")

    # Materials, colors, properties (values)
    valueTranslations = {}
    valueTranslations.update(translation_handler.get_translations_by_category("PL", "LT", "material"))
    valueTranslations.update(translation_handler.get_translations_by_category("PL", "LT", "color"))
    valueTranslations.update(translation_handler.get_translations_by_category("PL", "LT", "property"))

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
                    key = cells[0].get_text(strip=True).upper()
                    value = cells[1].get_text(strip=True)
                    

                    if value.upper() == "BRAK" or value.upper() == "NIE" or value.upper() == "TAK":
                        continue 
                    if key.upper() in [
                        "KOLOR BAZOWY",
                        "PRODUCENT",
                        "OSOBA ODPOWIEDZIALNA W UE",
                        "MOMENT OBROTOWY SILNIKA",
                        "MOC SILNIKA",
                        "UMIEJSCOWIENIE SILNIKA",
                        "POJEMNOŚĆ BATERII",
                        "UMIEJSCOWIENIE BATERII",
                        "MAKSYMALNY ZASIĘG (KM)",
                        "NAPIĘCIE SILNIKA (V)",
                        "ŁADOWARKA (NAPIĘCIE/NATĘŻENIE)",
                        "CZAS ŁADOWANIA (H)",
                        "MAKSYMALNA PRĘDKOŚĆ WSPOMAGANIA (KM/H)",
                        "NUMER CERTYFIKATU",
                        "TRYB WSPOMAGANIA"
                    ]:
                        continue

                    translatedKey = keyTranslations.get(key, key)

                    translatedValue = valueTranslations.get(value, None)
                    if translatedValue is None:
                        # Try full-phrase DB lookup across all categories (catches e.g. "TARCZOWY MECHANICZNY")
                        db_result = translation_handler.get_translation(value.upper(), "PL", "LT")
                        translatedValue = db_result if db_result != value.upper() else value
                    translatedValue = translation_handler.translate_first_word(translatedValue, valueTranslations)

                    tableData[translatedKey] = translatedValue
                    uniqueKeys.add(translatedKey)

            allData.append(tableData)

        # Extract main color if present
        colorBlock = soup.select_one(".product-related-colors .block-title.title")
        if colorBlock:
            colorText = colorBlock.get_text(strip=True).replace("Kolor bazowy:", "").strip()
            colors = colorText.split()

            if len(colors) >= 1:
                mainColor = colors[0]
                translated = translation_handler.translate_first_word(valueTranslations.get(mainColor, mainColor), valueTranslations)
                allData[0]["Spalva"] = translated
                uniqueKeys.add("Spalva")

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