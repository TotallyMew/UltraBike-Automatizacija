"""
UltraBike GUI - Main Application Class
Manages app state, navigation, and screen switching
"""

import flet as ft
from Config.BrowserConfig.BrowserManager import BrowserManager
from Config.LoginConfig.CredentialManager import CredentialManager
from Database.DatabaseManager import DatabaseManager
from Database.SettingsManager import SettingsManager

from GUI.screens.login_screen import LoginScreen
from GUI.screens.upload_screen import UploadScreen
from GUI.screens.history_screen import HistoryScreen
from GUI.screens.settings_screen import SettingsScreen
from GUI.components.navigation import NavigationRail
from GUI.components.top_bar import TopBar
from GUI.screens.master_password_screen import MasterPasswordScreen
from GUI.screens.master_password_prompt import MasterPasswordPrompt
from Utilities.Logger import Logger  # Add to imports at top
from GUI.screens.descriptions_screen import DescriptionsScreen


class UltraBikeApp:
    """Main application controller"""
    
    def __init__(self, page: ft.Page):
        self.page = page
        self.driver = None
        self.current_user = None
        self.logger = Logger()
        self.current_screen_index = 0
    
        # Database setup
        self.db = DatabaseManager()
        self.settings = SettingsManager(self.db)
        self.credential_manager = CredentialManager(self.db)
    
        # Configure window
        self.page.title = "UltraBike prekių automatizacija"
        self.page.window_width = 1200
        self.page.window_height = 800
        self.page.window_resizable = True
        self.page.padding = 0
    
        # Initialize screens (will be created as needed)
        self.login_screen = None
        self.upload_screen = None
        self.history_screen = None
        self.settings_screen = None
        self.translations_screen = None
        self.descriptions_screen = None
    
        # Check for valid session ONLY if master password exists
        if self.credential_manager.has_master_password():
            if self.credential_manager.session_manager.validate_session():
                # Valid session exists - show loading and auto-login
                email, password = self.credential_manager.get_saved_credentials()
                if email and password:
                    self.show_loading("Jungiamasi į PrestaShop...")
            
                    # Schedule auto-login after 100ms (let loading screen render)
                    def do_auto_login(e):
                        self.auto_login(email, password)
            
                    self.page.run_thread_safe = lambda: None  # Dummy to check if method exists
                    # Use page update cycle to trigger login
                    import threading
                    timer = threading.Timer(0.1, lambda: self.auto_login(email, password))
                    timer.daemon = True
                    timer.start()
                    return
    
            # Master password exists but session expired - prompt
            self.show_master_password_prompt()
        else:
            # First run - setup master password
            self.show_master_password_setup()
    
    def show_login(self):
        """Show login screen"""
        self.page.clean()
        self.page.add(self.login_screen.build())
        self.page.update()
    
    def on_login_success(self, email, driver):
        """Called when login succeeds"""
        self.current_user = email
        self.driver = driver
    
        # Get password from login screen if available
        if hasattr(self, 'login_screen') and self.login_screen:
            password = self.login_screen.password_field.value
            if password:
                # Create 24h session
                self.credential_manager.create_session(email, password)
    
        self.show_main()
    
    def show_main(self):
        """Show main application with navigation"""
        self.page.clean()

        # Initialize screens if not already created
        if not self.upload_screen:
            from GUI.screens.upload_screen import UploadScreen
            self.upload_screen = UploadScreen(self)

        if not self.history_screen:
            from GUI.screens.history_screen import HistoryScreen
            self.history_screen = HistoryScreen(self)

        if not self.settings_screen:
            from GUI.screens.settings_screen import SettingsScreen
            self.settings_screen = SettingsScreen(self)
   
        if not self.translations_screen:
            from GUI.screens.translations_screen import TranslationsScreen
            self.translations_screen = TranslationsScreen(self)

        if not self.descriptions_screen:
            from GUI.screens.descriptions_screen import DescriptionsScreen
            self.descriptions_screen = DescriptionsScreen(self)

        # Create navigation
        from GUI.components.navigation import NavigationRail
        from GUI.components.top_bar import TopBar

        self.nav = NavigationRail(self, on_change=self.handle_nav_change)

        # Create top bar
        self.top_bar = TopBar(self, self.current_user, on_logout=self.logout)

        # Build upload screen if not already built
        if not hasattr(self.upload_screen, 'screen_content'):
            self.upload_screen.build()

        # Content area (starts with upload screen)
        self.content_area = ft.Container(
            content=self.upload_screen.screen_content,  # ← Use cached content
            padding=20,
            expand=True
        )

        # Layout
        main_layout = ft.Column(
            [
                self.top_bar.build(),
                ft.Row(
                    [
                        self.nav.build(),
                        ft.VerticalDivider(width=1),
                        self.content_area
                    ],
                    expand=True
                )
            ],
            spacing=0,
            expand=True
        )

        self.page.add(main_layout)
        self.page.update()
    
    # GUI/app.py

    def handle_nav_change(self, index):
        """Handle navigation change"""
        self.current_screen_index = index

        screens = [
            self.upload_screen,
            self.history_screen,
            self.translations_screen,
            self.descriptions_screen,
            self.settings_screen
        ]
    
        selected_screen = screens[index]
    
        # Build screen if not already built (lazy loading)
        if not hasattr(selected_screen, 'screen_content'):
            print(f"DEBUG: Building screen {index} for first time")  # ← Add this
            selected_screen.build()
        else:
            print(f"DEBUG: Using cached content for screen {index}")  # ← Add this
    
        self.content_area.content = selected_screen.screen_content
    
        # Load data for screens that need it (only on first visit)
        if index == 1 and not hasattr(self.history_screen, '_data_loaded'):
            print("DEBUG: Loading history data")  # ← Add this
            self.history_screen.refresh_history()
            self.history_screen._data_loaded = True
        elif index == 2 and not hasattr(self.translations_screen, '_data_loaded'):
            print("DEBUG: Loading translations data")  # ← Add this
            self.translations_screen.refresh_translations()
            self.translations_screen._data_loaded = True
    
        self.page.update()
    
    def logout(self):
        """Logout and return to login"""
        if self.driver:
            self.driver.quit()
            self.driver = None
        self.current_user = None
        self.show_login()

    def show_master_password_setup(self):
        """Show master password setup screen (first run)"""
        self.page.clean()
    
        def on_complete(master_password):
            # Master password created, now show login
            self.master_password = master_password
            self.show_login()
    
        master_screen = MasterPasswordScreen(self, on_complete)
        self.page.add(master_screen.build())
        self.page.update()

    def show_master_password_prompt(self):
        """Show master password prompt (session expired)"""
        self.page.clean()
    
        def on_success(email, password):
            # Master password verified, auto-login
            self.auto_login(email, password)
    
        # No cancel callback - user must enter correct password
        prompt_screen = MasterPasswordPrompt(self, on_success)
        self.page.add(prompt_screen.build())
        self.page.update()

    def auto_login(self, email, password):
        """Auto-login with saved credentials (thread-safe)"""
        # Setup browser (can run in background)
        browser_choice = self.settings.get_browser_choice()
        browser_manager = BrowserManager()
        self.driver = browser_manager.setup_browser(browser_choice)
    
        if self.driver is None:
            # Browser failed, show login screen (must update UI on main thread)
            def show_login_ui():
                self.show_login()
            self.page.update()  # Force update first
            self.show_login()
            return
    
        # Attempt login (blocking operation, but that's fine in background thread)
        from Config.LoginConfig.LoginHandler import LoginHandler
        login_handler = LoginHandler(self.driver, self.credential_manager)
    
        success = login_handler.login(
            credentials_callback=lambda: (email, password),
            retry_callback=lambda: False,
            max_attempts=1
        )
    
        if success:
            self.current_user = email
            self.credential_manager.create_session(email, password)
        
            # Show main screen (UI update)
            self.show_main()
            self.page.update()
        else:
            # Auto-login failed, show login screen
            if self.driver:
                self.driver.quit()
                self.driver = None
        
            self.show_login()
            self.page.update()

    def show_login(self):
        """Show login screen"""
        self.page.clean()
    
        if not self.login_screen:
            from GUI.screens.login_screen import LoginScreen
            self.login_screen = LoginScreen(self)
    
        self.page.add(self.login_screen.build())
        self.page.update()

    def show_loading(self, message="Loading..."):
        """Show loading screen"""
        self.page.clean()
    
        from GUI.screens.loading_screen import LoadingScreen
        loading_screen = LoadingScreen(self, message)
        self.page.add(loading_screen.build())
        self.page.update()

    def start_batch_processing(self, items):
        """
        Start batch processing with collected items
    
        Args:
            items: List of {brand, code, url} dicts
        """
        # Switch to upload screen if not already there
        if self.current_screen_index != 0:
            self.current_screen_index = 0
            self.content_area.content = self.upload_screen.build()
            self.page.update()
    
    
        # Show batch processing UI
        self.upload_screen.show_batch_processing(items)