"""Settings screen component"""

import flet as ft
from tkinter import Tk
from tkinter.filedialog import askdirectory

class SettingsScreen:
    def __init__(self, app):
        self.app = app
        self.page = app.page
    
    def build(self):
        """Build settings screen UI"""
        
        # Browser selection
        self.browser_dropdown = ft.Dropdown(
            label="Browser",
            width=300,
            value=self.app.settings.get_browser_choice(),
            options=[
                ft.dropdown.Option("Chrome"),
                ft.dropdown.Option("Firefox"),
                ft.dropdown.Option("Edge"),
            ]
        )
        
        # Download images toggle
        self.download_images_switch = ft.Switch(
            label="Download and upload images",
            value=self.app.settings.download_pictures_and_upload()
        )
        
        # Extended mode toggle
        self.extended_mode_switch = ft.Switch(
            label="Extended mode (folder creator, scraper menu)",
            value=self.app.settings.is_extended_mode_enabled()
        )
        
        # KROSS path
        self.kross_path_field = ft.TextField(
            label="KROSS Images Download Path",
            value=self.app.settings.get_kross_path(),
            width=500,
            read_only=True
        )
        
        self.kross_path_button = ft.ElevatedButton(
            "Browse...",
            icon=ft.Icons.FOLDER_OPEN,
            on_click=lambda e: self.browse_folder("kross_download_path", self.kross_path_field)
        )
        
        # Repository path
        self.repo_path_field = ft.TextField(
            label="Bicycle Folder Repository Path",
            value=self.app.settings.get_repository_path(),
            width=500,
            read_only=True
        )
        
        self.repo_path_button = ft.ElevatedButton(
            "Browse...",
            icon=ft.Icons.FOLDER_OPEN,
            on_click=lambda e: self.browse_folder("repository_path", self.repo_path_field)
        )
        
        # Save button
        self.save_button = ft.ElevatedButton(
            "Save Settings",
            icon=ft.Icons.SAVE,
            on_click=self.save_settings,
            width=200
        )
        
        # Status text
        self.status_text = ft.Text("", size=14)
        
        # Build layout
        self.screen_content = ft.Column(
            [
                ft.Text("Nustatymai", size=24, weight=ft.FontWeight.BOLD),
                ft.Container(height=20),
                
                # Browser section
                ft.Text("Browser Settings", size=18, weight=ft.FontWeight.BOLD),
                ft.Container(height=10),
                self.browser_dropdown,
                ft.Container(height=20),
                
                # Feature toggles
                ft.Text("Features", size=18, weight=ft.FontWeight.BOLD),
                ft.Container(height=10),
                self.download_images_switch,
                ft.Container(height=5),
                self.extended_mode_switch,
                ft.Container(height=20),
                
                # Paths section
                ft.Text("Paths", size=18, weight=ft.FontWeight.BOLD),
                ft.Container(height=10),
                ft.Row(
                    [self.kross_path_field, self.kross_path_button],
                    spacing=10
                ),
                ft.Container(height=10),
                ft.Row(
                    [self.repo_path_field, self.repo_path_button],
                    spacing=10
                ),
                ft.Container(height=30),
                
                # Save button
                self.save_button,
                ft.Container(height=10),
                self.status_text
            ],
            scroll=ft.ScrollMode.AUTO,
            expand=True
        )
        return self.screen_content
    
    def browse_folder(self, setting_key, text_field):
        """Open folder picker dialog"""
        # Hide Tkinter root window
        root = Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        
        # Get current path as initial directory
        initial_dir = text_field.value or ""
        
        # Open folder picker
        folder = askdirectory(
            title=f"Select folder for {setting_key}",
            initialdir=initial_dir
        )
        
        root.destroy()
        
        # Update field if folder selected
        if folder:
            text_field.value = folder
            self.page.update()
    
    def save_settings(self, e):
        """Save all settings to database"""
        try:
            # Get values
            browser = self.browser_dropdown.value
            download_images = self.download_images_switch.value
            extended_mode = self.extended_mode_switch.value
            kross_path = self.kross_path_field.value
            repo_path = self.repo_path_field.value
            
            # Validate
            if not browser:
                self.show_status("Browser must be selected", ft.Colors.RED)
                return
            
            if not kross_path:
                self.show_status("KROSS path cannot be empty", ft.Colors.RED)
                return
            
            if not repo_path:
                self.show_status("Repository path cannot be empty", ft.Colors.RED)
                return
            
            # Save to database
            self.app.settings.set('browser_choice', browser)
            self.app.settings.set('download_images', download_images)
            self.app.settings.set('extended_mode', extended_mode)
            self.app.settings.set('kross_download_path', kross_path)
            self.app.settings.set('repository_path', repo_path)
            
            # Show success
            self.show_status("✓ Settings saved successfully!", ft.Colors.GREEN)
            
        except Exception as ex:
            self.show_status(f"✗ Error saving: {str(ex)}", ft.Colors.RED)
    
    def show_status(self, message, color):
        """Show status message"""
        self.status_text.value = message
        self.status_text.color = color
        self.page.update()
        
        # Clear after 3 seconds
        import threading
        def clear():
            import time
            time.sleep(3)
            self.status_text.value = ""
            self.page.update()
        
        threading.Thread(target=clear, daemon=True).start()