"""Theme-aware application loading screen."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    IndeterminateProgressRing,
    TitleLabel,
    isDarkTheme,
    qconfig,
)

from GUI_Qt.styles.screen_theme import apply_screen_theme
from GUI_Qt.styles.theme_config import (
    COLORS,
    FONTS,
    RADII,
    SPACING,
    get_subtle_border,
    get_surface_color,
    get_text_color,
)


class LoadingWidget(QWidget):
    """Centered loading state used while the app changes major views."""

    def __init__(self, message=None, tr=None, parent=None):
        super().__init__(parent)
        self.tr = tr or (lambda key, **values: key.format(**values) if values else key)
        self.message = message if message is not None else self.tr("loading.default")
        self._init_ui()
        self._apply_theme()
        qconfig.themeChangedFinished.connect(self._apply_theme)

    def _init_ui(self) -> None:
        self.setObjectName("loadingScreen")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        root = QVBoxLayout(self)
        root.setContentsMargins(SPACING["xl"], SPACING["xl"], SPACING["xl"], SPACING["xl"])
        root.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.card = QFrame(self)
        self.card.setObjectName("loadingCard")
        self.card.setMinimumWidth(360)
        self.card.setMaximumWidth(480)
        self.card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(
            SPACING["xxl"], SPACING["xxl"], SPACING["xxl"], SPACING["xxl"]
        )
        card_layout.setSpacing(SPACING["lg"])

        self.accent = QFrame(self.card)
        self.accent.setObjectName("loadingAccent")
        self.accent.setFixedSize(72, 4)
        card_layout.addWidget(self.accent, 0, Qt.AlignmentFlag.AlignHCenter)

        self.spinner = IndeterminateProgressRing(self.card)
        self.spinner.setFixedSize(52, 52)
        self.spinner.setStrokeWidth(4)
        self.spinner.setAccessibleName(self.tr("loading.default"))
        card_layout.addWidget(self.spinner, 0, Qt.AlignmentFlag.AlignHCenter)

        heading = QVBoxLayout()
        heading.setSpacing(SPACING["xs"])
        self.title_label = TitleLabel(self.tr("loading.title"), self.card)
        self.title_label.setObjectName("loadingTitle")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heading.addWidget(self.title_label)

        self.subtitle_label = CaptionLabel(self.tr("loading.subtitle"), self.card)
        self.subtitle_label.setObjectName("loadingSubtitle")
        self.subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heading.addWidget(self.subtitle_label)
        card_layout.addLayout(heading)

        self.status_panel = QFrame(self.card)
        self.status_panel.setObjectName("loadingStatusPanel")
        status_layout = QVBoxLayout(self.status_panel)
        status_layout.setContentsMargins(
            SPACING["base"], SPACING["md"], SPACING["base"], SPACING["md"]
        )
        self.message_label = BodyLabel(self.message, self.status_panel)
        self.message_label.setObjectName("loadingMessage")
        self.message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.message_label.setWordWrap(True)
        status_layout.addWidget(self.message_label)
        card_layout.addWidget(self.status_panel)

        root.addWidget(self.card, 0, Qt.AlignmentFlag.AlignCenter)
        self.set_message(self.message)

    def _apply_theme(self) -> None:
        dark = isDarkTheme()
        canvas = get_surface_color(dark, "canvas")
        surface = get_surface_color(dark)
        alternate = get_surface_color(dark, "alternate")
        border = get_subtle_border(dark)
        primary = get_text_color(dark, "primary")
        secondary = get_text_color(dark, "secondary")
        accent = COLORS["accent_dark" if dark else "accent_light"]
        accent_end = COLORS["blush_rose"]

        apply_screen_theme(self, "LoadingWidget")
        self.setStyleSheet(
            self.styleSheet()
            + f"""
            LoadingWidget {{
                background-color: {canvas};
            }}
            LoadingWidget QFrame#loadingCard {{
                background-color: {surface};
                border: 1px solid {border};
                border-radius: {RADII['lg']}px;
            }}
            LoadingWidget QFrame#loadingAccent {{
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 0,
                    stop: 0 {accent}, stop: 1 {accent_end}
                );
                border: none;
                border-radius: 2px;
            }}
            LoadingWidget QLabel#loadingTitle {{
                color: {primary};
                background: transparent;
                border: none;
                font-family: {FONTS['family']};
                font-size: {FONTS['size_title_2']};
                font-weight: 700;
            }}
            LoadingWidget QLabel#loadingSubtitle {{
                color: {secondary};
                background: transparent;
                border: none;
                font-size: {FONTS['size_body_sm']};
            }}
            LoadingWidget QFrame#loadingStatusPanel {{
                background-color: {alternate};
                border: 1px solid {border};
                border-radius: {RADII['md']}px;
            }}
            LoadingWidget QLabel#loadingMessage {{
                color: {primary};
                background: transparent;
                border: none;
                font-size: {FONTS['size_body']};
                font-weight: 600;
            }}
            """
        )

        shadow = self.card.graphicsEffect()
        if not isinstance(shadow, QGraphicsDropShadowEffect):
            shadow = QGraphicsDropShadowEffect(self.card)
            shadow.setBlurRadius(36)
            shadow.setOffset(0, 10)
            self.card.setGraphicsEffect(shadow)
        shadow.setColor(QColor(0, 0, 0, 90 if dark else 35))

    def set_message(self, message) -> None:
        """Update the visible and accessible loading status."""

        self.message = str(message or "").strip()
        self.message_label.setText(self.message)
        self.status_panel.setVisible(bool(self.message))
        self.setAccessibleName(self.tr("loading.title"))
        self.setAccessibleDescription(self.message or self.tr("loading.default"))
