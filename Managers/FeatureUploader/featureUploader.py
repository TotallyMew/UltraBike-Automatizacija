from Managers.FeatureUploader.languageSwitcher import LanguageSwitcher
from Managers.FeatureUploader.fieldWriter import FeatureFieldWriter

class FeatureUploader:
    def __init__(self, driver):
        self.driver = driver
        self.languageSwitcher = LanguageSwitcher(driver)
        self.writer = FeatureFieldWriter(driver)

    def uploadAllLanguages(self, ltData, enData, lvData):
        self.languageSwitcher.switchTo("lt")
        self.writer.fillFields(ltData, lang="lt", first_language=True)

        self.languageSwitcher.switchTo("en")
        self.writer.fillFields(enData, lang="en", first_language=False)

        self.languageSwitcher.switchTo("lv")
        self.writer.fillFields(lvData, lang="lv", first_language=False)

