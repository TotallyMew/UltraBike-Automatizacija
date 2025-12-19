"""
Settings Screen
Application settings with Fluent Design System
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFileDialog, QSizePolicy
from PySide6.QtCore import Qt
from qfluentwidgets import (
    CardWidget, TitleLabel, StrongBodyLabel, BodyLabel, CaptionLabel,
    ComboBox, SwitchButton, FluentIcon, InfoBar, InfoBarPosition,
    isDarkTheme, setTheme, Theme, PushButton, LineEdit, ScrollArea,
    PrimaryPushButton, qconfig
)
from GUI_Qt.styles.theme_config import COLORS
from GUI_Qt.styles.screen_theme import enforce_transparent_labels
from GUI_Qt.i18n import normalize_language, translate


class SettingsScreen(QWidget):
    """Settings screen with language and theme options"""

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main = main_window
        self._loading = True  # Flag to prevent notifications during initial load

        # UI elements that need retranslation
        self._ui = {}

        # Preview-only state (applies only inside this screen until Save)
        self._preview_lang_code = (
            self.main.i18n.language.code if hasattr(self.main, "i18n") else "en"
        )
        self._preview_theme_is_dark = isDarkTheme()

        # Store references for theme updates
        self.scroll = None
        self.content_widget = None

        self._init_ui()
        self._load_settings()
        self._loading = False  # Re-enable notifications after load

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
        self.setStyleSheet(f"SettingsScreen {{ background-color: {bg_color}; }}")

        # Scroll area for all settings
        self.scroll = ScrollArea()
        self.scroll.setWidgetResizable(True)
        self._update_scroll_style()

        # Content widget inside scroll
        self.content_widget = QWidget()
        self.content_widget.setObjectName("contentWidget")
        self.content_widget.setStyleSheet(f"#contentWidget {{ background-color: {bg_color}; }}")
        layout = QVBoxLayout(self.content_widget)
        layout.setContentsMargins(40, 20, 40, 20)  # Proper side margins
        layout.setSpacing(20)

        # Header
        header = QHBoxLayout()
        title_label = TitleLabel(translate(self._preview_lang_code, "settings.title"))
        self._ui["title_label"] = title_label
        header.addWidget(title_label)
        header.addStretch()
        layout.addLayout(header)

        # Settings should NOT show text background bars.
        enforce_transparent_labels(self)

        # === LANGUAGE CARD ===
        language_card = CardWidget()
        language_card.setBorderRadius(8)
        language_layout = QVBoxLayout(language_card)
        language_layout.setContentsMargins(24, 20, 24, 20)
        language_layout.setSpacing(16)

        # Language header
        lang_header = QHBoxLayout()
        from qfluentwidgets import IconWidget
        lang_icon = IconWidget(FluentIcon.GLOBE)
        lang_icon.setFixedSize(24, 24)
        lang_title = StrongBodyLabel(translate(self._preview_lang_code, "settings.language.title"))
        self._ui["lang_title"] = lang_title
        lang_title.setStyleSheet("font-size: 16px;")
        lang_header.addWidget(lang_icon)
        lang_header.addSpacing(12)
        lang_header.addWidget(lang_title)
        lang_header.addStretch()
        language_layout.addLayout(lang_header)

        # Language description
        lang_desc = CaptionLabel(translate(self._preview_lang_code, "settings.language.desc"))
        self._ui["lang_desc"] = lang_desc
        lang_desc.setStyleSheet(f"color: {COLORS['text_secondary']};")
        language_layout.addWidget(lang_desc)

        # Language selector
        lang_selector_layout = QHBoxLayout()
        lang_label = BodyLabel(translate(self._preview_lang_code, "settings.language.label"))
        self._ui["lang_label"] = lang_label
        lang_label.setMinimumWidth(100)

        self.language_combo = ComboBox()
        # NOTE: QFluentWidgets ComboBox placeholder behavior can mask index 0.
        # Insert a dummy first item so real languages are not at index 0.
        # We keep it as a visible (localized) placeholder option.
        self.language_combo.addItem(translate(self._preview_lang_code, "settings.language.placeholder"))
        self.language_combo.addItems(["English", "Lithuanian"])
        self.language_combo.setPlaceholderText("")
        self.language_combo.setMinimumWidth(200)
        self.language_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.language_combo.currentTextChanged.connect(self._on_language_change)

        lang_selector_layout.addWidget(lang_label)
        lang_selector_layout.addWidget(self.language_combo)
        lang_selector_layout.addStretch()
        language_layout.addLayout(lang_selector_layout)

        layout.addWidget(language_card)

        # === BROWSER CARD ===
        browser_card = CardWidget()
        browser_card.setBorderRadius(8)
        browser_layout = QVBoxLayout(browser_card)
        browser_layout.setContentsMargins(24, 20, 24, 20)
        browser_layout.setSpacing(16)

        # Browser header
        browser_header = QHBoxLayout()
        browser_icon = IconWidget(FluentIcon.GLOBE)
        browser_icon.setFixedSize(24, 24)
        browser_title = StrongBodyLabel(translate(self._preview_lang_code, "settings.browser.title"))
        self._ui["browser_title"] = browser_title
        browser_title.setStyleSheet("font-size: 16px;")
        browser_header.addWidget(browser_icon)
        browser_header.addSpacing(12)
        browser_header.addWidget(browser_title)
        browser_header.addStretch()
        browser_layout.addLayout(browser_header)

        # Browser description
        browser_desc = CaptionLabel(translate(self._preview_lang_code, "settings.browser.desc"))
        self._ui["browser_desc"] = browser_desc
        browser_desc.setStyleSheet(f"color: {COLORS['text_secondary']};")
        browser_layout.addWidget(browser_desc)

        # Browser selector
        browser_selector_layout = QHBoxLayout()
        browser_label = BodyLabel(translate(self._preview_lang_code, "settings.browser.label"))
        self._ui["browser_label"] = browser_label
        browser_label.setMinimumWidth(100)

        self.browser_combo = ComboBox()
        self.browser_combo.addItems(["Chrome", "Firefox", "Edge"])
        self.browser_combo.setMinimumWidth(200)
        self.browser_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        browser_selector_layout.addWidget(browser_label)
        browser_selector_layout.addWidget(self.browser_combo)
        browser_selector_layout.addStretch()
        browser_layout.addLayout(browser_selector_layout)

        layout.addWidget(browser_card)

        # === FEATURES CARD ===
        features_card = CardWidget()
        features_card.setBorderRadius(8)
        features_layout = QVBoxLayout(features_card)
        features_layout.setContentsMargins(24, 20, 24, 20)
        features_layout.setSpacing(16)

        # Features header
        features_header = QHBoxLayout()
        features_icon = IconWidget(FluentIcon.SETTING)
        features_icon.setFixedSize(24, 24)
        features_title = StrongBodyLabel(translate(self._preview_lang_code, "settings.features.title"))
        self._ui["features_title"] = features_title
        features_title.setStyleSheet("font-size: 16px;")
        features_header.addWidget(features_icon)
        features_header.addSpacing(12)
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
        download_images_sublabel.setStyleSheet(f"color: {COLORS['text_secondary']};")
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
        auto_save_sublabel.setStyleSheet(f"color: {COLORS['text_secondary']};")
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
        auto_delete_sublabel.setStyleSheet(f"color: {COLORS['text_secondary']};")
        auto_delete_info.addWidget(auto_delete_label)
        auto_delete_info.addWidget(auto_delete_sublabel)

        self.auto_delete_pabaigta_switch = SwitchButton()

        auto_delete_layout.addLayout(auto_delete_info)
        auto_delete_layout.addStretch()
        auto_delete_layout.addWidget(self.auto_delete_pabaigta_switch)
        features_layout.addLayout(auto_delete_layout)

        layout.addWidget(features_card)

        # === THEME CARD ===
        theme_card = CardWidget()
        theme_card.setBorderRadius(8)
        theme_layout = QVBoxLayout(theme_card)
        theme_layout.setContentsMargins(24, 20, 24, 20)
        theme_layout.setSpacing(16)

        # Theme header
        theme_header = QHBoxLayout()
        theme_icon = IconWidget(FluentIcon.BRUSH)
        theme_icon.setFixedSize(24, 24)
        theme_title = StrongBodyLabel(translate(self._preview_lang_code, "settings.appearance.title"))
        self._ui["theme_title"] = theme_title
        theme_title.setStyleSheet("font-size: 16px;")
        theme_header.addWidget(theme_icon)
        theme_header.addSpacing(12)
        theme_header.addWidget(theme_title)
        theme_header.addStretch()
        theme_layout.addLayout(theme_header)

        # Theme description
        theme_desc = CaptionLabel(translate(self._preview_lang_code, "settings.appearance.desc"))
        self._ui["theme_desc"] = theme_desc
        theme_desc.setStyleSheet(f"color: {COLORS['text_secondary']};")
        theme_layout.addWidget(theme_desc)

        # Theme toggle
        theme_toggle_layout = QHBoxLayout()

        theme_info_layout = QVBoxLayout()
        theme_label = BodyLabel(translate(self._preview_lang_code, "settings.appearance.dark.title"))
        self._ui["theme_label"] = theme_label
        theme_label.setStyleSheet("font-weight: 500;")
        theme_sublabel = CaptionLabel(translate(self._preview_lang_code, "settings.appearance.dark.desc"))
        self._ui["theme_sublabel"] = theme_sublabel
        theme_sublabel.setStyleSheet(f"color: {COLORS['text_secondary']};")
        theme_info_layout.addWidget(theme_label)
        theme_info_layout.addWidget(theme_sublabel)

        self.theme_switch = SwitchButton()
        self.theme_switch.setChecked(isDarkTheme())
        self.theme_switch.checkedChanged.connect(self._on_theme_change)

        theme_toggle_layout.addLayout(theme_info_layout)
        theme_toggle_layout.addStretch()
        theme_toggle_layout.addWidget(self.theme_switch)
        theme_layout.addLayout(theme_toggle_layout)

        layout.addWidget(theme_card)

        # === PATHS CARD ===
        paths_card = CardWidget()
        paths_card.setBorderRadius(8)
        paths_layout = QVBoxLayout(paths_card)
        paths_layout.setContentsMargins(24, 20, 24, 20)
        paths_layout.setSpacing(16)

        # Paths header
        paths_header = QHBoxLayout()
        paths_icon = IconWidget(FluentIcon.FOLDER)
        paths_icon.setFixedSize(24, 24)
        paths_title = StrongBodyLabel(translate(self._preview_lang_code, "settings.paths.title"))
        self._ui["paths_title"] = paths_title
        paths_title.setStyleSheet("font-size: 16px;")
        paths_header.addWidget(paths_icon)
        paths_header.addSpacing(12)
        paths_header.addWidget(paths_title)
        paths_header.addStretch()
        paths_layout.addLayout(paths_header)

        # Paths description
        paths_desc = CaptionLabel(translate(self._preview_lang_code, "settings.paths.desc"))
        self._ui["paths_desc"] = paths_desc
        paths_desc.setStyleSheet(f"color: {COLORS['text_secondary']};")
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
        kross_browse_btn.setFixedWidth(100)
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
        repo_browse_btn.setFixedWidth(100)
        repo_browse_btn.clicked.connect(lambda: self._browse_folder('repository_path', self.repo_path_field))

        repo_input_layout.addWidget(self.repo_path_field)
        repo_input_layout.addWidget(repo_browse_btn)

        repo_path_layout.addWidget(repo_label)
        repo_path_layout.addLayout(repo_input_layout)
        paths_layout.addLayout(repo_path_layout)

        layout.addWidget(paths_card)

        # === INFO CARD ===
        info_card = CardWidget()
        info_card.setBorderRadius(8)
        info_layout = QVBoxLayout(info_card)
        info_layout.setContentsMargins(24, 20, 24, 20)
        info_layout.setSpacing(12)

        info_title = StrongBodyLabel(translate(self._preview_lang_code, "settings.about.title"))
        self._ui["info_title"] = info_title
        info_title.setStyleSheet("font-size: 16px;")
        info_layout.addWidget(info_title)

        app_name = BodyLabel(translate(self._preview_lang_code, "settings.about.app"))
        self._ui["app_name"] = app_name
        app_name.setStyleSheet(f"color: {COLORS['lavender_grey']};")
        info_layout.addWidget(app_name)

        version = CaptionLabel(translate(self._preview_lang_code, "settings.about.version"))
        self._ui["version"] = version
        version.setStyleSheet(f"color: {COLORS['text_secondary']};")
        info_layout.addWidget(version)

        layout.addWidget(info_card)

        # Push everything to top
        layout.addStretch()

        # Set scroll widget and add to main layout
        self.scroll.setWidget(self.content_widget)
        main_layout.addWidget(self.scroll)

        # === SAVE BUTTON (Fixed at bottom) ===
        button_container = QWidget()
        button_layout = QHBoxLayout(button_container)
        button_layout.setContentsMargins(20, 12, 20, 12)
        button_layout.addStretch()

        save_btn = PrimaryPushButton(translate(self._preview_lang_code, "settings.save"))
        self._ui["save_btn"] = save_btn
        save_btn.setIcon(FluentIcon.SAVE)
        save_btn.setFixedHeight(40)
        save_btn.clicked.connect(self._save_all_settings)

        button_layout.addWidget(save_btn)
        main_layout.addWidget(button_container)

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
        if "version" in self._ui:
            self._ui["version"].setText(tr("settings.about.version"))
        if "save_btn" in self._ui:
            self._ui["save_btn"].setText(tr("settings.save"))

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
                width: 12px;
                margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background: {'rgba(141, 153, 174, 0.3)' if is_dark else 'rgba(43, 45, 66, 0.2)'};
                border-radius: 6px;
                min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {'rgba(141, 153, 174, 0.5)' if is_dark else 'rgba(43, 45, 66, 0.3)'};
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
            theme_is_dark = self.theme_switch.isChecked()
            theme_name = 'dark' if theme_is_dark else 'light'
            kross_path = self.kross_path_field.text()
            repo_path = self.repo_path_field.text()

            # Save all to database
            self.main.settings.set('language', language)
            self.main.settings.set('browser_choice', browser)
            self.main.settings.set('download_images', download_images)
            self.main.settings.set('auto_save', auto_save)
            self.main.settings.set('auto_delete_pabaigta_files', auto_delete_pabaigta)
            self.main.settings.set('theme', theme_name)

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

    def _on_theme_changed(self):
        """Handle theme change event from other screens"""
        is_dark = isDarkTheme()
        bg_color = COLORS['space_indigo'] if is_dark else COLORS['platinum']

        # Update main background
        self.setStyleSheet(f"SettingsScreen {{ background-color: {bg_color}; }}")

        # Update content widget background
        if self.content_widget:
            self.content_widget.setStyleSheet(f"#contentWidget {{ background-color: {bg_color}; }}")

        # Update scroll area styling
        if self.scroll:
            self._update_scroll_style()

        # Settings should NOT show text background bars.
        enforce_transparent_labels(self)
