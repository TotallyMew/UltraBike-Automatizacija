"""
Descriptions Screen - Fluent Design System
HTML description editor with list selection and tabbed editing
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QTextEdit, QTabWidget, QPushButton, QInputDialog, QMessageBox as QMsgBox
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from qfluentwidgets import (
    CardWidget, TransparentToolButton, FluentIcon,
    TitleLabel, BodyLabel, CaptionLabel, InfoBar, InfoBarPosition,
    isDarkTheme, PrimaryPushButton, LineEdit, PushButton, qconfig
)
from Managers.DescriptionManager import DescriptionManager
from GUI_Qt.styles.theme_config import COLORS, FONTS


class DescriptionsScreen(QWidget):
    """Descriptions management screen with list + tabs layout"""

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main = main_window
        self.desc_manager = DescriptionManager(self.main.db)
        self.current_description_name = None
        self.has_unsaved_changes = False

        self._editor_containers = []

        self._init_ui()
        self._load_description_list()
        self._setup_shortcuts()

        # Connect to theme change signal
        qconfig.themeChangedFinished.connect(self._on_theme_changed)

    def _setup_shortcuts(self):
        """Setup keyboard shortcuts for common actions"""
        # Ctrl+S to save
        save_shortcut = QShortcut(QKeySequence.StandardKey.Save, self)
        save_shortcut.activated.connect(self._handle_save)

        # Ctrl+N to create new
        new_shortcut = QShortcut(QKeySequence.StandardKey.New, self)
        new_shortcut.activated.connect(self._handle_new)

        # Delete key to delete (when list has focus and item is selected)
        delete_shortcut = QShortcut(QKeySequence.StandardKey.Delete, self)
        delete_shortcut.activated.connect(self._handle_delete_shortcut)

    def _handle_delete_shortcut(self):
        """Handle delete key press - only delete if list has focus and item is selected"""
        if self.description_list.hasFocus() and self.current_description_name:
            self._handle_delete()

    def _init_ui(self):
        """Initialize UI with side-by-side layout"""
        self._apply_theme()
        self.setAutoFillBackground(True)

        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(40, 20, 40, 20)  # Fluent standard: 40px sides
        main_layout.setSpacing(16)

        # === HEADER ===
        header = QHBoxLayout()

        # Title with icon
        title_container = QHBoxLayout()
        title_container.setSpacing(12)

        title_icon = TransparentToolButton(FluentIcon.DOCUMENT, self)
        title_icon.setFixedSize(32, 32)
        title_icon.setEnabled(False)

        self.title_label = TitleLabel("")

        title_container.addWidget(title_icon)
        title_container.addWidget(self.title_label)

        header.addLayout(title_container)
        header.addStretch()

        # Current description name
        is_dark = isDarkTheme()
        self.current_name_label = BodyLabel("")
        self.current_name_label.setStyleSheet(f"""
            background-color: {COLORS['lavender_grey']};
            color: white;
            padding: 8px 16px;
            border-radius: 6px;
            font-weight: 600;
        """)
        self.current_name_label.setVisible(False)
        header.addWidget(self.current_name_label)

        main_layout.addLayout(header)

        # === MAIN CONTENT (SIDE BY SIDE) ===
        content_layout = QHBoxLayout()
        content_layout.setSpacing(16)

        # LEFT PANEL - Description List
        left_panel = CardWidget()
        left_panel.setBorderRadius(8)
        left_panel.setMinimumWidth(250)
        left_panel.setMaximumWidth(350)  # Responsive width instead of fixed

        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(16, 16, 16, 16)
        left_layout.setSpacing(12)

        # List header
        list_header = QHBoxLayout()
        self.list_title = BodyLabel("")
        list_title = self.list_title
        list_title.setStyleSheet(f"font-weight: 600; color: {COLORS['text_secondary']};")

        self.refresh_btn = TransparentToolButton(FluentIcon.SYNC, self)
        self.refresh_btn.setFixedSize(28, 28)
        self.refresh_btn.clicked.connect(self._load_description_list)

        list_header.addWidget(list_title)
        list_header.addStretch()
        list_header.addWidget(self.refresh_btn)

        left_layout.addLayout(list_header)

        # Description list
        self.description_list = QListWidget()
        self.description_list.itemClicked.connect(self._on_description_selected)
        self._style_list()

        left_layout.addWidget(self.description_list)

        # List buttons
        list_btn_layout = QVBoxLayout()
        list_btn_layout.setSpacing(8)

        self.new_btn = PrimaryPushButton("")
        self.new_btn.setIcon(FluentIcon.ADD.icon())
        self.new_btn.clicked.connect(self._handle_new)

        self.delete_btn = PushButton("")
        self.delete_btn.setIcon(FluentIcon.DELETE.icon())
        self.delete_btn.setEnabled(False)
        self.delete_btn.clicked.connect(self._handle_delete)

        list_btn_layout.addWidget(self.new_btn)
        list_btn_layout.addWidget(self.delete_btn)

        left_layout.addLayout(list_btn_layout)

        content_layout.addWidget(left_panel, 3)  # 30% of space

        # RIGHT PANEL - Tabs with HTML Editors (with max-width for readability)
        right_panel = CardWidget()
        right_panel.setBorderRadius(8)
        right_panel.setMaximumWidth(1000)  # Prevent text editors from becoming too wide

        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(16, 16, 16, 16)
        right_layout.setSpacing(12)

        # Editor tabs
        self.tabs = QTabWidget()

        # Lithuanian tab
        self.lt_editor = self._create_html_editor()
        self.tabs.addTab(self.lt_editor, "🇱🇹 Lietuvių")

        # English tab
        self.en_editor = self._create_html_editor()
        self.tabs.addTab(self.en_editor, "🇬🇧 English")

        # Latvian tab
        self.lv_editor = self._create_html_editor()
        self.tabs.addTab(self.lv_editor, "🇱🇻 Latviešu")

        self._style_tabs()

        right_layout.addWidget(self.tabs)

        # Action buttons
        action_layout = QHBoxLayout()
        action_layout.setSpacing(12)

        self.save_btn = PrimaryPushButton("")
        self.save_btn.setIcon(FluentIcon.SAVE.icon())
        self.save_btn.setFixedHeight(36)
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self._handle_save)

        action_layout.addStretch()
        action_layout.addWidget(self.save_btn)

        right_layout.addLayout(action_layout)

        content_layout.addWidget(right_panel, 7)  # 70% of space

        main_layout.addLayout(content_layout, 1)

        self.retranslate_ui()

    def _create_html_editor(self):
        """Create HTML text editor widget"""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Warning message
        warning = QHBoxLayout()
        warning_icon = FluentIcon.INFO.icon()
        warning_label = CaptionLabel("")
        warning_label.setStyleSheet(f"color: {COLORS['lavender_grey']}; font-weight: 500;")

        warning.addWidget(warning_label)
        warning.addStretch()

        layout.addLayout(warning)

        # Text editor
        editor = QTextEdit()
        editor.setPlaceholderText("")
        editor.setAcceptRichText(False)
        editor.textChanged.connect(self._on_content_changed)

        # Store reference for theme updates
        editor.setObjectName("html_editor")

        # Apply styling immediately
        is_dark = isDarkTheme()
        editor.setStyleSheet(f"""
            QTextEdit {{
                background-color: {COLORS['bg_alt_dark'] if is_dark else COLORS['bg_light']};
                color: {COLORS['text_primary_dark'] if is_dark else COLORS['text_primary_light']};
                border: 1px solid {COLORS['border_dark'] if is_dark else COLORS['border_light']};
                border-radius: 6px;
                font-family: {FONTS['family_mono']};
                font-size: 14px;
                line-height: 1.5;
                padding: 12px;
            }}
        """)

        layout.addWidget(editor)

        # Keep references for retranslation
        container._warning_label = warning_label
        container._editor = editor
        self._editor_containers.append(container)

        return container

    def retranslate_ui(self):
        tr = self.main.i18n.tr

        self.title_label.setText(tr("descriptions.title"))
        self.list_title.setText(tr("descriptions.saved"))
        self.refresh_btn.setToolTip(tr("descriptions.refresh"))
        self.new_btn.setText(tr("descriptions.new"))
        self.delete_btn.setText(tr("descriptions.delete"))
        self.save_btn.setText(tr("descriptions.save"))

        for container in getattr(self, '_editor_containers', []):
            warning_label = getattr(container, '_warning_label', None)
            editor = getattr(container, '_editor', None)
            if warning_label is not None:
                warning_label.setText(tr("descriptions.editor.warning"))
            if editor is not None:
                editor.setPlaceholderText(tr("descriptions.editor.placeholder"))

        self._update_title_indicator()

    def _style_list(self):
        """Apply styling to description list"""
        is_dark = isDarkTheme()
        self.description_list.setStyleSheet(f"""
            QListWidget {{
                background-color: {COLORS['bg_dark'] if is_dark else COLORS['bg_light']};
                border: 1px solid {COLORS['border_dark'] if is_dark else COLORS['border_light']};
                border-radius: 6px;
                padding: 4px;
                font-family: {FONTS['family']};
                font-size: {FONTS['size_body']};
                color: {COLORS['text_primary_dark'] if is_dark else COLORS['text_primary_light']};
            }}
            QListWidget::item {{
                padding: 12px;
                border-radius: 4px;
                margin: 2px;
            }}
            QListWidget::item:hover {{
                background-color: {'rgba(141, 153, 174, ' + COLORS['hover_opacity_dark'] + ')' if is_dark else 'rgba(43, 45, 66, ' + COLORS['hover_opacity_light'] + ')'};
            }}
            QListWidget::item:selected {{
                background-color: {COLORS['lavender_grey']};
                color: {COLORS['text_white']};
            }}
        """)

    def _style_tabs(self):
        """Apply styling to tab widget"""
        is_dark = isDarkTheme()
        self.tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 1px solid {COLORS['border_dark'] if is_dark else COLORS['border_light']};
                border-radius: 6px;
                top: -1px;
                background-color: {COLORS['bg_dark'] if is_dark else COLORS['bg_light']};
            }}
            QTabBar::tab {{
                background-color: {COLORS['bg_alt_dark'] if is_dark else COLORS['bg_light']};
                color: {COLORS['text_secondary'] if not is_dark else COLORS['text_primary_dark']};
                padding: 10px 20px;
                border: 1px solid {COLORS['border_dark'] if is_dark else COLORS['border_light']};
                border-bottom: none;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                margin-right: 2px;
                font-family: {FONTS['family']};
                font-size: {FONTS['size_body']};
            }}
            QTabBar::tab:selected {{
                background-color: {COLORS['lavender_grey']};
                color: white;
                font-weight: {FONTS['weight_semibold']};
            }}
            QTabBar::tab:hover:!selected {{
                background-color: {'rgba(141, 153, 174, 0.2)' if is_dark else 'rgba(43, 45, 66, 0.1)'};
            }}
        """)

    def _load_description_list(self):
        """Load list of saved descriptions"""
        self.description_list.clear()

        try:
            descriptions = self.desc_manager.list_descriptions()

            for desc in descriptions:
                item = QListWidgetItem(desc['name'])
                item.setData(Qt.ItemDataRole.UserRole, desc)
                self.description_list.addItem(item)

        except Exception as ex:
            InfoBar.error(
                title=self.main.i18n.tr("descriptions.load_failed.title"),
                content=str(ex),
                parent=self,
                position=InfoBarPosition.TOP
            )

    def _on_description_selected(self, item):
        """Handle description selection from list"""
        desc_data = item.data(Qt.ItemDataRole.UserRole)
        name = desc_data['name']

        self._load_description(name)

    def _load_description(self, name):
        """Load description into editors"""
        try:
            desc = self.desc_manager.load_description(name)

            if desc:
                self.current_description_name = name
                self.has_unsaved_changes = False
                self.current_name_label.setVisible(True)
                self._update_title_indicator()

                # Get editors from tabs
                lt_editor = self.lt_editor.findChild(QTextEdit)
                en_editor = self.en_editor.findChild(QTextEdit)
                lv_editor = self.lv_editor.findChild(QTextEdit)

                # Temporarily disconnect text changed signals to avoid triggering unsaved changes
                lt_editor.textChanged.disconnect(self._on_content_changed)
                en_editor.textChanged.disconnect(self._on_content_changed)
                lv_editor.textChanged.disconnect(self._on_content_changed)

                # Load content
                lt_editor.setPlainText(desc['description_lt'] or "")
                en_editor.setPlainText(desc['description_en'] or "")
                lv_editor.setPlainText(desc['description_lv'] or "")

                # Reconnect signals
                lt_editor.textChanged.connect(self._on_content_changed)
                en_editor.textChanged.connect(self._on_content_changed)
                lv_editor.textChanged.connect(self._on_content_changed)

                self.save_btn.setEnabled(True)
                self.delete_btn.setEnabled(True)

                InfoBar.success(
                    title=self.main.i18n.tr("descriptions.loaded.title"),
                    content=self.main.i18n.tr("descriptions.loaded.content", name=name),
                    parent=self,
                    position=InfoBarPosition.TOP,
                    duration=2000
                )

        except Exception as ex:
            InfoBar.error(
                title=self.main.i18n.tr("descriptions.load_failed.title"),
                content=str(ex),
                parent=self,
                position=InfoBarPosition.TOP
            )

    def _on_content_changed(self):
        """Handle content change in editors"""
        self.has_unsaved_changes = True
        self.save_btn.setEnabled(True)
        self._update_title_indicator()

    def _update_title_indicator(self):
        """Update title label to show unsaved changes"""
        if not self.current_name_label.isVisible():
            return

        if self.current_description_name:
            indicator = " *" if self.has_unsaved_changes else ""
            self.current_name_label.setText(
                self.main.i18n.tr(
                    "descriptions.editing",
                    name=self.current_description_name,
                    indicator=indicator,
                )
            )
        else:
            self.current_name_label.setText(self.main.i18n.tr("descriptions.new_indicator"))

    def _handle_new(self):
        """Create new description"""
        self.current_description_name = None
        self.has_unsaved_changes = True
        self.current_name_label.setText(self.main.i18n.tr("descriptions.new_indicator"))
        self.current_name_label.setVisible(True)

        # Clear editors
        lt_editor = self.lt_editor.findChild(QTextEdit)
        en_editor = self.en_editor.findChild(QTextEdit)
        lv_editor = self.lv_editor.findChild(QTextEdit)

        lt_editor.clear()
        en_editor.clear()
        lv_editor.clear()

        self.save_btn.setEnabled(True)
        self.delete_btn.setEnabled(False)
        self.description_list.clearSelection()

        InfoBar.success(
            title=self.main.i18n.tr("descriptions.new.title"),
            content=self.main.i18n.tr("descriptions.new.content"),
            parent=self,
            position=InfoBarPosition.TOP,
            duration=2000
        )

    def _handle_save(self):
        """Save current description"""
        # Get content from editors
        lt_editor = self.lt_editor.findChild(QTextEdit)
        en_editor = self.en_editor.findChild(QTextEdit)
        lv_editor = self.lv_editor.findChild(QTextEdit)

        lt_content = lt_editor.toPlainText().strip()
        en_content = en_editor.toPlainText().strip()
        lv_content = lv_editor.toPlainText().strip()

        # If new, ask for name
        if not self.current_description_name:
            name, ok = QInputDialog.getText(
                self,
                self.main.i18n.tr("descriptions.save_dialog.title"),
                self.main.i18n.tr("descriptions.save_dialog.prompt"),
                text=""
            )

            if not ok or not name.strip():
                return

            self.current_description_name = name.strip()

        # Save to database
        try:
            success = self.desc_manager.save_description(
                self.current_description_name,
                lt_content,
                en_content,
                lv_content
            )

            if success:
                self.has_unsaved_changes = False
                self.delete_btn.setEnabled(True)
                self._update_title_indicator()

                InfoBar.success(
                    title=self.main.i18n.tr("descriptions.saved.title"),
                    content=self.main.i18n.tr("descriptions.saved.content", name=self.current_description_name),
                    parent=self,
                    position=InfoBarPosition.TOP,
                    duration=2000
                )

                # Reload list
                self._load_description_list()

        except Exception as ex:
            InfoBar.error(
                title=self.main.i18n.tr("descriptions.save_failed.title"),
                content=str(ex),
                parent=self,
                position=InfoBarPosition.TOP
            )

    def _handle_delete(self):
        """Delete current description"""
        if not self.current_description_name:
            return

        # Confirm deletion
        reply = QMsgBox.question(
            self,
            self.main.i18n.tr("descriptions.delete_confirm.title"),
            self.main.i18n.tr("descriptions.delete_confirm.content", name=self.current_description_name),
            QMsgBox.StandardButton.Yes | QMsgBox.StandardButton.No
        )

        if reply == QMsgBox.StandardButton.Yes:
            try:
                success = self.desc_manager.delete_description(self.current_description_name)

                if success:
                    InfoBar.success(
                        title=self.main.i18n.tr("descriptions.deleted.title"),
                        content=self.main.i18n.tr("descriptions.deleted.content", name=self.current_description_name),
                        parent=self,
                        position=InfoBarPosition.TOP,
                        duration=2000
                    )

                    # Reset and reload
                    self._handle_new()
                    self._load_description_list()

            except Exception as ex:
                InfoBar.error(
                    title=self.main.i18n.tr("descriptions.delete_failed.title"),
                    content=str(ex),
                    parent=self,
                    position=InfoBarPosition.TOP
                )

    def _apply_theme(self):
        """Apply theme to screen components"""
        is_dark = isDarkTheme()
        bg_color = COLORS['space_indigo'] if is_dark else COLORS['platinum']

        self.setStyleSheet(f"""
            DescriptionsScreen {{
                background-color: {bg_color};
                font-family: {FONTS['family']};
            }}
        """)

        # Apply styles to list and tabs
        if hasattr(self, 'description_list'):
            self._style_list()

        if hasattr(self, 'tabs'):
            self._style_tabs()
            # Update all HTML editors
            for i in range(self.tabs.count()):
                tab = self.tabs.widget(i)
                editor = tab.findChild(QTextEdit)
                if editor:
                    self._style_editor(editor)

    def _style_editor(self, editor):
        """Apply styling to HTML editor"""
        is_dark = isDarkTheme()
        editor.setStyleSheet(f"""
            QTextEdit {{
                background-color: {COLORS['bg_alt_dark'] if is_dark else COLORS['bg_light']};
                color: {COLORS['text_primary_dark'] if is_dark else COLORS['text_primary_light']};
                border: 1px solid {COLORS['border_dark'] if is_dark else COLORS['border_light']};
                border-radius: 6px;
                font-family: {FONTS['family_mono']};
                font-size: 13px;
                line-height: 1.5;
                padding: 12px;
            }}
        """)

    def _on_theme_changed(self):
        """Handle theme change event"""
        self._apply_theme()
