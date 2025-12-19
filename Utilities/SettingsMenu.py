from tkinter import Tk
from tkinter.filedialog import askdirectory
from Config.Settings.SettingsManager import SettingsManager

class SettingsMenu:
    def __init__(self, settings_manager: SettingsManager):
        self.settings_manager = settings_manager
    
    def display_menu(self):
        """Display settings menu (GUI only)"""
        pass
    
    def _toggle_download_pictures(self):
        """Toggle download/upload pictures setting (GUI only)"""
        current = self.settings_manager.download_pictures_and_upload()
        self.settings_manager.settings[0] = not current
        # GUI should display status
        # status = "įjungta" if not current else "išjungta"
    
    def _toggle_extended_mode(self):
        """Toggle extended mode setting (GUI only)"""
        current = self.settings_manager.is_extended_mode_enabled()
        self.settings_manager.settings[2] = not current
        # GUI should display status
    
    def _change_kross_path(self):
        """Change KROSS path using folder picker (GUI only)"""
        # GUI should handle folder picker and update settings
        pass

    def _change_repository_path(self):
        """Change repository path using folder picker (GUI only)"""
        # GUI should handle folder picker and update settings
        pass
    
    def _save_and_exit(self):
        """Save settings to file and reload (GUI only)"""
        self.settings_manager.save_settings()
        self.settings_manager.reload_settings()
        # GUI should display confirmation
