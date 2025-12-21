"""
Top Bar Widget
Displays user information and logout button
"""

from PySide6.QtWidgets import QWidget, QHBoxLayout
from PySide6.QtCore import Qt
from qfluentwidgets import BodyLabel, TransparentToolButton, PushButton, FluentIcon, isDarkTheme, qconfig
from GUI_Qt.styles.theme_config import COLORS, SPACING


class TopBar(QWidget):
    """Top bar with user info and logout button"""

    def __init__(self, user_text, on_reconnect, on_logout, tr=None, parent=None):
        super().__init__(parent)

        self.user_text = user_text
        self.on_reconnect_callback = on_reconnect
        self.on_logout_callback = on_logout
        self.tr = tr or (lambda k, **kw: k.format(**kw) if kw else k)

        self._init_ui()

    def _init_ui(self):
        """Initialize UI components"""

        self.setObjectName("TopBar")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(SPACING["xl"], SPACING["md"], SPACING["xl"], SPACING["md"])

        # User email label
        self.user_label = BodyLabel("")
        layout.addWidget(self.user_label)

        # Spacer
        layout.addStretch()

        # Reconnect browser button
        self.reconnect_button = TransparentToolButton(FluentIcon.SYNC, self)
        self.reconnect_button.setToolTip("")
        self.reconnect_button.clicked.connect(self.on_reconnect_callback)
        layout.addWidget(self.reconnect_button)

        # Logout button (more emphasized)
        self.logout_button = PushButton("")
        try:
            self.logout_button.setIcon(FluentIcon.CANCEL)
        except Exception:
            pass
        self.logout_button.clicked.connect(self.on_logout_callback)
        layout.addWidget(self.logout_button)

        self.setLayout(layout)

        self._apply_theme()
        qconfig.themeChangedFinished.connect(self._apply_theme)
        self.retranslate_ui()

    def _apply_theme(self):
        is_dark = isDarkTheme()

        bg_color = COLORS['space_indigo'] if is_dark else COLORS['platinum']
        text_primary = COLORS['text_primary_dark'] if is_dark else COLORS['text_primary_light']
        # Use a lighter caption color in dark mode than the standard secondary gray
        text_secondary = COLORS['lavender_grey'] if is_dark else COLORS['text_secondary']

        self.setStyleSheet(
            f"""
            #TopBar {{
                background-color: {bg_color};
            }}
            #TopBar BodyLabel {{
                color: {text_primary};
            }}
            #TopBar TransparentToolButton {{
                color: {text_secondary};
            }}
            """
        )

    def retranslate_ui(self):
        self.user_label.setText(self.tr("topbar.logged_in", user=self.user_text))
        self.reconnect_button.setToolTip(self.tr("topbar.reconnect"))
        self.logout_button.setText(self.tr("topbar.logout"))

    def update_user(self, user_text):
        """Update displayed user text"""
        self.user_text = user_text
        self.user_label.setText(self.tr("topbar.logged_in", user=user_text))
