import requests
from bs4 import BeautifulSoup
from Utilities.TranslationHandler import TranslationHandler

def scrapeAndTranslateToFileFactor(bicycleUrlOrCode, outputFile):
    translation_handler = TranslationHandler()
    keyTranslations = translation_handler.load_translations("Assets/Translations/FactorENG-LT.txt")
    valueTranslations = translation_handler.load_value_translations("Assets/Translations/vertimasSavybesENG-LT.txt")

    allData = []
    uniqueKeys = set()

    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(bicycleUrlOrCode, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        # Find all tables
        tables = soup.find_all('table', class_='table-fixed')
        if not tables:
            raise ValueError("Factor puslapio struktūra pasikeitė, atnaujinkite programą.")

        tableData = {}

        # Process first two tables (Specs and Groupset Specs, skip Geometry)
        for table_index, table in enumerate(tables[:2]):
            rows = table.find_all('tr')
            
            for row in rows:
                # Get cells
                cells = row.find_all('td')
                
                if len(cells) != 2:
                    continue
                
                key = cells[0].get_text(strip=True)
                value = cells[1].get_text(strip=True)
                
                # Normalize special characters
                # Replace inch symbol and similar characters
                key = key.replace('\u201c', '"').replace('\u201d', '"').replace('\u2033', '"').replace('″', '"')
                value = value.replace('\u201c', '"').replace('\u201d', '"').replace('\u2033', '"').replace('″', '"')

                if not key or not value or value == '-':
                    continue

                # Clean up the value - remove "Standard Package: n/a" prefix if present
                if "Standard Package: n/a" in value:
                    value = value.replace("Standard Package: n/a", "").strip()

                # Handle special keys that need to be split
                if key.lower() == "max rotor size":
                    # Split front and rear if both specified
                    if "front" in value.lower() and "rear" in value.lower():
                        # Extract just the size (e.g., "160mm" from "160mm front & rear")
                        import re
                        size_match = re.search(r'(\d+mm)', value)
                        if size_match:
                            size = size_match.group(1)
                            
                            for subKey in ["Front Rotors", "Rear Rotors"]:
                                translatedKey = keyTranslations.get(subKey, subKey)
                                translatedValue = translation_handler.translate_first_word(
                                    valueTranslations.get(size.upper(), size), valueTranslations
                                )
                                tableData[translatedKey] = translatedValue
                                uniqueKeys.add(translatedKey)
                            continue
                    else:
                        # Apply to both front and rear
                        for subKey in ["Front Rotors", "Rear Rotors"]:
                            translatedKey = keyTranslations.get(subKey, subKey)
                            translatedValue = translation_handler.translate_first_word(
                                valueTranslations.get(value.upper(), value), valueTranslations
                            )
                            tableData[translatedKey] = translatedValue
                            uniqueKeys.add(translatedKey)
                        continue

                # If key is "Rotors" (from Groupset Specs), also duplicate to Front/Rear
                if key.lower() == "rotors":
                    for subKey in ["Front Rotors", "Rear Rotors"]:
                        translatedKey = keyTranslations.get(subKey, subKey)
                        translatedValue = translation_handler.translate_first_word(
                            valueTranslations.get(value.upper(), value), valueTranslations
                        )
                        tableData[translatedKey] = translatedValue
                        uniqueKeys.add(translatedKey)
                    continue

                # Translate key and value
                translatedKey = keyTranslations.get(key, key)
                translatedValue = translation_handler.translate_first_word(
                    valueTranslations.get(value.upper(), value), valueTranslations
                )

                tableData[translatedKey] = translatedValue
                uniqueKeys.add(translatedKey)

        allData.append(tableData)

        # Write to file
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
        return f"Klaida apdorojant Factor duomenis: {e}"