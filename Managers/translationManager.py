# managers/translationManager.py

from Utilities.scrapeUtilities import (
    versti_I_Anglu,
    nuskaitytIsverstasFailasLietuviu,
    nuskaitytIsverstasFailasAnglu,
    resource_path
)

class TranslationManager:
    def __init__(self, brandName):
        self.brandName = brandName
        self.ltPath = resource_path(f"pabaigta{brandName}LT.txt")
        self.enPath = resource_path(f"pabaigta{brandName}ENG.txt")
        self.engDictPath = resource_path("Assets/Translations/vertimasSavybesLT-ENG.txt")
        self.descriptionPath = resource_path(f"Assets/Translations/aprasas{brandName}.txt")

    def prepareTranslationFiles(self, scrape_func, url, *args, **kwargs):
        scrape_func(url, self.ltPath, *args, **kwargs)
        versti_I_Anglu(self.ltPath, self.enPath, self.engDictPath)

    def translateAll(self):
        versti_I_Anglu(self.ltPath, self.enPath, self.engDictPath)

    def loadLT(self):
        return nuskaitytIsverstasFailasLietuviu(self.ltPath)

    def loadEN(self):
        return nuskaitytIsverstasFailasAnglu(self.enPath)

    def loadLV(self):
        return nuskaitytIsverstasFailasAnglu(self.enPath)  # Assuming LV is the same as EN for now

