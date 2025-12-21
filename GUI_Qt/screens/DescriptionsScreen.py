"""
Descriptions Screen - Fluent Design System
HTML description editor with list selection and tabbed editing
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QTextEdit, QTabWidget, QPushButton, QInputDialog, QMessageBox as QMsgBox
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut, QPalette, QColor
from qfluentwidgets import (
    CardWidget, TransparentToolButton, FluentIcon,
    TitleLabel, BodyLabel, CaptionLabel, InfoBar, InfoBarPosition,
    isDarkTheme, PrimaryPushButton, LineEdit, PushButton, qconfig
)
from Managers.DescriptionManager import DescriptionManager
from GUI_Qt.styles.theme_config import COLORS, FONTS, RADII, PADDINGS, rgba_from_hex
from GUI_Qt.styles.theme_config import SIZES
from GUI_Qt.styles.screen_theme import PAGE_MARGINS, PAGE_SPACING, ICON_TEXT_GAP, PANEL_MARGINS, CONTENT_SPACING, ROW_SPACING


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

        # Retranslate when app language changes.
        if hasattr(self.main, "i18n"):
            try:
                self.main.i18n.languageChanged.connect(lambda _c: self.retranslate_ui())
            except Exception:
                pass

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
        main_layout.setContentsMargins(*PAGE_MARGINS)
        main_layout.setSpacing(PAGE_SPACING)

        # === HEADER ===
        header = QHBoxLayout()

        # Title with icon
        title_container = QHBoxLayout()
        title_container.setSpacing(ICON_TEXT_GAP)

        title_icon = TransparentToolButton(FluentIcon.DOCUMENT, self)
        title_icon.setFixedSize(SIZES['icon_lg'], SIZES['icon_lg'])
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
            padding: {PADDINGS['pill']};
            border-radius: {RADII['sm']}px;
            font-weight: 600;
        """)
        self.current_name_label.setVisible(False)
        header.addWidget(self.current_name_label)

        main_layout.addLayout(header)

        # === MAIN CONTENT (SIDE BY SIDE) ===
        content_layout = QHBoxLayout()
        content_layout.setSpacing(PAGE_SPACING)

        # LEFT PANEL - Description List
        left_panel = CardWidget()
        left_panel.setBorderRadius(RADII['md'])
        left_panel.setMinimumWidth(SIZES['sidebar_min_width'])

        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(*PANEL_MARGINS)
        left_layout.setSpacing(CONTENT_SPACING)

        # List header
        list_header = QHBoxLayout()
        self.list_title = BodyLabel("")
        list_title = self.list_title
        list_title.setStyleSheet(f"font-weight: 600; color: {COLORS['text_secondary']};")

        self.refresh_btn = TransparentToolButton(FluentIcon.SYNC, self)
        self.refresh_btn.setFixedSize(SIZES['icon_action'], SIZES['icon_action'])
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
        list_btn_layout.setSpacing(ROW_SPACING)

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
        right_panel.setBorderRadius(RADII['md'])

        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(*PANEL_MARGINS)
        right_layout.setSpacing(CONTENT_SPACING)

        # Editor tabs
        self.tabs = QTabWidget()

        # Lithuanian tab
        self.lt_editor = self._create_html_editor()
        self.tabs.addTab(self.lt_editor, "")

        # English tab
        self.en_editor = self._create_html_editor()

        self.tabs.addTab(self.en_editor, "")

        # Latvian tab
        self.lv_editor = self._create_html_editor()
        self.tabs.addTab(self.lv_editor, "")

        self._style_tabs()

        right_layout.addWidget(self.tabs)

        # Action buttons
        action_layout = QHBoxLayout()
        action_layout.setSpacing(CONTENT_SPACING)

        self.save_btn = PrimaryPushButton("")
        self.save_btn.setIcon(FluentIcon.SAVE.icon())
        self.save_btn.setFixedHeight(SIZES['button_height_sm'])
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
        layout.setSpacing(ROW_SPACING)

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
        self._style_editor(editor)

        layout.addWidget(editor)

        # Keep references for retranslation
        container._warning_label = warning_label
        container._editor = editor
        self._editor_containers.append(container)

        return container

    def retranslate_ui(self):
        tr = self.main.i18n.tr

        # Tab titles
        try:
            self.tabs.setTabText(0, tr("descriptions.tab.lt"))
            self.tabs.setTabText(1, tr("descriptions.tab.en"))
            self.tabs.setTabText(2, tr("descriptions.tab.lv"))
        except Exception:
            pass

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
        bg = COLORS['lavender_grey'] if is_dark else COLORS['bg_light']
        border = COLORS['border_dark'] if is_dark else COLORS['border_light']
        text = COLORS['space_indigo'] if is_dark else COLORS['text_primary_light']
        hover_bg = rgba_from_hex(COLORS['space_indigo'], 0.12 if is_dark else 0.05)
        self.description_list.setStyleSheet(f"""
            QListWidget {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: {RADII['sm']}px;
                padding: {PADDINGS['xs']};
                font-family: {FONTS['family']};
                font-size: {FONTS['size_body']};
                color: {text};
            }}
            QListWidget::item {{
                padding: {PADDINGS['table_header']};
                border-radius: {RADII['xs']}px;
                margin: 2px;
            }}
            QListWidget::item:hover {{
                background-color: {hover_bg};
            }}
            QListWidget::item:selected {{
                background-color: {COLORS['space_indigo']};
                color: {COLORS['text_white']};
            }}
        """)

    def _style_tabs(self):
        """Apply styling to tab widget"""
        is_dark = isDarkTheme()
        self.tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 1px solid {COLORS['border_dark'] if is_dark else COLORS['border_light']};
                border-radius: {RADII['sm']}px;
                top: -1px;
                background-color: {COLORS['bg_alt_dark'] if is_dark else COLORS['bg_light']};
            }}
            QTabBar::tab {{
                background-color: {COLORS['bg_alt_dark'] if is_dark else COLORS['bg_light']};
                color: {COLORS['text_secondary'] if not is_dark else COLORS['text_primary_dark']};
                padding: {PADDINGS['tab']};
                border: 1px solid {COLORS['border_dark'] if is_dark else COLORS['border_light']};
                border-bottom: none;
                border-top-left-radius: {RADII['sm']}px;
                border-top-right-radius: {RADII['sm']}px;
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
                background-color: {rgba_from_hex(COLORS['lavender_grey'], 0.2) if is_dark else rgba_from_hex(COLORS['space_indigo'], 0.1)};
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
        bg = COLORS['lavender_grey'] if is_dark else COLORS['bg_light']
        text = COLORS['space_indigo'] if is_dark else COLORS['text_primary_light']
        border = COLORS['border_dark'] if is_dark else COLORS['border_light']
        editor.setStyleSheet(f"""
            QTextEdit {{
                background-color: {bg};
                color: {text};
                border: 1px solid {border};
                border-radius: {RADII['sm']}px;
                font-family: {FONTS['family_mono']};
                font-size: {FONTS['size_body_sm']};
                line-height: 1.5;
                padding: {PADDINGS['table_header']};
            }}
        """)

        # Improve placeholder readability (Qt uses palette role PlaceholderText).
        try:
            palette = editor.palette()
            if is_dark:
                palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(43, 45, 66, 140))
            else:
                palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(107, 114, 128, 180))
            editor.setPalette(palette)
        except Exception:
            pass

    def _on_theme_changed(self):
        """Handle theme change event"""
        self._apply_theme()
