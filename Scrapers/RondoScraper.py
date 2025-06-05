import requests
from bs4 import BeautifulSoup
from Utilities.scrapeUtilities import (
    loadTranslations,
    loadValueTranslations,
    verstTikPirmaZodi,
)

def scrapeAndTranslateToFileRondo(url, outputFile):
    keyTranslations = loadTranslations("Assets/Translations/RondoENG-LT.txt")
    valueTranslations = loadValueTranslations("Assets/Translations/vertimasSavybesENG-LT.txt")
    allData = []
    tableData = {}
    uniqueKeys = set()

    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:52.0) Gecko/20100101 Firefox/52.0',
        }
        response = requests.get(url, headers=headers, verify=False, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')
        rows = soup.find_all('tr') or soup.select('table[border="1"] tr')

        for row in rows:
            cells = row.find_all('td')
            if len(cells) != 2:
                continue

            key = cells[0].get_text(strip=True).replace(':', '').title()
            value = cells[1].get_text(strip=True)

            if not value or value == '-':
                continue

            specialKeys = {
                "brakes": ["Front Brakes", "Rear Brakes"],
                "rotors": ["Front Rotors", "Rear Rotors"],
                "hubs": ["Front Hub", "Rear Hub"]
            }

            keyLower = key.lower()

            if keyLower in specialKeys:
                for subKey in specialKeys[keyLower]:
                    translatedKey = keyTranslations.get(subKey, subKey)
                    translatedValue = verstTikPirmaZodi(valueTranslations.get(value, value), valueTranslations)
                    tableData[translatedKey] = translatedValue
                    uniqueKeys.add(translatedKey)
            else:
                translatedKey = keyTranslations.get(key, key)
                translatedValue = verstTikPirmaZodi(valueTranslations.get(value, value), valueTranslations)
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
