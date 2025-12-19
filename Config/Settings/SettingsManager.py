class SettingsManager:
    def __init__(self, settings_file="Config/Settings/settings.txt"):
        self.settings = []
        self.settings_file = settings_file
        self.load_settings()
    
    def load_settings(self):
        try:
            with open(self.settings_file, 'r') as file:
                for line in file:
                    stripped_line = line.strip()
                    if stripped_line.lower() == 'true':
                        self.settings.append(True)
                    elif stripped_line.lower() == 'false':
                        self.settings.append(False)
                    else:
                        self.settings.append(stripped_line)
        except FileNotFoundError:
            # Warning: Settings file not found at {self.settings_file}
            # Initialize with default settings
            self.settings = [
                False,  # Setting 0 - Download pictures and upload
                "C:\\Default\\Path\\To\\KROSS",  # Setting 1 - KROSS path
                False,  # Setting 2 - Extended mode
                "C:\\Default\\Repository\\Path"  # Setting 3 - Repository path
            ]
    
    def get(self, index, default=None):
        """Get setting by index (0-based)"""
        try:
            return self.settings[index]
        except IndexError:
            return default
    
    def reload_settings(self):
        """Reload settings from file - used after user edits settings"""
        self.settings = []
        self.load_settings()
    
    def save_settings(self):
        """Save current settings back to file"""
        with open(self.settings_file, 'w') as file:
            for setting in self.settings:
                if isinstance(setting, bool):
                    file.write('true\n' if setting else 'false\n')
                else:
                    file.write(f"{setting}\n")
    
    def download_pictures_and_upload(self):
        """Returns True/False for setting 0"""
        return self.get(0, False)
    
    def get_kross_path(self):
        """Returns the KROSS path (setting 1)"""
        return self.get(1, "C:\\Default\\Path\\To\\KROSS")
    
    def is_extended_mode_enabled(self):
        """Returns True/False for setting 2 - Extended mode toggle"""
        return self.get(2, False)
    
    def get_repository_path(self):
        """Returns repository path (setting 3)"""
        return self.get(3, "C:\\Default\\Repository\\Path")