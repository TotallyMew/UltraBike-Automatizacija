

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
            print(f"Warning: Settings file not found at {self.settings_file}")
            # Initialize with default settings matching your structure
            self.settings = [
                False,  # Setting 0
                "C:\\Default\\Path\\To\\KROSS",  # Setting 1
                True,   # Setting 2
                "C:\\Default\\Desktop\\Path"  # Setting 3
            ]
    
    def get(self, index, default=None):
        """Get setting by index (0-based)"""
        try:
            return self.settings[index]
        except IndexError:
            return default
    
    # Specific getters for your known settings
    def download_pictures_and_upload(self):
        """Returns True/False for setting 0"""
        return self.get(0, False)
    
    def get_kross_path(self):
        """Returns the KROSS path (setting 1)"""
        return self.get(1, "C:\\Default\\Path\\To\\KROSS")
    
    def get_auto_download(self):
        """Returns True/False for setting 2"""
        return self.get(2, True)
    
    def get_desktop_path(self):
        """Returns desktop path (setting 3)"""
        return self.get(3, "C:\\Default\\Desktop\\Path")