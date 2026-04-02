"""
Analytics Screen - Comprehensive dashboard with charts and insights
Modern analytics interface with visual data representation
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QFileDialog
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QColor, QPen, QFont
from qfluentwidgets import (
    CardWidget, TitleLabel, StrongBodyLabel, BodyLabel, CaptionLabel,
    ComboBox, PushButton, TransparentToolButton, FluentIcon,
    InfoBar, InfoBarPosition, ScrollArea, isDarkTheme, IconWidget,
    ProgressRing, IndeterminateProgressRing, qconfig
)
from datetime import datetime, timedelta
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment

from GUI_Qt.widgets.ResponsiveWidget import ResponsiveWidget
from GUI_Qt.styles.theme_config import COLORS, FONTS, RADII, SPACING, SIZES, rgba_from_hex
from GUI_Qt.styles.screen_theme import (
    apply_screen_theme, PAGE_MARGINS, PAGE_SPACING, CARD_MARGINS, CARD_SPACING,
    ICON_TEXT_GAP, TIGHT_SPACING, get_responsive_margins, get_responsive_spacing
)
from GUI_Qt.styles.screen_theme import enforce_transparent_labels


class MetricCard(CardWidget):
    """Large metric card with trend indicator"""

    def __init__(self, title, value, subtitle, icon, trend=None, trend_positive=True, parent=None):
        super().__init__(parent)
        self.setBorderRadius(RADII['md'])

        self._trend_positive = True

        # Apply proper card styling
        self._apply_theme()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(*CARD_MARGINS)
        layout.setSpacing(SPACING['md'])

        # Header with icon
        header = QHBoxLayout()
        header.setSpacing(ICON_TEXT_GAP)

        icon_widget = IconWidget(icon)
        icon_widget.setFixedSize(SIZES['icon_lg'], SIZES['icon_lg'])
        icon_widget.setStyleSheet(f"color: {COLORS['space_indigo']}; background: transparent; background-color: transparent;")

        # Keep title explicit and readable (icons alone are ambiguous)
        self.title_label = BodyLabel(str(title))
        self.title_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-weight: 600; background: transparent; background-color: transparent;")

        header.addWidget(icon_widget)
        header.addWidget(self.title_label)
        header.addStretch()

        layout.addLayout(header)

        # Value
        self.value_label = QLabel(str(value))
        self.value_label.setStyleSheet(f"""
            font-size: 36px;
            font-weight: 700;
            color: {COLORS['text_primary_dark'] if isDarkTheme() else COLORS['text_primary_light']};
        """)
        layout.addWidget(self.value_label)

        # Subtitle with optional trend
        bottom_layout = QHBoxLayout()
        self.subtitle_label = CaptionLabel(str(subtitle))
        self.subtitle_label.setStyleSheet(f"color: {COLORS['text_secondary']}; background: transparent; background-color: transparent;")
        bottom_layout.addWidget(self.subtitle_label)

        self.trend_label = CaptionLabel("")
        bottom_layout.addWidget(self.trend_label)

        bottom_layout.addStretch()
        layout.addLayout(bottom_layout)

        self.update_values(value=value, subtitle=subtitle, trend=trend, trend_positive=trend_positive)

        # Connect to theme changes
        qconfig.themeChangedFinished.connect(self._apply_theme)

    def update_values(self, *, value, subtitle, trend=None, trend_positive=True):
        self.value_label.setText(str(value))
        self.subtitle_label.setText(str(subtitle))

        if trend is None:
            self.trend_label.setVisible(False)
            self.trend_label.setText("")
            return

        self.trend_label.setVisible(True)
        trend_color = COLORS['success'] if trend_positive else COLORS['error']
        trend_icon = "↑" if trend_positive else "↓"
        self.trend_label.setText(f"{trend_icon} {abs(trend):.1f}%")
        self.trend_label.setStyleSheet(f"color: {trend_color}; font-weight: 600; background: transparent; background-color: transparent;")

    def _apply_theme(self):
        """Apply proper theming to card"""
        is_dark = isDarkTheme()
        card_bg = rgba_from_hex(COLORS['text_white'], 0.03) if is_dark else rgba_from_hex(COLORS['space_indigo'], 0.03)
        card_border = COLORS['border_dark'] if is_dark else COLORS['border_light']

        # Apply directly to this widget (avoid fragile class-name selectors in QSS)
        self.setStyleSheet(f"""
            background-color: {card_bg};
            border: 1px solid {card_border};
            border-radius: {RADII['md']}px;
        """)


class SimpleBarChart(QWidget):
    """Simple bar chart widget"""

    def __init__(self, data, labels, max_value=None, parent=None):
        super().__init__(parent)
        self.data = data  # List of values
        self.labels = labels  # List of labels
        self.max_value = max_value or (max(data) if data else 1)
        self.setMinimumHeight(200)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        width = self.width()
        height = self.height()

        if not self.data or not self.labels:
            return

        bar_count = len(self.data)
        bar_spacing = 10
        total_spacing = bar_spacing * (bar_count + 1)
        bar_width = (width - total_spacing) / bar_count

        # Draw bars
        for i, (value, label) in enumerate(zip(self.data, self.labels)):
            x = bar_spacing + i * (bar_width + bar_spacing)
            bar_height = (value / self.max_value) * (height - 60) if self.max_value > 0 else 0
            y = height - bar_height - 40

            # Bar
            is_dark = isDarkTheme()
            bar_color = QColor(COLORS['space_indigo'])
            painter.setBrush(bar_color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(int(x), int(y), int(bar_width), int(bar_height), 4, 4)

            # Value label
            font = QFont("Segoe UI", 10, QFont.Weight.Bold)
            painter.setFont(font)
            value_text = str(int(value))
            label_h = 20
            if y >= label_h + 2:
                # Enough room above the bar — draw above
                painter.setPen(QColor(COLORS['text_primary_dark'] if is_dark else COLORS['text_primary_light']))
                painter.drawText(int(x), int(y - label_h), int(bar_width), label_h, Qt.AlignmentFlag.AlignCenter, value_text)
            else:
                # Bar is too tall — draw inside the bar at the top
                painter.setPen(QColor("#FFFFFF"))
                painter.drawText(int(x), int(y + 4), int(bar_width), label_h, Qt.AlignmentFlag.AlignCenter, value_text)

            # Label at bottom
            painter.setPen(QColor(COLORS['text_secondary']))
            font = QFont("Segoe UI", 9)
            painter.setFont(font)
            painter.drawText(int(x), height - 30, int(bar_width), 20, Qt.AlignmentFlag.AlignCenter, label)


class DonutChart(QWidget):
    """Simple donut chart for success rate"""

    def __init__(self, percentage, parent=None):
        super().__init__(parent)
        self.percentage = max(0, min(100, percentage))
        self.setFixedSize(180, 180)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        def _blend(hex_a: str, hex_b: str, t: float) -> QColor:
            """Blend color A towards color B by t (0..1)."""
            t = max(0.0, min(1.0, float(t)))
            a = QColor(hex_a)
            b = QColor(hex_b)
            return QColor(
                int(a.red() * (1 - t) + b.red() * t),
                int(a.green() * (1 - t) + b.green() * t),
                int(a.blue() * (1 - t) + b.blue() * t),
                255,
            )

        # Center and radius
        cx, cy = self.width() // 2, self.height() // 2
        outer_radius = 70
        inner_radius = 50

        bg_hex = COLORS['space_indigo'] if isDarkTheme() else COLORS['platinum']

        # Background ring
        painter.setBrush(_blend(COLORS['text_tertiary'], bg_hex, 0.85))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(cx - outer_radius, cy - outer_radius, outer_radius * 2, outer_radius * 2)

        # Segments (softened towards background, but opaque to avoid muddy overlap)
        success_fill = _blend(COLORS['success'], bg_hex, 0.25)
        error_fill = _blend(COLORS['error'], bg_hex, 0.35)
        span_angle = int(360 * 16 * (self.percentage / 100))
        # Draw success first (from top), then remaining (fail) after it.
        if span_angle > 0:
            painter.setBrush(success_fill)
            painter.drawPie(
                cx - outer_radius,
                cy - outer_radius,
                outer_radius * 2,
                outer_radius * 2,
                90 * 16,
                -span_angle,
            )
        if span_angle < 360 * 16:
            painter.setBrush(error_fill)
            painter.drawPie(
                cx - outer_radius,
                cy - outer_radius,
                outer_radius * 2,
                outer_radius * 2,
                90 * 16 - span_angle,
                -(360 * 16 - span_angle),
            )

        # Inner circle (creates donut)
        painter.setBrush(QColor(bg_hex))
        painter.drawEllipse(cx - inner_radius, cy - inner_radius, inner_radius * 2, inner_radius * 2)

        # Percentage text
        painter.setPen(QColor(COLORS['text_primary_dark'] if isDarkTheme() else COLORS['text_primary_light']))
        font = QFont("Segoe UI", 24, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, f"{int(self.percentage)}%")


class AnalyticsScreen(ResponsiveWidget):
    """Analytics dashboard with comprehensive metrics and visualizations"""

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main = main_window
        self.db = main_window.db

        self._init_ui()
        self._apply_theme()
        self._apply_card_themes()  # Apply proper theming to all cards
        enforce_transparent_labels(self)
        self.load_analytics()
        self.update_translations()

        # Connect to theme change signal
        qconfig.themeChangedFinished.connect(self._on_theme_changed)

    def _init_ui(self):
        """Initialize UI"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(*PAGE_MARGINS)
        main_layout.setSpacing(PAGE_SPACING)

        # === HEADER ===
        header_layout = QHBoxLayout()
        header_layout.setSpacing(ICON_TEXT_GAP)

        # Header icon
        header_icon = TransparentToolButton(FluentIcon.PIE_SINGLE, self)
        header_icon.setFixedSize(SIZES['icon_lg'], SIZES['icon_lg'])
        header_icon.setEnabled(False)  # Icon only, not clickable

        # Title
        self.title_label = TitleLabel("")

        header_layout.addWidget(header_icon)
        header_layout.addWidget(self.title_label)
        header_layout.addStretch()

        main_layout.addLayout(header_layout)

        # Scroll area
        scroll = ScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(ScrollArea.Shape.NoFrame)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        # Reserve space so the (overlay) scrollbar doesn't cover card content
        content_layout.setContentsMargins(0, 0, SIZES['scrollbar_thickness'] + SPACING['xs'], 0)
        content_layout.setSpacing(CARD_SPACING)

        # Time range selector
        toolbar = self._create_toolbar()
        content_layout.addWidget(toolbar)

        # Key metrics (4 cards) - activity types
        metrics_grid = QGridLayout()
        metrics_grid.setSpacing(CARD_SPACING)

        # Make cards share available width evenly
        for col in range(4):
            metrics_grid.setColumnStretch(col, 1)

        self.regular_uploads_metric = MetricCard("Regular Uploads", "0", "", FluentIcon.UP)
        self.batch_uploads_metric = MetricCard("Batch Uploads", "0", "", FluentIcon.FOLDER)
        self.batch_desc_metric = MetricCard("Batch Descriptions", "0", "", FluentIcon.DOCUMENT)
        self.batch_titles_metric = MetricCard("Batch Titles", "0", "", FluentIcon.EDIT)

        metrics_grid.addWidget(self.regular_uploads_metric, 0, 0)
        metrics_grid.addWidget(self.batch_uploads_metric, 0, 1)
        metrics_grid.addWidget(self.batch_desc_metric, 0, 2)
        metrics_grid.addWidget(self.batch_titles_metric, 0, 3)

        content_layout.addLayout(metrics_grid)

        # Charts row
        charts_layout = QHBoxLayout()
        charts_layout.setSpacing(CARD_SPACING)

        # Brand performance chart
        self.brand_chart_card = CardWidget()
        self.brand_chart_card.setBorderRadius(RADII['md'])
        brand_chart_layout = QVBoxLayout(self.brand_chart_card)
        brand_chart_layout.setContentsMargins(*CARD_MARGINS)
        brand_chart_layout.setSpacing(SPACING['md'])

        brand_title = StrongBodyLabel("Brand Performance")
        brand_title.setStyleSheet(f"font-size: {FONTS['size_subtitle_2']};")
        brand_chart_layout.addWidget(brand_title)

        self.brand_chart = SimpleBarChart([], [])
        brand_chart_layout.addWidget(self.brand_chart)

        charts_layout.addWidget(self.brand_chart_card, 2)

        # Success donut chart
        self.success_chart_card = CardWidget()
        self.success_chart_card.setBorderRadius(RADII['md'])
        success_chart_layout = QVBoxLayout(self.success_chart_card)
        success_chart_layout.setContentsMargins(*CARD_MARGINS)
        success_chart_layout.setSpacing(SPACING['md'])
        success_chart_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        success_title = StrongBodyLabel("Success Rate")
        success_title.setStyleSheet(f"font-size: {FONTS['size_subtitle_2']};")
        success_chart_layout.addWidget(success_title, 0, Qt.AlignmentFlag.AlignCenter)

        self.success_donut = DonutChart(0)
        success_chart_layout.addWidget(self.success_donut, 0, Qt.AlignmentFlag.AlignCenter)

        success_caption = CaptionLabel("Last 30 days")
        success_caption.setStyleSheet(f"color: {COLORS['text_tertiary']}; background: transparent; background-color: transparent;")
        success_chart_layout.addWidget(success_caption, 0, Qt.AlignmentFlag.AlignCenter)

        charts_layout.addWidget(self.success_chart_card, 1)

        content_layout.addLayout(charts_layout)

        # Recent activity card
        self.activity_card = CardWidget()
        self.activity_card.setBorderRadius(RADII['md'])
        activity_layout = QVBoxLayout(self.activity_card)
        activity_layout.setContentsMargins(*CARD_MARGINS)
        activity_layout.setSpacing(SPACING['md'])

        activity_header = QHBoxLayout()
        activity_title = StrongBodyLabel("Recent Activity")
        activity_title.setStyleSheet(f"font-size: {FONTS['size_subtitle_2']};")
        activity_header.addWidget(activity_title)
        activity_header.addStretch()

        view_all_btn = TransparentToolButton(FluentIcon.RIGHT_ARROW)
        view_all_btn.setToolTip("View full history")
        view_all_btn.clicked.connect(self._view_full_history)
        activity_header.addWidget(view_all_btn)

        activity_layout.addLayout(activity_header)

        self.activity_container = QVBoxLayout()
        self.activity_container.setSpacing(TIGHT_SPACING)
        activity_layout.addLayout(self.activity_container)

        content_layout.addWidget(self.activity_card)

        # Top errors card
        self.errors_card = CardWidget()
        self.errors_card.setBorderRadius(RADII['md'])
        errors_layout = QVBoxLayout(self.errors_card)
        errors_layout.setContentsMargins(*CARD_MARGINS)
        errors_layout.setSpacing(SPACING['md'])

        errors_title = StrongBodyLabel("Common Issues")
        errors_title.setStyleSheet(f"font-size: {FONTS['size_subtitle_2']};")
        errors_layout.addWidget(errors_title)

        self.errors_container = QVBoxLayout()
        self.errors_container.setSpacing(TIGHT_SPACING)
        errors_layout.addLayout(self.errors_container)

        content_layout.addWidget(self.errors_card)

        content_layout.addStretch()
        scroll.setWidget(content)
        main_layout.addWidget(scroll)

        self.scroll = scroll
        self.content_widget = content

    def _apply_theme(self):
        """Apply consistent screen theming (background + scroll viewport + label transparency)."""
        apply_screen_theme(
            self,
            "AnalyticsScreen",
            scroll=getattr(self, "scroll", None),
            content=getattr(self, "content_widget", None),
            transparent_labels=True,
        )

        # Rounded scrollbars for the main scroll area
        try:
            scroll = getattr(self, "scroll", None)
            if scroll is not None:
                is_dark = isDarkTheme()
                bg_color = COLORS['space_indigo'] if is_dark else COLORS['platinum']
                handle = rgba_from_hex(COLORS['lavender_grey'], 0.35) if is_dark else rgba_from_hex(COLORS['space_indigo'], 0.22)
                handle_hover = rgba_from_hex(COLORS['lavender_grey'], 0.55) if is_dark else rgba_from_hex(COLORS['space_indigo'], 0.32)
                scroll.setStyleSheet(
                    (scroll.styleSheet() or "")
                    + f"""
                    QScrollBar:vertical {{
                        background: transparent;
                        width: {SIZES['scrollbar_thickness']}px;
                        margin: 0px;
                    }}
                    QScrollBar::handle:vertical {{
                        background: {handle};
                        border-radius: {RADII['sm']}px;
                        min-height: {SIZES['scrollbar_handle_min']}px;
                    }}
                    QScrollBar::handle:vertical:hover {{
                        background: {handle_hover};
                    }}
                    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                        height: 0px;
                    }}
                    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                        background: none;
                    }}

                    QScrollBar:horizontal {{
                        background: transparent;
                        height: {SIZES['scrollbar_thickness']}px;
                        margin: 0px;
                    }}
                    QScrollBar::handle:horizontal {{
                        background: {handle};
                        border-radius: {RADII['sm']}px;
                        min-width: {SIZES['scrollbar_handle_min']}px;
                    }}
                    QScrollBar::handle:horizontal:hover {{
                        background: {handle_hover};
                    }}
                    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                        width: 0px;
                    }}
                    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
                        background: none;
                    }}
                    """
                )
                try:
                    scroll.setViewportMargins(0, 0, SIZES['scrollbar_thickness'] + SPACING['xs'], 0)
                except Exception:
                    pass
        except Exception:
            pass
        enforce_transparent_labels(self)

    def _create_toolbar(self):
        """Create toolbar with filters"""
        self.toolbar_card = CardWidget()
        self.toolbar_card.setBorderRadius(RADII['md'])
        toolbar_layout = QHBoxLayout(self.toolbar_card)
        toolbar_layout.setContentsMargins(*CARD_MARGINS)
        toolbar_layout.setSpacing(CARD_SPACING)

        # Time range filter
        period_label = BodyLabel("Period:")
        toolbar_layout.addWidget(period_label)

        self.period_combo = ComboBox()
        self.period_combo.addItems(["Last 7 days", "Last 30 days", "Last 90 days", "All time"])
        self.period_combo.setCurrentIndex(1)  # Default: Last 30 days
        self.period_combo.currentTextChanged.connect(self.load_analytics)
        toolbar_layout.addWidget(self.period_combo)

        toolbar_layout.addStretch()

        # Refresh button
        refresh_btn = TransparentToolButton(FluentIcon.SYNC)
        refresh_btn.setToolTip("Refresh analytics")
        refresh_btn.clicked.connect(self.load_analytics)
        toolbar_layout.addWidget(refresh_btn)

        # Export button
        export_btn = PushButton("Export")
        export_btn.setIcon(FluentIcon.SAVE.icon())
        export_btn.clicked.connect(self._export_analytics)
        toolbar_layout.addWidget(export_btn)

        return self.toolbar_card

    def _apply_card_themes(self):
        """Apply proper theming to all cards"""
        is_dark = isDarkTheme()

        # Chart/content cards - subtle tinted backgrounds
        card_bg = rgba_from_hex(COLORS['text_white'], 0.03) if is_dark else rgba_from_hex(COLORS['space_indigo'], 0.03)
        card_border = COLORS['border_dark'] if is_dark else COLORS['border_light']

        # Apply directly on each card instance (avoid selector scoping issues)
        card_style = f"""
            background-color: {card_bg};
            border: 1px solid {card_border};
            border-radius: {RADII['md']}px;
        """

        # Apply to all content cards
        for card_attr in ['toolbar_card', 'brand_chart_card', 'success_chart_card',
                         'activity_card', 'errors_card']:
            if hasattr(self, card_attr):
                card_widget = getattr(self, card_attr)
                if card_widget is not None:
                    card_widget.setStyleSheet(card_style)

    def load_analytics(self):
        """Load and display analytics data"""
        cursor = self.db.conn.cursor()

        # Get time range
        period = self.period_combo.currentText()
        days_map = {
            "Last 7 days": 7,
            "Last 30 days": 30,
            "Last 90 days": 90,
            "All time": None
        }
        days = days_map.get(period)

        # Build date filter
        date_filter = ""
        params = []
        if days:
            date_threshold = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            date_filter = "WHERE DATE(processed_at) >= ?"
            params.append(date_threshold)

        # Overall counts + success rate (for donut)
        total_query = f"SELECT COUNT(*) FROM processing_history {date_filter}"
        total = cursor.execute(total_query, params).fetchone()[0]
        success_query = f"SELECT COUNT(*) FROM processing_history {date_filter} {'AND' if date_filter else 'WHERE'} status = 'success'"
        success = cursor.execute(success_query, params).fetchone()[0]
        success_rate = (success / total * 100) if total > 0 else 0

        # Activity-type counts (uses batch_id prefixes)
        where_prefix = "AND" if date_filter else "WHERE"

        regular_count = cursor.execute(
            f"SELECT COUNT(*) FROM processing_history {date_filter} {where_prefix} (batch_id IS NULL OR batch_id = '')",
            params,
        ).fetchone()[0]
        batch_upload_count = cursor.execute(
            f"SELECT COUNT(*) FROM processing_history {date_filter} {where_prefix} batch_id LIKE 'batch_%'",
            params,
        ).fetchone()[0]
        batch_desc_count = cursor.execute(
            f"SELECT COUNT(*) FROM processing_history {date_filter} {where_prefix} batch_id LIKE 'batchdesc_%'",
            params,
        ).fetchone()[0]
        batch_titles_count = cursor.execute(
            f"SELECT COUNT(*) FROM processing_history {date_filter} {where_prefix} batch_id LIKE 'batchtitle_%'",
            params,
        ).fetchone()[0]

        # Update metric cards
        self._update_metric(self.regular_uploads_metric, f"{regular_count:,}", period)
        self._update_metric(self.batch_uploads_metric, f"{batch_upload_count:,}", period)
        self._update_metric(self.batch_desc_metric, f"{batch_desc_count:,}", period)
        self._update_metric(self.batch_titles_metric, f"{batch_titles_count:,}", period)

        # Update success donut
        self.success_donut.percentage = success_rate
        self.success_donut.update()

        # Brand performance
        brand_query = f"""
            SELECT brand, COUNT(*) as count
            FROM processing_history
            {date_filter}
            GROUP BY brand
            ORDER BY count DESC
            LIMIT 8
        """
        brand_data = cursor.execute(brand_query, params).fetchall()

        if brand_data:
            brands = [row[0] for row in brand_data]
            counts = [row[1] for row in brand_data]
            self.brand_chart.data = counts
            self.brand_chart.labels = brands
            self.brand_chart.max_value = max(counts) if counts else 1
            self.brand_chart.update()

        # Recent activity (last 10)
        self._clear_layout(self.activity_container)

        recent_query = f"""
            SELECT brand, product_code, status, processed_at, batch_id
            FROM processing_history
            ORDER BY processed_at DESC
            LIMIT 10
        """
        recent = cursor.execute(recent_query).fetchall()

        for row in recent:
            item = self._create_activity_item(row[0], row[1], row[2], row[3], row[4])
            self.activity_container.addWidget(item)

        # Common errors
        self._clear_layout(self.errors_container)

        error_query = f"""
            SELECT error_message, COUNT(*) as count
            FROM processing_history
            {date_filter}
            {'AND' if date_filter else 'WHERE'} status = 'failed'
            AND error_message IS NOT NULL
            AND error_message != ''
            GROUP BY error_message
            ORDER BY count DESC
            LIMIT 5
        """
        errors = cursor.execute(error_query, params).fetchall()

        if errors:
            for row in errors:
                error_item = self._create_error_item(row[0], row[1])
                self.errors_container.addWidget(error_item)
        else:
            no_errors = CaptionLabel("No errors in this period")
            no_errors.setStyleSheet(f"color: {COLORS['success']}; font-style: italic; background: transparent; background-color: transparent;")
            self.errors_container.addWidget(no_errors)

    def _update_metric(self, card, value, subtitle, trend=None, trend_positive=True):
        """Update a metric card's values"""
        if hasattr(card, "update_values"):
            card.update_values(value=value, subtitle=subtitle, trend=trend, trend_positive=trend_positive)
            return

        # Fallback for older card variants
        for child in card.findChildren(QLabel):
            if "font-size: 36px" in child.styleSheet():
                child.setText(str(value))
                break

    def _create_activity_item(self, brand, code, status, timestamp, batch_id=None):
        """Create a recent activity item"""
        item = QWidget()
        item.setStyleSheet("background: transparent; background-color: transparent; border: none;")
        layout = QHBoxLayout(item)
        layout.setContentsMargins(SPACING['sm'], SPACING['sm'], SPACING['sm'], SPACING['sm'])
        layout.setSpacing(CARD_SPACING)

        # Activity type
        activity_type = "Regular" if not batch_id else (
            "Batch Upload" if str(batch_id).startswith('batch_') else (
                "Batch Descriptions" if str(batch_id).startswith('batchdesc_') else (
                    "Batch Titles" if str(batch_id).startswith('batchtitle_') else "Batch"
                )
            )
        )

        # Status icon
        status_icon = FluentIcon.ACCEPT if status == 'success' else FluentIcon.CANCEL
        status_color = COLORS['success'] if status == 'success' else COLORS['error']
        icon = IconWidget(status_icon)
        icon.setFixedSize(SIZES['icon_sm'], SIZES['icon_sm'])
        icon.setStyleSheet(f"color: {status_color}; background: transparent; background-color: transparent;")
        layout.addWidget(icon)

        # Brand and code
        text = BodyLabel(f"{activity_type} • {brand} • {code}")
        text.setStyleSheet(
            f"color: {COLORS['text_primary_dark'] if isDarkTheme() else COLORS['text_primary_light']};"
            "background: transparent; background-color: transparent; border: none;"
        )
        layout.addWidget(text)

        layout.addStretch()

        # Time
        try:
            if isinstance(timestamp, str):
                dt = datetime.fromisoformat(timestamp.replace('Z', '').replace('T', ' '))
            else:
                dt = timestamp
            time_ago = self._time_ago(dt)
            time_label = CaptionLabel(time_ago)
            time_label.setStyleSheet(f"color: {COLORS['text_tertiary']}; background: transparent; background-color: transparent; border: none;")
            layout.addWidget(time_label)
        except:
            pass

        return item

    def _create_error_item(self, error_msg, count):
        """Create an error item"""
        item = QWidget()
        item.setStyleSheet("background: transparent; background-color: transparent; border: none;")
        layout = QHBoxLayout(item)
        layout.setContentsMargins(SPACING['sm'], SPACING['sm'], SPACING['sm'], SPACING['sm'])
        layout.setSpacing(CARD_SPACING)

        # Count badge
        count_label = StrongBodyLabel(f"{count}×")
        count_label.setFixedWidth(50)
        count_label.setStyleSheet(f"color: {COLORS['error']}; font-weight: 700; background: transparent; background-color: transparent; border: none;")
        layout.addWidget(count_label)

        # Error message (truncated)
        display_error = error_msg if len(error_msg) <= 80 else error_msg[:77] + "..."
        error_label = BodyLabel(display_error)
        error_label.setWordWrap(False)
        error_label.setStyleSheet(f"color: {COLORS['text_secondary']}; background: transparent; background-color: transparent; border: none;")
        layout.addWidget(error_label, 1)

        return item

    def _time_ago(self, dt):
        """Convert datetime to relative time"""
        now = datetime.now()
        diff = now - dt

        if diff.days > 0:
            return f"{diff.days}d ago"
        elif diff.seconds >= 3600:
            return f"{diff.seconds // 3600}h ago"
        elif diff.seconds >= 60:
            return f"{diff.seconds // 60}m ago"
        else:
            return "Just now"

    def _clear_layout(self, layout):
        """Clear all widgets from layout"""
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _view_full_history(self):
        """Switch to full history view"""
        # Import and show HistoryScreen
        from GUI_Qt.screens.FullHistoryScreen import HistoryScreen

        if not hasattr(self.main, '_full_history_screen') or self.main._full_history_screen is None:
            self.main._full_history_screen = HistoryScreen(self.main)
            self.main._add_screen_to_stack(self.main._full_history_screen, "Full History")

        self.main._show_screen(self.main._full_history_screen)

    def _export_analytics(self):
        """Export analytics to Excel"""
        try:
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Export Analytics",
                f"analytics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                "Excel Files (*.xlsx)"
            )

            if not file_path:
                return

            wb = Workbook()
            ws = wb.active
            ws.title = "Analytics Summary"

            # Headers
            headers = ["Metric", "Value"]
            for col, header in enumerate(headers, 1):
                cell = ws.cell(1, col, header)
                cell.font = Font(bold=True)
                cell.fill = PatternFill(start_color="4F46E5", fill_type="solid")
                cell.font = Font(color="FFFFFF", bold=True)

            # Get current metrics
            cursor = self.db.conn.cursor()
            total = cursor.execute("SELECT COUNT(*) FROM processing_history").fetchone()[0]
            success = cursor.execute("SELECT COUNT(*) FROM processing_history WHERE status = 'success'").fetchone()[0]
            success_rate = (success / total * 100) if total > 0 else 0

            regular = cursor.execute("SELECT COUNT(*) FROM processing_history WHERE batch_id IS NULL OR batch_id = ''").fetchone()[0]
            batch_up = cursor.execute("SELECT COUNT(*) FROM processing_history WHERE batch_id LIKE 'batch_%'").fetchone()[0]
            batch_desc = cursor.execute("SELECT COUNT(*) FROM processing_history WHERE batch_id LIKE 'batchdesc_%'").fetchone()[0]
            batch_titles = cursor.execute("SELECT COUNT(*) FROM processing_history WHERE batch_id LIKE 'batchtitle_%'").fetchone()[0]

            # Write data
            data = [
                ["Total Activities", total],
                ["Successful", success],
                ["Success Rate", f"{success_rate:.1f}%"],
                ["Failed", total - success],
                ["Regular Uploads", regular],
                ["Batch Uploads", batch_up],
                ["Batch Descriptions", batch_desc],
                ["Batch Titles", batch_titles],
            ]

            for row_idx, row_data in enumerate(data, 2):
                for col_idx, value in enumerate(row_data, 1):
                    ws.cell(row_idx, col_idx, value)

            wb.save(file_path)

            InfoBar.success(
                title="Export Successful",
                content=f"Analytics exported to {file_path}",
                parent=self,
                position=InfoBarPosition.TOP,
                duration=3000
            )
        except Exception as e:
            InfoBar.error(
                title="Export Failed",
                content=str(e),
                parent=self,
                position=InfoBarPosition.TOP,
                duration=3000
            )

    def update_translations(self):
        """Update UI text for current language"""
        tr = self.main.i18n.tr
        self.title_label.setText(tr("analytics.title", default="Analytics"))

    def _on_breakpoint_changed(self, breakpoint: str):
        """Respond to breakpoint changes - adjust margins and spacing."""
        margins = get_responsive_margins(breakpoint)
        spacing = get_responsive_spacing(breakpoint)

        # Update main layout margins
        if self.layout():
            self.layout().setContentsMargins(*margins)
            self.layout().setSpacing(spacing)

        # Update content widget if it exists
        if hasattr(self, 'content_widget') and self.content_widget.layout():
            # For AnalyticsScreen, the content widget already has custom margins
            # Only update spacing to maintain the scrollbar offset
            self.content_widget.layout().setSpacing(spacing)

    def _on_theme_changed(self):
        """Handle theme change"""
        self._apply_theme()
        self._apply_card_themes()  # Re-apply card styling on theme change
        enforce_transparent_labels(self)
        self.load_analytics()  # Reload to update colors
