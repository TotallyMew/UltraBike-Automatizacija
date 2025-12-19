from Managers.FeatureUploader.languageSwitcher import LanguageSwitcher
from Managers.FeatureUploader.fieldWriter import FeatureFieldWriter

class FeatureUploader:
    def __init__(self, driver, logger=None):
        self.driver = driver
        self.logger = logger
        self.languageSwitcher = LanguageSwitcher(driver, logger)
        self.writer = FeatureFieldWriter(driver, logger)
    
    def _log(self, message, **context):
        if self.logger:
            self.logger.log("FeatureUploader", message, **context)

    def uploadAllLanguages(self, ltData, enData, lvData):
        self._log("Starting feature upload for all languages", lt_count=len(ltData), en_count=len(enData))
        
        self._log("Switching to Lithuanian")
        self.languageSwitcher.switchTo("lt")
        keep_mask = self.writer.fillFields(ltData, lang="lt", first_language=True)
        
        self._log("Switching to English")
        self.languageSwitcher.switchTo("en")
        self.writer.fillFields(enData, lang="en", first_language=False, keep_mask=keep_mask)
        
        self._log("Switching to Latvian")
        self.languageSwitcher.switchTo("lv")
        self.writer.fillFields(lvData, lang="lv", first_language=False, keep_mask=keep_mask)
        
        self._log("All language features uploaded successfully")
        return getattr(self.writer, "skipped_features", [])