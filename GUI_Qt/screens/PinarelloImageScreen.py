"""Pinarello Images Screen

Modern UI for Pinarello product image downloader:
- Table/list view for variants with sortable columns
- Large progress dashboard with real-time stats
- Clean layout optimized for maximized screens
"""

from __future__ import annotations

import os
import time
from typing import List, Dict

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QBoxLayout, QFileDialog,
    QCheckBox, QFrame, QTableWidgetItem,
    QHeaderView, QGridLayout
)

from qfluentwidgets import (
    CardWidget,
    TitleLabel,
    BodyLabel,
    CaptionLabel,
    LineEdit,
    PrimaryPushButton,
    PushButton,
    TransparentToolButton,
    FluentIcon,
    IconWidget,
    InfoBar,
    InfoBarPosition,
    IndeterminateProgressRing,
    PlainTextEdit,
    isDarkTheme,
    qconfig,
    TableWidget,
    ProgressBar,
    ScrollArea,
)

from GUI_Qt.widgets.ResponsiveWidget import ResponsiveWidget
from GUI_Qt.styles.theme_config import COLORS, FONTS, RADII, SIZES
from GUI_Qt.styles.screen_theme import (
    PAGE_MARGINS,
    PAGE_SPACING,
    CARD_MARGINS,
    ICON_TEXT_GAP,
    ROW_SPACING,
    CONTENT_SPACING,
    get_responsive_margins,
    get_responsive_spacing,
    apply_screen_theme,
)
from Utilities.URLHandler import URLHandler


DEFAULT_PINARELLO_URL_PLACEHOLDER = "pinarello.com/..."


