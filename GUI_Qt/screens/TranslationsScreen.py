"""
Translations Screen - Fluent Design System
Product name translation management with Space Indigo/Lavender Grey color scheme
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from qfluentwidgets import (
    CardWidget, PushButton, LineEdit, ComboBox, TransparentToolButton,
    FluentIcon, TitleLabel, StrongBodyLabel, BodyLabel, CaptionLabel,
    InfoBar, InfoBarPosition, isDarkTheme, SearchLineEdit,
    PrimaryPushButton, MessageBox, Dialog, qconfig
)
from GUI_Qt.styles.theme_config import COLORS, FONTS


class EditTranslationDialog(MessageBox):
    """Dialog for editing a translation"""

    def __init__(self, brand, original, translation, parent=None):
        super().__init__("Edit Translation", "", parent)
        self.brand = brand
        self.original_text = original
        self.original_translation = translation

        # Clear default content
        self.textLayout.removeWidget(self.contentLabel)
        self.contentLabel.deleteLater()

        # Add custom content
        content_widget = QWidget()
        layout = QVBoxLayout(content_widget)
        layout.setSpacing(12)
        layout.setContentsMargins(0, 0, 0, 0)

        # Brand (read-only)
        brand_label = CaptionLabel("Brand:")
        brand_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        brand_value = BodyLabel(brand)
        brand_value.setStyleSheet(f"""
            background-color: {COLORS['lavender_grey']};
            color: white;
            padding: 6px 12px;
            border-radius: 4px;
            font-weight: 500;
        """)

        # Original (read-only)
        original_label = CaptionLabel("Original Text:")
        original_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        original_value = BodyLabel(original)
        original_value.setStyleSheet(f"""
            background-color: {'rgba(255,255,255,0.05)' if isDarkTheme() else 'rgba(0,0,0,0.03)'};
            padding: 8px 12px;
            border-radius: 6px;
        """)
        original_value.setWordWrap(True)

        # Translation (editable)
        translation_label = CaptionLabel("Lithuanian Translation:")
        translation_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        self.translation_input = LineEdit()
        self.translation_input.setText(translation)
        self.translation_input.setPlaceholderText("Enter translation...")

        layout.addWidget(brand_label)
        layout.addWidget(brand_value)
        layout.addSpacing(8)
        layout.addWidget(original_label)
        layout.addWidget(original_value)
        layout.addSpacing(8)
        layout.addWidget(translation_label)
        layout.addWidget(self.translation_input)

        self.textLayout.addWidget(content_widget)

        # Update buttons
        self.yesButton.setText("Save")
        self.cancelButton.setText("Cancel")

    def get_translation(self):
        """Get the edited translation"""
        return self.translation_input.text().strip()


class AddTranslationDialog(MessageBox):
    """Dialog for adding a new translation"""

    def __init__(self, brands, parent=None):
        super().__init__("Add New Translation", "", parent)

        # Clear default content
        self.textLayout.removeWidget(self.contentLabel)
        self.contentLabel.deleteLater()

        # Add custom content
        content_widget = QWidget()
        layout = QVBoxLayout(content_widget)
        layout.setSpacing(12)
        layout.setContentsMargins(0, 0, 0, 0)

        # Brand selector
        brand_label = CaptionLabel("Brand:")
        brand_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        self.brand_combo = ComboBox()
        self.brand_combo.addItems(brands)
        self.brand_combo.setPlaceholderText("Select brand...")

        # Original text
        original_label = CaptionLabel("Original Text:")
        original_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        self.original_input = LineEdit()
        self.original_input.setPlaceholderText("Enter original product name...")

        # Translation text
        translation_label = CaptionLabel("Lithuanian Translation:")
        translation_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        self.translation_input = LineEdit()
        self.translation_input.setPlaceholderText("Enter translation...")

        layout.addWidget(brand_label)
        layout.addWidget(self.brand_combo)
        layout.addSpacing(8)
        layout.addWidget(original_label)
        layout.addWidget(self.original_input)
        layout.addSpacing(8)
        layout.addWidget(translation_label)
        layout.addWidget(self.translation_input)

        self.textLayout.addWidget(content_widget)

        # Update buttons
        self.yesButton.setText("Add")
        self.cancelButton.setText("Cancel")

    def get_data(self):
        """Get the translation data"""
        return (
            self.brand_combo.currentText(),
            self.original_input.text().strip(),
            self.translation_input.text().strip()
        )


class TranslationsScreen(QWidget):
    """Translations management screen with Fluent Design"""

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main = main_window
        self.current_page = 0
        self.page_size = 20
        self.all_translations = []
        self.filtered_translations = []
        self._init_ui()
        self._load_translations()

        # Connect to theme change signal
        qconfig.themeChangedFinished.connect(self._on_theme_changed)

    def _init_ui(self):
        """Initialize UI with Fluent Design"""
        # Apply background color
        is_dark = isDarkTheme()
        bg_color = COLORS['space_indigo'] if is_dark else COLORS['platinum']

        self.setStyleSheet(f"""
            TranslationsScreen {{
                background-color: {bg_color};
                font-family: {FONTS['family']};
            }}
        """)
        self.setAutoFillBackground(True)

        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 20, 40, 20)  # Fluent standard: 40px sides
        layout.setSpacing(20)

        # === HEADER SECTION ===
        header = QHBoxLayout()

        # Title with icon
        title_container = QHBoxLayout()
        title_container.setSpacing(12)

        title_icon = TransparentToolButton(FluentIcon.LANGUAGE, self)
        title_icon.setFixedSize(32, 32)
        title_icon.setEnabled(False)

        title_label = TitleLabel("Product Translations")

        title_container.addWidget(title_icon)
        title_container.addWidget(title_label)

        header.addLayout(title_container)
        header.addStretch()

        # Statistics badge
        self.stats_label = BodyLabel("0 translations")
        self.stats_label.setStyleSheet(f"""
            background-color: {COLORS['lavender_grey']};
            color: white;
            padding: 6px 16px;
            border-radius: 6px;
            font-weight: 500;
        """)
        header.addWidget(self.stats_label)

        layout.addLayout(header)

        # === TOOLBAR SECTION ===
        toolbar_card = CardWidget()
        toolbar_card.setBorderRadius(8)
        toolbar_layout = QHBoxLayout(toolbar_card)
        toolbar_layout.setContentsMargins(24, 20, 24, 20)  # Fluent standard card padding
        toolbar_layout.setSpacing(16)  # Fluent 4px increment

        # Search bar - flexible width with min/max constraints
        self.search_input = SearchLineEdit()
        self.search_input.setPlaceholderText("Search translations...")
        self.search_input.setMinimumWidth(200)
        self.search_input.setMaximumWidth(400)
        self.search_input.textChanged.connect(self._apply_filters)

        # Brand filter - flexible width
        brand_label = BodyLabel("Brand:")
        brand_label.setStyleSheet(f"color: {COLORS['text_secondary']};")

        self.brand_filter = ComboBox()
        self.brand_filter.addItems([
            "All", "KROSS", "Pinarello", "Basso", "Factor",
            "TREK", "Rondo", "Octane", "Rascal", "Lee Cougan"
        ])
        self.brand_filter.setMinimumWidth(120)
        self.brand_filter.setMaximumWidth(180)
        self.brand_filter.currentTextChanged.connect(self._apply_filters)

        # Add button
        add_btn = PrimaryPushButton("Add Translation")
        add_btn.setIcon(FluentIcon.ADD)
        add_btn.clicked.connect(self._show_add_dialog)

        # Refresh button
        refresh_btn = TransparentToolButton(FluentIcon.SYNC, self)
        refresh_btn.setToolTip("Refresh translations")
        refresh_btn.clicked.connect(self._load_translations)

        toolbar_layout.addWidget(self.search_input)
        toolbar_layout.addWidget(brand_label)
        toolbar_layout.addWidget(self.brand_filter)
        toolbar_layout.addStretch()
        toolbar_layout.addWidget(add_btn)
        toolbar_layout.addWidget(refresh_btn)

        layout.addWidget(toolbar_card)

        # === TABLE ===
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Brand", "Original", "Translation", "Actions"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.table.horizontalHeader().resizeSection(3, 120)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)

        # Apply table styling
        self._update_table_theme()

        # Table container with max-width for better layout on large screens
        table_container = QWidget()
        table_container.setStyleSheet("background: transparent;")
        table_container.setMaximumWidth(1400)
        table_container_layout = QVBoxLayout(table_container)
        table_container_layout.setContentsMargins(0, 0, 0, 0)
        table_container_layout.addWidget(self.table, 1)

        # Center table container
        table_wrapper = QHBoxLayout()
        table_wrapper.addStretch()
        table_wrapper.addWidget(table_container, 1)
        table_wrapper.addStretch()

        layout.addLayout(table_wrapper, 1)

        # === PAGINATION ===
        pagination_card = CardWidget()
        pagination_card.setBorderRadius(8)
        pagination_layout = QHBoxLayout(pagination_card)
        pagination_layout.setContentsMargins(20, 12, 20, 12)
        pagination_layout.setSpacing(12)

        self.page_info = BodyLabel("Page 1 of 1")
        self.page_info.setStyleSheet(f"color: {COLORS['text_secondary']};")

        self.prev_btn = TransparentToolButton(FluentIcon.LEFT_ARROW, self)
        self.prev_btn.setToolTip("Previous page")
        self.prev_btn.clicked.connect(self._prev_page)

        self.next_btn = TransparentToolButton(FluentIcon.RIGHT_ARROW, self)
        self.next_btn.setToolTip("Next page")
        self.next_btn.clicked.connect(self._next_page)

        pagination_layout.addWidget(self.page_info)
        pagination_layout.addStretch()
        pagination_layout.addWidget(self.prev_btn)
        pagination_layout.addWidget(self.next_btn)

        layout.addWidget(pagination_card)

    def _update_table_theme(self):
        """Update table styling based on current theme"""
        is_dark = isDarkTheme()
        bg_color = COLORS['bg_dark'] if is_dark else COLORS['bg_light']
        alt_bg = COLORS['bg_alt_dark'] if is_dark else COLORS['bg_alt_light']
        border_color = COLORS['border_dark'] if is_dark else COLORS['border_light']

        # Header colors: lavender_grey for dark mode, space_indigo for light mode
        header_bg = COLORS['lavender_grey'] if is_dark else COLORS['space_indigo']
        header_text = COLORS['space_indigo'] if is_dark else COLORS['text_white']

        text_color = COLORS['text_primary_dark'] if is_dark else COLORS['text_primary_light']

        self.table.setStyleSheet(f"""
            QTableWidget {{
                background-color: {bg_color};
                border: 1px solid {border_color};
                border-radius: 8px;
                gridline-color: {border_color};
            }}
            QTableWidget::item {{
                padding: 8px;
                color: {text_color};
                border-bottom: 1px solid {border_color};
            }}
            QTableWidget::item:selected {{
                background-color: {COLORS['lavender_grey']};
                color: {COLORS['space_indigo'] if is_dark else COLORS['text_white']};
            }}
            QTableWidget::item:hover {{
                background-color: {'rgba(141, 153, 174, 0.1)' if is_dark else 'rgba(43, 45, 66, 0.05)'};
            }}
            QHeaderView::section {{
                background-color: {header_bg};
                color: {header_text};
                padding: 12px 8px;
                border: none;
                border-bottom: 2px solid {COLORS['lavender_grey'] if is_dark else 'rgba(141, 153, 174, 0.3)'};
                font-weight: 600;
                font-size: 14px;
            }}
            QHeaderView::section:first {{
                border-top-left-radius: 8px;
            }}
            QHeaderView::section:last {{
                border-top-right-radius: 8px;
            }}
        """)

    def _load_translations(self):
        """Load all translations from database"""
        try:
            cursor = self.main.db.conn.cursor()

            # Get all translations
            self.all_translations = cursor.execute("""
                SELECT COALESCE(category, 'Uncategorized'), source_term, target_term
                FROM translations
                ORDER BY category, source_term
            """).fetchall()

            # Update statistics
            self.stats_label.setText(
                f"{len(self.all_translations)} translation{'s' if len(self.all_translations) != 1 else ''}"
            )

            # Apply filters and render
            self._apply_filters()

        except Exception as ex:
            InfoBar.error(
                title="Load Failed",
                content=str(ex),
                parent=self,
                position=InfoBarPosition.TOP
            )

    def _apply_filters(self):
        """Filter translations and reset to first page"""
        search_text = self.search_input.text().lower()
        brand_filter = self.brand_filter.currentText()

        # Filter translations
        self.filtered_translations = []
        for brand, original, translation in self.all_translations:
            # Brand filter
            if brand_filter != "All" and brand != brand_filter:
                continue

            # Search filter
            if search_text and not (
                search_text in original.lower() or
                search_text in translation.lower() or
                search_text in brand.lower()
            ):
                continue

            self.filtered_translations.append((brand, original, translation))

        # Reset to first page
        self.current_page = 0
        self._render_page()

    def _render_page(self):
        """Render current page of translations"""
        # Clear table
        self.table.setRowCount(0)

        # Calculate pagination
        total_pages = max(1, (len(self.filtered_translations) + self.page_size - 1) // self.page_size)
        start_idx = self.current_page * self.page_size
        end_idx = min(start_idx + self.page_size, len(self.filtered_translations))

        # Update page info
        self.page_info.setText(
            f"Page {self.current_page + 1} of {total_pages} ({len(self.filtered_translations)} results)"
        )

        # Enable/disable pagination buttons
        self.prev_btn.setEnabled(self.current_page > 0)
        self.next_btn.setEnabled(self.current_page < total_pages - 1)

        # Populate table
        page_data = self.filtered_translations[start_idx:end_idx]
        for row_idx, (brand, original, translation) in enumerate(page_data):
            self.table.insertRow(row_idx)

            # Brand badge
            brand_item = QTableWidgetItem(brand)
            brand_item.setForeground(QColor(COLORS['lavender_grey']))
            self.table.setItem(row_idx, 0, brand_item)

            # Original text
            original_item = QTableWidgetItem(original)
            self.table.setItem(row_idx, 1, original_item)

            # Translation
            translation_item = QTableWidgetItem(translation)
            self.table.setItem(row_idx, 2, translation_item)

            # Actions
            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(8, 2, 8, 2)
            actions_layout.setSpacing(8)

            edit_btn = TransparentToolButton(FluentIcon.EDIT, self)
            edit_btn.setFixedSize(32, 32)
            edit_btn.setToolTip("Edit translation")
            edit_btn.clicked.connect(lambda checked, b=brand, o=original, t=translation: self._edit_translation(b, o, t))

            delete_btn = TransparentToolButton(FluentIcon.DELETE, self)
            delete_btn.setFixedSize(32, 32)
            delete_btn.setToolTip("Delete translation")
            delete_btn.clicked.connect(lambda checked, b=brand, o=original: self._delete_translation(b, o))

            actions_layout.addWidget(edit_btn)
            actions_layout.addWidget(delete_btn)
            actions_layout.addStretch()

            self.table.setCellWidget(row_idx, 3, actions_widget)
            self.table.setRowHeight(row_idx, 44)

    def _prev_page(self):
        """Go to previous page"""
        if self.current_page > 0:
            self.current_page -= 1
            self._render_page()

    def _next_page(self):
        """Go to next page"""
        total_pages = (len(self.filtered_translations) + self.page_size - 1) // self.page_size
        if self.current_page < total_pages - 1:
            self.current_page += 1
            self._render_page()

    def _show_add_dialog(self):
        """Show dialog to add new translation"""
        brands = ["KROSS", "Pinarello", "Basso", "Factor", "TREK", "Rondo", "Octane", "Rascal", "Lee Cougan"]
        dialog = AddTranslationDialog(brands, self)

        if dialog.exec():
            brand, original, translation = dialog.get_data()

            if not brand or not original or not translation:
                InfoBar.warning(
                    title="Missing Information",
                    content="Please fill in all fields",
                    parent=self,
                    position=InfoBarPosition.TOP
                )
                return

            self._add_translation(brand, original, translation)

    def _add_translation(self, brand, original, translation):
        """Add new translation to database"""
        try:
            cursor = self.main.db.conn.cursor()

            # Check if already exists
            existing = cursor.execute(
                "SELECT 1 FROM translations WHERE category = ? AND source_term = ?",
                (brand, original)
            ).fetchone()

            if existing:
                InfoBar.warning(
                    title="Already Exists",
                    content="This translation already exists",
                    parent=self,
                    position=InfoBarPosition.TOP
                )
                return

            # Insert new translation
            cursor.execute(
                """INSERT INTO translations (source_lang, target_lang, source_term, target_term, category, created_at)
                   VALUES ('en', 'lt', ?, ?, ?, datetime('now'))""",
                (original, translation, brand)
            )
            self.main.db.conn.commit()

            # Reload translations
            self._load_translations()

            InfoBar.success(
                title="Translation Added",
                content=f"Added translation for '{original}'",
                parent=self,
                position=InfoBarPosition.TOP
            )

        except Exception as ex:
            InfoBar.error(
                title="Add Failed",
                content=str(ex),
                parent=self,
                position=InfoBarPosition.TOP
            )

    def _edit_translation(self, brand, original, translation):
        """Show dialog to edit translation"""
        dialog = EditTranslationDialog(brand, original, translation, self)

        if dialog.exec():
            new_translation = dialog.get_translation()

            if not new_translation:
                InfoBar.warning(
                    title="Invalid Input",
                    content="Translation cannot be empty",
                    parent=self,
                    position=InfoBarPosition.TOP
                )
                return

            self._update_translation(brand, original, new_translation)

    def _update_translation(self, brand, original, new_translation):
        """Update translation in database"""
        try:
            cursor = self.main.db.conn.cursor()

            cursor.execute(
                "UPDATE translations SET target_term = ? WHERE category = ? AND source_term = ?",
                (new_translation, brand, original)
            )
            self.main.db.conn.commit()

            # Reload translations
            self._load_translations()

            InfoBar.success(
                title="Translation Updated",
                content=f"Updated translation for '{original}'",
                parent=self,
                position=InfoBarPosition.TOP
            )

        except Exception as ex:
            InfoBar.error(
                title="Update Failed",
                content=str(ex),
                parent=self,
                position=InfoBarPosition.TOP
            )

    def _delete_translation(self, brand, original):
        """Delete translation with confirmation"""
        # Show confirmation dialog
        dialog = MessageBox(
            "Delete Translation",
            f"Are you sure you want to delete the translation for '{original}'?",
            self
        )
        dialog.yesButton.setText("Delete")
        dialog.cancelButton.setText("Cancel")

        if dialog.exec():
            try:
                cursor = self.main.db.conn.cursor()

                cursor.execute(
                    "DELETE FROM translations WHERE category = ? AND source_term = ?",
                    (brand, original)
                )
                self.main.db.conn.commit()

                # Reload translations
                self._load_translations()

                InfoBar.success(
                    title="Translation Deleted",
                    content=f"Deleted translation for '{original}'",
                    parent=self,
                    position=InfoBarPosition.TOP
                )

            except Exception as ex:
                InfoBar.error(
                    title="Delete Failed",
                    content=str(ex),
                    parent=self,
                    position=InfoBarPosition.TOP
                )

    def _on_theme_changed(self):
        """Handle theme change event"""
        is_dark = isDarkTheme()
        bg_color = COLORS['space_indigo'] if is_dark else COLORS['platinum']

        self.setStyleSheet(f"""
            TranslationsScreen {{
                background-color: {bg_color};
                font-family: {FONTS['family']};
            }}
        """)

        # Update table theme
        self._update_table_theme()
