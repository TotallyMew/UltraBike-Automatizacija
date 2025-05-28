import requests
from bs4 import BeautifulSoup
from Utilities.scrapeUtilities import (
    loadTranslations,
    loadValueTranslations,
    verstTikPirmaZodi,
    resource_path
)

def scrapeAndTranslateToFilePinarello(url, outputFile):
    keyTranslations = loadTranslations(resource_path("PinarelloENG-LT.txt"))
    valueTranslations = loadValueTranslations(resource_path("vertimasSavybesENG-LT.txt"))

    allData = []
    uniqueKeys = set()

    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
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

            if title.lower() == "axles disc":
                for subTitle in ["Front Hub", "Rear Hub"]:
                    translatedKey = keyTranslations.get(subTitle, subTitle)
                    translatedValue = verstTikPirmaZodi(valueTranslations.get(spec, spec), valueTranslations)
                    tableData[translatedKey] = translatedValue
                    uniqueKeys.add(translatedKey)
                continue

            translatedKey = keyTranslations.get(title, title)
            translatedValue = verstTikPirmaZodi(valueTranslations.get(spec, spec), valueTranslations)

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
