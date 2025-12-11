import requests
from bs4 import BeautifulSoup
from Utilities.TranslationHandler import TranslationHandler

def scrapeAndTranslateToFileRascal(url, outputFile, variant_index=None, db_manager=None):
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
        productParams = soup.find("ul", class_="list-unstyled product-params split-params") or \
                        soup.find("ul", class_="list-unstyled product-params")

        if not productParams:
            raise ValueError("Rascal puslapio struktūra pasikeitė, atnaujinkite programą.")

        tableData = {}

        for li in productParams.find_all("li"):
            keySpan = li.find("span")
            valueSpans = keySpan.find_next_siblings("span") if keySpan else []

            if not keySpan or not valueSpans:
                continue

            key = keySpan.get_text(strip=True).upper()  # ← .upper()

            # Handle multiple variants
            if len(valueSpans) > 1 and variant_index is None:
                print("Rasta daugiau nei vienas prekės variantas puslapyje.")
                for index, valueSpan in enumerate(valueSpans, start=1):
                    print(f"{index}: {valueSpan.get_text(strip=True)}")
                while True:
                    try:
                        variant_index = int(input("Pasirinkite pagal kurį rašyti: ")) - 1
                        if 0 <= variant_index < len(valueSpans):
                            break
                        else:
                            print("Neteisingas pasirinkimas.")
                    except ValueError:
                        print("Neteisingas pasirinkimas. Pasirinkite per naują.")

            selectedValue = (
                valueSpans[variant_index].get_text(strip=True)
                if len(valueSpans) > 1 and variant_index is not None
                else valueSpans[0].get_text(strip=True)
            )

            if key == "BRAKES":
                for subKey in ["FRONT BRAKES", "REAR BRAKES"]:
                    translatedKey = keyTranslations.get(subKey, subKey)
                    translatedValue = translation_handler.translate_first_word(valueTranslations.get(selectedValue, selectedValue), valueTranslations)
                    tableData[translatedKey] = translatedValue
                    uniqueKeys.add(translatedKey)
            else:
                translatedKey = keyTranslations.get(key, key)
                translatedValue = translation_handler.translate_first_word(valueTranslations.get(selectedValue, selectedValue), valueTranslations)
                tableData[translatedKey] = translatedValue
                uniqueKeys.add(translatedKey)

        allData.append(tableData)

        with open(outputFile, "w", encoding="utf-8") as f:
            for table in allData:
                for key, val in table.items():
                    if key and val:
                        f.write(f"{key}: {val}\n")
                f.write("\n")

        return f"Total unique keys: {len(uniqueKeys)}"

    except requests.HTTPError as e:
        return f"HTTP klaida: {e}"
    except Exception as e:
        return f"Klaida apdorojant Rascal duomenis: {e}"