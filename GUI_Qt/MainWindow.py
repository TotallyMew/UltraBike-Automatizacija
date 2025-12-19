"""
Main Application Window
Manages navigation, state, and screen switching
"""

from PySide6.QtWidgets import QWidget, QStackedWidget, QHBoxLayout, QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from qfluentwidgets import FluentWindow, NavigationItemPosition, FluentIcon

from Config.BrowserConfig.BrowserManager import BrowserManager
from Config.LoginConfig.CredentialManager import CredentialManager
from Database.DatabaseManager import DatabaseManager
from Database.SettingsManager import SettingsManager
from Utilities.Logger import Logger
from GUI_Qt.styles.theme_config import FONTS


class MainWindow(FluentWindow):
    """Main application window with Fluent Design navigation"""

    def __init__(self):
        super().__init__()

        # Initialize backend managers (same as Flet version)
        self.driver = None
        self.current_user = None
        self.logger = Logger()

        # Database setup
        self.db = DatabaseManager()
        self.settings = SettingsManager(self.db)
        self.credential_manager = CredentialManager(self.db)

        # Apply saved theme before UI initialization
        self._apply_saved_theme()

        # Configure window
        self.setWindowTitle("UltraBike prekių automatizacija")
        self.resize(1200, 800)

        # Set application font
        app_font = QFont()
        app_font.setFamily("Segoe UI")
        app_font.setPointSize(10)
        QApplication.instance().setFont(app_font)

        # Center window on screen
        self._center_on_screen()

        # Initialize screens (lazy loading)
        self.login_screen = None
        self.upload_screen = None
        self.batch_upload_screen = None
        self.history_screen = None
        self.translations_screen = None
        self.descriptions_screen = None
        self.settings_screen = None

        # Top bar reference
        self.top_bar = None

        # Setup UI
        self._init_navigation()
        self._init_window()

        # Hide navigation until logged in
        self.navigationInterface.setVisible(False)

        # Check session and show appropriate screen
        self._check_session()

    def _center_on_screen(self):
        """Center the window on the screen"""
        from PySide6.QtGui import QScreen
        screen = QScreen.availableGeometry(QApplication.primaryScreen())
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)

    def _init_navigation(self):
        """Initialize navigation sidebar"""

        # Add main navigation items
        self.navigationInterface.addItem(
            routeKey="upload",
            icon=FluentIcon.CLOUD_DOWNLOAD,
            text="Įkelti",
            onClick=lambda: self._switch_to_screen(0),
            position=NavigationItemPosition.TOP
        )

        self.navigationInterface.addItem(
            routeKey="batch",
            icon=FluentIcon.SYNC,
            text="Batch Upload",
            onClick=lambda: self._switch_to_screen(1),
            position=NavigationItemPosition.TOP
        )

        self.navigationInterface.addItem(
            routeKey="history",
            icon=FluentIcon.HISTORY,
            text="Istorija",
            onClick=lambda: self._switch_to_screen(2),
            position=NavigationItemPosition.TOP
        )

        self.navigationInterface.addItem(
            routeKey="translations",
            icon=FluentIcon.DOCUMENT,
            text="Vertimai",
            onClick=lambda: self._switch_to_screen(3),
            position=NavigationItemPosition.TOP
        )

        self.navigationInterface.addItem(
            routeKey="descriptions",
            icon=FluentIcon.EDIT,
            text="Aprašymai",
            onClick=lambda: self._switch_to_screen(4),
            position=NavigationItemPosition.TOP
        )

        # Add settings to bottom
        self.navigationInterface.addItem(
            routeKey="settings",
            icon=FluentIcon.SETTING,
            text="Nustatymai",
            onClick=lambda: self._switch_to_screen(5),
            position=NavigationItemPosition.BOTTOM
        )

    def _init_window(self):
        """Initialize window layout"""
        # FluentWindow automatically handles navigation layout
        # Make the navigation panel wider for better visibility
        self.navigationInterface.setExpandWidth(200)
        # Force navigation to stay expanded
        self.navigationInterface.expand(useAni=False)

    def _switch_to_screen(self, index):
        """Switch to a different screen"""
        # Lazy load screens
        if index == 0:  # Upload
            if not self.upload_screen:
                from GUI_Qt.screens.UploadScreen import UploadScreen
                self.upload_screen = UploadScreen(self)
                self._add_screen_to_stack(self.upload_screen, "Upload")
            self._show_screen(self.upload_screen)
        elif index == 1:  # Batch Upload
            if not self.batch_upload_screen:
                from GUI_Qt.screens.BatchUploadScreen import BatchUploadScreen
                self.batch_upload_screen = BatchUploadScreen(self)
                self._add_screen_to_stack(self.batch_upload_screen, "Batch Upload")
            self._show_screen(self.batch_upload_screen)
        elif index == 2:  # History
            if not self.history_screen:
                from GUI_Qt.screens.HistoryScreen import HistoryScreen
                self.history_screen = HistoryScreen(self)
                self._add_screen_to_stack(self.history_screen, "History")
            self._show_screen(self.history_screen)
        elif index == 3:  # Translations
            if not self.translations_screen:
                from GUI_Qt.screens.TranslationsScreen import TranslationsScreen
                self.translations_screen = TranslationsScreen(self)
                self._add_screen_to_stack(self.translations_screen, "Translations")
            self._show_screen(self.translations_screen)
        elif index == 4:  # Descriptions
            if not self.descriptions_screen:
                from GUI_Qt.screens.DescriptionsScreen import DescriptionsScreen
                self.descriptions_screen = DescriptionsScreen(self)
                self._add_screen_to_stack(self.descriptions_screen, "Descriptions")
            self._show_screen(self.descriptions_screen)
        elif index == 5:  # Settings
            if not self.settings_screen:
                from GUI_Qt.screens.SettingsScreen import SettingsScreen
                self.settings_screen = SettingsScreen(self)
                self._add_screen_to_stack(self.settings_screen, "Settings")
            self._show_screen(self.settings_screen)

    def _add_screen_to_stack(self, screen, name):
        """Add screen to content stack if not already added"""
        # Check if content_stack exists (after login)
        if not hasattr(self, 'content_stack'):
            return False

        # Check if screen already in stack
        for i in range(self.content_stack.count()):
            if self.content_stack.widget(i) == screen:
                return True

        # Add screen to stack
        self.content_stack.addWidget(screen)
        return True

    def _show_screen(self, screen):
        """Show a specific screen in content stack"""
        if not hasattr(self, 'content_stack'):
            return

        # Verify screen is in stack before trying to show it
        is_in_stack = False
        for i in range(self.content_stack.count()):
            if self.content_stack.widget(i) == screen:
                is_in_stack = True
                break

        if is_in_stack:
            self.content_stack.setCurrentWidget(screen)

    def _check_session(self):
        """Check for valid session and show appropriate screen"""

        if self.credential_manager.has_master_password():
            if self.credential_manager.session_manager.validate_session():
                # Valid session exists - auto-login
                email, password = self.credential_manager.get_saved_credentials()
                if email and password:
                    self._auto_login(email, password)
                    return

            # Master password exists but session expired
            self._show_master_password_prompt()
        else:
            # First run - setup master password
            self._show_master_password_setup()

    def _show_loading(self, message):
        """Show loading screen"""
        from GUI_Qt.widgets.LoadingWidget import LoadingWidget

        loading_widget = LoadingWidget(message)
        self.stackedWidget.addWidget(loading_widget)
        self.stackedWidget.setCurrentWidget(loading_widget)

    def _show_master_password_setup(self):
        """Show master password setup screen (first run)"""
        from GUI_Qt.dialogs.MasterPasswordDialog import MasterPasswordSetupDialog

        def on_complete(master_password):
            # Master password created, now show login
            self.show_login()

        setup_screen = MasterPasswordSetupDialog(self, on_complete)
        self.stackedWidget.addWidget(setup_screen)
        self.stackedWidget.setCurrentWidget(setup_screen)

    def _show_master_password_prompt(self):
        """Show master password prompt (session expired)"""
        from GUI_Qt.dialogs.MasterPasswordDialog import MasterPasswordPromptDialog

        def on_success(email, password):
            # Master password verified, auto-login
            self._auto_login(email, password)

        prompt_screen = MasterPasswordPromptDialog(self, on_success)
        self.stackedWidget.addWidget(prompt_screen)
        self.stackedWidget.setCurrentWidget(prompt_screen)

    def _auto_login(self, email, password):
        """Auto-login with saved credentials"""
        from GUI_Qt.widgets.LoadingWidget import LoadingWidget
        from PySide6.QtCore import QThread, Signal
        from Config.BrowserConfig.BrowserManager import BrowserManager
        from Config.LoginConfig.LoginHandler import LoginHandler

        class AutoLoginWorker(QThread):
            finished = Signal(bool, object)  # success, driver

            def __init__(self, email, password, settings, credential_manager):
                super().__init__()
                self.email = email
                self.password = password
                self.settings = settings
                self.credential_manager = credential_manager

            def run(self):
                try:
                    browser_choice = self.settings.get_browser_choice()
                    browser_manager = BrowserManager()
                    driver = browser_manager.setup_browser(
                        browser_choice,
                        retry_callback=lambda: False
                    )

                    if driver is None:
                        self.finished.emit(False, None)
                        return

                    login_handler = LoginHandler(driver, self.credential_manager)
                    success = login_handler.login(
                        credentials_callback=lambda: (self.email, self.password),
                        retry_callback=lambda: False,
                        max_attempts=1
                    )

                    if success:
                        self.finished.emit(True, driver)
                    else:
                        if driver:
                            driver.quit()
                        self.finished.emit(False, None)

                except Exception:
                    self.finished.emit(False, None)

        # Show loading
        self._show_loading("Jungiamasi į PrestaShop...")

        # Start auto-login worker
        worker = AutoLoginWorker(email, password, self.settings, self.credential_manager)

        def on_complete(success, driver):
            if success:
                self.current_user = email
                self.driver = driver
                self.credential_manager.create_session(email, password)
                self.show_main()
            else:
                self.show_login()

        worker.finished.connect(on_complete)
        worker.start()
        self._auto_login_worker = worker  # Keep reference

    def show_login(self):
        """Show login screen"""
        from GUI_Qt.screens.LoginScreen import LoginScreen

        if not self.login_screen:
            self.login_screen = LoginScreen(self)

        self.stackedWidget.addWidget(self.login_screen)
        self.stackedWidget.setCurrentWidget(self.login_screen)

    def show_main(self):
        """Show main application with navigation"""
        from GUI_Qt.widgets.TopBar import TopBar
        from PySide6.QtWidgets import QWidget, QVBoxLayout, QStackedWidget

        # Show navigation bar
        self.navigationInterface.setVisible(True)

        # Create top bar if not exists
        if not self.top_bar:
            self.top_bar = TopBar(self.current_user, self.logout, self)

        # Create main content container with top bar and content area
        main_container = QWidget()
        main_container.setObjectName("mainContainer")
        main_layout = QVBoxLayout(main_container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(self.top_bar)

        # Create our own stacked widget for content screens
        self.content_stack = QStackedWidget()
        self.content_stack.setObjectName("contentStack")

        # Apply background colors to containers
        from qfluentwidgets import isDarkTheme
        from GUI_Qt.styles.theme_config import COLORS
        is_dark = isDarkTheme()
        bg_color = COLORS['space_indigo'] if is_dark else COLORS['platinum']

        main_container.setStyleSheet(f"""
            #mainContainer {{
                background-color: {bg_color};
            }}
        """)
        self.content_stack.setStyleSheet(f"""
            #contentStack {{
                background-color: {bg_color};
            }}
        """)

        main_layout.addWidget(self.content_stack, 1)

        # Add main container to FluentWindow's stackedWidget
        self.stackedWidget.addWidget(main_container)
        self.stackedWidget.setCurrentWidget(main_container)

        # Switch to upload screen by default
        self._switch_to_screen(0)

    def on_login_success(self, email, driver):
        """Called when login succeeds"""
        self.current_user = email
        self.driver = driver

        # Create session if login screen has password
        if hasattr(self, 'login_screen') and self.login_screen:
            password = getattr(self.login_screen, 'password', None)
            if password:
                self.credential_manager.create_session(email, password)

        self.show_main()

    def logout(self):
        """Logout and return to login"""
        if self.driver:
            self.driver.quit()
            self.driver = None
        self.current_user = None

        # Hide navigation bar
        self.navigationInterface.setVisible(False)

        self.show_login()

    def start_batch_processing(self, items):
        """
        Start batch processing with collected items

        Args:
            items: List of {brand, code, url} dicts
        """
        # Switch to upload screen
        self._switch_to_screen(0)

        # Trigger batch processing in upload screen
        if self.upload_screen:
            self.upload_screen.show_batch_processing(items)

    def _apply_saved_theme(self):
        """Apply saved theme from settings"""
        from qfluentwidgets import setTheme, Theme
        from GUI_Qt.styles.global_styles import get_global_stylesheet

        theme = self.settings.get('theme', 'light')
        if theme == 'dark':
            setTheme(Theme.DARK)
        else:
            setTheme(Theme.LIGHT)

        # Apply global stylesheet for consistent styling
        self.setStyleSheet(get_global_stylesheet())

    def update_container_backgrounds(self):
        """Update main container and content stack backgrounds when theme changes"""
        from qfluentwidgets import isDarkTheme
        from GUI_Qt.styles.theme_config import COLORS

        if not hasattr(self, 'content_stack'):
            return

        is_dark = isDarkTheme()
        bg_color = COLORS['space_indigo'] if is_dark else COLORS['platinum']

        # Find and update main container
        for i in range(self.stackedWidget.count()):
            widget = self.stackedWidget.widget(i)
            if widget.objectName() == "mainContainer":
                widget.setStyleSheet(f"""
                    #mainContainer {{
                        background-color: {bg_color};
                    }}
                """)
                break

        # Update content stack
        if hasattr(self, 'content_stack'):
            self.content_stack.setStyleSheet(f"""
                #contentStack {{
                    background-color: {bg_color};
                }}
            """)
