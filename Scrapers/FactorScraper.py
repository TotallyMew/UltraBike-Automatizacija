import requests
from bs4 import BeautifulSoup
from Utilities.TranslationHandler import TranslationHandler, load_translations, load_value_translations

def scrapeAndTranslateToFileFactor(bicycleUrlOrCode, outputFile, db_manager=None):
    translation_handler = TranslationHandler(db_manager)
    
    # Component names (keys)
    keyTranslations = translation_handler.get_translations_by_category("EN", "LT", "component")
    
    # Materials, colors, properties (values)
    valueTranslations = {}
    valueTranslations.update(translation_handler.get_translations_by_category("EN", "LT", "material"))
    valueTranslations.update(translation_handler.get_translations_by_category("EN", "LT", "color"))
    valueTranslations.update(translation_handler.get_translations_by_category("EN", "LT", "property"))
    
    # ... rest unchanged

    # Skip these fields until translations are available
    skip_fields = {
        "barstem", "head tube diameter", "saddle rail clamps",
        "cable routing", "compatible components", "max chainring",
        "wheel size", "manufacturer warranty", "included accessories"
    }

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
                
                key = cells[0].get_text(strip=True).upper()
                value = cells[1].get_text(strip=True)
                
                # Skip fields we don't have translations for yet
                if key.lower() in skip_fields:
                    continue
                
                # Normalize special characters
                key = key.replace('\u201c', '"').replace('\u201d', '"').replace('\u2033', '"').replace('″', '"')
                value = value.replace('\u201c', '"').replace('\u201d', '"').replace('\u2033', '"').replace('″', '"')

                if not key or not value or value == '-':
                    continue

                # Clean up the value
                if "Standard Package: n/a" in value:
                    value = value.replace("Standard Package: n/a", "").strip()

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