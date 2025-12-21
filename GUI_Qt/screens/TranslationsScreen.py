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
    PrimaryPushButton, MessageBox, Dialog, IconWidget, qconfig
)
from GUI_Qt.styles.theme_config import COLORS, FONTS, RADII, PADDINGS, SIZES, rgba_from_hex
from GUI_Qt.styles.screen_theme import (
    PAGE_MARGINS,
    PAGE_SPACING,
    CARD_MARGINS,
    CARD_SPACING,
    ICON_TEXT_GAP,
    FOOTER_MARGINS,
    CONTENT_SPACING,
    ROW_SPACING,
    MICRO_SPACING,
)


class EditTranslationDialog(MessageBox):
    """Dialog for editing a translation"""

    def __init__(self, categories, category, original, translation, parent=None, tr=None):
        self.tr = tr or (lambda k, **kw: k.format(**kw) if kw else k)
        super().__init__(self.tr("translations.edit_dialog.title"), "", parent)
        self.categories = categories or []
        self.original_category = category
        self.original_text = original
        self.original_translation = translation

        # Clear default content
        self.textLayout.removeWidget(self.contentLabel)
        self.contentLabel.deleteLater()

        # Add custom content
        content_widget = QWidget()
        layout = QVBoxLayout(content_widget)
        layout.setSpacing(CONTENT_SPACING)
        layout.setContentsMargins(0, 0, 0, 0)

        # Category (editable)
        category_label = CaptionLabel(self.tr("translations.edit_dialog.category"))
        category_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        self.category_combo = ComboBox()
        self.category_combo.addItems(self.categories)
        if category:
            idx = self.category_combo.findText(category)
            if idx >= 0:
                self.category_combo.setCurrentIndex(idx)

        # Base word (editable)
        base_label = CaptionLabel(self.tr("translations.edit_dialog.base"))
        base_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        self.base_input = LineEdit()
        self.base_input.setText(original)
        self.base_input.setPlaceholderText(self.tr("translations.edit_dialog.base.placeholder"))

        # Translation (editable)
        translation_label = CaptionLabel(self.tr("translations.translation"))
        translation_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        self.translation_input = LineEdit()
        self.translation_input.setText(translation)
        self.translation_input.setPlaceholderText(self.tr("translations.translation.placeholder"))

        layout.addWidget(category_label)
        layout.addWidget(self.category_combo)
        layout.addSpacing(ROW_SPACING)
        layout.addWidget(base_label)
        layout.addWidget(self.base_input)
        layout.addSpacing(ROW_SPACING)
        layout.addWidget(translation_label)
        layout.addWidget(self.translation_input)

        self.textLayout.addWidget(content_widget)

        # Update buttons
        self.yesButton.setText(self.tr("translations.dialog.save"))
        self.cancelButton.setText(self.tr("translations.dialog.cancel"))

    def get_data(self):
        """Get the edited translation data."""
        return (
            self.category_combo.currentText().strip(),
            self.base_input.text().strip(),
            self.translation_input.text().strip(),
        )


class AddTranslationDialog(MessageBox):
    """Dialog for adding a new translation"""

    def __init__(self, categories, parent=None, tr=None):
        self.tr = tr or (lambda k, **kw: k.format(**kw) if kw else k)
        super().__init__(self.tr("translations.add_dialog.title"), "", parent)

        # Clear default content
        self.textLayout.removeWidget(self.contentLabel)
        self.contentLabel.deleteLater()

        # Add custom content
        content_widget = QWidget()
        layout = QVBoxLayout(content_widget)
        layout.setSpacing(CONTENT_SPACING)
        layout.setContentsMargins(0, 0, 0, 0)

        # Category selector
        category_label = CaptionLabel(self.tr("translations.add_dialog.category"))
        category_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        self.category_combo = ComboBox()
        self.category_combo.addItems(categories)
        self.category_combo.setPlaceholderText(self.tr("translations.brand.placeholder"))

        # Original text
        original_label = CaptionLabel(self.tr("translations.original"))
        original_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        self.original_input = LineEdit()
        self.original_input.setPlaceholderText(self.tr("translations.original.placeholder"))

        # Translation text
        translation_label = CaptionLabel(self.tr("translations.translation"))
        translation_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        self.translation_input = LineEdit()
        self.translation_input.setPlaceholderText(self.tr("translations.translation.placeholder"))

        layout.addWidget(category_label)
        layout.addWidget(self.category_combo)
        layout.addSpacing(ROW_SPACING)
        layout.addWidget(original_label)
        layout.addWidget(self.original_input)
        layout.addSpacing(ROW_SPACING)
        layout.addWidget(translation_label)
        layout.addWidget(self.translation_input)

        self.textLayout.addWidget(content_widget)

        # Update buttons
        self.yesButton.setText(self.tr("translations.dialog.add"))
        self.cancelButton.setText(self.tr("translations.dialog.cancel"))

    def get_data(self):
        """Get the translation data"""
        return (
            self.category_combo.currentText(),
            self.original_input.text().strip(),
            self.translation_input.text().strip()
        )


