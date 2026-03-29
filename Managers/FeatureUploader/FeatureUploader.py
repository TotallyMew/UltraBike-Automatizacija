from Managers.FeatureUploader.FieldWriter import FeatureFieldWriter
from Managers.FeatureUploader.LanguageSwitcher import LanguageSwitcher
from Utilities.WebIntercationHandler import WebInteractionHandler


class FeatureUploader:
    def __init__(self, driver, logger=None):
        self.driver = driver
        self.logger = logger
        self.writer = FeatureFieldWriter(driver, logger)
        self.lang_switcher = LanguageSwitcher(driver, logger)
        self.web_handler = WebInteractionHandler(driver)

    def _log(self, message, **context):
        if self.logger:
            self.logger.log("FeatureUploader", message, **context)

    def uploadAllLanguages(self, ltData, enData, lvData):
        """Upload product specifications for LT and EN.

        Flow:
          1. Apply template + fill LT values.
          2. Save the product (so values persist across locale switch).
          3. Switch to EN locale.
          4. Fill EN translated values (overwriting the LT ones where applicable).
          5. Switch back to LT locale.

        LV is no longer used.
        """
        self._log("Starting specification upload", lt_count=len(ltData))

        # 1. Fill LT specs (applies template if needed)
        self.writer.fillFields(ltData, lang="lt", first_language=True)

        # 2. Save so values carry over to other locales
        self._log("Saving after LT spec fill")
        self.web_handler.save_information()

        # 3. Switch to EN and fill translated values
        self._log("Switching to EN for translated specs")
        self.lang_switcher.switchTo("en")
        self.writer.fillFields(enData, lang="en", first_language=False)

        # 4. Switch back to LT
        self.lang_switcher.switchTo("lt")

        self._log("Specification upload complete")
        return getattr(self.writer, "skipped_features", [])
