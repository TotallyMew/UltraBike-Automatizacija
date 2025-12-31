"""Folder Creator Screen - Fluent Design System

Scrapes product names from the current logged-in Selenium browser session and
creates a folder structure on disk.

Path must be set for each run (it is cleared after completion).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QFileDialog,
    QSizePolicy,
)

from qfluentwidgets import (
    CardWidget,
    TitleLabel,
    BodyLabel,
    CaptionLabel,
    LineEdit,
    MessageBox,
    PrimaryPushButton,
    PushButton,
    TransparentToolButton,
    FluentIcon,
    InfoBar,
    InfoBarPosition,
    IndeterminateProgressRing,
    isDarkTheme,
    qconfig,
    ScrollArea,
)

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from GUI_Qt.widgets.ResponsiveWidget import ResponsiveWidget
from GUI_Qt.styles.theme_config import COLORS, FONTS, RADII, PADDINGS, SIZES, rgba_from_hex
from GUI_Qt.styles.screen_theme import (
    PAGE_MARGINS,
    PAGE_SPACING,
    ICON_TEXT_GAP,
    PANEL_MARGINS,
    CONTENT_SPACING,
    ROW_SPACING,
    CARD_SPACING,
    CARD_MARGINS,
    get_responsive_margins,
    get_responsive_spacing,
    apply_screen_theme,
)


@dataclass(frozen=True)
class ScrapedProduct:
    name: str
    reference: str


class ScrapeProductsWorker(QThread):
    finished = Signal(bool, str, object)  # success, message, products

    def __init__(self, driver, tr):
        super().__init__()
        self.driver = driver
        self.tr = tr

    def run(self):
        try:
            if self.driver is None:
                self.finished.emit(False, self.tr("folders.no_session"), [])
                return

            # Navigate to products page (uses existing session)
            try:
                products_link = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.ID, "subtab-AdminProducts"))
                )
                products_link.click()
            except Exception:
                # If already on products page, clicking might fail; try to continue.
                pass

            # Wait for table
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "table.table"))
            )

            table = self.driver.find_element(By.CSS_SELECTOR, "table.table")
            rows = table.find_elements(By.CSS_SELECTOR, "tbody tr[data-product-id]")

            products: list[ScrapedProduct] = []
            for row in rows:
                try:
                    name = row.find_element(By.CSS_SELECTOR, "td:nth-child(4) a").text
                    reference = row.find_element(By.CSS_SELECTOR, "td:nth-child(5)").text
                    if name:
                        products.append(ScrapedProduct(name=name, reference=reference))
                except Exception:
                    continue

            if not products:
                self.finished.emit(False, self.tr("folders.scrape.empty"), [])
                return

            self.finished.emit(True, self.tr("folders.scrape.ok", count=len(products)), products)
        except Exception as e:
            self.finished.emit(False, self.tr("folders.scrape.failed", error=str(e)), [])


class CreateFoldersWorker(QThread):
    finished = Signal(bool, str)  # success, message

    def __init__(self, products: list[ScrapedProduct], repository_path: str, tr):
        super().__init__()
        self.products = products
        self.repository_path = repository_path
        self.tr = tr

    @staticmethod
    def _extract_model(full_name: str) -> str:
        # Parent folder = everything before the first '/'
        before_slash, sep, _ = full_name.partition("/")
        if sep:
            return before_slash.strip()
        return full_name.strip()

    @staticmethod
    def _sanitize_folder_name(name: str) -> str:
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            name = name.replace(char, '-')
        return name.strip('. ')

    def run(self):
        try:
            if not self.repository_path or not os.path.isdir(self.repository_path):
                self.finished.emit(False, self.tr("folders.path.invalid"))
                return

            if not self.products:
                self.finished.emit(False, self.tr("folders.create.no_products"))
                return

            model_groups: dict[str, list[str]] = {}
            for product in self.products:
                full_name = product.name
                model = self._extract_model(full_name)
                model_groups.setdefault(model, []).append(full_name)

            created_products = 0
            for model, full_names in model_groups.items():
                model_folder = self._sanitize_folder_name(model)
                model_path = os.path.join(self.repository_path, model_folder)
                os.makedirs(model_path, exist_ok=True)

                for full_name in full_names:
                    child_folder = self._sanitize_folder_name(full_name)
                    child_path = os.path.join(model_path, child_folder)
                    os.makedirs(child_path, exist_ok=True)
                    created_products += 1

            self.finished.emit(
                True,
                self.tr(
                    "folders.create.ok",
                    models=len(model_groups),
                    products=created_products,
                ),
            )
        except Exception as e:
            self.finished.emit(False, self.tr("folders.create.failed", error=str(e)))


class FolderCreatorScreen(ResponsiveWidget):
    """Folder creator screen."""

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main = main_window

        self._products: list[ScrapedProduct] = []
        self._scrape_worker: ScrapeProductsWorker | None = None
        self._create_worker: CreateFoldersWorker | None = None

        self._init_ui()
        qconfig.themeChangedFinished.connect(self._on_theme_changed)

    def _apply_theme(self):
        is_dark = isDarkTheme()
        bg_color = COLORS['space_indigo'] if is_dark else COLORS['platinum']
        self.setStyleSheet(f"""
            FolderCreatorScreen {{
                background-color: {bg_color};
                font-family: {FONTS['family']};
            }}
        """)

        panel_bg = COLORS['lavender_grey'] if is_dark else COLORS['bg_light']
        item_divider = rgba_from_hex(COLORS['text_white'], 0.08) if is_dark else rgba_from_hex(COLORS['space_indigo'], 0.10)

        if hasattr(self, 'products_list') and self.products_list is not None:
            self.products_list.setStyleSheet(f"""
                QListWidget {{
                    background-color: {panel_bg};
                    border-radius: {RADII['sm']}px;
                    padding: {PADDINGS['combo_item']};
                }}
                QListWidget::viewport {{
                    background-color: {panel_bg};
                }}
                QListWidget::item {{
                    padding: {PADDINGS['combo_item']};
                    border-bottom: 1px solid {item_divider};
                }}
            """)

        if hasattr(self, 'preview_tree') and self.preview_tree is not None:
            self.preview_tree.setStyleSheet(f"""
                QTreeWidget {{
                    background-color: {panel_bg};
                    border-radius: {RADII['sm']}px;
                    padding: {PADDINGS['combo_item']};
                }}
                QTreeWidget::viewport {{
                    background-color: {panel_bg};
                }}
                QTreeWidget::item {{
                    padding: {PADDINGS['tree_item']};
                }}
            """)

    def _init_ui(self):
        self._apply_theme()
        self.setAutoFillBackground(True)

        # Root layout (for ScrollArea container)
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)

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

        # Header
        header = QHBoxLayout()
        title_container = QHBoxLayout()
        title_container.setSpacing(ICON_TEXT_GAP)

        title_icon = TransparentToolButton(FluentIcon.FOLDER, self)
        title_icon.setFixedSize(SIZES['icon_lg'], SIZES['icon_lg'])
        title_icon.setEnabled(False)

        self.title_label = TitleLabel("")
        title_container.addWidget(title_icon)
        title_container.addWidget(self.title_label)
        header.addLayout(title_container)
        header.addStretch()
        main_layout.addLayout(header)

        # Content row
        self.content_layout = QHBoxLayout()
        self.content_layout.setSpacing(PAGE_SPACING)

        # Left: scraped products list
        left_panel = CardWidget()
        left_panel.setBorderRadius(RADII['md'])
        left_panel.setMinimumWidth(SIZES['left_panel_min_width'])
        left_panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(*PANEL_MARGINS)
        left_layout.setSpacing(CONTENT_SPACING)

        list_header = QHBoxLayout()
        self.list_title = BodyLabel("")
        self.list_title.setStyleSheet(f"font-weight: 600; color: {COLORS['text_secondary']};")

        self.scrape_btn = PrimaryPushButton("")
        self.scrape_btn.setIcon(FluentIcon.SYNC.icon())
        self.scrape_btn.clicked.connect(self._handle_scrape)

        list_header.addWidget(self.list_title)
        list_header.addStretch()
        list_header.addWidget(self.scrape_btn)
        left_layout.addLayout(list_header)

        self.products_list = QListWidget()
        self._apply_theme()
        left_layout.addWidget(self.products_list, 1)

        self.list_hint = CaptionLabel("")
        self.list_hint.setStyleSheet(f"color: {COLORS['text_secondary']};")
        left_layout.addWidget(self.list_hint)

        self.left_panel = left_panel
        self.content_layout.addWidget(left_panel, 4)

        # Right: actions
        right_panel = CardWidget()
        right_panel.setBorderRadius(RADII['md'])
        right_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(*CARD_MARGINS)
        right_layout.setSpacing(CARD_SPACING)

        self.subtitle_label = BodyLabel("")
        self.subtitle_label.setWordWrap(True)
        right_layout.addWidget(self.subtitle_label)

        # Preview
        self.preview_title = BodyLabel("")
        self.preview_title.setStyleSheet(f"font-weight: 600; color: {COLORS['text_secondary']};")
        right_layout.addWidget(self.preview_title)

        self.preview_hint = CaptionLabel("")
        self.preview_hint.setStyleSheet(f"color: {COLORS['text_secondary']};")
        right_layout.addWidget(self.preview_hint)

        self.preview_tree = QTreeWidget()
        self.preview_tree.setHeaderHidden(True)
        self.preview_tree.setRootIsDecorated(True)
        self.preview_tree.setIndentation(SIZES['tree_indent'])
        self._apply_theme()
        self.preview_tree.setMinimumHeight(SIZES['tree_min_height'])
        right_layout.addWidget(self.preview_tree, 1)

        # Path chooser card-like block
        self.path_label = BodyLabel("")
        self.path_caption = CaptionLabel("")
        self.path_caption.setStyleSheet(f"color: {COLORS['text_secondary']};")
        right_layout.addWidget(self.path_label)
        right_layout.addWidget(self.path_caption)

        path_row = QHBoxLayout()
        path_row.setSpacing(ROW_SPACING)
        self.path_field = LineEdit()
        self.path_field.setPlaceholderText("")
        path_row.addWidget(self.path_field, 1)

        self.browse_btn = PushButton("")
        self.browse_btn.setIcon(FluentIcon.FOLDER_ADD.icon())
        self.browse_btn.clicked.connect(self._browse_path)
        path_row.addWidget(self.browse_btn)
        right_layout.addLayout(path_row)

        # Actions
        actions_row = QHBoxLayout()
        actions_row.setSpacing(CONTENT_SPACING)
        self.create_btn = PrimaryPushButton("")
        self.create_btn.setIcon(FluentIcon.SEND.icon())
        self.create_btn.clicked.connect(self._handle_create)

        self.clear_btn = PushButton("")
        self.clear_btn.setIcon(FluentIcon.DELETE.icon())
        self.clear_btn.clicked.connect(self._clear_results)

        self.progress_ring = IndeterminateProgressRing()
        self.progress_ring.setFixedSize(SIZES['progress_ring'], SIZES['progress_ring'])
        self.progress_ring.setVisible(False)

        actions_row.addWidget(self.create_btn)
        actions_row.addWidget(self.clear_btn)
        actions_row.addStretch(1)
        actions_row.addWidget(self.progress_ring)
        right_layout.addLayout(actions_row)

        right_layout.addStretch(1)
        self.right_panel = right_panel
        self.content_layout.addWidget(right_panel, 6)

        main_layout.addLayout(self.content_layout, 1)

        # Apply theme
        apply_screen_theme(
            self,
            "FolderCreatorScreen",
            scroll=self.scroll,
            content=self.content_widget
        )

        self.retranslate_ui()

        # Initial preview state
        self._refresh_preview()

    def retranslate_ui(self):
        tr = self.main.i18n.tr
        self.title_label.setText(tr("folders.title"))
        self.list_title.setText(tr("folders.list.title"))
        self.list_hint.setText(tr("folders.list.hint"))
        self.subtitle_label.setText(tr("folders.subtitle"))
        self.preview_title.setText(tr("folders.preview.title"))
        self.preview_hint.setText(tr("folders.preview.hint"))
        self.scrape_btn.setText(tr("folders.scrape"))
        self.scrape_btn.setToolTip(tr("folders.scrape.tip"))
        self.path_label.setText(tr("folders.path.label"))
        self.path_caption.setText(tr("folders.path.caption"))
        self.path_field.setPlaceholderText(tr("folders.path.placeholder"))
        self.browse_btn.setText(tr("folders.path.browse"))
        self.browse_btn.setToolTip(tr("folders.path.browse.tip"))
        self.create_btn.setText(tr("folders.create"))
        self.create_btn.setToolTip(tr("folders.create.tip"))
        self.clear_btn.setText(tr("folders.clear"))
        self.clear_btn.setToolTip(tr("folders.clear.tip"))

        # Re-render empty state label on language change
        self._refresh_preview()

    def _on_breakpoint_changed(self, breakpoint: str):
        """Respond to breakpoint changes - adjust margins and spacing."""
        margins = get_responsive_margins(breakpoint)
        spacing = get_responsive_spacing(breakpoint)
        if hasattr(self, 'content_widget') and self.content_widget.layout():
            self.content_widget.layout().setContentsMargins(*margins)
            self.content_widget.layout().setSpacing(spacing)

    def _on_theme_changed(self):
        self._apply_theme()

    def _set_busy(self, busy: bool):
        self.progress_ring.setVisible(busy)
        self.scrape_btn.setEnabled(not busy)
        self.create_btn.setEnabled(not busy)
        self.browse_btn.setEnabled(not busy)
        self.clear_btn.setEnabled(not busy)

    def _browse_path(self):
        tr = self.main.i18n.tr
        folder = QFileDialog.getExistingDirectory(self, tr("folders.path.browse.title"), "")
        if folder:
            self.path_field.setText(folder)

    def _clear_results(self):
        """Clear scraped results with confirmation dialog"""
        # Show confirmation dialog
        w = MessageBox(
            title=self.main.i18n.tr("common.confirm"),
            content=self.main.i18n.tr("folders.clear.confirm"),
            parent=self
        )
        if w.exec():
            self._products = []
            self.products_list.clear()
            self._refresh_preview()

    def _refresh_preview(self):
        """Render a preview of the folder structure that would be created."""
        tr = self.main.i18n.tr
        self.preview_tree.clear()

        if not self._products:
            empty = QTreeWidgetItem([tr("folders.preview.empty")])
            empty.setFlags(empty.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self.preview_tree.addTopLevelItem(empty)
            self.preview_tree.expandAll()
            return

        # Group by model (parent folder) and show sanitized folder names.
        groups: dict[str, list[str]] = {}
        for p in self._products:
            model = CreateFoldersWorker._extract_model(p.name)
            groups.setdefault(model, []).append(p.name)

        for model, full_names in sorted(groups.items(), key=lambda kv: kv[0].lower()):
            model_folder = CreateFoldersWorker._sanitize_folder_name(model)
            parent = QTreeWidgetItem([model_folder])
            parent.setExpanded(True)

            for full_name in sorted(full_names, key=lambda s: s.lower()):
                child_folder = CreateFoldersWorker._sanitize_folder_name(full_name)
                child = QTreeWidgetItem([child_folder])
                parent.addChild(child)

            self.preview_tree.addTopLevelItem(parent)

        self.preview_tree.expandAll()

    def _handle_scrape(self):
        tr = self.main.i18n.tr
        if getattr(self.main, "driver", None) is None:
            InfoBar.error(
                title=tr("common.error"),
                content=tr("folders.no_session"),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
            return

        self._set_busy(True)
        self._scrape_worker = ScrapeProductsWorker(self.main.driver, tr)
        self._scrape_worker.finished.connect(self._on_scrape_finished)
        self._scrape_worker.start()

    def _on_scrape_finished(self, success: bool, message: str, products):
        tr = self.main.i18n.tr
        self._set_busy(False)

        if success:
            self._products = list(products or [])
            self.products_list.clear()
            for p in self._products:
                item = QListWidgetItem(f"{p.name}")
                item.setToolTip(p.reference)
                self.products_list.addItem(item)

            self._refresh_preview()

            InfoBar.success(
                title=tr("common.success"),
                content=message,
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=2500,
                parent=self,
            )
        else:
            InfoBar.error(
                title=tr("common.error"),
                content=message,
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3500,
                parent=self,
            )

            self._products = []
            self.products_list.clear()
            self._refresh_preview()

    def _handle_create(self):
        tr = self.main.i18n.tr
        repository_path = self.path_field.text().strip()

        if not repository_path or not os.path.isdir(repository_path):
            InfoBar.error(
                title=tr("common.error"),
                content=tr("folders.path.invalid"),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3500,
                parent=self,
            )
            return

        if not self._products:
            InfoBar.warning(
                title=tr("common.error"),
                content=tr("folders.create.no_products"),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3500,
                parent=self,
            )
            return

        self._set_busy(True)
        self._create_worker = CreateFoldersWorker(self._products, repository_path, tr)
        self._create_worker.finished.connect(self._on_create_finished)
        self._create_worker.start()

    def _on_create_finished(self, success: bool, message: str):
        tr = self.main.i18n.tr
        self._set_busy(False)

        # Enforce "set path every time" by clearing it after any run.
        self.path_field.clear()

        if success:
            InfoBar.success(
                title=tr("common.success"),
                content=message,
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self,
            )
        else:
            InfoBar.error(
                title=tr("common.error"),
                content=message,
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=4000,
                parent=self,
            )
