"""
Top Bar Widget
Displays user information and logout button
"""

from PySide6.QtWidgets import QWidget, QHBoxLayout, QMenu
from PySide6.QtCore import Qt
from qfluentwidgets import TransparentToolButton, PushButton, FluentIcon, isDarkTheme, qconfig
from GUI_Qt.styles.theme_config import COLORS, SPACING, get_surface_color, get_text_color


class TopBar(QWidget):
    """Top bar with user info and logout button"""

    def __init__(
        self,
        user_text,
        on_reconnect,
        on_logout,
        tr=None,
        parent=None,
        on_account=None,
        on_settings=None,
        on_activity=None,
    ):
        super().__init__(parent)

        self.user_text = user_text
        self.on_reconnect_callback = on_reconnect
        self.on_logout_callback = on_logout
        self.on_account_callback = on_account
        self.on_settings_callback = on_settings
        self.on_activity_callback = on_activity
        self.running_jobs = 0
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
        self.activity_button = PushButton(FluentIcon.SYNC, "", self)
        self.activity_button.setObjectName("activityIndicator")
        self.activity_button.setVisible(False)
        if callable(self.on_activity_callback):
            self.activity_button.clicked.connect(self.on_activity_callback)
        layout.addWidget(self.activity_button)

        # Reconnect browser button
        self.reconnect_button = TransparentToolButton(FluentIcon.SYNC, self)
        self.reconnect_button.setToolTip("")
        self.reconnect_button.setFixedSize(36, 36)
        self.reconnect_button.clicked.connect(self.on_reconnect_callback)
        layout.addWidget(self.reconnect_button)

        self.user_button = PushButton("", self)
        self.user_button.setObjectName("accountMenu")
        self.user_menu = QMenu(self.user_button)
        self.account_action = self.user_menu.addAction("")
        if callable(self.on_account_callback):
            self.account_action.triggered.connect(self.on_account_callback)
        self.settings_action = self.user_menu.addAction("")
        if callable(self.on_settings_callback):
            self.settings_action.triggered.connect(self.on_settings_callback)
        self.user_menu.addSeparator()
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

        bg_color = get_surface_color(is_dark, 'canvas')
        text_primary = COLORS['text_primary_dark'] if is_dark else COLORS['text_primary_light']
        # Use a lighter caption color in dark mode than the standard secondary gray
        text_secondary = get_text_color(is_dark, 'secondary')

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
                background-color: {COLORS['bg_alt_dark'] if is_dark else COLORS['bg_light']};
            }}
            #TopBar PushButton#activityIndicator {{
                color: {text_primary};
                background-color: {COLORS['bg_alt_dark'] if is_dark else COLORS['bg_light']};
                border: 1px solid {COLORS['border_dark'] if is_dark else COLORS['border_light']};
                border-radius: 7px;
                padding: 6px 10px;
            }}
            #TopBar TransparentToolButton {{
                color: {text_secondary};
            }}
            """
        )

    def retranslate_ui(self):
        self.user_button.setText(self.tr("topbar.logged_in", user=self.user_text))
        reconnect = self.tr("topbar.reconnect")
        self.reconnect_button.setToolTip(f"{reconnect} (Ctrl+Shift+R)")
        self.reconnect_button.setAccessibleName(reconnect)
        self.reconnect_button.setAccessibleDescription(self.tr("topbar.reconnect.description"))
        self.user_button.setAccessibleName(self.tr("topbar.account_menu"))
        activity_text = self.tr("topbar.activity", count=self.running_jobs)
        self.activity_button.setText(str(self.running_jobs))
        self.activity_button.setToolTip(activity_text)
        self.activity_button.setAccessibleName(activity_text)
        self.account_action.setText(self.tr("nav.account"))
        self.settings_action.setText(self.tr("nav.settings"))
        self.logout_action.setText(self.tr("topbar.logout"))

    def update_user(self, user_text):
        """Update displayed user text"""
        self.user_text = user_text
        self.user_button.setText(self.tr("topbar.logged_in", user=user_text))

    def update_running_jobs(self, count: int) -> None:
        self.running_jobs = max(0, int(count))
        self.activity_button.setVisible(self.running_jobs > 0)
        self.activity_button.setText(str(self.running_jobs))
        activity_text = self.tr("topbar.activity", count=self.running_jobs)
        self.activity_button.setToolTip(activity_text)
        self.activity_button.setAccessibleName(activity_text)
