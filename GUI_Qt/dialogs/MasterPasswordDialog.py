"""
Master Password Dialogs
Setup dialog (first run) and prompt dialog (session expired)
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtCore import Qt
from qfluentwidgets import (
    MessageBox, PasswordLineEdit, BodyLabel, TitleLabel,
    PrimaryPushButton, InfoBar, InfoBarPosition
)


class MasterPasswordSetupDialog(QWidget):
    """Master password setup screen (first run)"""

    def __init__(self, main_window, on_complete, parent=None):
        super().__init__(parent)
        self.main = main_window
        self.on_complete_callback = on_complete

        self._init_ui()

    def _init_ui(self):
        """Initialize UI components"""

        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addStretch(1)

        # Center container
        center_container = QWidget()
        center_container.setMaximumWidth(400)
        center_layout = QVBoxLayout(center_container)
        center_layout.setSpacing(24)
        center_layout.setContentsMargins(40, 40, 40, 40)

        # Title
        title = TitleLabel("Welcome to UltraBike")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center_layout.addWidget(title)

        subtitle = BodyLabel("Set up your master password to secure your credentials")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setWordWrap(True)
        center_layout.addWidget(subtitle)

        # Spacer
        center_layout.addSpacing(16)

        # Password field
        password_row = QWidget()
        password_row_layout = QVBoxLayout(password_row)
        password_row_layout.setSpacing(8)
        password_row_layout.setContentsMargins(0, 0, 0, 0)

        password_label = BodyLabel("Master Password:")
        self.password_field = PasswordLineEdit()
        self.password_field.setPlaceholderText("Enter a strong password")
        self.password_field.textChanged.connect(self._check_form_valid)

        password_row_layout.addWidget(password_label)
        password_row_layout.addWidget(self.password_field)
        center_layout.addWidget(password_row)

        # Confirm password field
        confirm_row = QWidget()
        confirm_row_layout = QVBoxLayout(confirm_row)
        confirm_row_layout.setSpacing(8)
        confirm_row_layout.setContentsMargins(0, 0, 0, 0)

        confirm_label = BodyLabel("Confirm Password:")
        self.confirm_field = PasswordLineEdit()
        self.confirm_field.setPlaceholderText("Re-enter password")
        self.confirm_field.textChanged.connect(self._check_form_valid)

        confirm_row_layout.addWidget(confirm_label)
        confirm_row_layout.addWidget(self.confirm_field)
        center_layout.addWidget(confirm_row)

        # Spacer
        center_layout.addSpacing(16)

        # Create button
        self.create_button = PrimaryPushButton("Create Master Password")
        self.create_button.setEnabled(False)
        self.create_button.clicked.connect(self._handle_create)
        center_layout.addWidget(self.create_button)

        # Horizontally center
        h_layout = QHBoxLayout()
        h_layout.addStretch(1)
        h_layout.addWidget(center_container)
        h_layout.addStretch(1)

        main_layout.addLayout(h_layout)
        main_layout.addStretch(1)

        self.setLayout(main_layout)

    def _check_form_valid(self):
        """Check if passwords match and enable button"""
        password = self.password_field.text()
        confirm = self.confirm_field.text()

        valid = len(password) >= 6 and password == confirm
        self.create_button.setEnabled(valid)

    def _handle_create(self):
        """Handle create button click"""
        password = self.password_field.text()

        # Create master password
        self.main.credential_manager.create_master_password(password)

        # Show success
        InfoBar.success(
            title="Success",
            content="Master password created successfully!",
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=2000,
            parent=self
        )

        # Callback
        if self.on_complete_callback:
            self.on_complete_callback(password)


class MasterPasswordPromptDialog(QWidget):
    """Master password prompt screen (session expired)"""

    def __init__(self, main_window, on_success, parent=None):
        super().__init__(parent)
        self.main = main_window
        self.on_success_callback = on_success

        self._init_ui()

    def _init_ui(self):
        """Initialize UI components"""

        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addStretch(1)

        # Center container
        center_container = QWidget()
        center_container.setMaximumWidth(400)
        center_layout = QVBoxLayout(center_container)
        center_layout.setSpacing(24)
        center_layout.setContentsMargins(40, 40, 40, 40)

        # Title
        title = TitleLabel("Session Expired")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center_layout.addWidget(title)

        subtitle = BodyLabel("Enter your master password to continue")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center_layout.addWidget(subtitle)

        # Spacer
        center_layout.addSpacing(16)

        # Password field
        password_row = QWidget()
        password_row_layout = QVBoxLayout(password_row)
        password_row_layout.setSpacing(8)
        password_row_layout.setContentsMargins(0, 0, 0, 0)

        password_label = BodyLabel("Master Password:")
        self.password_field = PasswordLineEdit()
        self.password_field.setPlaceholderText("Enter master password")
        self.password_field.textChanged.connect(self._check_form_valid)
        self.password_field.returnPressed.connect(self._handle_unlock)

        password_row_layout.addWidget(password_label)
        password_row_layout.addWidget(self.password_field)
        center_layout.addWidget(password_row)

        # Spacer
        center_layout.addSpacing(16)

        # Unlock button
        self.unlock_button = PrimaryPushButton("Unlock")
        self.unlock_button.setEnabled(False)
        self.unlock_button.clicked.connect(self._handle_unlock)
        center_layout.addWidget(self.unlock_button)

        # Horizontally center
        h_layout = QHBoxLayout()
        h_layout.addStretch(1)
        h_layout.addWidget(center_container)
        h_layout.addStretch(1)

        main_layout.addLayout(h_layout)
        main_layout.addStretch(1)

        self.setLayout(main_layout)

    def _check_form_valid(self):
        """Check if password is entered"""
        password = self.password_field.text()
        self.unlock_button.setEnabled(len(password) > 0)

    def _handle_unlock(self):
        """Handle unlock button click"""
        password = self.password_field.text()

        # Verify master password
        if self.main.credential_manager.verify_master_password(password):
            # Get saved credentials
            email, saved_password = self.main.credential_manager.get_saved_credentials()

            # Show success
            InfoBar.success(
                title="Success",
                content="Master password verified!",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=2000,
                parent=self
            )

            # Callback with credentials
            if self.on_success_callback:
                self.on_success_callback(email, saved_password)
        else:
            # Show error
            InfoBar.error(
                title="Error",
                content="Invalid master password",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self
            )

            # Clear password field
            self.password_field.clear()
