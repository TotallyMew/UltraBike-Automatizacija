from datetime import datetime
from pathlib import Path

class SettingsManager:
    """
    Manage settings in database with named keys instead of index-based access
    """
    
    def __init__(self, db_manager):
        self.db = db_manager
        self._initialize_defaults()
    
    def _initialize_defaults(self):
        """
        Insert default settings if they don't exist
        """
        DEFAULT_UPDATE_MANIFEST_URL = (
            "https://raw.githubusercontent.com/TotallyMew/UltraBike_Automatizacija_Release/main/latest.json"
        )

        desktop = str(Path.home() / "Desktop")
        default_kross = str(Path.home() / "Desktop" / "KROSS")
        defaults = [
            # Paths
            ('download_images', 'false', 'bool', 'paths', 
             'Download and upload bicycle images', 'false'),
            
            ('kross_download_path', default_kross,
             'path', 'paths', 'Path to download KROSS images', ''),
            
            ('repository_path', desktop,
             'path', 'paths', 'Base path for bicycle folders', ''),
            
            # Processing
            ('extended_mode', 'true', 'bool', 'processing',
             'Enable extended mode (folder creator, scraper menu)', 'false'),

            ('auto_save', 'true', 'bool', 'processing',
             'Automatically save product updates after upload', 'true'),

            ('auto_delete_pabaigta_files', 'false', 'bool', 'processing',
             'Automatically delete generated pabaigta*.txt files after successful run', 'false'),

            # Browser
            ('browser_choice', 'Chrome', 'string', 'browser',
             'Preferred browser (Chrome/Firefox/Edge)', 'Chrome'),
            
            ('last_brand', '', 'string', 'processing', 
             'Last used brand', ''),
            
            # UI
            ('window_width', '1200', 'int', 'ui',
             'Window width in pixels', '1200'),

            ('window_height', '800', 'int', 'ui',
             'Window height in pixels', '800'),

            ('theme', 'light', 'string', 'ui',
             'UI theme (light/dark)', 'light'),

            ('language', 'English', 'string', 'ui',
             'Application language (English/Lithuanian)', 'English'),

              ('display_name', '', 'string', 'ui',
               'Display name shown in the top bar', ''),

             # Updates
             ('update_check_enabled', 'true', 'bool', 'updates',
              'Check for application updates on startup', 'true'),

             ('update_manifest_url', DEFAULT_UPDATE_MANIFEST_URL, 'string', 'updates',
              'URL to update manifest JSON (latest.json)', DEFAULT_UPDATE_MANIFEST_URL),
        ]
        
        cursor = self.db.conn.cursor()
        
        for key, value, value_type, category, description, default_value in defaults:
            # Check if exists
            existing = cursor.execute(
                "SELECT key FROM settings WHERE key = ?", (key,)
            ).fetchone()
            
            if not existing:
                cursor.execute("""
                    INSERT INTO settings 
                    (key, value, value_type, category, description, default_value)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (key, value, value_type, category, description, default_value))
            else:
                # Backfill defaults for existing installs if the value is empty.
                # This ensures update checks work by default without requiring manual scripts.
                if key == 'update_manifest_url':
                    try:
                        row = cursor.execute(
                            "SELECT value FROM settings WHERE key = ?", (key,)
                        ).fetchone()
                        current_val = (row[0] if row else '')
                        if (current_val is None) or (str(current_val).strip() == ''):
                            cursor.execute(
                                "UPDATE settings SET value=?, default_value=? WHERE key=?",
                                (DEFAULT_UPDATE_MANIFEST_URL, DEFAULT_UPDATE_MANIFEST_URL, key),
                            )
                    except Exception:
                        pass
        
        self.db.conn.commit()
    
    def get(self, key: str, default=None):
        """
        Get setting value (automatically converts type)
        """
        # Database already has sqlite3.Row factory set
        cursor = self.db.conn.cursor()
        result = cursor.execute("""
            SELECT value, value_type
            FROM settings
            WHERE key = ?
        """, (key,)).fetchone()

        if not result:
            return default

        value = result['value']
        value_type = result['value_type']
        
        # Convert to proper type
        if value_type == 'bool':
            return value.lower() == 'true'
        elif value_type == 'int':
            return int(value)
        elif value_type == 'path' or value_type == 'string':
            return value
        else:
            return value
    
    def set(self, key: str, value):
        """
        Set setting value
        """
        cursor = self.db.conn.cursor()
        
        # Convert value to string
        if isinstance(value, bool):
            value_str = 'true' if value else 'false'
        else:
            value_str = str(value)
        
        cursor.execute("""
            UPDATE settings 
            SET value = ?, updated_at = ?
            WHERE key = ?
        """, (value_str, datetime.now(), key))
        
        self.db.conn.commit()
    
    def get_all_by_category(self, category: str) -> dict:
        """
        Get all settings in a category
        Returns dict of {key: value}
        """
        cursor = self.db.conn.cursor()
        results = cursor.execute("""
            SELECT key, value, value_type 
            FROM settings 
            WHERE category = ?
            ORDER BY key
        """, (category,)).fetchall()
        
        settings = {}
        for row in results:
            key = row['key']
            value = row['value']
            value_type = row['value_type']
            
            # Convert type
            if value_type == 'bool':
                settings[key] = value.lower() == 'true'
            elif value_type == 'int':
                settings[key] = int(value)
            else:
                settings[key] = value
        
        return settings
    
    # Convenience methods (backward compatible with old SettingsManager)
    
    def download_pictures_and_upload(self) -> bool:
        return self.get('download_images', False)
    
    def get_kross_path(self) -> str:
        return self.get('kross_download_path', '')
    
    def is_extended_mode_enabled(self) -> bool:
        return self.get('extended_mode', False)
    
    def get_repository_path(self) -> str:
        return self.get('repository_path', '')
    
    def get_browser_choice(self) -> str:
        return self.get('browser_choice', 'Chrome')

    def is_auto_save_enabled(self) -> bool:
        return self.get('auto_save', True)

    def is_auto_delete_pabaigta_files_enabled(self) -> bool:
        return self.get('auto_delete_pabaigta_files', False)