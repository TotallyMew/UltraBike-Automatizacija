"""
Settings Screen
Application settings with Fluent Design System
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFileDialog, QSizePolicy
from PySide6.QtCore import Qt, QThread, Signal
from qfluentwidgets import (
    CardWidget, TitleLabel, StrongBodyLabel, BodyLabel, CaptionLabel,
    ComboBox, SwitchButton, FluentIcon, InfoBar, InfoBarPosition,
    isDarkTheme, setTheme, Theme, PushButton, LineEdit, ScrollArea,
    PrimaryPushButton, TransparentToolButton, qconfig
)
from GUI_Qt.widgets.ResponsiveWidget import ResponsiveWidget
from GUI_Qt.styles.theme_config import COLORS, FONTS, RADII, SIZES, rgba_from_hex
from GUI_Qt.styles.screen_theme import (
    PAGE_MARGINS, PAGE_SPACING, CARD_MARGINS, CARD_SPACING, ICON_TEXT_GAP, FOOTER_MARGINS,
    enforce_transparent_labels, apply_screen_theme, get_responsive_margins, get_responsive_spacing
)
from GUI_Qt.i18n import normalize_language, translate
from GUI_Qt.components.accessibility import KeyboardNavigationMixin


class _PrestaShopConnectionTestWorker(QThread):
    done = Signal(bool, str)  # ok, error_details

    def __init__(self, *, base_url: str, api_key: str, logger=None):
        super().__init__()
        self._base_url = base_url
        self._api_key = api_key
        self._logger = logger

    def run(self):
        from Managers.PrestaShopAPI import PrestaShopAPI

        api = PrestaShopAPI(self._base_url, self._api_key, logger=self._logger)
        ok = False
        try:
            ok = bool(api.test_connection())
        except Exception:
            ok = False

        if ok:
            self.done.emit(True, "")
            return

        details = ""
        try:
            details = (api.last_error_summary() or "").strip()
        except Exception:
            details = ""
        self.done.emit(False, details)


class SettingsScreen(ResponsiveWidget, KeyboardNavigationMixin):
    """Settings screen with language and theme options"""

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main = main_window
        self._loading = True  # Flag to prevent notifications during initial load
        self._is_dirty = False  # Track unsaved changes

        # UI elements that need retranslation
        self._ui = {}

        # Preview-only state (applies only inside this screen until Save)
        self._preview_lang_code = (
            self.main.i18n.language.code if hasattr(self.main, "i18n") else "en"
        )

        # Store references for responsive UI
        self.scroll = None
        self.content_widget = None
        self._preview_theme_is_dark = isDarkTheme()

        # Store references for theme updates
        self.scroll = None
        self.content_widget = None

        self._init_ui()
        self._load_settings()
        self._loading = False  # Re-enable notifications after load

        # Setup keyboard shortcuts for accessibility
        self.setup_keyboard_shortcuts(
            save_callback=self._save_all_settings,
            cancel_callback=self._cancel_changes
        )

        # Connect to theme change signal
        qconfig.themeChangedFinished.connect(self._on_theme_changed)

        # Connect to language change signal
        if hasattr(self.main, "i18n"):
            self.main.i18n.languageChanged.connect(lambda _c: self._sync_preview_from_saved_and_retranslate())

    def showEvent(self, event):
        super().showEvent(event)
        if self._loading:
            return
        # If user navigated away without saving, reset preview state.
        self._sync_preview_from_saved_and_retranslate()

    def hideEvent(self, event):
        super().hideEvent(event)
        if self._loading:
            return
        # Leaving Settings without saving should not leak preview state.
        self._revert_preview_to_saved()

    def _get_saved_language_display(self) -> str:
        language = self.main.settings.get('language', 'English')
        if language in ("en", "lt"):
            return "English" if language == "en" else "Lithuanian"
        if language not in ("English", "Lithuanian"):
            return "English"
        return language

    def _get_saved_theme_is_dark(self) -> bool:
        return self.main.settings.get('theme', 'light') == 'dark'

    def _sync_preview_from_saved_and_retranslate(self) -> None:
        """Sync preview state + controls from saved settings.

        This is used when entering Settings, or after global language/theme changes.
        """
        try:
            saved_language = self._get_saved_language_display()
            self._preview_lang_code = normalize_language(saved_language, self._preview_lang_code)

            self._loading = True
            try:
                idx = self.language_combo.findText(saved_language)
                if idx >= 0:
                    self.language_combo.setCurrentIndex(idx)
                else:
                    self.language_combo.setCurrentText(saved_language)

                saved_is_dark = self._get_saved_theme_is_dark()
                self.theme_switch.setChecked(saved_is_dark)
                self._preview_theme_is_dark = saved_is_dark
            finally:
                self._loading = False

            # Ensure the Settings screen itself is in the saved language.
            self.retranslate_ui(preview=True)

            # Ensure app chrome matches preview language when Settings is open.
            if hasattr(self.main, "apply_language_preview"):
                try:
                    self.main.apply_language_preview(self._preview_lang_code)
                except Exception:
                    pass

            # Ensure the Settings screen styling matches the currently-applied global theme.
            self._on_theme_changed()
        except Exception:
            pass

    def _apply_global_theme(self, is_dark: bool) -> None:
        """Apply qfluentwidgets theme globally (used for preview + saved apply)."""
        try:
            # Only flip if needed to avoid extra signals.
            if is_dark == isDarkTheme():
                return

            setTheme(Theme.DARK if is_dark else Theme.LIGHT)

            # Keep global stylesheet + container backgrounds consistent.
            try:
                from GUI_Qt.styles.global_styles import get_global_stylesheet
                self.main.setStyleSheet(get_global_stylesheet())
            except Exception:
                pass

            try:
                self.main.update_container_backgrounds()
            except Exception:
                pass

            # Some custom widgets need manual theme refresh.
            if getattr(self.main, "batch_upload_screen", None):
                try:
                    self.main.batch_upload_screen._update_table_theme()
                except Exception:
                    pass
        except Exception:
            pass

    def _revert_preview_to_saved(self) -> None:
        """Revert any preview-only state back to saved global settings."""
        try:
            saved_is_dark = self._get_saved_theme_is_dark()
            self._apply_global_theme(saved_is_dark)
            self._preview_theme_is_dark = saved_is_dark

            saved_language = self._get_saved_language_display()
            self._preview_lang_code = normalize_language(saved_language, self._preview_lang_code)

            self._loading = True
            try:
                idx = self.language_combo.findText(saved_language)
                if idx >= 0:
                    self.language_combo.setCurrentIndex(idx)
                self.theme_switch.setChecked(saved_is_dark)
            finally:
                self._loading = False

            self.retranslate_ui(preview=True)
            self._on_theme_changed()

            # Restore chrome language (undo preview) when leaving Settings.
            if hasattr(self.main, "clear_language_preview"):
                try:
                    self.main.clear_language_preview()
                except Exception:
                    pass
        except Exception:
            pass

    def _init_ui(self):
        """Initialize UI"""
        # Main layout
        self.setAutoFillBackground(True)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Apply background color based on theme - using our color scheme
        is_dark = self._preview_theme_is_dark
        bg_color = COLORS['space_indigo'] if is_dark else COLORS['platinum']
        text_primary = COLORS['text_primary_dark'] if is_dark else COLORS['text_primary_light']
        text_caption = COLORS['lavender_grey'] if is_dark else COLORS['text_secondary']
        self.setStyleSheet(
            f"""
            SettingsScreen {{
                background-color: {bg_color};
            }}
            SettingsScreen TitleLabel,
            SettingsScreen StrongBodyLabel,
            SettingsScreen BodyLabel {{
                color: {text_primary};
            }}
            SettingsScreen CaptionLabel {{
                color: {text_caption};
            }}
            """
        )

        # Scroll area for all settings
        self.scroll = ScrollArea()

        # Apply theme before building content
        apply_screen_theme(
            self,
            "SettingsScreen",
            scroll=self.scroll
        )
        self.scroll.setWidgetResizable(True)
        self._update_scroll_style()

        # Content widget inside scroll
        self.content_widget = QWidget()
        self.content_widget.setObjectName("contentWidget")
        self.content_widget.setStyleSheet(f"#contentWidget {{ background-color: {bg_color}; }}")
        layout = QVBoxLayout(self.content_widget)
        layout.setContentsMargins(*PAGE_MARGINS)
        layout.setSpacing(PAGE_SPACING)

        # Header
        header = QHBoxLayout()

        title_container = QHBoxLayout()
        title_container.setSpacing(ICON_TEXT_GAP)

        title_icon = TransparentToolButton(FluentIcon.SETTING, self)
        title_icon.setFixedSize(SIZES['icon_lg'], SIZES['icon_lg'])
        title_icon.setEnabled(False)

        title_label = TitleLabel(translate(self._preview_lang_code, "settings.title"))
        self._ui["title_label"] = title_label

        title_container.addWidget(title_icon)
        title_container.addWidget(title_label)

        header.addLayout(title_container)
        header.addStretch()
        layout.addLayout(header)

        # Settings should NOT show text background bars.
        enforce_transparent_labels(self)

        # === LANGUAGE CARD ===
        language_card = CardWidget()
        language_card.setBorderRadius(RADII['md'])
        language_layout = QVBoxLayout(language_card)
        language_layout.setContentsMargins(*CARD_MARGINS)
        language_layout.setSpacing(CARD_SPACING)

        # Language header
        lang_header = QHBoxLayout()
        from qfluentwidgets import IconWidget
        lang_icon = IconWidget(FluentIcon.GLOBE)
        lang_icon.setFixedSize(SIZES['icon_md'], SIZES['icon_md'])
        lang_title = StrongBodyLabel(translate(self._preview_lang_code, "settings.language.title"))
        self._ui["lang_title"] = lang_title
        lang_title.setStyleSheet(f"font-size: {FONTS['size_subtitle_2']};")
        lang_header.addWidget(lang_icon)
        lang_header.addSpacing(ICON_TEXT_GAP)
        lang_header.addWidget(lang_title)
        lang_header.addStretch()
        language_layout.addLayout(lang_header)

        # Language description
        lang_desc = CaptionLabel(translate(self._preview_lang_code, "settings.language.desc"))
        self._ui["lang_desc"] = lang_desc
        language_layout.addWidget(lang_desc)

        # Language selector
        lang_selector_layout = QHBoxLayout()
        lang_label = BodyLabel(translate(self._preview_lang_code, "settings.language.label"))
        self._ui["lang_label"] = lang_label
        lang_label.setMinimumWidth(SIZES['label_min_width'])

        self.language_combo = ComboBox()
        # NOTE: QFluentWidgets ComboBox placeholder behavior can mask index 0.
        # Insert a dummy first item so real languages are not at index 0.
        # We keep it as a visible (localized) placeholder option.
        self.language_combo.addItem(translate(self._preview_lang_code, "settings.language.placeholder"))
        self.language_combo.addItems(["English", "Lithuanian"])
        self.language_combo.setPlaceholderText("")
        self.language_combo.setMinimumWidth(SIZES['field_min_width_md'])
        self.language_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.language_combo.currentTextChanged.connect(self._on_language_change)
        # Accessibility
        self.language_combo.setAccessibleName(translate(self._preview_lang_code, "settings.language.label"))
        self.language_combo.setAccessibleDescription(translate(self._preview_lang_code, "settings.language.desc"))

        lang_selector_layout.addWidget(lang_label)
        lang_selector_layout.addWidget(self.language_combo)
        lang_selector_layout.addStretch()
        language_layout.addLayout(lang_selector_layout)

        layout.addWidget(language_card)

        # === BROWSER CARD ===
        browser_card = CardWidget()
        browser_card.setBorderRadius(RADII['md'])
        browser_layout = QVBoxLayout(browser_card)
        browser_layout.setContentsMargins(*CARD_MARGINS)
        browser_layout.setSpacing(CARD_SPACING)

        # Browser header
        browser_header = QHBoxLayout()
        browser_icon = IconWidget(FluentIcon.GLOBE)
        browser_icon.setFixedSize(SIZES['icon_md'], SIZES['icon_md'])
        browser_title = StrongBodyLabel(translate(self._preview_lang_code, "settings.browser.title"))
        self._ui["browser_title"] = browser_title
        browser_title.setStyleSheet(f"font-size: {FONTS['size_subtitle_2']};")
        browser_header.addWidget(browser_icon)
        browser_header.addSpacing(ICON_TEXT_GAP)
        browser_header.addWidget(browser_title)
        browser_header.addStretch()
        browser_layout.addLayout(browser_header)

        # Browser description
        browser_desc = CaptionLabel(translate(self._preview_lang_code, "settings.browser.desc"))
        self._ui["browser_desc"] = browser_desc
        browser_layout.addWidget(browser_desc)

        # Browser selector
        browser_selector_layout = QHBoxLayout()
        browser_label = BodyLabel(translate(self._preview_lang_code, "settings.browser.label"))
        self._ui["browser_label"] = browser_label
        browser_label.setMinimumWidth(SIZES['label_min_width'])

        self.browser_combo = ComboBox()
        self.browser_combo.addItems(["Chrome", "Firefox", "Edge"])
        self.browser_combo.setMinimumWidth(SIZES['field_min_width_md'])
        self.browser_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        browser_selector_layout.addWidget(browser_label)
        browser_selector_layout.addWidget(self.browser_combo)
        browser_selector_layout.addStretch()
        browser_layout.addLayout(browser_selector_layout)

        layout.addWidget(browser_card)

        # === FEATURES CARD ===
        features_card = CardWidget()
        features_card.setBorderRadius(RADII['md'])
        features_layout = QVBoxLayout(features_card)
        features_layout.setContentsMargins(*CARD_MARGINS)
        features_layout.setSpacing(CARD_SPACING)

        # Features header
        features_header = QHBoxLayout()
        features_icon = IconWidget(FluentIcon.SETTING)
        features_icon.setFixedSize(SIZES['icon_md'], SIZES['icon_md'])
        features_title = StrongBodyLabel(translate(self._preview_lang_code, "settings.features.title"))
        self._ui["features_title"] = features_title
        features_title.setStyleSheet(f"font-size: {FONTS['size_subtitle_2']};")
        features_header.addWidget(features_icon)
        features_header.addSpacing(ICON_TEXT_GAP)
        features_header.addWidget(features_title)
        features_header.addStretch()
        features_layout.addLayout(features_header)

        # Download images toggle
        download_images_layout = QHBoxLayout()
        download_images_info = QVBoxLayout()
        download_images_label = BodyLabel(translate(self._preview_lang_code, "settings.features.download.title"))
        self._ui["download_images_label"] = download_images_label
        download_images_label.setStyleSheet("font-weight: 500;")
        download_images_sublabel = CaptionLabel(translate(self._preview_lang_code, "settings.features.download.desc"))
        self._ui["download_images_sublabel"] = download_images_sublabel
        download_images_info.addWidget(download_images_label)
        download_images_info.addWidget(download_images_sublabel)

        self.download_images_switch = SwitchButton()

        download_images_layout.addLayout(download_images_info)
        download_images_layout.addStretch()
        download_images_layout.addWidget(self.download_images_switch)
        features_layout.addLayout(download_images_layout)

        # Auto-save toggle
        auto_save_layout = QHBoxLayout()
        auto_save_info = QVBoxLayout()
        auto_save_label = BodyLabel(translate(self._preview_lang_code, "settings.features.autosave.title"))
        self._ui["auto_save_label"] = auto_save_label
        auto_save_label.setStyleSheet("font-weight: 500;")
        auto_save_sublabel = CaptionLabel(translate(self._preview_lang_code, "settings.features.autosave.desc"))
        self._ui["auto_save_sublabel"] = auto_save_sublabel
        auto_save_info.addWidget(auto_save_label)
        auto_save_info.addWidget(auto_save_sublabel)

        self.auto_save_switch = SwitchButton()

        auto_save_layout.addLayout(auto_save_info)
        auto_save_layout.addStretch()
        auto_save_layout.addWidget(self.auto_save_switch)
        features_layout.addLayout(auto_save_layout)

        # Auto-delete pabaigta*.txt toggle
        auto_delete_layout = QHBoxLayout()
        auto_delete_info = QVBoxLayout()
        auto_delete_label = BodyLabel(translate(self._preview_lang_code, "settings.features.auto_delete_pabaigta.title"))
        self._ui["auto_delete_label"] = auto_delete_label
        auto_delete_label.setStyleSheet("font-weight: 500;")
        auto_delete_sublabel = CaptionLabel(translate(self._preview_lang_code, "settings.features.auto_delete_pabaigta.desc"))
        self._ui["auto_delete_sublabel"] = auto_delete_sublabel
        auto_delete_info.addWidget(auto_delete_label)
        auto_delete_info.addWidget(auto_delete_sublabel)

        self.auto_delete_pabaigta_switch = SwitchButton()

        auto_delete_layout.addLayout(auto_delete_info)
        auto_delete_layout.addStretch()
        auto_delete_layout.addWidget(self.auto_delete_pabaigta_switch)
        features_layout.addLayout(auto_delete_layout)

        # Multi-session toggle
        multi_session_layout = QHBoxLayout()
        multi_session_info = QVBoxLayout()
        multi_session_label = BodyLabel(translate(self._preview_lang_code, "settings.features.multi_session.title"))
        self._ui["multi_session_label"] = multi_session_label
        multi_session_label.setStyleSheet("font-weight: 500;")
        multi_session_sublabel = CaptionLabel(translate(self._preview_lang_code, "settings.features.multi_session.desc"))
        self._ui["multi_session_sublabel"] = multi_session_sublabel
        multi_session_info.addWidget(multi_session_label)
        multi_session_info.addWidget(multi_session_sublabel)

        self.multi_session_switch = SwitchButton()
        try:
            self.multi_session_switch.checkedChanged.connect(self._on_multi_session_change)
        except Exception:
            pass

        multi_session_layout.addLayout(multi_session_info)
        multi_session_layout.addStretch()
        multi_session_layout.addWidget(self.multi_session_switch)
        features_layout.addLayout(multi_session_layout)

        # Browser count (used when multi-session is enabled)
        browser_count_layout = QHBoxLayout()
        browser_count_info = QVBoxLayout()
        browser_count_label = BodyLabel(translate(self._preview_lang_code, "settings.features.browser_count.label"))
        self._ui["browser_count_label"] = browser_count_label
        browser_count_label.setStyleSheet("font-weight: 500;")
        browser_count_caption = CaptionLabel(translate(self._preview_lang_code, "settings.features.browser_count.caption"))
        self._ui["browser_count_caption"] = browser_count_caption
        browser_count_info.addWidget(browser_count_label)
        browser_count_info.addWidget(browser_count_caption)

        self.browser_count_combo = ComboBox()
        self.browser_count_combo.addItems(["2", "3", "4"])
        self.browser_count_combo.setMinimumWidth(SIZES['field_min_width_md'])
        self.browser_count_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        browser_count_layout.addLayout(browser_count_info)
        browser_count_layout.addStretch()
        browser_count_layout.addWidget(self.browser_count_combo)
        features_layout.addLayout(browser_count_layout)

        # === PRESTASHOP API (optional) ===
        prestashop_api_header = QHBoxLayout()
        prestashop_api_icon = IconWidget(FluentIcon.GLOBE)
        prestashop_api_icon.setFixedSize(SIZES['icon_md'], SIZES['icon_md'])
        prestashop_api_title = StrongBodyLabel(translate(self._preview_lang_code, "settings.features.prestashop_api.title"))
        self._ui["prestashop_api_title"] = prestashop_api_title
        prestashop_api_title.setStyleSheet(f"font-size: {FONTS['size_body_lg']};")
        prestashop_api_header.addWidget(prestashop_api_icon)
        prestashop_api_header.addSpacing(ICON_TEXT_GAP)
        prestashop_api_header.addWidget(prestashop_api_title)
        prestashop_api_header.addStretch()
        features_layout.addSpacing(PAGE_SPACING)
        features_layout.addLayout(prestashop_api_header)

        prestashop_api_desc = CaptionLabel(translate(self._preview_lang_code, "settings.features.prestashop_api.desc"))
        self._ui["prestashop_api_desc"] = prestashop_api_desc
        features_layout.addWidget(prestashop_api_desc)

        # Enable toggle
        prestashop_enable_layout = QHBoxLayout()
        prestashop_enable_info = QVBoxLayout()
        prestashop_enable_label = BodyLabel(translate(self._preview_lang_code, "settings.features.prestashop_api.enable"))
        self._ui["prestashop_enable_label"] = prestashop_enable_label
        prestashop_enable_label.setStyleSheet("font-weight: 500;")
        prestashop_enable_info.addWidget(prestashop_enable_label)

        self.prestashop_api_switch = SwitchButton()
        prestashop_enable_layout.addLayout(prestashop_enable_info)
        prestashop_enable_layout.addStretch()
        prestashop_enable_layout.addWidget(self.prestashop_api_switch)
        features_layout.addLayout(prestashop_enable_layout)

        # URL
        prestashop_url_layout = QHBoxLayout()
        prestashop_url_info = QVBoxLayout()
        prestashop_url_label = BodyLabel(translate(self._preview_lang_code, "settings.features.prestashop_url.label"))
        self._ui["prestashop_url_label"] = prestashop_url_label
        prestashop_url_label.setStyleSheet("font-weight: 500;")
        prestashop_url_caption = CaptionLabel(translate(self._preview_lang_code, "settings.features.prestashop_url.caption"))
        self._ui["prestashop_url_caption"] = prestashop_url_caption
        prestashop_url_info.addWidget(prestashop_url_label)
        prestashop_url_info.addWidget(prestashop_url_caption)

        self.prestashop_url_field = LineEdit()
        self.prestashop_url_field.setMinimumWidth(SIZES['field_min_width_lg'])
        self.prestashop_url_field.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        prestashop_url_layout.addLayout(prestashop_url_info)
        prestashop_url_layout.addStretch()
        prestashop_url_layout.addWidget(self.prestashop_url_field)
        features_layout.addLayout(prestashop_url_layout)

        # API key
        prestashop_key_layout = QHBoxLayout()
        prestashop_key_info = QVBoxLayout()
        prestashop_key_label = BodyLabel(translate(self._preview_lang_code, "settings.features.prestashop_api_key.label"))
        self._ui["prestashop_key_label"] = prestashop_key_label
        prestashop_key_label.setStyleSheet("font-weight: 500;")
        prestashop_key_caption = CaptionLabel(translate(self._preview_lang_code, "settings.features.prestashop_api_key.caption"))
        self._ui["prestashop_key_caption"] = prestashop_key_caption
        prestashop_key_info.addWidget(prestashop_key_label)
        prestashop_key_info.addWidget(prestashop_key_caption)

        self.prestashop_key_field = LineEdit()
        try:
            from PySide6.QtWidgets import QLineEdit as _QLineEdit
            self.prestashop_key_field.setEchoMode(_QLineEdit.EchoMode.Password)
        except Exception:
            pass
        self.prestashop_key_field.setMinimumWidth(SIZES['field_min_width_lg'])
        self.prestashop_key_field.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        prestashop_key_layout.addLayout(prestashop_key_info)
        prestashop_key_layout.addStretch()
        prestashop_key_layout.addWidget(self.prestashop_key_field)
        features_layout.addLayout(prestashop_key_layout)

        # Test connection button
        prestashop_test_layout = QHBoxLayout()
        prestashop_test_layout.addStretch()
        self.prestashop_test_btn = PushButton(
            translate(self._preview_lang_code, "settings.features.prestashop_api.test")
        )
        self._ui["prestashop_test_btn"] = self.prestashop_test_btn
        self.prestashop_test_btn.clicked.connect(self._on_test_prestashop_connection)
        prestashop_test_layout.addWidget(self.prestashop_test_btn)
        features_layout.addLayout(prestashop_test_layout)

        layout.addWidget(features_card)

        # === THEME CARD ===
        theme_card = CardWidget()
        theme_card.setBorderRadius(RADII['md'])
        theme_layout = QVBoxLayout(theme_card)
        theme_layout.setContentsMargins(*CARD_MARGINS)
        theme_layout.setSpacing(CARD_SPACING)

        # Theme header
        theme_header = QHBoxLayout()
        theme_icon = IconWidget(FluentIcon.BRUSH)
        theme_icon.setFixedSize(SIZES['icon_md'], SIZES['icon_md'])
        theme_title = StrongBodyLabel(translate(self._preview_lang_code, "settings.appearance.title"))
        self._ui["theme_title"] = theme_title
        theme_title.setStyleSheet(f"font-size: {FONTS['size_subtitle_2']};")
        theme_header.addWidget(theme_icon)
        theme_header.addSpacing(ICON_TEXT_GAP)
        theme_header.addWidget(theme_title)
        theme_header.addStretch()
        theme_layout.addLayout(theme_header)

        # Theme description
        theme_desc = CaptionLabel(translate(self._preview_lang_code, "settings.appearance.desc"))
        self._ui["theme_desc"] = theme_desc
        theme_layout.addWidget(theme_desc)

        # Theme toggle
        theme_toggle_layout = QHBoxLayout()

        theme_info_layout = QVBoxLayout()
        theme_label = BodyLabel(translate(self._preview_lang_code, "settings.appearance.dark.title"))
        self._ui["theme_label"] = theme_label
        theme_label.setStyleSheet("font-weight: 500;")
        theme_sublabel = CaptionLabel(translate(self._preview_lang_code, "settings.appearance.dark.desc"))
        self._ui["theme_sublabel"] = theme_sublabel
        theme_info_layout.addWidget(theme_label)
        theme_info_layout.addWidget(theme_sublabel)

        self.theme_switch = SwitchButton()
        self.theme_switch.setChecked(isDarkTheme())
        self.theme_switch.checkedChanged.connect(self._on_theme_change)
        # Accessibility
        self.theme_switch.setAccessibleName(translate(self._preview_lang_code, "settings.appearance.dark.title"))
        self.theme_switch.setAccessibleDescription(translate(self._preview_lang_code, "settings.appearance.dark.desc"))

        theme_toggle_layout.addLayout(theme_info_layout)
        theme_toggle_layout.addStretch()
        theme_toggle_layout.addWidget(self.theme_switch)
        theme_layout.addLayout(theme_toggle_layout)

        layout.addWidget(theme_card)

        # === PATHS CARD ===
        paths_card = CardWidget()
        paths_card.setBorderRadius(RADII['md'])
        paths_layout = QVBoxLayout(paths_card)
        paths_layout.setContentsMargins(*CARD_MARGINS)
        paths_layout.setSpacing(CARD_SPACING)

        # Paths header
        paths_header = QHBoxLayout()
        paths_icon = IconWidget(FluentIcon.FOLDER)
        paths_icon.setFixedSize(SIZES['icon_md'], SIZES['icon_md'])
        paths_title = StrongBodyLabel(translate(self._preview_lang_code, "settings.paths.title"))
        self._ui["paths_title"] = paths_title
        paths_title.setStyleSheet(f"font-size: {FONTS['size_subtitle_2']};")
        paths_header.addWidget(paths_icon)
        paths_header.addSpacing(ICON_TEXT_GAP)
        paths_header.addWidget(paths_title)
        paths_header.addStretch()
        paths_layout.addLayout(paths_header)

        # Paths description
        paths_desc = CaptionLabel(translate(self._preview_lang_code, "settings.paths.desc"))
        self._ui["paths_desc"] = paths_desc
        paths_layout.addWidget(paths_desc)

        # KROSS path
        kross_path_layout = QVBoxLayout()
        kross_label = BodyLabel(translate(self._preview_lang_code, "settings.paths.kross.title"))
        self._ui["kross_label"] = kross_label
        kross_label.setStyleSheet("font-weight: 500;")

        kross_input_layout = QHBoxLayout()
        self.kross_path_field = LineEdit()
        self.kross_path_field.setReadOnly(True)
        self.kross_path_field.setPlaceholderText(translate(self._preview_lang_code, "settings.paths.placeholder"))

        kross_browse_btn = PushButton(translate(self._preview_lang_code, "settings.paths.browse"))
        self._ui["kross_browse_btn"] = kross_browse_btn
        kross_browse_btn.setIcon(FluentIcon.FOLDER)
        kross_browse_btn.setFixedWidth(SIZES['browse_button_width'])
        kross_browse_btn.clicked.connect(lambda: self._browse_folder('kross_download_path', self.kross_path_field))

        kross_input_layout.addWidget(self.kross_path_field)
        kross_input_layout.addWidget(kross_browse_btn)

        kross_path_layout.addWidget(kross_label)
        kross_path_layout.addLayout(kross_input_layout)
        paths_layout.addLayout(kross_path_layout)

        # Repository path
        repo_path_layout = QVBoxLayout()
        repo_label = BodyLabel(translate(self._preview_lang_code, "settings.paths.repo.title"))
        self._ui["repo_label"] = repo_label
        repo_label.setStyleSheet("font-weight: 500;")

        repo_input_layout = QHBoxLayout()
        self.repo_path_field = LineEdit()
        self.repo_path_field.setReadOnly(True)
        self.repo_path_field.setPlaceholderText(translate(self._preview_lang_code, "settings.paths.placeholder"))

        repo_browse_btn = PushButton(translate(self._preview_lang_code, "settings.paths.browse"))
        self._ui["repo_browse_btn"] = repo_browse_btn
        repo_browse_btn.setIcon(FluentIcon.FOLDER)
        repo_browse_btn.setFixedWidth(SIZES['browse_button_width'])
        repo_browse_btn.clicked.connect(lambda: self._browse_folder('repository_path', self.repo_path_field))

        repo_input_layout.addWidget(self.repo_path_field)
        repo_input_layout.addWidget(repo_browse_btn)

        repo_path_layout.addWidget(repo_label)
        repo_path_layout.addLayout(repo_input_layout)
        paths_layout.addLayout(repo_path_layout)

        layout.addWidget(paths_card)

        # === INFO CARD ===
        info_card = CardWidget()
        info_card.setBorderRadius(RADII['md'])
        info_layout = QVBoxLayout(info_card)
        info_layout.setContentsMargins(*CARD_MARGINS)
        info_layout.setSpacing(CARD_SPACING)

        info_title = StrongBodyLabel(translate(self._preview_lang_code, "settings.about.title"))
        self._ui["info_title"] = info_title
        info_title.setStyleSheet(f"font-size: {FONTS['size_subtitle_2']};")
        info_layout.addWidget(info_title)

        app_name = BodyLabel(translate(self._preview_lang_code, "settings.about.app"))
        self._ui["app_name"] = app_name
        app_name.setStyleSheet(f"color: {COLORS['lavender_grey']}; background: transparent; background-color: transparent;")
        info_layout.addWidget(app_name)

        layout.addWidget(info_card)

        # Push everything to top
        layout.addStretch()

        # Set scroll widget and add to main layout
        self.scroll.setWidget(self.content_widget)
        main_layout.addWidget(self.scroll)

        # === SAVE/CANCEL BUTTONS (Fixed at bottom) ===
        button_container = QWidget()
        button_layout = QHBoxLayout(button_container)
        button_layout.setContentsMargins(*FOOTER_MARGINS)
        button_layout.addStretch()

        # Cancel button
        cancel_btn = PushButton(translate(self._preview_lang_code, "settings.cancel"))
        self._ui["cancel_btn"] = cancel_btn
        cancel_btn.setIcon(FluentIcon.CANCEL)
        cancel_btn.setFixedHeight(SIZES['button_height'])
        cancel_btn.clicked.connect(self._cancel_changes)
        cancel_btn.setEnabled(False)  # Disabled until changes are made
        # Accessibility
        cancel_btn.setAccessibleName(translate(self._preview_lang_code, "shortcuts.cancel"))
        cancel_btn.setAccessibleDescription("Discard all unsaved changes and revert to saved settings")

        # Save button
        save_btn = PrimaryPushButton(translate(self._preview_lang_code, "settings.save"))
        self._ui["save_btn"] = save_btn
        save_btn.setIcon(FluentIcon.SAVE)
        save_btn.setFixedHeight(SIZES['button_height'])
        save_btn.clicked.connect(self._save_all_settings)
        save_btn.setEnabled(False)  # Disabled until changes are made
        # Accessibility
        save_btn.setAccessibleName(translate(self._preview_lang_code, "shortcuts.save"))
        save_btn.setAccessibleDescription("Save all settings changes")

        button_layout.addWidget(cancel_btn)
        button_layout.addSpacing(12)
        button_layout.addWidget(save_btn)
        main_layout.addWidget(button_container)

        # Connect all controls to mark dirty when changed
        self._connect_dirty_tracking()

    def _connect_dirty_tracking(self):
        """Connect all form controls to mark dirty state when changed"""
        # Note: language_combo and theme_switch already mark dirty in their handlers

        # ComboBoxes
        self.browser_combo.currentTextChanged.connect(lambda: self._mark_dirty())
        if hasattr(self, 'browser_count_combo'):
            self.browser_count_combo.currentTextChanged.connect(lambda: self._mark_dirty())

        # Switches
        self.download_images_switch.checkedChanged.connect(lambda: self._mark_dirty())
        self.auto_save_switch.checkedChanged.connect(lambda: self._mark_dirty())
        self.auto_delete_pabaigta_switch.checkedChanged.connect(lambda: self._mark_dirty())
        if hasattr(self, 'multi_session_switch'):
            self.multi_session_switch.checkedChanged.connect(lambda: self._mark_dirty())
        if hasattr(self, 'prestashop_api_switch'):
            self.prestashop_api_switch.checkedChanged.connect(lambda: self._mark_dirty())

        # Text fields
        self.kross_path_field.textChanged.connect(lambda: self._mark_dirty())
        self.repo_path_field.textChanged.connect(lambda: self._mark_dirty())
        if hasattr(self, 'prestashop_url_field'):
            self.prestashop_url_field.textChanged.connect(lambda: self._mark_dirty())
        if hasattr(self, 'prestashop_key_field'):
            self.prestashop_key_field.textChanged.connect(lambda: self._mark_dirty())

    def _load_settings(self):
        """Load current settings from database"""
        # Load language
        language_display = self._get_saved_language_display()
        self._preview_lang_code = normalize_language(language_display, self._preview_lang_code)
        index = self.language_combo.findText(language_display)
        if index >= 0:
            self.language_combo.setCurrentIndex(index)
        else:
            # Fallback: force the visible value even if it doesn't match items
            self.language_combo.setCurrentText(language_display)

        # Safety: ComboBox should never show placeholder when we have a saved value
        if not self.language_combo.currentText():
            self.language_combo.setCurrentText(language_display)

        # Load browser
        browser = self.main.settings.get('browser_choice', 'Chrome')
        index = self.browser_combo.findText(browser)
        if index >= 0:
            self.browser_combo.setCurrentIndex(index)

        # Load feature toggles
        self.download_images_switch.setChecked(self.main.settings.get('download_images', False))
        self.auto_save_switch.setChecked(self.main.settings.get('auto_save', True))
        self.auto_delete_pabaigta_switch.setChecked(self.main.settings.get('auto_delete_pabaigta_files', False))

        # Load multi-session + browser count
        if hasattr(self, 'multi_session_switch'):
            self.multi_session_switch.setChecked(self.main.settings.get('multi_session_enabled', False))
        if hasattr(self, 'browser_count_combo'):
            try:
                bc = int(self.main.settings.get('browser_count', 2))
            except Exception:
                bc = 2
            if bc < 2:
                bc = 2
            if bc > 4:
                bc = 4
            self.browser_count_combo.setCurrentText(str(bc))

        self._update_multi_session_enabled_state()

        # Load PrestaShop API settings
        if hasattr(self, 'prestashop_api_switch'):
            self.prestashop_api_switch.setChecked(bool(self.main.settings.get('prestashop_api_enabled', False)))
        if hasattr(self, 'prestashop_url_field'):
            self.prestashop_url_field.setText(self.main.settings.get('prestashop_url', '') or '')
        if hasattr(self, 'prestashop_key_field'):
            self.prestashop_key_field.setText(self.main.settings.get('prestashop_api_key', '') or '')

        # Load theme
        theme = self.main.settings.get('theme', 'light')
        self.theme_switch.setChecked(theme == 'dark')
        self._preview_theme_is_dark = (theme == 'dark')
        self._apply_theme_preview(self._preview_theme_is_dark)

        # Load paths
        self.kross_path_field.setText(self.main.settings.get('kross_download_path', ''))
        self.repo_path_field.setText(self.main.settings.get('repository_path', ''))

    def _on_language_change(self, language):
        """Handle language change (no longer auto-saves)"""
        if self._loading:
            return

        # Ignore dummy placeholder item.
        if self.language_combo.currentIndex() == 0:
            return

        # Live preview ONLY within Settings screen.
        # Live preview within Settings + app chrome (navigation) only.
        self._preview_lang_code = normalize_language(language, self._preview_lang_code)

        # Ensure combo shows an actual value, not placeholder.
        if not self.language_combo.currentText():
            idx = self.language_combo.findText(language)
            if idx >= 0:
                self.language_combo.setCurrentIndex(idx)
            else:
                self.language_combo.setCurrentText(language)

        self.retranslate_ui(preview=True)

        if hasattr(self.main, "apply_language_preview"):
            try:
                self.main.apply_language_preview(self._preview_lang_code)
            except Exception:
                pass

        # Mark as dirty
        self._mark_dirty()

    def _apply_theme_preview(self, is_dark: bool) -> None:
        """Live preview while Settings screen is visible.

        Applies the qfluentwidgets theme globally so cards/navigation look correct,
        but is reverted when leaving Settings unless Save is clicked.
        """
        self._preview_theme_is_dark = bool(is_dark)
        self._apply_global_theme(self._preview_theme_is_dark)
        self._on_theme_changed()

    def retranslate_ui(self, preview: bool = False):
        """Update visible strings.

        If preview=True, uses the Settings screen preview language.
        Otherwise uses the globally-applied app language.
        """
        if hasattr(self.main, "i18n"):
            lang_code = self._preview_lang_code if preview else self.main.i18n.language.code
        else:
            lang_code = self._preview_lang_code

        tr = lambda k, **kw: translate(lang_code, k, **kw)
        if "title_label" in self._ui:
            self._ui["title_label"].setText(tr("settings.title"))
        if "lang_title" in self._ui:
            self._ui["lang_title"].setText(tr("settings.language.title"))
        if "lang_desc" in self._ui:
            self._ui["lang_desc"].setText(tr("settings.language.desc"))
        if "lang_label" in self._ui:
            self._ui["lang_label"].setText(tr("settings.language.label"))

        # Placeholders
        # Update language placeholder item (index 0)
        if hasattr(self, "language_combo") and self.language_combo.count() > 0:
            try:
                self.language_combo.setItemText(0, tr("settings.language.placeholder"))
            except Exception:
                pass
        if hasattr(self, "kross_path_field"):
            self.kross_path_field.setPlaceholderText(tr("settings.paths.placeholder"))
        if hasattr(self, "repo_path_field"):
            self.repo_path_field.setPlaceholderText(tr("settings.paths.placeholder"))

        if "browser_title" in self._ui:
            self._ui["browser_title"].setText(tr("settings.browser.title"))
        if "browser_desc" in self._ui:
            self._ui["browser_desc"].setText(tr("settings.browser.desc"))
        if "browser_label" in self._ui:
            self._ui["browser_label"].setText(tr("settings.browser.label"))

        if "features_title" in self._ui:
            self._ui["features_title"].setText(tr("settings.features.title"))
        if "download_images_label" in self._ui:
            self._ui["download_images_label"].setText(tr("settings.features.download.title"))
        if "download_images_sublabel" in self._ui:
            self._ui["download_images_sublabel"].setText(tr("settings.features.download.desc"))
        if "auto_save_label" in self._ui:
            self._ui["auto_save_label"].setText(tr("settings.features.autosave.title"))
        if "auto_save_sublabel" in self._ui:
            self._ui["auto_save_sublabel"].setText(tr("settings.features.autosave.desc"))
        if "auto_delete_label" in self._ui:
            self._ui["auto_delete_label"].setText(tr("settings.features.auto_delete_pabaigta.title"))
        if "auto_delete_sublabel" in self._ui:
            self._ui["auto_delete_sublabel"].setText(tr("settings.features.auto_delete_pabaigta.desc"))

        if "multi_session_label" in self._ui:
            self._ui["multi_session_label"].setText(tr("settings.features.multi_session.title"))
        if "multi_session_sublabel" in self._ui:
            self._ui["multi_session_sublabel"].setText(tr("settings.features.multi_session.desc"))
        if "browser_count_label" in self._ui:
            self._ui["browser_count_label"].setText(tr("settings.features.browser_count.label"))
        if "browser_count_caption" in self._ui:
            self._ui["browser_count_caption"].setText(tr("settings.features.browser_count.caption"))

        if "prestashop_api_title" in self._ui:
            self._ui["prestashop_api_title"].setText(tr("settings.features.prestashop_api.title"))
        if "prestashop_api_desc" in self._ui:
            self._ui["prestashop_api_desc"].setText(tr("settings.features.prestashop_api.desc"))
        if "prestashop_enable_label" in self._ui:
            self._ui["prestashop_enable_label"].setText(tr("settings.features.prestashop_api.enable"))
        if "prestashop_url_label" in self._ui:
            self._ui["prestashop_url_label"].setText(tr("settings.features.prestashop_url.label"))
        if "prestashop_url_caption" in self._ui:
            self._ui["prestashop_url_caption"].setText(tr("settings.features.prestashop_url.caption"))
        if "prestashop_key_label" in self._ui:
            self._ui["prestashop_key_label"].setText(tr("settings.features.prestashop_api_key.label"))
        if "prestashop_key_caption" in self._ui:
            self._ui["prestashop_key_caption"].setText(tr("settings.features.prestashop_api_key.caption"))
        if "prestashop_test_btn" in self._ui:
            self._ui["prestashop_test_btn"].setText(tr("settings.features.prestashop_api.test"))

        if "theme_title" in self._ui:
            self._ui["theme_title"].setText(tr("settings.appearance.title"))
        if "theme_desc" in self._ui:
            self._ui["theme_desc"].setText(tr("settings.appearance.desc"))
        if "theme_label" in self._ui:
            self._ui["theme_label"].setText(tr("settings.appearance.dark.title"))
        if "theme_sublabel" in self._ui:
            self._ui["theme_sublabel"].setText(tr("settings.appearance.dark.desc"))

        if "paths_title" in self._ui:
            self._ui["paths_title"].setText(tr("settings.paths.title"))
        if "paths_desc" in self._ui:
            self._ui["paths_desc"].setText(tr("settings.paths.desc"))
        if "kross_label" in self._ui:
            self._ui["kross_label"].setText(tr("settings.paths.kross.title"))
        if "repo_label" in self._ui:
            self._ui["repo_label"].setText(tr("settings.paths.repo.title"))
        if "kross_browse_btn" in self._ui:
            self._ui["kross_browse_btn"].setText(tr("settings.paths.browse"))
        if "repo_browse_btn" in self._ui:
            self._ui["repo_browse_btn"].setText(tr("settings.paths.browse"))

        if "info_title" in self._ui:
            self._ui["info_title"].setText(tr("settings.about.title"))
        if "app_name" in self._ui:
            self._ui["app_name"].setText(tr("settings.about.app"))
        if "save_btn" in self._ui:
            self._ui["save_btn"].setText(tr("settings.save"))
        if "cancel_btn" in self._ui:
            self._ui["cancel_btn"].setText(tr("settings.cancel"))

    def _update_scroll_style(self):
        """Update scroll area styling based on current theme"""
        is_dark = getattr(self, "_preview_theme_is_dark", isDarkTheme())
        bg_color = COLORS['space_indigo'] if is_dark else COLORS['platinum']

        self.scroll.setStyleSheet(f"""
            QScrollArea {{
                border: none;
                background-color: {bg_color};
            }}
            QScrollArea QWidget#qt_scrollarea_viewport {{
                background-color: {bg_color};
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: {SIZES['scrollbar_thickness']}px;
                margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background: {rgba_from_hex(COLORS['lavender_grey'], 0.3) if is_dark else rgba_from_hex(COLORS['space_indigo'], 0.2)};
                border-radius: {RADII['sm']}px;
                min-height: {SIZES['scrollbar_handle_min']}px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {rgba_from_hex(COLORS['lavender_grey'], 0.5) if is_dark else rgba_from_hex(COLORS['space_indigo'], 0.3)};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none;
            }}
        """)

    def _on_theme_change(self, checked):
        """Handle theme toggle.

        Theme changes are applied only after user clicks Save.
        """
        if self._loading:
            return

        # Live preview ONLY within Settings screen.
        self._apply_theme_preview(bool(checked))

        # Mark as dirty
        self._mark_dirty()

    def _browse_folder(self, setting_key, text_field):
        """Browse for folder (no longer auto-saves)"""
        folder = QFileDialog.getExistingDirectory(
            self,
            translate(self._preview_lang_code, "settings.paths.select_folder.title"),
            text_field.text() or ""
        )

        if folder:
            text_field.setText(folder)
            # Path will be saved when user clicks Save button

    def _save_all_settings(self):
        """Save all settings to database"""
        try:
            # Get current values
            language = self.language_combo.currentText() or self._get_saved_language_display()
            browser = self.browser_combo.currentText()
            download_images = self.download_images_switch.isChecked()
            auto_save = self.auto_save_switch.isChecked()
            auto_delete_pabaigta = self.auto_delete_pabaigta_switch.isChecked()
            multi_session_enabled = self.multi_session_switch.isChecked() if hasattr(self, 'multi_session_switch') else False
            try:
                browser_count = int(self.browser_count_combo.currentText().strip()) if hasattr(self, 'browser_count_combo') else 2
            except Exception:
                browser_count = 2
            theme_is_dark = self.theme_switch.isChecked()
            theme_name = 'dark' if theme_is_dark else 'light'
            kross_path = self.kross_path_field.text()
            repo_path = self.repo_path_field.text()

            prestashop_enabled = self.prestashop_api_switch.isChecked() if hasattr(self, 'prestashop_api_switch') else False
            prestashop_url = self.prestashop_url_field.text().strip() if hasattr(self, 'prestashop_url_field') else ''
            prestashop_key = self.prestashop_key_field.text().strip() if hasattr(self, 'prestashop_key_field') else ''

            # Save all to database
            self.main.settings.set('language', language)
            self.main.settings.set('browser_choice', browser)
            self.main.settings.set('download_images', download_images)
            self.main.settings.set('auto_save', auto_save)
            self.main.settings.set('auto_delete_pabaigta_files', auto_delete_pabaigta)
            self.main.settings.set('multi_session_enabled', bool(multi_session_enabled))
            self.main.settings.set('browser_count', int(browser_count))
            self.main.settings.set('theme', theme_name)

            # Optional APIs
            self.main.settings.set('prestashop_api_enabled', bool(prestashop_enabled))
            self.main.settings.set('prestashop_url', prestashop_url)
            self.main.settings.set('prestashop_api_key', prestashop_key)

            if kross_path:
                self.main.settings.set('kross_download_path', kross_path)
            if repo_path:
                self.main.settings.set('repository_path', repo_path)

            # Apply theme globally now that it is saved
            self.main._apply_saved_theme()
            self.main.update_container_backgrounds()

            # Update settings screen background + scroll styling after theme apply
            self._on_theme_changed()

            # Sync preview to global theme after applying
            self._preview_theme_is_dark = isDarkTheme()

            # Update batch upload screen table if it exists
            if self.main.batch_upload_screen:
                try:
                    self.main.batch_upload_screen._update_table_theme()
                except Exception:
                    pass

            # Apply language globally (in case user changed it and wants persistence)
            if hasattr(self.main, "i18n"):
                self.main.i18n.set_language(language, persist=True)
                # Sync preview to global language after applying
                self._preview_lang_code = self.main.i18n.language.code
                self.retranslate_ui(preview=False)

                # Ensure chrome is in the new global language.
                if hasattr(self.main, "clear_language_preview"):
                    try:
                        self.main.clear_language_preview()
                    except Exception:
                        pass

            # Show success message
            InfoBar.success(
                title=self.main.i18n.tr("settings.saved.title"),
                content=self.main.i18n.tr("settings.saved.content"),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self
            )

            # Clear dirty flag after successful save
            self._mark_clean()

        except Exception as e:
            InfoBar.error(
                title=translate(self._preview_lang_code, "settings.save_failed.title"),
                content=translate(self._preview_lang_code, "settings.save_failed.content", error=str(e)),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=4000,
                parent=self
            )

    def _cancel_changes(self):
        """Discard changes and revert to saved settings"""
        # Reload settings from database
        self._loading = True
        self._load_settings()
        self._loading = False

        # Reset preview states to saved values
        self._sync_preview_from_saved_and_retranslate()

        # Clear dirty flag
        self._mark_clean()

        # Show info message
        InfoBar.info(
            title=self.main.i18n.tr("settings.cancelled.title"),
            content=self.main.i18n.tr("settings.cancelled.content"),
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=2000,
            parent=self
        )

    def _mark_dirty(self):
        """Mark settings as having unsaved changes"""
        if self._loading:
            return

        self._is_dirty = True

        # Enable Save/Cancel buttons
        if "save_btn" in self._ui:
            self._ui["save_btn"].setEnabled(True)
        if "cancel_btn" in self._ui:
            self._ui["cancel_btn"].setEnabled(True)

    def _mark_clean(self):
        """Mark settings as saved (no unsaved changes)"""
        self._is_dirty = False

        # Disable Save/Cancel buttons
        if "save_btn" in self._ui:
            self._ui["save_btn"].setEnabled(False)
        if "cancel_btn" in self._ui:
            self._ui["cancel_btn"].setEnabled(False)

    def _on_test_prestashop_connection(self):
        base_url = self.prestashop_url_field.text().strip() if hasattr(self, "prestashop_url_field") else ""
        api_key = self.prestashop_key_field.text().strip() if hasattr(self, "prestashop_key_field") else ""

        if not base_url or not api_key:
            InfoBar.warning(
                title=translate(self._preview_lang_code, "settings.features.prestashop_api.test_missing.title"),
                content=translate(self._preview_lang_code, "settings.features.prestashop_api.test_missing.content"),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3500,
                parent=self,
            )
            return

        try:
            self.prestashop_test_btn.setEnabled(False)
        except Exception:
            pass

        worker = _PrestaShopConnectionTestWorker(
            base_url=base_url,
            api_key=api_key,
            logger=getattr(self.main, "logger", None),
        )
        self._prestashop_test_worker = worker

        def _done(ok: bool, details: str):
            try:
                self.prestashop_test_btn.setEnabled(True)
            except Exception:
                pass

            if ok:
                InfoBar.success(
                    title=translate(self._preview_lang_code, "settings.features.prestashop_api.test_ok.title"),
                    content=translate(self._preview_lang_code, "settings.features.prestashop_api.test_ok.content"),
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=3000,
                    parent=self,
                )
            else:
                InfoBar.error(
                    title=translate(self._preview_lang_code, "settings.features.prestashop_api.test_failed.title"),
                    content=translate(
                        self._preview_lang_code,
                        "settings.features.prestashop_api.test_failed.content",
                        error=(details or ""),
                    ),
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=5000,
                    parent=self,
                )

        worker.done.connect(_done)
        worker.start()

    def _on_breakpoint_changed(self, breakpoint: str):
        """Respond to breakpoint changes - adjust margins and spacing."""
        margins = get_responsive_margins(breakpoint)
        spacing = get_responsive_spacing(breakpoint)
        if hasattr(self, 'content_widget') and self.content_widget and self.content_widget.layout():
            self.content_widget.layout().setContentsMargins(*margins)
            self.content_widget.layout().setSpacing(spacing)

    def _on_theme_changed(self):
        """Handle theme change event from other screens"""
        apply_screen_theme(
            self,
            "SettingsScreen",
            scroll=self.scroll,
            content=self.content_widget
        )

        is_dark = isDarkTheme()
        bg_color = COLORS['space_indigo'] if is_dark else COLORS['platinum']

        text_primary = COLORS['text_primary_dark'] if is_dark else COLORS['text_primary_light']
        text_caption = COLORS['lavender_grey'] if is_dark else COLORS['text_secondary']

        # Update main background
        self.setStyleSheet(
            f"""
            SettingsScreen {{
                background-color: {bg_color};
            }}
            SettingsScreen TitleLabel,
            SettingsScreen StrongBodyLabel,
            SettingsScreen BodyLabel {{
                color: {text_primary};
            }}
            SettingsScreen CaptionLabel {{
                color: {text_caption};
            }}
            """
        )

        # Update content widget background
        if self.content_widget:
            self.content_widget.setStyleSheet(f"#contentWidget {{ background-color: {bg_color}; }}")

        # Update scroll area styling
        if self.scroll:
            self._update_scroll_style()

        # Settings should NOT show text background bars.
        enforce_transparent_labels(self)

    def _on_multi_session_change(self, checked) -> None:
        if self._loading:
            return
        self._update_multi_session_enabled_state()

    def _update_multi_session_enabled_state(self) -> None:
        try:
            enabled = bool(self.multi_session_switch.isChecked())
        except Exception:
            enabled = False

        try:
            self.browser_count_combo.setEnabled(enabled)
        except Exception:
            pass
