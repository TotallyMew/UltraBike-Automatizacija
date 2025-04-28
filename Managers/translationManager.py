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
        self.ltPath = resource_path(f"pabaigta{brandName[:1]}LT.txt")
        self.enPath = resource_path(f"pabaigta{brandName[:1]}ENG.txt")
        self.engDictPath = resource_path("vertimasSavybesLT-ENG.txt")

    def prepareTranslationFiles(self, scrape_func, url):
        scrape_func(url, self.ltPath)
        versti_I_Anglu(self.ltPath, self.enPath, self.engDictPath)

    def translateAll(self):
        versti_I_Anglu(self.ltPath, self.enPath, self.engDictPath)

    def loadLT(self):
        return nuskaitytIsverstasFailasLietuviu(self.ltPath)

    def loadEN(self):
        return nuskaitytIsverstasFailasAnglu(self.enPath)

