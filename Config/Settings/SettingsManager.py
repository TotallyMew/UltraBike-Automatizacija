from Database.DatabaseManager import DatabaseManager
from Database.SettingsManager import SettingsManager as DbSettingsManager


class SettingsManager:
    """Legacy compatibility wrapper.

    Historically this project stored settings in a text file using index-based
    lookups. The app has migrated to DB-backed named settings.

    This wrapper keeps older code working while ensuring there is a single
    source of truth (the database).
    """

    _INDEX_TO_KEY = {
        0: 'download_images',
        1: 'kross_download_path',
        2: 'extended_mode',
        3: 'repository_path',
    }

    def __init__(self, settings_file="Config/Settings/settings.txt", db_manager=None):
        self.settings_file = settings_file
        self._owns_db = False

        if db_manager is None:
            db_manager = DatabaseManager()
            self._owns_db = True

        self._db_manager = db_manager
        self._settings = DbSettingsManager(db_manager)

    def close(self):
        if self._owns_db and self._db_manager is not None:
            try:
                self._db_manager.close()
            finally:
                self._db_manager = None

    def get(self, index, default=None):
        """Get setting by legacy index (0-based)."""
        key = self._INDEX_TO_KEY.get(index)
        if key is None:
            return default
        return self._settings.get(key, default)

    def reload_settings(self):
        """No-op: DB settings are read on demand."""
        return

    def save_settings(self):
        """No-op: settings are persisted via the DB settings manager."""
        return

    def download_pictures_and_upload(self):
        return self._settings.download_pictures_and_upload()

    def get_kross_path(self):
        return self._settings.get_kross_path()

    def is_extended_mode_enabled(self):
        return self._settings.is_extended_mode_enabled()

    def get_repository_path(self):
        return self._settings.get_repository_path()