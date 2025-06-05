# managers/translationManager.py

from Utilities.scrapeUtilities import (
    versti_I_Anglu,
    nuskaitytIsverstasFailasLietuviu,
    nuskaitytIsverstasFailasAnglu,
)
import inspect

class TranslationManager:
    def __init__(self, brandName):
        self.brandName = brandName
        self.ltPath =  f"pabaigta{brandName}LT.txt"
        self.enPath = f"pabaigta{brandName}ENG.txt"
        self.engDictPath = "Assets/Translations/vertimasSavybesLT-ENG.txt"
        self.descriptionPath = "Assets/Translations/vertimasSavybesPL-LT.txt"

    def prepareTranslationFiles(self, scrape_func, url, **kwargs):
        args = {
            "bicycleUrlOrCode": url,
            "outputFile": self.ltPath
        }

        # Only add 'driver' if the scrape_func supports it
        if 'driver' in inspect.signature(scrape_func).parameters:
            args["driver"] = kwargs.get("driver")

        scrape_func(**args)
        versti_I_Anglu(self.ltPath, self.enPath, self.engDictPath)


    def translateAll(self):
        versti_I_Anglu(self.ltPath, self.enPath, self.engDictPath)

    def loadLT(self):
        return nuskaitytIsverstasFailasLietuviu(self.ltPath)

    def loadEN(self):
        return nuskaitytIsverstasFailasAnglu(self.enPath)

    def loadLV(self):
        return nuskaitytIsverstasFailasAnglu(self.enPath)  # Assuming LV is the same as EN for now

