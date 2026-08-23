"""
Login Screen
Email, password, and browser selection with Selenium integration
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout
from PySide6.QtCore import Qt, QTimer
from qfluentwidgets import (
    LineEdit, PasswordLineEdit, ComboBox, PrimaryPushButton,
    IndeterminateProgressRing, BodyLabel, TitleLabel, InfoBar, InfoBarPosition, CardWidget, isDarkTheme
)

from GUI_Qt.styles.theme_config import FONTS, SIZES, get_surface_color
from GUI_Qt.styles.screen_theme import CARD_SPACING, CARD_SPACING_LARGE, CENTER_FORM_MARGINS, ROW_SPACING, CONTENT_SPACING

from GUI_Qt.workers.login_workers import PimboLoginWorker as LoginWorker


class LoginScreen(QWidget):
    """Login screen with email, password, and browser selection"""

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main = main_window
        self.login_worker = None

        self._init_ui()

    def _init_ui(self):
        """Initialize UI components"""

        # Background to match the rest of the app
        is_dark = isDarkTheme()
        bg_color = get_surface_color(is_dark, 'canvas')
        self.setStyleSheet(f"""
            LoginScreen {{
                background-color: {bg_color};
                font-family: {FONTS['family']};
            }}
        """)

        # Main layout with proper centering
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Add top stretch
        main_layout.addStretch(1)

        # Center container (card for better contrast in light theme)
        center_container = CardWidget()
        center_container.setMaximumWidth(SIZES['center_form_max_width'])
        center_layout = QVBoxLayout(center_container)
        center_layout.setSpacing(CARD_SPACING_LARGE)
        center_layout.setContentsMargins(*CENTER_FORM_MARGINS)

        # Title
        self.title_label = TitleLabel("")
        title = self.title_label
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center_layout.addWidget(title)

        self.subtitle_label = BodyLabel("")
        subtitle = self.subtitle_label
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center_layout.addWidget(subtitle)

        # Spacer
        center_layout.addSpacing(CARD_SPACING)

        # Email field with label on same line (horizontal)
        email_row = QWidget()
        email_row_layout = QVBoxLayout(email_row)
        email_row_layout.setSpacing(ROW_SPACING)
        email_row_layout.setContentsMargins(0, 0, 0, 0)

        self.email_label = BodyLabel("")
        email_label = self.email_label
        self.email_field = LineEdit()
        self.email_field.textChanged.connect(self._check_form_valid)

        email_row_layout.addWidget(email_label)
        email_row_layout.addWidget(self.email_field)
        center_layout.addWidget(email_row)

        # Password field
        password_row = QWidget()
        password_row_layout = QVBoxLayout(password_row)
        password_row_layout.setSpacing(ROW_SPACING)
        password_row_layout.setContentsMargins(0, 0, 0, 0)

        self.password_label = BodyLabel("")
        password_label = self.password_label
        self.password_field = PasswordLineEdit()
        self.password_field.textChanged.connect(self._check_form_valid)

        password_row_layout.addWidget(password_label)
        password_row_layout.addWidget(self.password_field)
        center_layout.addWidget(password_row)

        # Browser selection
        browser_row = QWidget()
        browser_row_layout = QVBoxLayout(browser_row)
        browser_row_layout.setSpacing(ROW_SPACING)
        browser_row_layout.setContentsMargins(0, 0, 0, 0)

        self.browser_label = BodyLabel("")
        browser_label = self.browser_label
        self.browser_combo = ComboBox()
        self.browser_combo.addItems(["Chrome", "Firefox", "Edge"])
        self.browser_combo.setCurrentText(self.main.settings.get_browser_choice() or "Chrome")

        browser_row_layout.addWidget(browser_label)
        browser_row_layout.addWidget(self.browser_combo)
        center_layout.addWidget(browser_row)

        # Spacer
        center_layout.addSpacing(CARD_SPACING)

        # Login button with progress ring
        button_row = QWidget()
        button_row_layout = QHBoxLayout(button_row)
        button_row_layout.setSpacing(CONTENT_SPACING)
        button_row_layout.setContentsMargins(0, 0, 0, 0)

        self.login_button = PrimaryPushButton("")
        self.login_button.setEnabled(False)
        self.login_button.clicked.connect(self._handle_login)

        self.progress_ring = IndeterminateProgressRing()
        self.progress_ring.setFixedSize(SIZES['progress_ring_lg'], SIZES['progress_ring_lg'])
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

        self.retranslate_ui()

    def retranslate_ui(self):
        tr = self.main.i18n.tr
        self.title_label.setText(tr("login.title"))
        self.subtitle_label.setText(tr("login.subtitle"))
        self.email_label.setText(tr("login.email"))
        self.email_field.setPlaceholderText(tr("login.email.placeholder"))
        self.password_label.setText(tr("login.password"))
        self.password_field.setPlaceholderText(tr("login.password.placeholder"))
        self.browser_label.setText(tr("login.browser"))
        self.login_button.setText(tr("login.button"))

    def _check_form_valid(self):
        """Check if form is valid and enable/disable login button"""
        email = self.email_field.text().strip()
        password = self.password_field.text().strip()

        valid = len(email) > 0 and len(password) > 0
        self.login_button.setEnabled(valid)

    def prefill_credentials(self, email: str = "", password: str = ""):
        """Prefill login fields for credential recovery or first-run setup."""
        if email:
            self.email_field.setText(email)
        if password:
            self.password_field.setText(password)
        else:
            self.password_field.clear()
        self._check_form_valid()

    def show_saved_login_failed_message(self):
        """Tell the user they can enter a new password to update stored creds."""
        def _show():
            InfoBar.warning(
                title=self.main.i18n.tr("login.saved_failed.title"),
                content=self.main.i18n.tr("login.saved_failed.content"),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=7000,
                parent=self
            )

        QTimer.singleShot(0, _show)

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
        self.login_worker = LoginWorker(email, password, browser, self.main.credential_manager, self.main.i18n.tr)
        self.login_worker.result.connect(self._on_login_complete)
        self.login_worker.start()

        # Preload heavy screens while Selenium login runs (avoids first-switch lag)
        try:
            self.main.start_screen_preload()
        except Exception:
            pass

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
                title=self.main.i18n.tr("login.success.title"),
                content=self.main.i18n.tr("login.success.content"),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=2000,
                parent=self
            )

            # Notify main window
            self.main.on_login_success(self.email_field.text().strip(), driver)
        else:
            try:
                self.main.cancel_screen_preload()
            except Exception:
                pass
            # Show error message
            InfoBar.error(
                title=self.main.i18n.tr("login.failed.title"),
                content=message,
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self
            )