class ColorIndicatorWidget(QFrame):
    """Small colored circle widget for table cells"""

    def __init__(self, color_hex: str, parent=None):
        super().__init__(parent)
        self.setFixedSize(20, 20)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {color_hex};
                border: 1px solid {COLORS['border_dark'] if isDarkTheme() else COLORS['border_light']};
                border-radius: 10px;
            }}
        """)


class PinarelloPreviewWorker(QThread):
    """Worker thread for previewing variants without downloading"""
    progress = Signal(str)
    finished = Signal(bool, str, object)  # success, message, preview_data

    def __init__(self, driver, url: str, wait_s: int, tr):
        super().__init__()
        self.driver = driver
        self.url = url
        self.wait_s = wait_s
        self.tr = tr

    def run(self):
        try:
            from pinarello_image_downloader import PinarelloScraper

            if not self.url:
                self.finished.emit(False, self.tr("pinarello.images.url.invalid"), None)
                return

            self.progress.emit(self.tr("pinarello.images.preview.fetching"))

            downloader = PinarelloScraper(
                url=self.url,
                log=self.progress.emit
            )

            preview_data = downloader.preview_variants()

            variant_count = len(preview_data.get('variants', []))
            extra_count = preview_data.get('extra_count', 0)
            self.progress.emit(
                self.tr("pinarello.images.preview.found",
                       variants=variant_count,
                       extras=extra_count)
            )

            self.finished.emit(True, self.tr("pinarello.images.preview.success"), preview_data)

        except Exception as e:
            self.finished.emit(False, self.tr("pinarello.images.preview.failed", error=str(e)), None)


class PinarelloImageWorker(QThread):
    progress_text = Signal(str)  # Text messages
    progress_data = Signal(dict)  # Structured progress updates
    finished = Signal(bool, str, object)  # success, message, results

    def __init__(self, driver, url: str, output_dir: str, wait_s: int, tr, selected_variant_ids: List[str] = None):
        super().__init__()
        self.driver = driver
        self.url = url
        self.output_dir = output_dir
        self.wait_s = wait_s
        self.tr = tr
        self.selected_variant_ids = selected_variant_ids

    def run(self):
        try:
            from pinarello_image_downloader import PinarelloScraper

            if not self.url:
                self.finished.emit(False, self.tr("pinarello.images.url.invalid"), None)
                return

            if not self.output_dir:
                self.finished.emit(False, self.tr("pinarello.images.output.invalid"), [])
                return

            os.makedirs(self.output_dir, exist_ok=True)

            self.progress_text.emit(self.tr("pinarello.images.status.starting"))

            # Create progress callback that emits both text and structured data
            def progress_callback(msg: str):
                self.progress_text.emit(msg)

            downloader = PinarelloScraper(
                url=self.url,
                log=progress_callback
            )

            # Load page and get variants
            html = downloader.fetch_page()
            downloader.parse_page(html)

            total_variants = len(downloader.variants)
            if self.selected_variant_ids:
                downloader.variants = {k: v for k, v in downloader.variants.items() if k in self.selected_variant_ids}

            # Calculate total images
            total_images = sum(len(v['images']) for v in downloader.variants.values()) + len(downloader.extra_gallery_images)

            # Emit initial progress
            self.progress_data.emit({
                "type": "init",
                "variant_total": len(downloader.variants),
                "image_total": total_images
            })

            # Run download with progress tracking
            # We'll track progress by wrapping the log callback
            image_count = [0]  # Use list to allow modification in closure

            def tracking_callback(msg: str):
                self.progress_text.emit(msg)
                # Count completed images (messages with pattern [X/Y])
                if "]" in msg and "/" in msg:
                    try:
                        parts = msg.split("[")[1].split("]")[0].split("/")
                        current = int(parts[0])
                        image_count[0] = current

                        self.progress_data.emit({
                            "type": "progress",
                            "variant_current": 0,  # Will be calculated
                            "variant_total": len(downloader.variants),
                            "image_current": current,
                            "image_total": total_images
                        })
                    except Exception:
                        pass

            downloader._log_cb = tracking_callback

            res = downloader.run(
                output_dir=self.output_dir,
                selected_variant_ids=self.selected_variant_ids
            )

            self.progress_text.emit("")
            self.progress_text.emit(self.tr("pinarello.images.done"))

            self.finished.emit(True, self.tr("pinarello.images.done"), res)

        except Exception as e:
            self.progress_text.emit("")
            self.progress_text.emit(f"ERROR: {str(e)}")
            self.finished.emit(False, self.tr("pinarello.images.failed", error=str(e)), [])


class PinarelloImageScreen(ResponsiveWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main = main_window
        self.worker: PinarelloImageWorker | None = None
        self.preview_worker: PinarelloPreviewWorker | None = None
        self.preview_data: Dict | None = None
        self.download_start_time: float = 0
        self._init_ui()
        qconfig.themeChangedFinished.connect(self._on_theme_changed)

    def _apply_theme(self):
        is_dark = isDarkTheme()
        bg_color = COLORS["space_indigo"] if is_dark else COLORS["platinum"]
        self.setStyleSheet(
            f"""
            PinarelloImageScreen {{
                background-color: {bg_color};
                font-family: {FONTS['family']};
            }}
            """
        )

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

        title_icon = IconWidget(FluentIcon.ALBUM)
        title_icon.setFixedSize(SIZES['icon_lg'], SIZES['icon_lg'])

        self.title_label = TitleLabel("")
        title_container.addWidget(title_icon)
        title_container.addWidget(self.title_label)
        header.addLayout(title_container)
        header.addStretch()
        main_layout.addLayout(header)

        # Two-column layout (40% / 60%)
        self.content_layout = QHBoxLayout()
        self.content_layout.setSpacing(PAGE_SPACING)

        # LEFT COLUMN: Controls
        left_column = QVBoxLayout()
        left_column.setSpacing(CONTENT_SPACING)

        # URL Card
        url_card = CardWidget()
        url_card.setBorderRadius(RADII['md'])
        url_layout = QVBoxLayout(url_card)
        url_layout.setContentsMargins(*CARD_MARGINS)
        url_layout.setSpacing(CONTENT_SPACING)

        self.url_label = BodyLabel("")
        self.url_label.setStyleSheet("font-weight: 600;")
        url_layout.addWidget(self.url_label)

        self.url_caption = CaptionLabel("")
        self.url_caption.setStyleSheet(f"color: {COLORS['text_secondary']}; background: transparent; background-color: transparent;")
        self.url_caption.setWordWrap(True)
        url_layout.addWidget(self.url_caption)

        self.url_field = LineEdit()
        self.url_field.setPlaceholderText(DEFAULT_PINARELLO_URL_PLACEHOLDER)
        url_layout.addWidget(self.url_field)

        self.preview_btn = PushButton("")
        self.preview_btn.setIcon(FluentIcon.VIEW.icon())
        self.preview_btn.clicked.connect(self._preview_variants)
        url_layout.addWidget(self.preview_btn)

        left_column.addWidget(url_card)

        # Variant Table Card
        self.variant_card = CardWidget()
        self.variant_card.setBorderRadius(RADII['md'])
        self.variant_card.setVisible(False)
        variant_layout = QVBoxLayout(self.variant_card)
        variant_layout.setContentsMargins(*CARD_MARGINS)
        variant_layout.setSpacing(CONTENT_SPACING)

        variant_header = QHBoxLayout()
        self.variant_title = BodyLabel("")
        self.variant_title.setStyleSheet("font-weight: 600;")
        variant_header.addWidget(self.variant_title)
        variant_header.addStretch()

        # Selection buttons
        select_btns = QHBoxLayout()
        select_btns.setSpacing(8)

        self.select_all_btn = PushButton("")
        self.select_all_btn.setIcon(FluentIcon.ACCEPT.icon())
        self.select_all_btn.clicked.connect(self._select_all_variants)

        self.deselect_all_btn = PushButton("")
        self.deselect_all_btn.setIcon(FluentIcon.CANCEL.icon())
        self.deselect_all_btn.clicked.connect(self._deselect_all_variants)

        select_btns.addWidget(self.select_all_btn)
        select_btns.addWidget(self.deselect_all_btn)
        variant_header.addLayout(select_btns)

        variant_layout.addLayout(variant_header)

        # Table widget
        self.variant_table = TableWidget()
        self.variant_table.setColumnCount(5)
        self.variant_table.setHorizontalHeaderLabels(["", "", "Code", "Variant Name", "Images"])

        # Configure columns - adjusted for better default size display
        self.variant_table.setColumnWidth(0, 40)   # Checkbox - narrower
        self.variant_table.setColumnWidth(1, 40)   # Color dot - narrower
        self.variant_table.setColumnWidth(2, 80)   # Code - slightly narrower
        self.variant_table.horizontalHeader().setStretchLastSection(False)
        self.variant_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)  # Name expands
        self.variant_table.setColumnWidth(4, 60)   # Image count - narrower

        # Table styling
        self.variant_table.setSortingEnabled(True)
        self.variant_table.setAlternatingRowColors(True)
        self.variant_table.verticalHeader().setVisible(False)
        self.variant_table.verticalHeader().setDefaultSectionSize(42)  # Smaller rows to fit more variants
        self.variant_table.setSelectionBehavior(TableWidget.SelectionBehavior.SelectRows)
        # No minimum height - let it size based on content up to maximum
        self.variant_table.setMaximumHeight(350)  # Cap at 350px to enable scrolling with many variants

        variant_layout.addWidget(self.variant_table)
        left_column.addWidget(self.variant_card)

        # Output Directory Card
        output_card = CardWidget()
        output_card.setBorderRadius(RADII['md'])
        output_layout = QVBoxLayout(output_card)
        output_layout.setContentsMargins(*CARD_MARGINS)
        output_layout.setSpacing(CONTENT_SPACING)

        self.output_label = BodyLabel("")
        self.output_label.setStyleSheet("font-weight: 600;")
        output_layout.addWidget(self.output_label)

        self.output_caption = CaptionLabel("")
        self.output_caption.setStyleSheet(f"color: {COLORS['text_secondary']}; background: transparent; background-color: transparent;")
        self.output_caption.setWordWrap(True)
        output_layout.addWidget(self.output_caption)

        out_row = QHBoxLayout()
        out_row.setSpacing(ROW_SPACING)
        self.output_field = LineEdit()
        out_row.addWidget(self.output_field, 1)
        self.browse_btn = PushButton("")
        self.browse_btn.setIcon(FluentIcon.FOLDER_ADD.icon())
        self.browse_btn.clicked.connect(self._browse_output)
        out_row.addWidget(self.browse_btn)
        output_layout.addLayout(out_row)

        left_column.addWidget(output_card)

        # Action button
        action_row = QHBoxLayout()
        action_row.setSpacing(CONTENT_SPACING)

        self.run_btn = PrimaryPushButton("")
        self.run_btn.setIcon(FluentIcon.PLAY.icon())
        self.run_btn.setMinimumHeight(44)
        self.run_btn.clicked.connect(self._run)

        self.progress_ring = IndeterminateProgressRing()
        self.progress_ring.setFixedSize(32, 32)
        self.progress_ring.setVisible(False)

        action_row.addWidget(self.run_btn, 1)
        action_row.addWidget(self.progress_ring)

        left_column.addLayout(action_row)
        left_column.addStretch(1)

        # RIGHT COLUMN: Progress Dashboard
        right_column = QVBoxLayout()
        right_column.setSpacing(CONTENT_SPACING)

        # Main Progress Card
        progress_card = CardWidget()
        progress_card.setBorderRadius(RADII['md'])
        progress_layout = QVBoxLayout(progress_card)
        progress_layout.setContentsMargins(24, 20, 24, 20)
        progress_layout.setSpacing(16)

        # Status header
        status_header = QHBoxLayout()
        self.status_icon = IconWidget(FluentIcon.HISTORY)
        self.status_icon.setFixedSize(SIZES['icon_lg'], SIZES['icon_lg'])
        self.status_title = TitleLabel("Ready")
        status_header.addWidget(self.status_icon)
        status_header.addSpacing(12)
        status_header.addWidget(self.status_title, 1)
        progress_layout.addLayout(status_header)

        # Progress bar
        self.main_progress = ProgressBar()
        self.main_progress.setMinimumHeight(16)
        self.main_progress.setRange(0, 100)
        self.main_progress.setValue(0)
        progress_layout.addWidget(self.main_progress)

        # Progress label
        self.progress_label = BodyLabel("0 of 0 variants downloaded")
        self.progress_label.setStyleSheet("font-size: 16px; font-weight: 600;")
        progress_layout.addWidget(self.progress_label)

        # Stats grid
        stats_grid = QGridLayout()
        stats_grid.setSpacing(16)
        stats_grid.setContentsMargins(0, 8, 0, 0)

        self.stat_variants = self._create_stat_item("Variants", "0 / 0")
        self.stat_images = self._create_stat_item("Images", "0 / 0")
        self.stat_speed = self._create_stat_item("Speed", "—")
        self.stat_eta = self._create_stat_item("ETA", "—")

        stats_grid.addWidget(self.stat_variants, 0, 0)
        stats_grid.addWidget(self.stat_images, 0, 1)
        stats_grid.addWidget(self.stat_speed, 1, 0)
        stats_grid.addWidget(self.stat_eta, 1, 1)

        progress_layout.addLayout(stats_grid)

        # Toggle details button
        self.toggle_details_btn = PushButton("Show Details")
        self.toggle_details_btn.setIcon(FluentIcon.DOWN.icon())
        self.toggle_details_btn.clicked.connect(self._toggle_details)
        progress_layout.addWidget(self.toggle_details_btn)

        right_column.addWidget(progress_card)

        # Details log (hidden by default)
        self.detail_log = PlainTextEdit()
        self.detail_log.setReadOnly(True)
        self.detail_log.setMaximumHeight(200)
        self.detail_log.setVisible(False)
        log_font = QFont(FONTS['family'], 9)
        self.detail_log.setFont(log_font)

        is_dark = isDarkTheme()
        self.detail_log.setStyleSheet(f"""
            PlainTextEdit {{
                background-color: {COLORS['bg_alt_dark'] if is_dark else COLORS['bg_alt_light']};
                border: none;
                border-radius: {RADII['sm']}px;
                padding: 12px;
            }}
        """)

        right_column.addWidget(self.detail_log)

        # Summary card (shown after completion)
        self.summary_card = CardWidget()
        self.summary_card.setBorderRadius(RADII['md'])
        self.summary_card.setVisible(False)
        summary_layout = QVBoxLayout(self.summary_card)
        summary_layout.setContentsMargins(*CARD_MARGINS)
        summary_layout.setSpacing(12)

        self.summary_title = BodyLabel("📊 Summary")
        self.summary_title.setStyleSheet("font-size: 16px; font-weight: 600;")
        summary_layout.addWidget(self.summary_title)

        self.summary_text = BodyLabel("")
        self.summary_text.setWordWrap(True)
        summary_layout.addWidget(self.summary_text)

        right_column.addWidget(self.summary_card)
        right_column.addStretch(1)

        # Add columns to content
        self.content_layout.addLayout(left_column, 2)
        self.content_layout.addLayout(right_column, 3)

        main_layout.addLayout(self.content_layout, 1)

        # Apply theme
        apply_screen_theme(
            self,
            "PinarelloImageScreen",
            scroll=self.scroll,
            content=self.content_widget
        )

        self.retranslate_ui()

    def _create_stat_item(self, label: str, value: str) -> QWidget:
        """Create a stat display widget"""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(4)
        layout.setContentsMargins(12, 8, 12, 8)

        label_widget = CaptionLabel(label)
        label_widget.setStyleSheet(f"color: {COLORS['text_secondary']}; background: transparent; background-color: transparent;")

        value_widget = BodyLabel(value)
        value_widget.setStyleSheet("font-size: 22px; font-weight: 600;")

        layout.addWidget(label_widget)
        layout.addWidget(value_widget)

        # Store reference
        container.value_label = value_widget
        container.title_label = label_widget

        return container

    def _extract_color_hint(self, variant_data: Dict) -> str:
        """Extract a color hint from variant name/code"""
        name_lower = variant_data['name'].lower()
        code_lower = variant_data['code'].lower()
        combined = name_lower + " " + code_lower

        color_map = {
            'black': '#1a1a1a',
            'white': '#f5f5f5',
            'red': '#e74c3c',
            'blue': '#3498db',
            'green': '#2ecc71',
            'yellow': '#f39c12',
            'orange': '#e67e22',
            'purple': '#9b59b6',
            'pink': '#e91e63',
            'grey': '#95a5a6',
            'gray': '#95a5a6',
            'silver': '#bdc3c7',
            'gold': '#f1c40f',
        }

        for color_name, color_hex in color_map.items():
            if color_name in combined:
                return color_hex

        return COLORS['lavender_grey']

    def _toggle_details(self):
        """Toggle detailed log visibility"""
        is_visible = self.detail_log.isVisible()
        self.detail_log.setVisible(not is_visible)
        if not is_visible:
            self.toggle_details_btn.setText(self.main.i18n.tr("pinarello.images.details.hide"))
            self.toggle_details_btn.setIcon(FluentIcon.UP.icon())
        else:
            self.toggle_details_btn.setText(self.main.i18n.tr("pinarello.images.details.show"))
            self.toggle_details_btn.setIcon(FluentIcon.DOWN.icon())

    def retranslate_ui(self):
        tr = self.main.i18n.tr
        self.title_label.setText(tr("pinarello.images.title"))
        self.url_label.setText(tr("pinarello.images.url.label"))
        self.url_caption.setText(tr("pinarello.images.url.caption"))
        self.url_field.setPlaceholderText(tr("pinarello.images.url.placeholder"))
        self.preview_btn.setText(tr("pinarello.images.preview.button"))
        self.preview_btn.setToolTip(tr("pinarello.images.preview.button.tip"))
        self.variant_title.setText(tr("pinarello.images.variant.title"))
        self.select_all_btn.setText(tr("common.select_all"))
        self.select_all_btn.setToolTip(tr("pinarello.images.variant.select_all.tip"))
        self.deselect_all_btn.setText(tr("common.deselect_all"))
        self.deselect_all_btn.setToolTip(tr("pinarello.images.variant.deselect_all.tip"))
        self.output_label.setText(tr("pinarello.images.output.label"))
        self.output_caption.setText(tr("pinarello.images.output.caption"))
        self.output_field.setPlaceholderText(tr("pinarello.images.output.placeholder"))
        self.browse_btn.setText(tr("pinarello.images.output.browse"))
        self.browse_btn.setToolTip(tr("pinarello.images.output.browse.tip"))
        self.run_btn.setText(tr("pinarello.images.run"))
        self.run_btn.setToolTip(tr("pinarello.images.run.tip"))
        self.variant_table.setHorizontalHeaderLabels([
            "", "", tr("pinarello.images.table.code"),
            tr("pinarello.images.table.variant"), tr("pinarello.images.table.images"),
        ])
        self.stat_variants.title_label.setText(tr("pinarello.images.stats.variants"))
        self.stat_images.title_label.setText(tr("pinarello.images.stats.images"))
        self.stat_speed.title_label.setText(tr("pinarello.images.stats.speed"))
        self.stat_eta.title_label.setText(tr("pinarello.images.stats.eta"))
        self.toggle_details_btn.setText(
            tr("pinarello.images.details.hide")
            if self.detail_log.isVisible()
            else tr("pinarello.images.details.show")
        )
        self.summary_title.setText(tr("pinarello.images.summary.title"))
        status_key = self.status_title.property("statusKey") or "pinarello.images.status.ready"
        self.status_title.setText(tr(status_key))

    def _set_status(self, key: str) -> None:
        self.status_title.setProperty("statusKey", key)
        self.status_title.setText(self.main.i18n.tr(key))

    def _on_theme_changed(self):
        self._apply_theme()
        is_dark = isDarkTheme()
        self.detail_log.setStyleSheet(f"""
            PlainTextEdit {{
                background-color: {COLORS['bg_alt_dark'] if is_dark else COLORS['bg_alt_light']};
                border: none;
                border-radius: {RADII['sm']}px;
                padding: 12px;
            }}
        """)

    def _on_breakpoint_changed(self, breakpoint: str):
        """Respond to breakpoint changes - adjust margins and spacing."""
        margins = get_responsive_margins(breakpoint)
        spacing = get_responsive_spacing(breakpoint)
        if hasattr(self, 'content_widget') and self.content_widget.layout():
            self.content_widget.layout().setContentsMargins(*margins)
            self.content_widget.layout().setSpacing(spacing)
        if hasattr(self, "content_layout"):
            self.content_layout.setDirection(
                QBoxLayout.Direction.TopToBottom
                if breakpoint in ("xs", "sm")
                else QBoxLayout.Direction.LeftToRight
            )
            self.content_layout.setSpacing(spacing)

    def _browse_output(self):
        tr = self.main.i18n.tr
        folder = QFileDialog.getExistingDirectory(self, tr("pinarello.images.output.browse.title"), "")
        if folder:
            self.output_field.setText(folder)

    def _append_log(self, text: str):
        """Append to detail log"""
        if not text.strip():
            self.detail_log.appendPlainText("")
            return

        formatted_text = text

        # Add icons
        if "✓" in text or "complete" in text.lower() or "done" in text.lower():
            if not text.startswith("✓"):
                formatted_text = f"✓  {text}"
        elif "✗" in text or "failed" in text.lower() or "error" in text.lower():
            if not text.startswith("✗"):
                formatted_text = f"✗  {text}"

        self.detail_log.appendPlainText(formatted_text)

        # Auto-scroll
        scrollbar = self.detail_log.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _update_progress(self, progress_data: dict):
        """Handle structured progress updates"""
        if progress_data["type"] == "init":
            variant_total = progress_data.get("variant_total", 0)
            image_total = progress_data.get("image_total", 0)

            self.stat_variants.value_label.setText(f"0 / {variant_total}")
            self.stat_images.value_label.setText(f"0 / {image_total}")
            self.main_progress.setValue(0)

        elif progress_data["type"] == "progress":
            variant_current = progress_data.get("variant_current", 0)
            variant_total = progress_data.get("variant_total", 0)
            image_current = progress_data.get("image_current", 0)
            image_total = progress_data.get("image_total", 0)

            # Update progress bar
            if image_total > 0:
                percentage = int((image_current / image_total) * 100)
                self.main_progress.setValue(percentage)

            # Update labels
            self.progress_label.setText(
                self.main.i18n.tr(
                    "pinarello.images.progress.images",
                    current=image_current,
                    total=image_total,
                )
            )
            self.stat_variants.value_label.setText(f"{variant_current} / {variant_total}")
            self.stat_images.value_label.setText(f"{image_current} / {image_total}")

            # Calculate speed and ETA
            if self.download_start_time > 0:
                elapsed = time.time() - self.download_start_time
                if elapsed > 0 and image_current > 0:
                    speed = image_current / elapsed
                    remaining_images = image_total - image_current
                    eta_seconds = remaining_images / speed if speed > 0 else 0

                    self.stat_speed.value_label.setText(f"{speed:.1f}/s")

                    if eta_seconds < 60:
                        self.stat_eta.value_label.setText(f"{int(eta_seconds)}s")
                    else:
                        minutes = int(eta_seconds / 60)
                        seconds = int(eta_seconds % 60)
                        self.stat_eta.value_label.setText(f"{minutes}m {seconds}s")

    def _set_busy(self, busy: bool):
        self.progress_ring.setVisible(busy)
        self.run_btn.setEnabled(not busy)
        self.preview_btn.setEnabled(not busy)
        self.browse_btn.setEnabled(not busy)
        self.url_field.setEnabled(not busy)
        self.output_field.setEnabled(not busy)
        self.select_all_btn.setEnabled(not busy)
        self.deselect_all_btn.setEnabled(not busy)

    def _preview_variants(self):
        """Preview available color variants"""
        tr = self.main.i18n.tr
        url = URLHandler.normalize_url(self.url_field.text())

        if not URLHandler.is_valid_url(url):
            InfoBar.error(
                title=tr("common.error"),
                content=tr("pinarello.images.url.invalid"),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3500,
                parent=self,
            )
            return
        self.url_field.setText(url)

        self.detail_log.clear()
        self.status_icon.setIcon(FluentIcon.SYNC)
        self._set_status("pinarello.images.status.loading")
        self._set_busy(True)

        self.preview_worker = PinarelloPreviewWorker(
            driver=getattr(self.main, "driver", None),
            url=url,
            wait_s=20,
            tr=tr,
        )
        self.preview_worker.progress.connect(self._append_log)
        self.preview_worker.finished.connect(self._on_preview_finished)
        self.preview_worker.start()

    def _on_preview_finished(self, success: bool, message: str, preview_data):
        """Handle preview completion"""
        tr = self.main.i18n.tr
        self._set_busy(False)

        self._append_log(message)

        if success and preview_data:
            self.preview_data = preview_data
            self._populate_variant_table(preview_data)

            variant_count = len(preview_data.get('variants', []))
            self.status_icon.setIcon(FluentIcon.ACCEPT)
            self._set_status("pinarello.images.status.ready")

            InfoBar.success(
                title=tr("common.success"),
                content=message,
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3500,
                parent=self,
            )
        else:
            self.status_icon.setIcon(FluentIcon.CLOSE)
            self._set_status("pinarello.images.status.failed")
            InfoBar.error(
                title=tr("common.error"),
                content=message,
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=4500,
                parent=self,
            )

    def _populate_variant_table(self, preview_data: Dict):
        """Populate variant table with data"""
        tr = self.main.i18n.tr

        self.variant_table.setRowCount(0)
        variants = preview_data.get('variants', [])

        if not variants:
            return

        self.variant_title.setText(
            f"{tr('pinarello.images.variant.title')} "
            f"({len(variants)} {tr('pinarello.images.variant.found')})"
        )

        for variant in variants:
            row = self.variant_table.rowCount()
            self.variant_table.insertRow(row)

            # Checkbox
            checkbox = QCheckBox()
            checkbox.setChecked(True)
            checkbox.setProperty('variant_id', variant['id'])
            checkbox_widget = QWidget()
            checkbox_layout = QHBoxLayout(checkbox_widget)
            checkbox_layout.addWidget(checkbox)
            checkbox_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            checkbox_layout.setContentsMargins(0, 0, 0, 0)
            self.variant_table.setCellWidget(row, 0, checkbox_widget)

            # Color indicator
            color_hex = self._extract_color_hint(variant)
            color_widget = QWidget()
            color_layout = QHBoxLayout(color_widget)
            color_layout.addWidget(ColorIndicatorWidget(color_hex))
            color_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            color_layout.setContentsMargins(0, 0, 0, 0)
            self.variant_table.setCellWidget(row, 1, color_widget)

            # Code
            code_item = QTableWidgetItem(variant['code'])
            code_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self.variant_table.setItem(row, 2, code_item)

            # Name
            name_item = QTableWidgetItem(variant['name'])
            name_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self.variant_table.setItem(row, 3, name_item)

            # Image count
            count_item = QTableWidgetItem(str(variant['image_count']))
            count_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            self.variant_table.setItem(row, 4, count_item)

        self.variant_card.setVisible(True)

    def _select_all_variants(self):
        """Select all variants in table"""
        for row in range(self.variant_table.rowCount()):
            checkbox_widget = self.variant_table.cellWidget(row, 0)
            if checkbox_widget:
                checkbox = checkbox_widget.findChild(QCheckBox)
                if checkbox:
                    checkbox.setChecked(True)

    def _deselect_all_variants(self):
        """Deselect all variants in table"""
        for row in range(self.variant_table.rowCount()):
            checkbox_widget = self.variant_table.cellWidget(row, 0)
            if checkbox_widget:
                checkbox = checkbox_widget.findChild(QCheckBox)
                if checkbox:
                    checkbox.setChecked(False)

    def _get_selected_variant_ids(self) -> List[str]:
        """Get list of selected variant IDs from table"""
        selected = []
        for row in range(self.variant_table.rowCount()):
            checkbox_widget = self.variant_table.cellWidget(row, 0)
            if checkbox_widget:
                checkbox = checkbox_widget.findChild(QCheckBox)
                if checkbox and checkbox.isChecked():
                    variant_id = checkbox.property('variant_id')
                    if variant_id:
                        selected.append(variant_id)
        return selected

    def _run(self):
        tr = self.main.i18n.tr

        url = URLHandler.normalize_url(self.url_field.text())
        output_dir = self.output_field.text().strip()

        if not URLHandler.is_valid_url(url):
            InfoBar.error(
                title=tr("common.error"),
                content=tr("pinarello.images.url.invalid"),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3500,
                parent=self,
            )
            return
        self.url_field.setText(url)
        if not output_dir:
            InfoBar.error(
                title=tr("common.error"),
                content=tr("pinarello.images.output.invalid"),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3500,
                parent=self,
            )
            return

        # Get selected variants
        selected_variant_ids = None
        if self.variant_table.rowCount() > 0:
            selected_variant_ids = self._get_selected_variant_ids()
            if not selected_variant_ids:
                InfoBar.warning(
                    title=tr("common.warning"),
                    content=tr("pinarello.images.variant.none_selected"),
                    orient=Qt.Orientation.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=3500,
                    parent=self,
                )
                return

        self.detail_log.clear()
        self.summary_card.setVisible(False)
        self.status_icon.setIcon(FluentIcon.SYNC)
        self._set_status("pinarello.images.status.downloading")
        self.main_progress.setValue(0)
        self.download_start_time = time.time()

        self._set_busy(True)

        self.worker = PinarelloImageWorker(
            driver=getattr(self.main, "driver", None),
            url=url,
            output_dir=output_dir,
            wait_s=20,
            tr=tr,
            selected_variant_ids=selected_variant_ids,
        )
        self.worker.progress_text.connect(self._append_log)
        self.worker.progress_data.connect(self._update_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.start()

    def _on_finished(self, success: bool, message: str, results):
        tr = self.main.i18n.tr
        self._set_busy(False)

        if success:
            try:
                r = results if isinstance(results, dict) else None
                if r:
                    self.status_icon.setIcon(FluentIcon.ACCEPT)
                    self._set_status("pinarello.images.status.complete")
                    self.main_progress.setValue(100)

                    # Show summary
                    product_dir = r.get("product_dir")
                    title = r.get("title")
                    gallery_count = r.get("gallery_count")
                    variant_images = r.get("variant_images")
                    variants = r.get("variants")

                    summary_lines = []
                    if title:
                        summary_lines.append(f"<b>{tr('pinarello.images.summary.product')}:</b> {title}")
                    if product_dir:
                        summary_lines.append(f"<b>{tr('pinarello.images.summary.location')}:</b> {product_dir}")
                    summary_lines.append(
                        f"<b>{tr('pinarello.images.summary.gallery')}:</b> {gallery_count or 0}"
                    )
                    summary_lines.append(
                        f"<b>{tr('pinarello.images.summary.variants')}:</b> {variants or 0}"
                    )
                    summary_lines.append(
                        f"<b>{tr('pinarello.images.summary.variant_images')}:</b> {variant_images or 0}"
                    )

                    self.summary_text.setText("<br>".join(summary_lines))
                    self.summary_card.setVisible(True)
            except Exception:
                pass

            InfoBar.success(
                title=tr("common.success"),
                content=message,
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3500,
                parent=self,
            )
        else:
            self.status_icon.setIcon(FluentIcon.CLOSE)
            self._set_status("pinarello.images.status.failed")
            InfoBar.error(
                title=tr("common.error"),
                content=message,
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=4500,
                parent=self,
            )