class TranslationsScreen(QWidget):
    """Translations management screen with Fluent Design"""

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main = main_window
        self._FILTER_ALL = "__all__"
        # Canonical translation categories used by scrapers/translation logic.
        # Legacy values (e.g. brand names like "KROSS") can exist in older DBs;
        # we intentionally hide them from the UI to avoid confusion.
        self._CATEGORY_UNCATEGORIZED = "Uncategorized"
        self._ALLOWED_CATEGORIES = ["component", "material", "color", "property"]
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
        layout.setContentsMargins(*PAGE_MARGINS)
        layout.setSpacing(PAGE_SPACING)

        # === HEADER SECTION ===
        header = QHBoxLayout()

        # Title with icon
        title_container = QHBoxLayout()
        title_container.setSpacing(ICON_TEXT_GAP)

        title_icon = IconWidget(FluentIcon.LANGUAGE)
        title_icon.setFixedSize(SIZES['icon_lg'], SIZES['icon_lg'])

        self.title_label = TitleLabel("")

        title_container.addWidget(title_icon)
        title_container.addWidget(self.title_label)

        header.addLayout(title_container)
        header.addStretch()

        # Statistics badge
        self.stats_label = BodyLabel("")
        self.stats_label.setProperty("ubAllowBg", True)
        self.stats_label.setStyleSheet(f"""
            background-color: {COLORS['lavender_grey']};
            color: white;
            padding: {PADDINGS['badge']};
            border-radius: {RADII['sm']}px;
            font-weight: 500;
        """)
        header.addWidget(self.stats_label)

        layout.addLayout(header)

        # === TOOLBAR SECTION ===
        toolbar_card = CardWidget()
        toolbar_card.setBorderRadius(RADII['md'])
        toolbar_layout = QHBoxLayout(toolbar_card)
        toolbar_layout.setContentsMargins(*CARD_MARGINS)
        toolbar_layout.setSpacing(CARD_SPACING)

        # Search bar - flexible width with min/max constraints
        self.search_input = SearchLineEdit()
        self.search_input.setPlaceholderText("")
        self.search_input.setMinimumWidth(SIZES['field_min_width_md'])
        self.search_input.textChanged.connect(self._apply_filters)

        # Brand filter - flexible width
        self.brand_label = BodyLabel("")
        brand_label = self.brand_label
        brand_label.setStyleSheet(f"color: {COLORS['text_secondary']};")

        self.brand_filter = ComboBox()
        self._populate_brand_filter()
        self.brand_filter.setMinimumWidth(SIZES['field_min_width_sm'])
        self.brand_filter.currentTextChanged.connect(self._apply_filters)

        # Add button
        self.add_btn = PrimaryPushButton("")
        self.add_btn.setIcon(FluentIcon.ADD.icon())
        self.add_btn.clicked.connect(self._show_add_dialog)

        # Refresh button
        self.refresh_btn = TransparentToolButton(FluentIcon.SYNC, self)
        self.refresh_btn.clicked.connect(self._load_translations)

        toolbar_layout.addWidget(self.search_input)
        toolbar_layout.addWidget(brand_label)
        toolbar_layout.addWidget(self.brand_filter)
        toolbar_layout.addStretch()
        toolbar_layout.addWidget(self.add_btn)
        toolbar_layout.addWidget(self.refresh_btn)

        layout.addWidget(toolbar_card)

        # === TABLE ===
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["", "", "", ""])
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
        pagination_card.setBorderRadius(RADII['md'])
        pagination_layout = QHBoxLayout(pagination_card)
        pagination_layout.setContentsMargins(*FOOTER_MARGINS)
        pagination_layout.setSpacing(CONTENT_SPACING)

        self.page_info = BodyLabel("")
        self.page_info.setStyleSheet(f"color: {COLORS['text_secondary']};")

        self.prev_btn = TransparentToolButton(FluentIcon.LEFT_ARROW, self)
        self.prev_btn.clicked.connect(self._prev_page)

        self.next_btn = TransparentToolButton(FluentIcon.RIGHT_ARROW, self)
        self.next_btn.clicked.connect(self._next_page)

        pagination_layout.addWidget(self.page_info)
        pagination_layout.addStretch()
        pagination_layout.addWidget(self.prev_btn)
        pagination_layout.addWidget(self.next_btn)

        layout.addWidget(pagination_card)

        self.retranslate_ui()

    def _category_options(self) -> list[str]:
        """Return the category/type options shown in the UI."""
        return [*self._ALLOWED_CATEGORIES, self._CATEGORY_UNCATEGORIZED]

    def _populate_brand_filter(self):
        tr = self.main.i18n.tr
        current = self.brand_filter.currentData() if hasattr(self, 'brand_filter') else None

        self.brand_filter.blockSignals(True)
        self.brand_filter.clear()
        self.brand_filter.addItem(tr("common.all"), self._FILTER_ALL)
        for cat in self._category_options():
            self.brand_filter.addItem(cat, cat)
        if current is not None:
            idx = self.brand_filter.findData(current)
            if idx >= 0:
                self.brand_filter.setCurrentIndex(idx)
        self.brand_filter.blockSignals(False)

    def _translations_plural_suffix(self, count: int) -> str:
        code = getattr(self.main.i18n.language, 'code', 'en')
        if code == 'lt':
            return 's' if count == 1 else 'i'
        return '' if count == 1 else 's'

    def retranslate_ui(self):
        tr = self.main.i18n.tr

        self.title_label.setText(tr("translations.title"))
        self.search_input.setPlaceholderText(tr("translations.search.placeholder"))
        self.brand_label.setText(tr("translations.brand"))
        self.add_btn.setText(tr("translations.add"))
        self.refresh_btn.setToolTip(tr("translations.refresh"))
        self.prev_btn.setToolTip(tr("common.previous_page"))
        self.next_btn.setToolTip(tr("common.next_page"))

        self.table.setHorizontalHeaderLabels([
            tr("translations.table.brand"),
            tr("translations.table.original"),
            tr("translations.table.translation"),
            tr("translations.table.actions"),
        ])

        self._populate_brand_filter()
        self._render_page()

    def _update_table_theme(self):
        """Update table styling based on current theme"""
        is_dark = isDarkTheme()
        bg_color = COLORS['bg_alt_dark'] if is_dark else COLORS['bg_light']
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
                border-radius: {RADII['md']}px;
                gridline-color: {border_color};
            }}
            QTableWidget::item {{
                padding: {PADDINGS['table_cell']};
                color: {text_color};
                border-bottom: 1px solid {border_color};
            }}
            QTableWidget::item:selected {{
                background-color: {COLORS['lavender_grey']};
                color: {COLORS['space_indigo'] if is_dark else COLORS['text_white']};
            }}
            QTableWidget::item:hover {{
                background-color: {rgba_from_hex(COLORS['lavender_grey'], 0.1) if is_dark else rgba_from_hex(COLORS['space_indigo'], 0.05)};
            }}
            QHeaderView::section {{
                background-color: {header_bg};
                color: {header_text};
                padding: {PADDINGS['table_header']};
                border: none;
                border-bottom: 2px solid {COLORS['lavender_grey'] if is_dark else rgba_from_hex(COLORS['lavender_grey'], 0.3)};
                font-weight: 600;
                font-size: {FONTS['size_body']};
            }}
            QHeaderView::section:first {{
                border-top-left-radius: {RADII['md']}px;
            }}
            QHeaderView::section:last {{
                border-top-right-radius: {RADII['md']}px;
            }}
        """)

    def _load_translations(self):
        """Load all translations from database"""
        try:
            cursor = self.main.db.conn.cursor()

            # Get only canonical categories (plus NULL/legacy Uncategorized).
            # This prevents brand names (e.g. "KROSS") from showing up as a "type".
            allowed = [*self._ALLOWED_CATEGORIES, self._CATEGORY_UNCATEGORIZED]
            placeholders = ",".join(["?"] * len(allowed))
            self.all_translations = cursor.execute(
                f"""
                SELECT id,
                       COALESCE(category, '{self._CATEGORY_UNCATEGORIZED}') AS category,
                       source_term,
                       target_term
                FROM translations
                WHERE category IS NULL OR category IN ({placeholders})
                ORDER BY category, source_term
                """,
                allowed,
            ).fetchall()

            # Update statistics
            count = len(self.all_translations)
            self.stats_label.setText(
                self.main.i18n.tr("translations.stats", count=count, plural=self._translations_plural_suffix(count))
            )

            # Apply filters and render
            self._apply_filters()

        except Exception as ex:
            InfoBar.error(
                title=self.main.i18n.tr("translations.load_failed.title"),
                content=str(ex),
                parent=self,
                position=InfoBarPosition.TOP
            )

    def _apply_filters(self):
        """Filter translations and reset to first page"""
        search_text = self.search_input.text().lower()
        brand_filter = self.brand_filter.currentData()

        # Filter translations
        self.filtered_translations = []
        for row in self.all_translations:
            tid, category, original, translation = row
            # Brand filter
            if brand_filter and brand_filter != self._FILTER_ALL and category != brand_filter:
                continue

            # Search filter
            if search_text and not (
                search_text in original.lower() or
                search_text in translation.lower() or
                search_text in category.lower()
            ):
                continue

            self.filtered_translations.append((tid, category, original, translation))

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
            self.main.i18n.tr(
                "translations.page",
                current=self.current_page + 1,
                total=total_pages,
                results=len(self.filtered_translations),
            )
        )

        # Enable/disable pagination buttons
        self.prev_btn.setEnabled(self.current_page > 0)
        self.next_btn.setEnabled(self.current_page < total_pages - 1)

        # Populate table
        page_data = self.filtered_translations[start_idx:end_idx]
        for row_idx, (tid, category, original, translation) in enumerate(page_data):
            self.table.insertRow(row_idx)

            # Category badge
            brand_item = QTableWidgetItem(category)
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
            actions_layout.setContentsMargins(ROW_SPACING, MICRO_SPACING, ROW_SPACING, MICRO_SPACING)
            actions_layout.setSpacing(ROW_SPACING)

            edit_btn = TransparentToolButton(FluentIcon.EDIT, self)
            edit_btn.setFixedSize(SIZES['icon_lg'], SIZES['icon_lg'])
            edit_btn.setToolTip(self.main.i18n.tr("translations.edit.tip"))
            edit_btn.clicked.connect(lambda checked, _id=tid: self._edit_translation(_id))

            delete_btn = TransparentToolButton(FluentIcon.DELETE, self)
            delete_btn.setFixedSize(SIZES['icon_lg'], SIZES['icon_lg'])
            delete_btn.setToolTip(self.main.i18n.tr("translations.delete.tip"))
            delete_btn.clicked.connect(lambda checked, _id=tid, o=original: self._delete_translation(_id, o))

            actions_layout.addWidget(edit_btn)
            actions_layout.addWidget(delete_btn)
            actions_layout.addStretch()

            self.table.setCellWidget(row_idx, 3, actions_widget)
            self.table.setRowHeight(row_idx, SIZES['table_row_height'])

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
        dialog = AddTranslationDialog(self._category_options(), self, tr=self.main.i18n.tr)

        if dialog.exec():
            category, original, translation = dialog.get_data()

            if not category or not original or not translation:
                InfoBar.warning(
                    title=self.main.i18n.tr("translations.missing.title"),
                    content=self.main.i18n.tr("translations.missing.content"),
                    parent=self,
                    position=InfoBarPosition.TOP
                )
                return

            self._add_translation(category, original, translation)

    def _add_translation(self, category, original, translation):
        """Add new translation to database"""
        try:
            cursor = self.main.db.conn.cursor()

            # Check if already exists
            existing = cursor.execute(
                "SELECT 1 FROM translations WHERE source_lang = 'EN' AND target_lang = 'LT' AND source_term = ?",
                (original,)
            ).fetchone()

            if existing:
                InfoBar.warning(
                    title=self.main.i18n.tr("translations.exists.title"),
                    content=self.main.i18n.tr("translations.exists.content"),
                    parent=self,
                    position=InfoBarPosition.TOP
                )
                return

            # Insert new translation
            cursor.execute(
                """INSERT INTO translations (source_lang, target_lang, source_term, target_term, category, created_at)
                   VALUES ('EN', 'LT', ?, ?, ?, datetime('now'))""",
                (original, translation, category)
            )
            self.main.db.conn.commit()

            # Reload translations
            self._load_translations()

            InfoBar.success(
                title=self.main.i18n.tr("translations.added.title"),
                content=self.main.i18n.tr("translations.added.content", original=original),
                parent=self,
                position=InfoBarPosition.TOP
            )

        except Exception as ex:
            InfoBar.error(
                title=self.main.i18n.tr("translations.add_failed.title"),
                content=str(ex),
                parent=self,
                position=InfoBarPosition.TOP
            )

    def _edit_translation(self, translation_id: int):
        """Show dialog to edit translation"""
        try:
            cursor = self.main.db.conn.cursor()
            row = cursor.execute(
                "SELECT id, COALESCE(category, 'Uncategorized') AS category, source_term, target_term FROM translations WHERE id = ?",
                (translation_id,)
            ).fetchone()
            if not row:
                return

            categories = self._category_options()

            dialog = EditTranslationDialog(
                categories,
                row["category"],
                row["source_term"],
                row["target_term"],
                self,
                tr=self.main.i18n.tr,
            )

            if not dialog.exec():
                return

            new_category, new_base, new_translation = dialog.get_data()
            if not new_category or not new_base or not new_translation:
                InfoBar.warning(
                    title=self.main.i18n.tr("translations.invalid.title"),
                    content=self.main.i18n.tr("translations.invalid.content"),
                    parent=self,
                    position=InfoBarPosition.TOP
                )
                return

            # Uniqueness is on (source_lang,target_lang,source_term) - guard collisions.
            existing = cursor.execute(
                """SELECT 1 FROM translations
                   WHERE source_lang = 'EN' AND target_lang = 'LT' AND source_term = ? AND id != ?""",
                (new_base, translation_id),
            ).fetchone()
            if existing:
                InfoBar.warning(
                    title=self.main.i18n.tr("translations.exists.title"),
                    content=self.main.i18n.tr("translations.exists.content"),
                    parent=self,
                    position=InfoBarPosition.TOP
                )
                return

            cursor.execute(
                "UPDATE translations SET category = ?, source_term = ?, target_term = ? WHERE id = ?",
                (new_category, new_base, new_translation, translation_id),
            )
            self.main.db.conn.commit()

            self._load_translations()

            InfoBar.success(
                title=self.main.i18n.tr("translations.updated.title"),
                content=self.main.i18n.tr("translations.updated.content", original=new_base),
                parent=self,
                position=InfoBarPosition.TOP
            )

        except Exception as ex:
            InfoBar.error(
                title=self.main.i18n.tr("translations.update_failed.title"),
                content=str(ex),
                parent=self,
                position=InfoBarPosition.TOP
            )

    def _delete_translation(self, translation_id: int, original: str):
        """Delete translation with confirmation"""
        # Show confirmation dialog
        dialog = MessageBox(
            self.main.i18n.tr("translations.delete_confirm.title"),
            self.main.i18n.tr("translations.delete_confirm.content", original=original),
            self
        )
        dialog.yesButton.setText(self.main.i18n.tr("common.delete"))
        dialog.cancelButton.setText(self.main.i18n.tr("common.cancel"))

        if dialog.exec():
            try:
                cursor = self.main.db.conn.cursor()

                cursor.execute(
                    "DELETE FROM translations WHERE id = ?",
                    (translation_id,)
                )
                self.main.db.conn.commit()

                # Reload translations
                self._load_translations()

                InfoBar.success(
                    title=self.main.i18n.tr("translations.deleted.title"),
                    content=self.main.i18n.tr("translations.deleted.content", original=original),
                    parent=self,
                    position=InfoBarPosition.TOP
                )

            except Exception as ex:
                InfoBar.error(
                    title=self.main.i18n.tr("translations.delete_failed.title"),
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
