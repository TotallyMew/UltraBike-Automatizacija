"""Account Screen
Manage credentials for PrestaShop and external brand portals.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout
from qfluentwidgets import (
    ScrollArea,
    CardWidget,
    TitleLabel,
    StrongBodyLabel,
    BodyLabel,
    LineEdit,
    PasswordLineEdit,
    PrimaryPushButton,
    InfoBar,
    InfoBarPosition,
)

from GUI_Qt.styles.theme_config import COLORS, FONTS
from qfluentwidgets import isDarkTheme, qconfig


class AccountScreen(QWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main = main_window

        self._ui = {}
        self._init_ui()
        self._load_saved_values()
        self.retranslate_ui()

        # Keep styling consistent when theme changes
        qconfig.themeChangedFinished.connect(self._apply_theme)

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        self.scroll = ScrollArea(self)
        self.scroll.setWidgetResizable(True)
        root.addWidget(self.scroll)

        self.content = QWidget()
        self.content.setObjectName("accountContent")
        self.scroll.setWidget(self.content)

        layout = QVBoxLayout(self.content)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        self._ui["title"] = TitleLabel("")
        layout.addWidget(self._ui["title"])

        # PrestaShop credentials
        self.prestashop_card = CardWidget()
        self.prestashop_card.setObjectName("accountCardPrestaShop")
        p_layout = QVBoxLayout(self.prestashop_card)
        p_layout.setContentsMargins(16, 16, 16, 16)
        p_layout.setSpacing(10)

        self._ui["ps_title"] = StrongBodyLabel("")
        p_layout.addWidget(self._ui["ps_title"])

        self._ui["ps_caption"] = BodyLabel("")
        self._ui["ps_caption"].setWordWrap(True)
        p_layout.addWidget(self._ui["ps_caption"])

        self._ui["ps_email_label"] = BodyLabel("")
        self.ps_email = LineEdit()
        p_layout.addWidget(self._ui["ps_email_label"])
        p_layout.addWidget(self.ps_email)

        self._ui["ps_password_label"] = BodyLabel("")
        self.ps_password = PasswordLineEdit()
        p_layout.addWidget(self._ui["ps_password_label"])
        p_layout.addWidget(self.ps_password)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self._ui["ps_view"] = PrimaryPushButton("")
        self._ui["ps_view"].clicked.connect(self._view_prestashop)
        btn_row.addWidget(self._ui["ps_view"])
        self._ui["ps_save"] = PrimaryPushButton("")
        self._ui["ps_save"].clicked.connect(self._save_prestashop)
        btn_row.addWidget(self._ui["ps_save"])
        p_layout.addLayout(btn_row)

        layout.addWidget(self.prestashop_card)

        # External brand credentials
        self.brand_card = CardWidget()
        self.brand_card.setObjectName("accountCardExternal")
        b_layout = QVBoxLayout(self.brand_card)
        b_layout.setContentsMargins(16, 16, 16, 16)
        b_layout.setSpacing(14)

        self._ui["brand_title"] = StrongBodyLabel("")
        b_layout.addWidget(self._ui["brand_title"])

        self._ui["brand_caption"] = BodyLabel("")
        self._ui["brand_caption"].setWordWrap(True)
        b_layout.addWidget(self._ui["brand_caption"])

        # Basso
        self._ui["basso_section"] = StrongBodyLabel("")
        b_layout.addWidget(self._ui["basso_section"])

        self._ui["basso_user_label"] = BodyLabel("")
        self.basso_username = LineEdit()
        b_layout.addWidget(self._ui["basso_user_label"])
        b_layout.addWidget(self.basso_username)

        self._ui["basso_pass_label"] = BodyLabel("")
        self.basso_password = PasswordLineEdit()
        b_layout.addWidget(self._ui["basso_pass_label"])
        b_layout.addWidget(self.basso_password)

        basso_btn = QHBoxLayout()
        basso_btn.addStretch(1)
        self._ui["basso_view"] = PrimaryPushButton("")
        self._ui["basso_view"].clicked.connect(lambda: self._view_external("basso"))
        basso_btn.addWidget(self._ui["basso_view"])
        self._ui["basso_save"] = PrimaryPushButton("")
        self._ui["basso_save"].clicked.connect(lambda: self._save_external("basso"))
        basso_btn.addWidget(self._ui["basso_save"])
        b_layout.addLayout(basso_btn)

        # Lee Cougan
        self._ui["lc_section"] = StrongBodyLabel("")
        b_layout.addWidget(self._ui["lc_section"])

        self._ui["lc_user_label"] = BodyLabel("")
        self.lc_username = LineEdit()
        b_layout.addWidget(self._ui["lc_user_label"])
        b_layout.addWidget(self.lc_username)

        self._ui["lc_pass_label"] = BodyLabel("")
        self.lc_password = PasswordLineEdit()
        b_layout.addWidget(self._ui["lc_pass_label"])
        b_layout.addWidget(self.lc_password)

        lc_btn = QHBoxLayout()
        lc_btn.addStretch(1)
        self._ui["lc_view"] = PrimaryPushButton("")
        self._ui["lc_view"].clicked.connect(lambda: self._view_external("leecougan"))
        lc_btn.addWidget(self._ui["lc_view"])
        self._ui["lc_save"] = PrimaryPushButton("")
        self._ui["lc_save"].clicked.connect(lambda: self._save_external("leecougan"))
        lc_btn.addWidget(self._ui["lc_save"])
        b_layout.addLayout(lc_btn)

        layout.addWidget(self.brand_card)
        layout.addStretch(1)

        # Apply theme after all widgets exist (important for scroll area + cards)
        self._apply_theme()

    def _apply_theme(self):
        is_dark = isDarkTheme()
        bg_color = COLORS['space_indigo'] if is_dark else COLORS['platinum']
        text_primary = COLORS['text_primary_dark'] if is_dark else COLORS['text_primary_light']
        card_bg = COLORS['bg_dark'] if is_dark else COLORS['bg_light']
        border = COLORS['border_dark'] if is_dark else COLORS['border_light']

        # Screen + scroll must be themed explicitly; otherwise QScrollArea paints a default.
        self.setStyleSheet(f"""
            AccountScreen {{
                background-color: {bg_color};
                font-family: {FONTS['family']};
            }}

            /* Keep all text labels transparent (prevents "text background blocks") */
            QLabel, BodyLabel, StrongBodyLabel, TitleLabel, CaptionLabel {{
                background: transparent;
            }}

            QScrollArea {{
                border: none;
                background: transparent;
            }}
            QScrollArea > QWidget {{
                background: transparent;
            }}
            QWidget#accountContent {{
                background: transparent;
            }}

            /* Card styling scoped by objectName so it doesn't bleed into children */
            CardWidget#accountCardPrestaShop, CardWidget#accountCardExternal {{
                background-color: {card_bg};
                border: 1px solid {border};
                border-radius: 8px;
            }}
        """)

        # Ensure the title uses the correct text color (TitleLabel sometimes inherits poorly).
        try:
            if 'title' in self._ui:
                self._ui['title'].setStyleSheet(f"color: {text_primary};")
        except Exception:
            pass

    def _load_saved_values(self):
        # PrestaShop email can be read without decrypting password
        try:
            self.ps_email.setText(self.main.credential_manager.get_last_saved_email() or "")
        except Exception:
            self.ps_email.setText("")

        # External usernames are stored plaintext; passwords require master to decrypt, but we don't show them
        try:
            self.basso_username.setText(self.main.credential_manager.get_external_username("basso") or "")
        except Exception:
            self.basso_username.setText("")

        try:
            self.lc_username.setText(self.main.credential_manager.get_external_username("leecougan") or "")
        except Exception:
            self.lc_username.setText("")

    def retranslate_ui(self):
        tr = self.main.i18n.tr

        self._ui["title"].setText(tr("account.title"))

        self._ui["ps_title"].setText(tr("account.prestashop.title"))
        self._ui["ps_caption"].setText(tr("account.prestashop.caption"))
        self._ui["ps_email_label"].setText(tr("account.email"))
        self.ps_email.setPlaceholderText(tr("account.email.placeholder"))
        self._ui["ps_password_label"].setText(tr("account.password"))
        self.ps_password.setPlaceholderText(tr("account.password.placeholder"))
        self._ui["ps_view"].setText(tr("account.view"))
        self._ui["ps_save"].setText(tr("account.save"))

        self._ui["brand_title"].setText(tr("account.external.title"))
        self._ui["brand_caption"].setText(tr("account.external.caption"))

        self._ui["basso_section"].setText(tr("account.basso.title"))
        self._ui["basso_user_label"].setText(tr("account.username"))
        self.basso_username.setPlaceholderText(tr("account.username.placeholder"))
        self._ui["basso_pass_label"].setText(tr("account.password"))
        self.basso_password.setPlaceholderText(tr("account.password.placeholder"))
        self._ui["basso_view"].setText(tr("account.view"))
        self._ui["basso_save"].setText(tr("account.save"))

        self._ui["lc_section"].setText(tr("account.leecougan.title"))
        self._ui["lc_user_label"].setText(tr("account.username"))
        self.lc_username.setPlaceholderText(tr("account.username.placeholder"))
        self._ui["lc_pass_label"].setText(tr("account.password"))
        self.lc_password.setPlaceholderText(tr("account.password.placeholder"))
        self._ui["lc_view"].setText(tr("account.view"))
        self._ui["lc_save"].setText(tr("account.save"))

    def _require_master(self):
        master = self.main.get_unlocked_master_password(parent=self)
        if not master:
            InfoBar.error(
                title=self.main.i18n.tr("master.invalid.title"),
                content=self.main.i18n.tr("master.invalid.content"),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3500,
                parent=self,
            )
            return None
        return master

    def _save_prestashop(self):
        email = self.ps_email.text().strip()
        password = self.ps_password.text().strip()

        if not email or not password:
            InfoBar.warning(
                title=self.main.i18n.tr("common.error"),
                content=self.main.i18n.tr("account.missing_fields"),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return

        master = self._require_master()
        if not master:
            return

        try:
            self.main.credential_manager.save_credentials(email, password, master)
            self.ps_password.clear()
            InfoBar.success(
                title=self.main.i18n.tr("common.success"),
                content=self.main.i18n.tr("account.saved"),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=2500,
                parent=self,
            )
        except Exception as ex:
            InfoBar.error(
                title=self.main.i18n.tr("common.error"),
                content=str(ex),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=4000,
                parent=self,
            )

    def _view_prestashop(self):
        master = self._require_master()
        if not master:
            return

        try:
            email, password = self.main.credential_manager.get_credentials_with_master(master)
            if not email or not password:
                InfoBar.warning(
                    title=self.main.i18n.tr("common.error"),
                    content=self.main.i18n.tr("account.not_saved"),
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=3500,
                    parent=self,
                )
                return
            self.ps_email.setText(email)
            self.ps_password.setText(password)
            InfoBar.success(
                title=self.main.i18n.tr("common.success"),
                content=self.main.i18n.tr("account.loaded"),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=2000,
                parent=self,
            )
        except Exception as ex:
            InfoBar.error(
                title=self.main.i18n.tr("common.error"),
                content=str(ex),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=4000,
                parent=self,
            )

    def _save_external(self, service_key: str):
        if service_key == "basso":
            username = self.basso_username.text().strip()
            password = self.basso_password.text().strip()
        else:
            username = self.lc_username.text().strip()
            password = self.lc_password.text().strip()

        if not username or not password:
            InfoBar.warning(
                title=self.main.i18n.tr("common.error"),
                content=self.main.i18n.tr("account.missing_fields"),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return

        master = self._require_master()
        if not master:
            return

        try:
            self.main.credential_manager.save_external_credentials(service_key, username, password, master)
            if service_key == "basso":
                self.basso_password.clear()
            else:
                self.lc_password.clear()

            InfoBar.success(
                title=self.main.i18n.tr("common.success"),
                content=self.main.i18n.tr("account.saved"),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=2500,
                parent=self,
            )
        except Exception as ex:
            InfoBar.error(
                title=self.main.i18n.tr("common.error"),
                content=str(ex),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=4000,
                parent=self,
            )

    def _view_external(self, service_key: str):
        master = self._require_master()
        if not master:
            return

        try:
            username, password = self.main.credential_manager.get_external_credentials_with_master(service_key, master)
            if not username or not password:
                InfoBar.warning(
                    title=self.main.i18n.tr("common.error"),
                    content=self.main.i18n.tr("account.not_saved"),
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=3500,
                    parent=self,
                )
                return

            if service_key == "basso":
                self.basso_username.setText(username)
                self.basso_password.setText(password)
            else:
                self.lc_username.setText(username)
                self.lc_password.setText(password)

            InfoBar.success(
                title=self.main.i18n.tr("common.success"),
                content=self.main.i18n.tr("account.loaded"),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=2000,
                parent=self,
            )
        except Exception as ex:
            InfoBar.error(
                title=self.main.i18n.tr("common.error"),
                content=str(ex),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=4000,
                parent=self,
            )
