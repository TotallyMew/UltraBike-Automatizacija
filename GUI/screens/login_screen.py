"""Login screen component"""

import flet as ft
from Config.BrowserConfig.BrowserManager import BrowserManager
from Config.LoginConfig.LoginHandler import LoginHandler

class LoginScreen:
    def __init__(self, app):
        self.app = app
        self.page = app.page
    
    def build(self):
        """Build login screen UI"""
        
        # Email field
        self.email_field = ft.TextField(
            label="El. paštas",
            width=300,
            autofocus=True
        )
        
        # Password field
        self.password_field = ft.TextField(
            label="Slaptažodis",
            password=True,
            can_reveal_password=True,
            width=300
        )
        
        # Login button
        self.login_button = ft.ElevatedButton(
            "Prisijungti",
            on_click=self.handle_login,
            width=300
        )
        
        # Status text
        self.status_text = ft.Text("", size=14)
        
        # Pre-fill saved credentials
        saved_email, saved_password = self.app.credential_manager.get_saved_credentials()
        if saved_email:
            self.email_field.value = saved_email
            self.password_field.value = saved_password
        
        # Layout
        return ft.Container(
            content=ft.Column(
                [
                    ft.Text(
                        "UltraBike Automation",
                        size=32,
                        weight=ft.FontWeight.BOLD
                    ),
                    ft.Text(
                        "Prisijunkite prie PrestaShop",
                        size=16,
                        color=ft.Colors.GREY_700
                    ),
                    ft.Container(height=20),
                    self.email_field,
                    self.password_field,
                    ft.Container(height=10),
                    self.login_button,
                    ft.Container(height=10),
                    self.status_text
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=10
            ),
            padding=40,
            alignment=ft.alignment.center
        )
    
    def handle_login(self, e):
        """Handle login button click"""
        email = self.email_field.value
        password = self.password_field.value

        # Validate
        if not email or not password:
            self.status_text.value = "Įveskite el. paštą ir slaptažodį"
            self.status_text.color = ft.Colors.RED
            self.page.update()
            return

        # Show progress
        self.login_button.disabled = True
        self.status_text.value = "Jungiamasi..."
        self.status_text.color = ft.Colors.BLUE
        self.page.update()

        # Setup browser with retry callback
        browser_choice = self.app.settings.get_browser_choice()
        browser_manager = BrowserManager()

        def internet_retry_callback():
            """Called when internet connection fails - just fail in GUI"""
            return False  # Don't retry in GUI, just fail

        driver = browser_manager.setup_browser(browser_choice, retry_callback=internet_retry_callback)

        if driver is None:
            self.status_text.value = "Naršyklės paleisti nepavyko. Patikrinkite interneto ryšį."
            self.status_text.color = ft.Colors.RED
            self.login_button.disabled = False
            self.page.update()
            return
    
        # Attempt login
        login_handler = LoginHandler(driver, self.app.credential_manager)
    
        success = login_handler.login(
            credentials_callback=lambda: (email, password),
            retry_callback=lambda: False,
            max_attempts=1
        )
    
        if success:
            # Save credentials
            if hasattr(self.app, 'master_password') and self.app.master_password:
                # Save with master password encryption
                self.app.credential_manager.save_credentials(email, password, self.app.master_password)
            else:
                # Save to legacy JSON (fallback)
                self.app.credential_manager.save_credentials(email, password)
        
            self.status_text.value = "Prisijungimas sėkmingas!"
            self.status_text.color = ft.Colors.GREEN
            self.page.update()
        
            import time
            time.sleep(1)
        
            # Notify app of successful login
            self.app.on_login_success(email, driver)
        else:
            self.status_text.value = "Prisijungimas nepavyko. Patikrinkite duomenis."
            self.status_text.color = ft.Colors.RED
            self.login_button.disabled = False
            self.page.update()