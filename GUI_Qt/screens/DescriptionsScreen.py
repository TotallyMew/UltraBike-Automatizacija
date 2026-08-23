"""
Descriptions Screen - Fluent Design System
HTML description editor with list selection and tabbed editing
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QBoxLayout, QToolButton, QFrame,
    QTextEdit, QTabWidget, QPushButton, QInputDialog
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut, QPalette, QColor
from qfluentwidgets import (
    CardWidget, TransparentToolButton, FluentIcon,
    TitleLabel, BodyLabel, CaptionLabel, InfoBar, InfoBarPosition,
    isDarkTheme, PrimaryPushButton, LineEdit, PushButton, ComboBox, qconfig,
    ScrollArea, IconWidget
)
from Managers.DescriptionManager import DescriptionManager
from GUI_Qt.widgets.ResponsiveWidget import ResponsiveWidget
from GUI_Qt.components.dialogs import DestructiveActionDialog, UnsavedChangesDialog
from GUI_Qt.styles.theme_config import (
    COLORS, FONTS, RADII, PADDINGS, get_accent_colors, get_surface_color,
    get_text_color, rgba_from_hex,
)
from GUI_Qt.styles.theme_config import SIZES
from GUI_Qt.styles.screen_theme import (
    PAGE_MARGINS, PAGE_SPACING, ICON_TEXT_GAP, PANEL_MARGINS, CONTENT_SPACING, ROW_SPACING,
    apply_screen_theme, get_responsive_margins, get_responsive_spacing
)


class DescriptionsScreen(ResponsiveWidget):
    """Descriptions management screen with list + tabs layout"""

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main = main_window
        self.desc_manager = DescriptionManager(self.main.db)
        self.current_description_name = None
        self.current_description_folder = ""
        self.available_folders: list[str] = []
        self._folder_sections = {}
        self.has_unsaved_changes = False

        self._editor_containers = []
        self.scroll = None
        self.content_widget = None

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
        # Root layout (for ScrollArea container)
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Create ScrollArea
        self.scroll = ScrollArea(self)
        self.scroll.setWidgetResizable(True)
        root_layout.addWidget(self.scroll)

        # Content widget (inside ScrollArea)
        self.content_widget = QWidget()
        self.scroll.setWidget(self.content_widget)

        # Main layout (on content widget)
        main_layout = QVBoxLayout(self.content_widget)
        main_layout.setContentsMargins(*PAGE_MARGINS)
        main_layout.setSpacing(PAGE_SPACING)

        # Apply theme
        apply_screen_theme(
            self,
            "DescriptionsScreen",
            scroll=self.scroll,
            content=self.content_widget
        )

        # === HEADER ===
        header = QHBoxLayout()

        # Title with icon
        title_container = QHBoxLayout()
        title_container.setSpacing(ICON_TEXT_GAP)

        title_icon = IconWidget(FluentIcon.DOCUMENT)
        title_icon.setFixedSize(SIZES['icon_lg'], SIZES['icon_lg'])

        self.title_label = TitleLabel("")

        title_container.addWidget(title_icon)
        title_container.addWidget(self.title_label)

        header.addLayout(title_container)
        header.addStretch()

        # Current description name
        self.current_name_label = BodyLabel("")
        self.current_name_label.setProperty("ubAllowBg", True)
        self._style_current_name()
        self.current_name_label.setVisible(False)
        header.addWidget(self.current_name_label)

        main_layout.addLayout(header)

        # === MAIN CONTENT (SIDE BY SIDE) ===
        self.content_layout = QHBoxLayout()
        self.content_layout.setSpacing(PAGE_SPACING)

        # LEFT PANEL - Description List
        self.left_panel = CardWidget()
        self.left_panel.setBorderRadius(RADII['md'])
        self.left_panel.setMinimumWidth(SIZES['sidebar_min_width'])

        left_layout = QVBoxLayout(self.left_panel)
        left_layout.setContentsMargins(*PANEL_MARGINS)
        left_layout.setSpacing(CONTENT_SPACING)

        # List header
        list_header = QHBoxLayout()
        self.list_title = BodyLabel("")
        list_title = self.list_title
        list_title.setStyleSheet(f"font-weight: 600; color: {get_text_color(isDarkTheme(), 'secondary')}; background: transparent; background-color: transparent;")

        self.refresh_btn = TransparentToolButton(FluentIcon.SYNC, self)
        self.refresh_btn.setFixedSize(SIZES['icon_action'], SIZES['icon_action'])
        self.refresh_btn.clicked.connect(self._load_description_list)

        self.new_folder_btn = TransparentToolButton(FluentIcon.FOLDER_ADD, self)
        self.new_folder_btn.setFixedSize(SIZES['icon_action'], SIZES['icon_action'])
        self.new_folder_btn.clicked.connect(self._handle_create_folder)

        list_header.addWidget(list_title)
        list_header.addStretch()
        list_header.addWidget(self.new_folder_btn)
        list_header.addWidget(self.refresh_btn)

        left_layout.addLayout(list_header)

        # Description folders + items
        self.description_scroll = ScrollArea(self)
        self.description_scroll.setWidgetResizable(True)
        self.description_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.description_scroll.setFrameShape(QFrame.Shape.NoFrame)

        self.description_list = QWidget()
        self.description_list_layout = QVBoxLayout(self.description_list)
        self.description_list_layout.setContentsMargins(0, 0, 0, 0)
        self.description_list_layout.setSpacing(10)
        self.description_list_layout.addStretch(1)
        self.description_scroll.setWidget(self.description_list)
        self._style_list()

        left_layout.addWidget(self.description_scroll)

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

        self.content_layout.addWidget(self.left_panel, 3)  # 30% of space

        # RIGHT PANEL - Tabs with HTML Editors (with max-width for readability)
        self.right_panel = CardWidget()
        self.right_panel.setBorderRadius(RADII['md'])

        right_layout = QVBoxLayout(self.right_panel)
        right_layout.setContentsMargins(*PANEL_MARGINS)
        right_layout.setSpacing(CONTENT_SPACING)

        # Editable description name
        name_row = QHBoxLayout()
        name_row.setSpacing(ICON_TEXT_GAP)
        self.name_label = BodyLabel("")
        self.name_input = LineEdit(self)
        self.name_input.setClearButtonEnabled(True)
        self.name_input.textChanged.connect(self._on_name_changed)
        name_row.addWidget(self.name_label)
        name_row.addWidget(self.name_input, 1)
        right_layout.addLayout(name_row)

        # Editable description folder (typing a new value creates a new folder grouping)
        folder_row = QHBoxLayout()
        folder_row.setSpacing(ICON_TEXT_GAP)
        self.folder_label = BodyLabel("")
        self.folder_input = ComboBox(self)
        self.folder_input.setAccessibleName(
            self.main.i18n.tr("descriptions.folder.label")
        )
        self.folder_input.currentTextChanged.connect(self._on_folder_changed)
        folder_row.addWidget(self.folder_label)
        folder_row.addWidget(self.folder_input, 1)
        right_layout.addLayout(folder_row)

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

        self.content_layout.addWidget(self.right_panel, 7)  # 70% of space

        main_layout.addLayout(self.content_layout, 1)

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
        warning_label.setStyleSheet(
            f"color: {get_text_color(isDarkTheme(), 'secondary')}; font-weight: 500; "
            "background: transparent; background-color: transparent;"
        )

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
        self.new_folder_btn.setToolTip(tr("descriptions.folder.create.tip"))
        self.new_btn.setText(tr("descriptions.new"))
        self.new_btn.setToolTip(tr("descriptions.new.tip"))
        self.delete_btn.setText(tr("descriptions.delete"))
        self.delete_btn.setToolTip(tr("descriptions.delete.tip"))
        self.save_btn.setText(tr("descriptions.save"))
        self.save_btn.setToolTip(tr("descriptions.save.tip"))
        self.name_label.setText(tr("descriptions.name.label"))
        self.name_input.setPlaceholderText(tr("descriptions.name.placeholder"))
        self.folder_label.setText(tr("descriptions.folder.label"))
        self.folder_input.setAccessibleName(tr("descriptions.folder.label"))

        try:
            self.folder_input.setPlaceholderText(tr("descriptions.folder.placeholder"))
        except Exception:
            pass

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
        bg = get_surface_color(is_dark)
        border = COLORS['border_dark'] if is_dark else COLORS['border_light']
        text = get_text_color(is_dark)
        hover_bg = rgba_from_hex(COLORS['lavender_grey'] if is_dark else COLORS['space_indigo'], 0.16 if is_dark else 0.05)
        accent = get_accent_colors(is_dark)
        self.description_scroll.setStyleSheet(f"""
            ScrollArea {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: {RADII['sm']}px;
                padding: {PADDINGS['xs']};
                font-family: {FONTS['family']};
                font-size: {FONTS['size_body']};
                color: {text};
            }}
            QToolButton[role="folder"] {{
                background: transparent;
                border: none;
                text-align: left;
                padding: 5px 6px;
                font-weight: {FONTS['weight_semibold']};
                font-size: {FONTS['size_body']};
                color: {text};
            }}
            QToolButton[role="folder"]:hover {{
                background-color: {hover_bg};
                border-radius: {RADII['xs']}px;
            }}
            QToolButton[role="folder"]:checked {{
                background-color: {accent['base']};
                color: {accent['text']};
                border-radius: {RADII['xs']}px;
            }}
            QToolButton[role="description"] {{
                background: transparent;
                border: none;
                text-align: left;
                padding: 5px 6px 5px 20px;
                margin-left: 12px;
                color: {text};
                border-radius: {RADII['xs']}px;
            }}
            QToolButton[role="description"]:hover {{
                background-color: {hover_bg};
            }}
            QToolButton[role="description"]:checked {{
                background-color: {accent['base']};
                color: {accent['text']};
                border-radius: {RADII['xs']}px;
            }}
            QFrame[role="folderContent"] {{
                background: transparent;
                margin-left: 4px;
            }}
        """)

    def _style_current_name(self):
        """Style the intentional selected-description badge."""
        accent = get_accent_colors(isDarkTheme())
        self.current_name_label.setStyleSheet(f"""
            background-color: {accent['base']};
            color: {accent['text']};
            padding: {PADDINGS['pill']};
            border-radius: {RADII['sm']}px;
            font-weight: 600;
        """)

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget is not None:
                widget.deleteLater()
            elif child_layout is not None:
                self._clear_layout(child_layout)

    def _set_folder_expanded(self, folder_name: str, expanded: bool):
        section = self._folder_sections.get(folder_name)
        if not section:
            return
        section["content"].setVisible(expanded)
        section["button"].setChecked(expanded)
        section["button"].setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)

    def _toggle_folder(self, folder_name: str):
        section = self._folder_sections.get(folder_name)
        if not section:
            return
        expanded = not section["content"].isVisible()
        self._set_folder_expanded(folder_name, expanded)

    def _select_description_button(self, description_name: str):
        for section in self._folder_sections.values():
            for button in section.get("description_buttons", []):
                button.setChecked(button.property("descriptionName") == description_name)

    def _make_folder_button(self, folder_name: str, display_name: str, expanded: bool):
        button = QToolButton()
        button.setProperty("role", "folder")
        button.setText(display_name)
        button.setCheckable(True)
        button.setChecked(expanded)
        button.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        button.setAutoRaise(True)
        button.clicked.connect(lambda _checked=False, name=folder_name: self._toggle_folder(name))
        return button

    def _make_description_button(self, description_name: str, display_text: str):
        button = QToolButton()
        button.setProperty("role", "description")
        button.setProperty("descriptionName", description_name)
        button.setText(display_text)
        button.setCheckable(True)
        button.setAutoRaise(True)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        button.clicked.connect(lambda _checked=False, name=description_name: self._on_description_clicked(name))
        return button

    def _on_description_clicked(self, description_name: str):
        """Select exactly one description and load it."""
        if description_name == self.current_description_name:
            return
        if not self.request_navigation_away():
            self._select_description_button(self.current_description_name or "")
            return
        self._select_description_button(description_name)
        self._load_description(description_name)

    def _refresh_folder_dropdown(self, selected_folder: str = ""):
        """Refresh folder dropdown with existing folder names."""
        current = (selected_folder or "").strip()
        self.folder_input.blockSignals(True)
        self.folder_input.clear()
        self.folder_input.addItem("")
        for folder_name in self.available_folders:
            self.folder_input.addItem(folder_name)
        if current and current in self.available_folders:
            self.folder_input.setCurrentText(current)
        else:
            self.folder_input.setCurrentIndex(0)
        self.folder_input.blockSignals(False)

    def _style_tabs(self):
        """Apply styling to tab widget"""
        is_dark = isDarkTheme()
        accent = get_accent_colors(is_dark)
        self.tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 1px solid {COLORS['border_dark'] if is_dark else COLORS['border_light']};
                border-radius: {RADII['sm']}px;
                top: -1px;
                background-color: {COLORS['bg_alt_dark'] if is_dark else COLORS['bg_light']};
            }}
            QTabBar::tab {{
                background-color: {COLORS['bg_alt_dark'] if is_dark else COLORS['bg_light']};
                color: {get_text_color(is_dark, 'secondary')};
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
                background-color: {accent['base']};
                color: {accent['text']};
                font-weight: {FONTS['weight_semibold']};
            }}
            QTabBar::tab:hover:!selected {{
                background-color: {rgba_from_hex(COLORS['lavender_grey'], 0.2) if is_dark else rgba_from_hex(COLORS['space_indigo'], 0.1)};
            }}
        """)

    def _load_description_list(self):
        """Load list of saved descriptions"""
        expanded_folders = {
            folder_name
            for folder_name, section in self._folder_sections.items()
            if section["content"].isVisible()
        }

        self._clear_layout(self.description_list_layout)
        self._folder_sections = {}

        try:
            descriptions = self.desc_manager.list_descriptions()
            folder_candidates = {folder.strip() for folder in self.desc_manager.list_folders() if folder and folder.strip()}
            descriptions_by_folder: dict[str, list[dict]] = {}

            for desc in descriptions:
                folder_name = (desc.get('folder') or '').strip()
                if folder_name:
                    folder_candidates.add(folder_name)
                descriptions_by_folder.setdefault(folder_name, []).append(desc)

            folder_order: list[str] = []
            if descriptions_by_folder.get("") or "" in folder_candidates:
                folder_order.append("")

            folder_order.extend(sorted(folder_candidates, key=lambda x: x.lower()))

            for folder_key in folder_order:
                folder_title = folder_key or self.main.i18n.tr("descriptions.folder.uncategorized")
                expanded = folder_key in expanded_folders or self.current_description_folder == folder_key

                folder_widget = QWidget()
                folder_layout = QVBoxLayout(folder_widget)
                folder_layout.setContentsMargins(0, 0, 0, 0)
                folder_layout.setSpacing(4)

                folder_button = self._make_folder_button(folder_key, folder_title, expanded)
                folder_layout.addWidget(folder_button)

                content = QFrame()
                content.setProperty("role", "folderContent")
                content_layout = QVBoxLayout(content)
                content_layout.setContentsMargins(0, 0, 0, 0)
                content_layout.setSpacing(2)

                for desc in descriptions_by_folder.get(folder_key, []):
                    desc_button = self._make_description_button(desc['name'], desc['name'])
                    content_layout.addWidget(desc_button)

                folder_layout.addWidget(content)
                content.setVisible(expanded)

                self.description_list_layout.addWidget(folder_widget)
                self._folder_sections[folder_key] = {
                    "button": folder_button,
                    "content": content,
                    "layout": content_layout,
                    "description_buttons": [
                        content_layout.itemAt(i).widget()
                        for i in range(content_layout.count())
                        if content_layout.itemAt(i).widget() is not None
                    ],
                }

            self._select_description_button(self.current_description_name or "")

            self.available_folders = sorted(folder_candidates, key=lambda x: x.lower())
            self.description_list_layout.addStretch(1)
            current_folder = self.current_description_folder if self.current_description_name else ""
            self._refresh_folder_dropdown(current_folder)

        except Exception as ex:
            InfoBar.error(
                title=self.main.i18n.tr("descriptions.load_failed.title"),
                content=str(ex),
                parent=self,
                position=InfoBarPosition.TOP
            )

    def _on_description_selected(self, item, _column=0):
        """Handle description selection from list"""
        desc_data = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(desc_data, dict):
            return

        name = desc_data['name']

        if self.request_navigation_away():
            self._load_description(name)

    def _load_description(self, name, notify: bool = True):
        """Load description into editors"""
        try:
            desc = self.desc_manager.load_description(name)

            if desc:
                self.current_description_name = name
                self.current_description_folder = desc.get('folder', '') or ''
                self.has_unsaved_changes = False
                self.current_name_label.setVisible(True)
                self.name_input.blockSignals(True)
                self.name_input.setText(name)
                self.name_input.blockSignals(False)
                self._refresh_folder_dropdown(self.current_description_folder)
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

                if notify:
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

    def _on_name_changed(self):
        """Handle editable description name changes."""
        self.has_unsaved_changes = True
        self.save_btn.setEnabled(True)
        self._update_title_indicator()

    def _on_folder_changed(self):
        """Handle editable description folder changes."""
        self.has_unsaved_changes = True
        self.save_btn.setEnabled(True)
        self._update_title_indicator()

    def _update_title_indicator(self):
        """Update title label to show unsaved changes"""
        if not self.current_name_label.isVisible():
            return

        entered_name = self.name_input.text().strip() if hasattr(self, "name_input") else ""

        if self.current_description_name:
            display_name = entered_name or self.current_description_name
            indicator = " *" if self.has_unsaved_changes else ""
            self.current_name_label.setText(
                self.main.i18n.tr(
                    "descriptions.editing",
                    name=display_name,
                    indicator=indicator,
                )
            )
        else:
            if entered_name:
                indicator = " *" if self.has_unsaved_changes else ""
                self.current_name_label.setText(
                    self.main.i18n.tr(
                        "descriptions.editing",
                        name=entered_name,
                        indicator=indicator,
                    )
                )
            else:
                self.current_name_label.setText(self.main.i18n.tr("descriptions.new_indicator"))

    def _handle_new(self):
        """Create new description"""
        if self.has_unsaved_changes and not self.request_navigation_away():
            return
        self._start_new_description(notify=True)

    def _start_new_description(self, notify: bool = True):
        """Reset the editor for a new description."""
        self.current_description_name = None
        self.current_description_folder = ""
        self.has_unsaved_changes = True
        self.current_name_label.setText(self.main.i18n.tr("descriptions.new_indicator"))
        self.current_name_label.setVisible(True)
        self.name_input.blockSignals(True)
        self.name_input.clear()
        self.name_input.blockSignals(False)
        self._refresh_folder_dropdown("")

        # Clear editors
        lt_editor = self.lt_editor.findChild(QTextEdit)
        en_editor = self.en_editor.findChild(QTextEdit)
        lv_editor = self.lv_editor.findChild(QTextEdit)

        lt_editor.clear()
        en_editor.clear()
        lv_editor.clear()

        self.save_btn.setEnabled(True)
        self.delete_btn.setEnabled(False)
        self._select_description_button("")

        if notify:
            InfoBar.success(
                title=self.main.i18n.tr("descriptions.new.title"),
                content=self.main.i18n.tr("descriptions.new.content"),
                parent=self,
                position=InfoBarPosition.TOP,
                duration=2000
            )

    def request_navigation_away(self) -> bool:
        """Offer to save or discard edits before changing context."""
        if not self.has_unsaved_changes:
            return True
        choice = UnsavedChangesDialog.ask(parent=self, tr_func=self.main.i18n.tr)
        if choice == UnsavedChangesDialog.SAVE:
            self._handle_save()
            return not self.has_unsaved_changes
        if choice == UnsavedChangesDialog.DISCARD:
            if self.current_description_name:
                self._load_description(self.current_description_name, notify=False)
            else:
                self._start_new_description(notify=False)
                self.has_unsaved_changes = False
                self.save_btn.setEnabled(False)
                self.current_name_label.setVisible(False)
            return True
        return False

    def _handle_save(self):
        """Save current description"""
        # Get content from editors
        lt_editor = self.lt_editor.findChild(QTextEdit)
        en_editor = self.en_editor.findChild(QTextEdit)
        lv_editor = self.lv_editor.findChild(QTextEdit)

        lt_content = lt_editor.toPlainText().strip()
        en_content = en_editor.toPlainText().strip()
        lv_content = lv_editor.toPlainText().strip()

        target_name = self.name_input.text().strip()
        target_folder = self.folder_input.currentText().strip()
        if not target_name:
            InfoBar.warning(
                title=self.main.i18n.tr("common.warning"),
                content=self.main.i18n.tr("descriptions.name.required"),
                parent=self,
                position=InfoBarPosition.TOP,
                duration=2500,
            )
            return

        original_name = self.current_description_name
        if original_name and target_name != original_name:
            existing = self.desc_manager.load_description(target_name)
            if existing:
                InfoBar.error(
                    title=self.main.i18n.tr("common.error"),
                    content=self.main.i18n.tr("descriptions.name.exists", name=target_name),
                    parent=self,
                    position=InfoBarPosition.TOP,
                    duration=3000,
                )
                return

        # Save to database
        try:
            success = self.desc_manager.save_description(
                target_name,
                lt_content,
                en_content,
                lv_content,
                original_name=original_name,
                folder=target_folder,
            )

            if success:
                self.current_description_name = target_name
                self.current_description_folder = target_folder
                self.has_unsaved_changes = False
                self.delete_btn.setEnabled(True)
                self._update_title_indicator()

                InfoBar.success(
                    title=self.main.i18n.tr("descriptions.saved.title"),
                    content=self.main.i18n.tr("descriptions.saved.content", name=target_name),
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

    def _handle_create_folder(self):
        """Create a folder from the saved descriptions card."""
        folder_name, ok = QInputDialog.getText(
            self,
            self.main.i18n.tr("descriptions.folder.create.title"),
            self.main.i18n.tr("descriptions.folder.create.prompt"),
        )
        if not ok:
            return

        name = (folder_name or "").strip()
        if not name:
            return

        if not self.desc_manager.create_folder(name):
            InfoBar.error(
                title=self.main.i18n.tr("common.error"),
                content=self.main.i18n.tr("descriptions.folder.create.failed"),
                parent=self,
                position=InfoBarPosition.TOP,
                duration=3000,
            )
            return

        self._load_description_list()
        self.folder_input.setCurrentText(name)

        InfoBar.success(
            title=self.main.i18n.tr("common.success"),
            content=self.main.i18n.tr("descriptions.folder.create.success", name=name),
            parent=self,
            position=InfoBarPosition.TOP,
            duration=2000,
        )

    def _handle_delete(self):
        """Delete current description"""
        if not self.current_description_name:
            return

        # Confirm deletion with destructive dialog
        confirmed = DestructiveActionDialog.ask(
            title=self.main.i18n.tr("descriptions.delete_confirm.title"),
            message=self.main.i18n.tr("descriptions.delete_confirm.content", name=self.current_description_name),
            action_text=self.main.i18n.tr("common.delete"),
            parent=self,
            tr_func=self.main.i18n.tr
        )

        if confirmed:
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
        bg_color = get_surface_color(is_dark, 'canvas')

        self.setStyleSheet(f"""
            DescriptionsScreen {{
                background-color: {bg_color};
                font-family: {FONTS['family']};
            }}
        """)

        # Apply styles to list and tabs
        if hasattr(self, 'description_list'):
            self._style_list()

        if hasattr(self, 'current_name_label'):
            self._style_current_name()

        if hasattr(self, 'tabs'):
            self._style_tabs()
            # Update all HTML editors
            for i in range(self.tabs.count()):
                tab = self.tabs.widget(i)
                editor = tab.findChild(QTextEdit)
                if editor:
                    self._style_editor(editor)

        for container in getattr(self, '_editor_containers', []):
            warning_label = getattr(container, '_warning_label', None)
            if warning_label is not None:
                warning_label.setStyleSheet(
                    f"color: {get_text_color(is_dark, 'secondary')}; font-weight: 500; "
                    "background: transparent; background-color: transparent;"
                )

    def _style_editor(self, editor):
        """Apply styling to HTML editor"""
        is_dark = isDarkTheme()
        bg = get_surface_color(is_dark)
        text = get_text_color(is_dark)
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
                palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(COLORS['text_tertiary_dark']))
            else:
                palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(107, 114, 128, 180))
            editor.setPalette(palette)
        except Exception:
            pass

    def _on_breakpoint_changed(self, breakpoint: str):
        """Respond to breakpoint changes - adjust margins and spacing."""
        margins = get_responsive_margins(breakpoint)
        spacing = get_responsive_spacing(breakpoint)
        if hasattr(self, 'content_widget') and self.content_widget and self.content_widget.layout():
            self.content_widget.layout().setContentsMargins(*margins)
            self.content_widget.layout().setSpacing(spacing)
        compact = breakpoint in ("xs", "sm")
        if hasattr(self, "content_layout"):
            self.content_layout.setDirection(
                QBoxLayout.Direction.TopToBottom if compact
                else QBoxLayout.Direction.LeftToRight
            )
            self.content_layout.setSpacing(spacing)
        if hasattr(self, "left_panel"):
            self.left_panel.setMinimumWidth(0 if compact else SIZES['sidebar_min_width'])

    def _on_theme_changed(self):
        """Handle theme change event"""
        apply_screen_theme(
            self,
            "DescriptionsScreen",
            scroll=self.scroll,
            content=self.content_widget
        )
        self._apply_theme()
