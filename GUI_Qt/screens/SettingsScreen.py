"""
Settings Screen
Application settings with Fluent Design System
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFileDialog
from PySide6.QtCore import Qt
from qfluentwidgets import (
    CardWidget, TitleLabel, StrongBodyLabel, BodyLabel, CaptionLabel,
    ComboBox, SwitchButton, FluentIcon, InfoBar, InfoBarPosition,
    isDarkTheme, setTheme, Theme, PushButton, LineEdit, ScrollArea,
    PrimaryPushButton, qconfig
)
from GUI_Qt.styles.theme_config import COLORS


class SettingsScreen(QWidget):
    """Settings screen with language and theme options"""

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main = main_window
        self._loading = True  # Flag to prevent notifications during initial load

        # Store references for theme updates
        self.scroll = None
        self.content_widget = None

        self._init_ui()
        self._load_settings()
        self._loading = False  # Re-enable notifications after load

        # Connect to theme change signal
        qconfig.themeChangedFinished.connect(self._on_theme_changed)

    def _init_ui(self):
        """Initialize UI"""
        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Apply background color based on theme - using our color scheme
        is_dark = isDarkTheme()
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
        title_label = TitleLabel("Settings")
        header.addWidget(title_label)
        header.addStretch()
        layout.addLayout(header)

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
        lang_title = StrongBodyLabel("Language")
        lang_title.setStyleSheet("font-size: 16px;")
        lang_header.addWidget(lang_icon)
        lang_header.addSpacing(12)
        lang_header.addWidget(lang_title)
        lang_header.addStretch()
        language_layout.addLayout(lang_header)

        # Language description
        lang_desc = CaptionLabel("Choose your preferred language for the application")
        lang_desc.setStyleSheet(f"color: {COLORS['text_secondary']};")
        language_layout.addWidget(lang_desc)

        # Language selector
        lang_selector_layout = QHBoxLayout()
        lang_label = BodyLabel("Language:")
        lang_label.setFixedWidth(100)

        self.language_combo = ComboBox()
        self.language_combo.addItems(["English", "Lithuanian"])
        self.language_combo.setPlaceholderText("Select language")
        self.language_combo.setFixedWidth(200)
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
        browser_title = StrongBodyLabel("Browser Settings")
        browser_title.setStyleSheet("font-size: 16px;")
        browser_header.addWidget(browser_icon)
        browser_header.addSpacing(12)
        browser_header.addWidget(browser_title)
        browser_header.addStretch()
        browser_layout.addLayout(browser_header)

        # Browser description
        browser_desc = CaptionLabel("Select your preferred browser for automation")
        browser_desc.setStyleSheet(f"color: {COLORS['text_secondary']};")
        browser_layout.addWidget(browser_desc)

        # Browser selector
        browser_selector_layout = QHBoxLayout()
        browser_label = BodyLabel("Browser:")
        browser_label.setFixedWidth(100)

        self.browser_combo = ComboBox()
        self.browser_combo.addItems(["Chrome", "Firefox", "Edge"])
        self.browser_combo.setFixedWidth(200)

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
        features_title = StrongBodyLabel("Features")
        features_title.setStyleSheet("font-size: 16px;")
        features_header.addWidget(features_icon)
        features_header.addSpacing(12)
        features_header.addWidget(features_title)
        features_header.addStretch()
        features_layout.addLayout(features_header)

        # Download images toggle
        download_images_layout = QHBoxLayout()
        download_images_info = QVBoxLayout()
        download_images_label = BodyLabel("Download and Upload Images")
        download_images_label.setStyleSheet("font-weight: 500;")
        download_images_sublabel = CaptionLabel("Automatically download and upload bicycle images")
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
        auto_save_label = BodyLabel("Auto-Save")
        auto_save_label.setStyleSheet("font-weight: 500;")
        auto_save_sublabel = CaptionLabel("Automatically save product updates after upload")
        auto_save_sublabel.setStyleSheet(f"color: {COLORS['text_secondary']};")
        auto_save_info.addWidget(auto_save_label)
        auto_save_info.addWidget(auto_save_sublabel)

        self.auto_save_switch = SwitchButton()

        auto_save_layout.addLayout(auto_save_info)
        auto_save_layout.addStretch()
        auto_save_layout.addWidget(self.auto_save_switch)
        features_layout.addLayout(auto_save_layout)

        # Extended mode toggle
        extended_mode_layout = QHBoxLayout()
        extended_mode_info = QVBoxLayout()
        extended_mode_label = BodyLabel("Extended Mode")
        extended_mode_label.setStyleSheet("font-weight: 500;")
        extended_mode_sublabel = CaptionLabel("Enable folder creator and scraper menu")
        extended_mode_sublabel.setStyleSheet(f"color: {COLORS['text_secondary']};")
        extended_mode_info.addWidget(extended_mode_label)
        extended_mode_info.addWidget(extended_mode_sublabel)

        self.extended_mode_switch = SwitchButton()

        extended_mode_layout.addLayout(extended_mode_info)
        extended_mode_layout.addStretch()
        extended_mode_layout.addWidget(self.extended_mode_switch)
        features_layout.addLayout(extended_mode_layout)

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
        theme_title = StrongBodyLabel("Appearance")
        theme_title.setStyleSheet("font-size: 16px;")
        theme_header.addWidget(theme_icon)
        theme_header.addSpacing(12)
        theme_header.addWidget(theme_title)
        theme_header.addStretch()
        theme_layout.addLayout(theme_header)

        # Theme description
        theme_desc = CaptionLabel("Customize the look and feel of the application")
        theme_desc.setStyleSheet(f"color: {COLORS['text_secondary']};")
        theme_layout.addWidget(theme_desc)

        # Theme toggle
        theme_toggle_layout = QHBoxLayout()

        theme_info_layout = QVBoxLayout()
        theme_label = BodyLabel("Dark Theme")
        theme_label.setStyleSheet("font-weight: 500;")
        theme_sublabel = CaptionLabel("Switch between light and dark mode")
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
        paths_title = StrongBodyLabel("File Paths")
        paths_title.setStyleSheet("font-size: 16px;")
        paths_header.addWidget(paths_icon)
        paths_header.addSpacing(12)
        paths_header.addWidget(paths_title)
        paths_header.addStretch()
        paths_layout.addLayout(paths_header)

        # Paths description
        paths_desc = CaptionLabel("Configure file storage locations")
        paths_desc.setStyleSheet(f"color: {COLORS['text_secondary']};")
        paths_layout.addWidget(paths_desc)

        # KROSS path
        kross_path_layout = QVBoxLayout()
        kross_label = BodyLabel("KROSS Images Download Path")
        kross_label.setStyleSheet("font-weight: 500;")

        kross_input_layout = QHBoxLayout()
        self.kross_path_field = LineEdit()
        self.kross_path_field.setReadOnly(True)
        self.kross_path_field.setPlaceholderText("Select folder...")

        kross_browse_btn = PushButton("Browse")
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
        repo_label = BodyLabel("Bicycle Folder Repository Path")
        repo_label.setStyleSheet("font-weight: 500;")

        repo_input_layout = QHBoxLayout()
        self.repo_path_field = LineEdit()
        self.repo_path_field.setReadOnly(True)
        self.repo_path_field.setPlaceholderText("Select folder...")

        repo_browse_btn = PushButton("Browse")
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

        info_title = StrongBodyLabel("About")
        info_title.setStyleSheet("font-size: 16px;")
        info_layout.addWidget(info_title)

        app_name = BodyLabel("UltraBike Product Automation")
        app_name.setStyleSheet(f"color: {COLORS['lavender_grey']};")
        info_layout.addWidget(app_name)

        version = CaptionLabel("Version 2.0 - Qt Edition")
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

        save_btn = PrimaryPushButton("Save All Settings")
        save_btn.setIcon(FluentIcon.SAVE)
        save_btn.setFixedHeight(40)
        save_btn.clicked.connect(self._save_all_settings)

        button_layout.addWidget(save_btn)
        main_layout.addWidget(button_container)

    def _load_settings(self):
        """Load current settings from database"""
        # Load language
        language = self.main.settings.get('language', 'English')
        index = self.language_combo.findText(language)
        if index >= 0:
            self.language_combo.setCurrentIndex(index)

        # Load browser
        browser = self.main.settings.get('browser_choice', 'Chrome')
        index = self.browser_combo.findText(browser)
        if index >= 0:
            self.browser_combo.setCurrentIndex(index)

        # Load feature toggles
        self.download_images_switch.setChecked(self.main.settings.get('download_images', False))
        self.auto_save_switch.setChecked(self.main.settings.get('auto_save', True))
        self.extended_mode_switch.setChecked(self.main.settings.get('extended_mode', True))

        # Load theme
        theme = self.main.settings.get('theme', 'light')
        self.theme_switch.setChecked(theme == 'dark')

        # Load paths
        self.kross_path_field.setText(self.main.settings.get('kross_download_path', ''))
        self.repo_path_field.setText(self.main.settings.get('repository_path', ''))

    def _on_language_change(self, language):
        """Handle language change (no longer auto-saves)"""
        # Language will be saved when user clicks Save button
        pass

    def _update_scroll_style(self):
        """Update scroll area styling based on current theme"""
        is_dark = isDarkTheme()
        bg_color = COLORS['space_indigo'] if is_dark else COLORS['platinum']

        self.scroll.setStyleSheet(f"""
            QScrollArea {{
                border: none;
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
        """Handle theme change (preview only, saved on button click)"""
        from GUI_Qt.styles.global_styles import get_global_stylesheet

        if self._loading:  # Ignore during initial load
            return

        # Apply theme preview immediately for better UX
        if checked:
            setTheme(Theme.DARK)
        else:
            setTheme(Theme.LIGHT)

        # Reapply global stylesheet
        self.main.setStyleSheet(get_global_stylesheet())

        # Update settings screen background - using our color scheme
        bg_color = COLORS['space_indigo'] if checked else COLORS['platinum']
        self.setStyleSheet(f"SettingsScreen {{ background-color: {bg_color}; }}")

        # Update content widget background
        if self.content_widget:
            self.content_widget.setStyleSheet(f"#contentWidget {{ background-color: {bg_color}; }}")

        # Update scroll area styling
        if self.scroll:
            self._update_scroll_style()

        # Update main window containers
        self.main.update_container_backgrounds()

        # Update batch upload screen table if it exists
        if self.main.batch_upload_screen:
            self.main.batch_upload_screen._update_table_theme()

        # Theme will be saved when user clicks Save button

    def _browse_folder(self, setting_key, text_field):
        """Browse for folder (no longer auto-saves)"""
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Folder",
            text_field.text() or ""
        )

        if folder:
            text_field.setText(folder)
            # Path will be saved when user clicks Save button

    def _save_all_settings(self):
        """Save all settings to database"""
        try:
            # Get current values
            language = self.language_combo.currentText()
            browser = self.browser_combo.currentText()
            download_images = self.download_images_switch.isChecked()
            auto_save = self.auto_save_switch.isChecked()
            extended_mode = self.extended_mode_switch.isChecked()
            theme_is_dark = self.theme_switch.isChecked()
            theme_name = 'dark' if theme_is_dark else 'light'
            kross_path = self.kross_path_field.text()
            repo_path = self.repo_path_field.text()

            # Save all to database
            self.main.settings.set('language', language)
            self.main.settings.set('browser_choice', browser)
            self.main.settings.set('download_images', download_images)
            self.main.settings.set('auto_save', auto_save)
            self.main.settings.set('extended_mode', extended_mode)
            self.main.settings.set('theme', theme_name)

            if kross_path:
                self.main.settings.set('kross_download_path', kross_path)
            if repo_path:
                self.main.settings.set('repository_path', repo_path)

            # Show success message
            InfoBar.success(
                title="Settings Saved",
                content="All settings have been saved successfully",
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self
            )

        except Exception as e:
            InfoBar.error(
                title="Save Failed",
                content=f"Failed to save settings: {str(e)}",
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
