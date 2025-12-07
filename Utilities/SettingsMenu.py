from tkinter import Tk
from tkinter.filedialog import askdirectory
from Config.Settings.SettingsManager import SettingsManager

class SettingsMenu:
    def __init__(self, settings_manager: SettingsManager):
        self.settings_manager = settings_manager
    
    def display_menu(self):
        """Display settings menu with current values"""
        while True:
            print("\n" + "="*60)
            print("SETTINGS")
            print("="*60)
            
            # Setting 0: Download/Upload Pictures
            download_status = "[X]" if self.settings_manager.download_pictures_and_upload() else "[ ]"
            print(f"1. {download_status} Download and upload bicycle pictures")
            print(f"   (Downloads KROSS images and uploads to PrestaShop)")
            
            # Setting 1: KROSS Path
            kross_path = self.settings_manager.get_kross_path()
            print(f"\n2. KROSS Image Download Path")
            print(f"   Current: {kross_path}")
            print(f"   (Where KROSS bicycle images are downloaded)")
            
            # Setting 2: Extended Mode
            extended_status = "[X]" if self.settings_manager.is_extended_mode_enabled() else "[ ]"
            print(f"\n3. {extended_status} Extended Mode")
            print(f"   (Enables folder creator and scraper selection menu)")
            
            # Setting 3: Repository Path
            repo_path = self.settings_manager.get_repository_path()
            print(f"\n4. Bicycle Folder Repository Path")
            print(f"   Current: {repo_path}")
            print(f"   (Base path for creating bicycle folder structure)")
            
            print("\n" + "="*60)
            print("5. Save and Exit")
            print("6. Exit without saving")
            print("="*60)
            
            choice = input("\nPasirinkite nustatymą (1-6): ").strip()
            
            if choice == "1":
                self._toggle_download_pictures()
            elif choice == "2":
                self._change_kross_path()
            elif choice == "3":
                self._toggle_extended_mode()
            elif choice == "4":
                self._change_repository_path()
            elif choice == "5":
                self._save_and_exit()
                return True
            elif choice == "6":
                print("Nustatymai nebuvo išsaugoti.")
                return False
            else:
                print("Neteisingas pasirinkimas. Bandykite dar kartą.")
    
    def _toggle_download_pictures(self):
        """Toggle download/upload pictures setting"""
        current = self.settings_manager.download_pictures_and_upload()
        self.settings_manager.settings[0] = not current
        status = "įjungta" if not current else "išjungta"
        print(f"Nuotraukų siuntimas {status}")
    
    def _toggle_extended_mode(self):
        """Toggle extended mode setting"""
        current = self.settings_manager.is_extended_mode_enabled()
        self.settings_manager.settings[2] = not current
        status = "įjungtas" if not current else "išjungtas"
        print(f"Išplėstinis režimas {status}")
    
    def _change_kross_path(self):
        """Change KROSS path using folder picker"""
        print("\nAtidaroma aplanko pasirinkimo dialogo langas...")
        
        # Hide the root tkinter window
        root = Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        
        new_path = askdirectory(
            title="Pasirinkite KROSS nuotraukų aplanką",
            initialdir=self.settings_manager.get_kross_path()
        )
        
        root.destroy()
        
        if new_path:
            self.settings_manager.settings[1] = new_path
            print(f"Naujas kelias: {new_path}")
        else:
            print("Kelias nepakeistas")
    
    def _change_repository_path(self):
        """Change repository path using folder picker"""
        print("\nAtidaroma aplanko pasirinkimo dialogo langas...")
        
        # Hide the root tkinter window
        root = Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        
        new_path = askdirectory(
            title="Pasirinkite dviračių aplanką",
            initialdir=self.settings_manager.get_repository_path()
        )
        
        root.destroy()
        
        if new_path:
            self.settings_manager.settings[3] = new_path
            print(f"Naujas kelias: {new_path}")
        else:
            print("Kelias nepakeistas")
    
    def _save_and_exit(self):
        """Save settings to file and reload"""
        self.settings_manager.save_settings()
        self.settings_manager.reload_settings()
        print("Nustatymai išsaugoti!")
