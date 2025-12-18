"""
Login Screen
Email, password, and browser selection with Selenium integration
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout
from PySide6.QtCore import Qt, QThread, Signal
from qfluentwidgets import (
    LineEdit, PasswordLineEdit, ComboBox, PrimaryPushButton,
    IndeterminateProgressRing, BodyLabel, TitleLabel, InfoBar, InfoBarPosition
)

from Config.BrowserConfig.BrowserManager import BrowserManager
from Config.LoginConfig.LoginHandler import LoginHandler


class LoginWorker(QThread):
    """Background worker for login process"""
    finished = Signal(bool, str, object)  # success, message, driver

    def __init__(self, email, password, browser_choice, credential_manager):
        super().__init__()
        self.email = email
        self.password = password
        self.browser_choice = browser_choice
        self.credential_manager = credential_manager
        self.driver = None

    def run(self):
        """Perform login in background thread"""
        try:
            # Setup browser
            browser_manager = BrowserManager()
            self.driver = browser_manager.setup_browser(
                self.browser_choice,
                retry_callback=lambda: False
            )

            if self.driver is None:
                self.finished.emit(False, "Failed to initialize browser", None)
                return

            # Attempt login
            login_handler = LoginHandler(self.driver, self.credential_manager)
            success = login_handler.login(
                credentials_callback=lambda: (self.email, self.password),
                retry_callback=lambda: False,
                max_attempts=1
            )

            if success:
                self.finished.emit(True, "Login successful", self.driver)
            else:
                if self.driver:
                    self.driver.quit()
                self.finished.emit(False, "Invalid credentials", None)

        except Exception as e:
            if self.driver:
                self.driver.quit()
            self.finished.emit(False, str(e), None)


class LoginScreen(QWidget):
    """Login screen with email, password, and browser selection"""

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main = main_window
        self.login_worker = None

        self._init_ui()

    def _init_ui(self):
        """Initialize UI components"""

        # Main layout with proper centering
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Add top stretch
        main_layout.addStretch(1)

        # Center container
        center_container = QWidget()
        center_container.setMaximumWidth(400)
        center_layout = QVBoxLayout(center_container)
        center_layout.setSpacing(24)
        center_layout.setContentsMargins(40, 40, 40, 40)

        # Title
        title = TitleLabel("UltraBike Automation")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center_layout.addWidget(title)

        subtitle = BodyLabel("Prisijunkite prie PrestaShop")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center_layout.addWidget(subtitle)

        # Spacer
        center_layout.addSpacing(16)

        # Email field with label on same line (horizontal)
        email_row = QWidget()
        email_row_layout = QVBoxLayout(email_row)
        email_row_layout.setSpacing(8)
        email_row_layout.setContentsMargins(0, 0, 0, 0)

        email_label = BodyLabel("El. paštas:")
        self.email_field = LineEdit()
        self.email_field.setPlaceholderText("jusu@email.lt")
        self.email_field.textChanged.connect(self._check_form_valid)

        email_row_layout.addWidget(email_label)
        email_row_layout.addWidget(self.email_field)
        center_layout.addWidget(email_row)

        # Password field
        password_row = QWidget()
        password_row_layout = QVBoxLayout(password_row)
        password_row_layout.setSpacing(8)
        password_row_layout.setContentsMargins(0, 0, 0, 0)

        password_label = BodyLabel("Slaptažodis:")
        self.password_field = PasswordLineEdit()
        self.password_field.setPlaceholderText("••••••••")
        self.password_field.textChanged.connect(self._check_form_valid)

        password_row_layout.addWidget(password_label)
        password_row_layout.addWidget(self.password_field)
        center_layout.addWidget(password_row)

        # Browser selection
        browser_row = QWidget()
        browser_row_layout = QVBoxLayout(browser_row)
        browser_row_layout.setSpacing(8)
        browser_row_layout.setContentsMargins(0, 0, 0, 0)

        browser_label = BodyLabel("Naršyklė:")
        self.browser_combo = ComboBox()
        self.browser_combo.addItems(["Chrome", "Firefox", "Edge"])
        self.browser_combo.setCurrentText(self.main.settings.get_browser_choice() or "Chrome")

        browser_row_layout.addWidget(browser_label)
        browser_row_layout.addWidget(self.browser_combo)
        center_layout.addWidget(browser_row)

        # Spacer
        center_layout.addSpacing(16)

        # Login button with progress ring
        button_row = QWidget()
        button_row_layout = QHBoxLayout(button_row)
        button_row_layout.setSpacing(12)
        button_row_layout.setContentsMargins(0, 0, 0, 0)

        self.login_button = PrimaryPushButton("Prisijungti")
        self.login_button.setEnabled(False)
        self.login_button.clicked.connect(self._handle_login)

        self.progress_ring = IndeterminateProgressRing()
        self.progress_ring.setFixedSize(32, 32)
        self.progress_ring.setVisible(False)

        button_row_layout.addWidget(self.login_button, 1)
        button_row_layout.addWidget(self.progress_ring)
        center_layout.addWidget(button_row)

        # Horizontally center the container
        h_layout = QHBoxLayout()
        h_layout.addStretch(1)
        h_layout.addWidget(center_container)
        h_layout.addStretch(1)

        main_layout.addLayout(h_layout)

        # Add bottom stretch
        main_layout.addStretch(1)

        self.setLayout(main_layout)

    def _check_form_valid(self):
        """Check if form is valid and enable/disable login button"""
        email = self.email_field.text().strip()
        password = self.password_field.text().strip()

        valid = len(email) > 0 and len(password) > 0
        self.login_button.setEnabled(valid)

    def _handle_login(self):
        """Handle login button click"""
        email = self.email_field.text().strip()
        password = self.password_field.text().strip()
        browser = self.browser_combo.currentText()

        # Save browser choice
        self.main.settings.set('browser_choice', browser)

        # Show loading state
        self.login_button.setEnabled(False)
        self.progress_ring.setVisible(True)
        self.email_field.setEnabled(False)
        self.password_field.setEnabled(False)
        self.browser_combo.setEnabled(False)

        # Store password for session creation
        self.password = password

        # Start login worker
        self.login_worker = LoginWorker(email, password, browser, self.main.credential_manager)
        self.login_worker.finished.connect(self._on_login_complete)
        self.login_worker.start()

    def _on_login_complete(self, success, message, driver):
        """Handle login completion"""
        # Hide loading state
        self.progress_ring.setVisible(False)
        self.email_field.setEnabled(True)
        self.password_field.setEnabled(True)
        self.browser_combo.setEnabled(True)
        self.login_button.setEnabled(True)

        if success:
            # Show success message
            InfoBar.success(
                title="Success",
                content="Login successful!",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=2000,
                parent=self
            )

            # Notify main window
            self.main.on_login_success(self.email_field.text().strip(), driver)
        else:
            # Show error message
            InfoBar.error(
                title="Login Failed",
                content=message,
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self
            )
