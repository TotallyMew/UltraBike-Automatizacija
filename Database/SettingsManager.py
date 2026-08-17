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

        desktop_candidates = [
            Path.home() / "Desktop",
            Path.home() / "OneDrive" / "Desktop",
        ]
        desktop_path = next((p for p in desktop_candidates if p.exists()), desktop_candidates[0])
        desktop = str(desktop_path)
        default_kross = str(desktop_path / "KROSS")
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

            ('auto_save', 'false', 'bool', 'processing',
             'Legacy setting; PIMBO changes always require manual review', 'false'),

            ('magicai_title_template', 'Prekės pavadinimas', 'string', 'processing',
             'PIMBO MagicAI template used for Lithuanian product names', 'Prekės pavadinimas'),

            ('magicai_description_template', 'Aprašymas LT', 'string', 'processing',
             'PIMBO MagicAI template used for Lithuanian descriptions', 'Aprašymas LT'),

            ('auto_delete_pabaigta_files', 'false', 'bool', 'processing',
             'Automatically delete generated pabaigta*.txt files after successful run', 'false'),

            # Browser
            ('browser_choice', 'Chrome', 'string', 'browser',
             'Preferred browser (Chrome/Firefox/Edge)', 'Chrome'),

            # Multi-session
            ('multi_session_enabled', 'false', 'bool', 'browser',
             'Process batches using multiple browser instances', 'false'),

            ('browser_count', '2', 'int', 'browser',
             'Number of browsers to use for multi-session', '2'),
            
            ('last_brand', '', 'string', 'processing', 
             'Last used brand', ''),

            # Orbea automation
            ('orbea_catalogue_path', '', 'path', 'orbea',
             'Last Orbea catalogue workbook used by the automation tab', ''),

            ('orbea_output_root', '', 'path', 'orbea',
             'Base folder for timestamped Orbea automation runs', ''),

            ('orbea_filter_preset', '', 'string', 'orbea',
             'Last Pimbo filter preset used by the Orbea automation tab', ''),

            ('orbea_description_output', '', 'path', 'orbea',
             'Output folder for Orbea model-page description text files', ''),
            
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

             # Earnings tracker
             ('earning_rate_bicycle_cents', '100', 'int', 'earnings',
              'Payout in cents for a bicycle', '100'),

             ('earning_rate_frameset_cents', '100', 'int', 'earnings',
              'Payout in cents for a frameset', '100'),

             ('earning_rate_other_cents', '75', 'int', 'earnings',
              'Payout in cents for another product type', '75'),

             ('daily_earning_goal_cents', '0', 'int', 'earnings',
              'Optional daily earnings target in cents; zero disables it', '0'),

             ('weekly_earning_goal_cents', '0', 'int', 'earnings',
              'Optional weekly earnings target in cents; zero disables it', '0'),

             ('daily_work_goal_minutes', '0', 'int', 'earnings',
              'Optional daily tracked-time target in minutes; zero disables it', '0'),

             ('weekly_work_goal_minutes', '0', 'int', 'earnings',
              'Optional weekly tracked-time target in minutes; zero disables it', '0'),

             ('standard_workday_minutes', '480', 'int', 'earnings',
              'Normal workday length used for income projections', '480'),

             ('standard_workdays_per_week', '5', 'int', 'earnings',
              'Normal workdays per week used for income projections', '5'),

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
        self.set_many({key: value})

    def set_many(self, values: dict) -> None:
        """Persist a group of settings atomically."""
        if not values:
            return
        with self.db.conn:
            cursor = self.db.conn.cursor()
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            for key, value in values.items():
                if isinstance(value, bool):
                    value_str = 'true' if value else 'false'
                    value_type = 'bool'
                    default_value = value_str
                elif isinstance(value, int):
                    value_str = str(value)
                    value_type = 'int'
                    default_value = value_str
                else:
                    value_str = str(value)
                    value_type = 'string'
                    default_value = ''

                cursor.execute(
                    """
                    UPDATE settings
                    SET value = ?, updated_at = ?
                    WHERE key = ?
                    """,
                    (value_str, now, key),
                )
                if cursor.rowcount == 0:
                    cursor.execute(
                        """
                        INSERT INTO settings
                        (key, value, value_type, category, description, default_value, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (key, value_str, value_type, 'misc', '', default_value, now),
                    )
    
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
        """Automatic PIMBO Save is permanently disabled by workflow policy."""
        return False

    def get_magicai_title_template(self) -> str:
        return str(self.get('magicai_title_template', 'Prekės pavadinimas')).strip()

    def get_magicai_description_template(self) -> str:
        return str(self.get('magicai_description_template', 'Aprašymas LT')).strip()

    def is_auto_delete_pabaigta_files_enabled(self) -> bool:
        return self.get('auto_delete_pabaigta_files', False)
