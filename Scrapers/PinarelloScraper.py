import requests
from bs4 import BeautifulSoup
from Utilities.TranslationHandler import TranslationHandler, load_translations, load_value_translations

def scrapeAndTranslateToFilePinarello(bicycleUrlOrCode, outputFile, frameset_only=None):
    translation_handler = TranslationHandler()
    keyTranslations = load_translations("Assets/Translations/PinarelloENG-LT.txt")
    valueTranslations = load_value_translations("Assets/Translations/vertimasSavybesENG-LT.txt")

    # Determine mode
    if frameset_only is None:
        # CLI mode - prompt user
        while True:
            choice = input("Pasirinkite: (1) Frameset, (2) Pilnas dviratis: ").strip()
            if choice == "1":
                frameset_only = True
                break
            elif choice == "2":
                frameset_only = False
                break
            else:
                print("Neteisingas pasirinkimas. Įveskite 1 arba 2.")
    
    # Set allowed fields based on mode
    if frameset_only:
        allowed_fields = {"frame", "fork", "seatpost", "seat clamp"}
    else:
        allowed_fields = set()  # All fields allowed

    allData = []
    uniqueKeys = set()

    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(bicycleUrlOrCode, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')

        partsDivs = soup.find_all('div', class_='col-lg-4 p-3')
        if not partsDivs:
            raise ValueError("Pinarello puslapio struktūra pasikeitė, atnaujinkite programą.")

        tableData = {}

        for partDiv in partsDivs:
            titleDiv = partDiv.find('div', class_='text--small color--mid-dark-gray mb-2')
            specDiv = partDiv.find('div', class_='color--dark-gray')

            if not titleDiv or not specDiv:
                continue

            title = titleDiv.get_text(strip=True).replace(':', '').strip().title()
            spec = specDiv.get_text(strip=True).strip()

            if not title or not spec:
                continue

            # Filter if frameset mode
            if frameset_only and title.lower() not in allowed_fields:
                continue

            translatedKey = keyTranslations.get(title, title)
            translatedValue = translation_handler.translate_first_word(valueTranslations.get(spec, spec), valueTranslations)

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
        return f"Klaida apdorojant Pinarello duomenis: {e}"