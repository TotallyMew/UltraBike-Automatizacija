"""
Top Bar Widget
Displays user information and logout button
"""

from PySide6.QtWidgets import QWidget, QHBoxLayout
from PySide6.QtCore import Qt
from qfluentwidgets import BodyLabel, TransparentToolButton, FluentIcon


class TopBar(QWidget):
    """Top bar with user info and logout button"""

    def __init__(self, user_email, on_logout, parent=None):
        super().__init__(parent)

        self.user_email = user_email
        self.on_logout_callback = on_logout

        self._init_ui()

    def _init_ui(self):
        """Initialize UI components"""

        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 12, 24, 12)

        # User email label
        self.user_label = BodyLabel(f"Prisijungęs: {self.user_email}")
        layout.addWidget(self.user_label)

        # Spacer
        layout.addStretch()

        # Logout button
        self.logout_button = TransparentToolButton(FluentIcon.CANCEL, self)
        self.logout_button.setToolTip("Atsijungti")
        self.logout_button.clicked.connect(self.on_logout_callback)
        layout.addWidget(self.logout_button)

        self.setLayout(layout)

    def update_user(self, email):
        """Update displayed user email"""
        self.user_email = email
        self.user_label.setText(f"Prisijungęs: {email}")
