"""
Master Password Dialogs
Setup dialog (first run) and prompt dialog (session expired)
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout
from PySide6.QtCore import Qt
from qfluentwidgets import (
    MessageBox, PasswordLineEdit, BodyLabel, TitleLabel,
    CaptionLabel, PrimaryPushButton, InfoBar, InfoBarPosition
)

from GUI_Qt.styles.theme_config import SIZES, SPACING
from GUI_Qt.styles.screen_theme import (
    CARD_SPACING, CARD_SPACING_LARGE, CENTER_FORM_MARGINS, ROW_SPACING,
    apply_screen_theme,
)


class MasterPasswordSetupDialog(QWidget):
    """Master password setup screen (first run)"""

    def __init__(self, main_window, on_complete, parent=None):
        super().__init__(parent)
        self.main = main_window
        self.on_complete_callback = on_complete

        self._init_ui()
        apply_screen_theme(self, "MasterPasswordSetupDialog")

    def _init_ui(self):
        """Initialize UI components"""

        # Main layout with outer margins to prevent edge clipping
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(SPACING['xl'], SPACING['xl'], SPACING['xl'], SPACING['xl'])
        main_layout.addStretch(1)

        # Center container
        center_container = QWidget()
        center_container.setMaximumWidth(SIZES['center_form_max_width'])
        center_layout = QVBoxLayout(center_container)
        center_layout.setSpacing(CARD_SPACING_LARGE)
        center_layout.setContentsMargins(*CENTER_FORM_MARGINS)

        # Title
        title = TitleLabel(self.main.i18n.tr("master.setup.title"))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setWordWrap(True)
        center_layout.addWidget(title)

        subtitle = BodyLabel(self.main.i18n.tr("master.setup.subtitle"))
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setWordWrap(True)
        center_layout.addWidget(subtitle)

        # Spacer
        center_layout.addSpacing(CARD_SPACING)

        # Password field
        password_row = QWidget()
        password_row_layout = QVBoxLayout(password_row)
        password_row_layout.setSpacing(ROW_SPACING)
        password_row_layout.setContentsMargins(0, 0, 0, 0)

        password_label = BodyLabel(self.main.i18n.tr("master.password.label"))
        self.password_field = PasswordLineEdit()
        self.password_field.setPlaceholderText(self.main.i18n.tr("master.password.placeholder"))
        self.password_field.setAccessibleName(self.main.i18n.tr("master.password.label"))
        self.password_field.textChanged.connect(self._check_form_valid)
        password_label.setBuddy(self.password_field)

        password_row_layout.addWidget(password_label)
        password_row_layout.addWidget(self.password_field)
        center_layout.addWidget(password_row)

        # Confirm password field
        confirm_row = QWidget()
        confirm_row_layout = QVBoxLayout(confirm_row)
        confirm_row_layout.setSpacing(ROW_SPACING)
        confirm_row_layout.setContentsMargins(0, 0, 0, 0)

        confirm_label = BodyLabel(self.main.i18n.tr("master.confirm.label"))
        self.confirm_field = PasswordLineEdit()
        self.confirm_field.setPlaceholderText(self.main.i18n.tr("master.confirm.placeholder"))
        self.confirm_field.setAccessibleName(self.main.i18n.tr("master.confirm.label"))
        self.confirm_field.textChanged.connect(self._check_form_valid)
        self.confirm_field.returnPressed.connect(self._handle_create)
        confirm_label.setBuddy(self.confirm_field)

        confirm_row_layout.addWidget(confirm_label)
        confirm_row_layout.addWidget(self.confirm_field)
        center_layout.addWidget(confirm_row)

        self.validation_label = CaptionLabel(self.main.i18n.tr("master.password.requirement"))
        self.validation_label.setWordWrap(True)
        center_layout.addWidget(self.validation_label)

        # Spacer
        center_layout.addSpacing(CARD_SPACING)

        # Create button
        self.create_button = PrimaryPushButton(self.main.i18n.tr("master.create"))
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

        valid_length = len(password) >= 10
        matches = password == confirm
        valid = valid_length and matches
        self.create_button.setEnabled(valid)
        if not valid_length:
            self.validation_label.setText(self.main.i18n.tr("master.password.requirement"))
            state = "error" if password else ""
        elif not confirm:
            self.validation_label.setText(self.main.i18n.tr("master.password.confirm_requirement"))
            state = ""
        elif not matches:
            self.validation_label.setText(self.main.i18n.tr("master.password.mismatch"))
            state = "error"
        else:
            self.validation_label.setText(self.main.i18n.tr("master.password.ready"))
            state = "valid"
        self.password_field.setProperty("validationState", "valid" if valid_length else state)
        self.confirm_field.setProperty("validationState", state)
        for field in (self.password_field, self.confirm_field):
            field.style().unpolish(field)
            field.style().polish(field)

    def _handle_create(self):
        """Handle create button click"""
        password = self.password_field.text()
        if not self.create_button.isEnabled():
            return

        try:
            self.main.credential_manager.create_master_password(password)
        except Exception as error:
            InfoBar.error(
                title=self.main.i18n.tr("common.error"),
                content=str(error),
                position=InfoBarPosition.TOP,
                duration=4000,
                parent=self,
            )
            return

        # Show success
        InfoBar.success(
            title=self.main.i18n.tr("master.created.title"),
            content=self.main.i18n.tr("master.created.content"),
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
        apply_screen_theme(self, "MasterPasswordPromptDialog")

    def _init_ui(self):
        """Initialize UI components"""

        # Main layout with outer margins to prevent edge clipping
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(SPACING['xl'], SPACING['xl'], SPACING['xl'], SPACING['xl'])
        main_layout.addStretch(1)

        # Center container
        center_container = QWidget()
        center_container.setMaximumWidth(SIZES['center_form_max_width'])
        center_layout = QVBoxLayout(center_container)
        center_layout.setSpacing(CARD_SPACING_LARGE)
        center_layout.setContentsMargins(*CENTER_FORM_MARGINS)

        # Title
        title = TitleLabel(self.main.i18n.tr("master.prompt.title"))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setWordWrap(True)
        center_layout.addWidget(title)

        subtitle = BodyLabel(self.main.i18n.tr("master.prompt.subtitle"))
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setWordWrap(True)
        center_layout.addWidget(subtitle)

        # Spacer
        center_layout.addSpacing(CARD_SPACING)

        # Password field
        password_row = QWidget()
        password_row_layout = QVBoxLayout(password_row)
        password_row_layout.setSpacing(ROW_SPACING)
        password_row_layout.setContentsMargins(0, 0, 0, 0)

        password_label = BodyLabel(self.main.i18n.tr("master.password.label"))
        self.password_field = PasswordLineEdit()
        self.password_field.setPlaceholderText(self.main.i18n.tr("master.password.placeholder"))
        self.password_field.setAccessibleName(self.main.i18n.tr("master.password.label"))
        self.password_field.textChanged.connect(self._check_form_valid)
        self.password_field.returnPressed.connect(self._handle_unlock)
        password_label.setBuddy(self.password_field)

        password_row_layout.addWidget(password_label)
        password_row_layout.addWidget(self.password_field)
        center_layout.addWidget(password_row)

        # Spacer
        center_layout.addSpacing(CARD_SPACING)

        # Unlock button
        self.unlock_button = PrimaryPushButton(self.main.i18n.tr("master.unlock"))
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
            # Cache unlocked master password for this run
            try:
                self.main._unlocked_master_password = password
            except Exception:
                pass

            # Decrypt credentials from DB using master password
            email, saved_password = self.main.credential_manager.get_credentials_with_master(password)

            # Fallback: if credentials haven't been stored in DB yet, try legacy saved creds
            if not email or not saved_password:
                try:
                    email, saved_password = self.main.credential_manager.get_saved_credentials()
                except Exception:
                    pass

            # Show success
            InfoBar.success(
                title=self.main.i18n.tr("master.verified.title"),
                content=self.main.i18n.tr("master.verified.content"),
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
                title=self.main.i18n.tr("master.invalid.title"),
                content=self.main.i18n.tr("master.invalid.content"),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self
            )

            # Clear password field
            self.password_field.clear()
            self.password_field.setFocus(Qt.FocusReason.OtherFocusReason)
