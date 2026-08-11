"""
Top Bar Widget
Displays user information and logout button
"""

from PySide6.QtWidgets import QWidget, QHBoxLayout, QMenu
from PySide6.QtCore import Qt
from qfluentwidgets import TransparentToolButton, PushButton, FluentIcon, isDarkTheme, qconfig
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

        # Secondary app controls stay together on the right.
        layout.addStretch()

        # Reconnect browser button
        self.reconnect_button = TransparentToolButton(FluentIcon.SYNC, self)
        self.reconnect_button.setToolTip("")
        self.reconnect_button.clicked.connect(self.on_reconnect_callback)
        layout.addWidget(self.reconnect_button)

        self.user_button = PushButton("")
        self.user_button.setObjectName("accountMenu")
        self.user_menu = QMenu(self.user_button)
        self.logout_action = self.user_menu.addAction("")
        self.logout_action.triggered.connect(self.on_logout_callback)
        self.user_button.setMenu(self.user_menu)
        layout.addWidget(self.user_button)

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
            #TopBar PushButton#accountMenu {{
                color: {text_primary};
                background: transparent;
                border: 1px solid {COLORS['border_dark'] if is_dark else COLORS['border_light']};
                border-radius: 7px;
                padding: 6px 12px;
            }}
            #TopBar PushButton#accountMenu:hover {{
                background-color: {'#303447' if is_dark else '#FFFFFF'};
            }}
            #TopBar TransparentToolButton {{
                color: {text_secondary};
            }}
            """
        )

    def retranslate_ui(self):
        self.user_button.setText(self.tr("topbar.logged_in", user=self.user_text))
        self.reconnect_button.setToolTip(self.tr("topbar.reconnect"))
        self.logout_action.setText(self.tr("topbar.logout"))

    def update_user(self, user_text):
        """Update displayed user text"""
        self.user_text = user_text
        self.user_button.setText(self.tr("topbar.logged_in", user=user_text))
