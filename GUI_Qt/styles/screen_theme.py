"""Shared screen theming helpers.

Centralizes the common pattern used across screens:
- Apply a consistent background (space_indigo/platinum)
- Ensure ScrollArea and its viewport paint the same background
- Keep QFluent label widgets transparent to avoid "text blocks"

Keep this small and dependency-free so screens can adopt it incrementally.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QLabel, QSizePolicy, QWidget

from qfluentwidgets import ScrollArea, isDarkTheme

from GUI_Qt.styles.theme_config import (
    COLORS,
    FONTS,
    SPACING,
    SIZES,
    get_surface_color,
    get_text_color,
)


# =====================
# Fluent layout presets
# =====================

# Windows/Fluent-style page gutters used across this app.
# Keep these centralized so we can tune spacing globally.
PAGE_MARGINS = (SPACING["xxxl"], SPACING["lg"], SPACING["xxxl"], SPACING["lg"])  # 40,20,40,20
PAGE_SPACING = SPACING["lg"]  # 20

# Standard card padding (used for toolbars/sections)
CARD_MARGINS = (SPACING["xl"], SPACING["lg"], SPACING["xl"], SPACING["lg"])  # 24,20,24,20
CARD_SPACING = SPACING["base"]  # 16

# Large cards (forms) need slightly more breathing room.
CARD_MARGINS_LARGE = (SPACING["xxl"], SPACING["xxl"], SPACING["xxl"], SPACING["xxl"])  # 32
CARD_SPACING_LARGE = SPACING["xl"]  # 24

# Centered form containers (Login / MasterPassword) use larger padding.
CENTER_FORM_MARGINS = (SPACING["xxxl"], SPACING["xxxl"], SPACING["xxxl"], SPACING["xxxl"])  # 40

# Compact inline gaps
ROW_SPACING = SPACING["sm"]  # 8
ICON_TEXT_GAP = SPACING["md"]  # 12

# Common content gaps (used in many forms and card internals)
CONTENT_SPACING = SPACING["md"]  # 12

# Common paddings used across toolbars/footers/panels
TOOLBAR_MARGINS = (SPACING["lg"], SPACING["base"], SPACING["lg"], SPACING["base"])  # 20,16,20,16
FOOTER_MARGINS = (SPACING["lg"], SPACING["md"], SPACING["lg"], SPACING["md"])  # 20,12,20,12
PANEL_MARGINS = (SPACING["base"], SPACING["base"], SPACING["base"], SPACING["base"])  # 16

# Small gaps used in compact sublayouts
MICRO_SPACING = SPACING["xxs"]  # 2
TIGHT_SPACING = SPACING["xs"]   # 4

# Non-grid but repeated in a few places (kept exact for parity)
MID_SPACING = 10

# Common “pill”/chip padding for compact labels (keep exact for UX parity)
PILL_MARGINS = (10, 8, 10, 8)

# Table cell widget margins (prevents gridlines from overlapping input borders)
TABLE_CELL_MARGINS = (SPACING["sm"], SPACING["xxs"], SPACING["sm"], SPACING["xxs"])  # 8,2,8,2

# Reused “details” layout constants (kept exact to avoid UI regressions)
DETAILS_MARGINS = (12, 10, 12, 10)
DETAILS_SPACING = 6

# Navigation footer (version label) layout
NAV_VERSION_MARGINS = (SPACING["base"], SPACING["xs"], SPACING["base"], 6)
NAV_VERSION_SPACING = 6


def _normalize_label_widget(label: QLabel) -> None:
    """Apply label transparency without re-entering Qt style events."""

    try:
        # Some labels (badges/counters) intentionally use backgrounds.
        if bool(label.property("ubAllowBg")):
            return

        current = label.styleSheet() or ""
        override = "\n".join(
            [
                "background: transparent;",
                "background-color: transparent;",
                "border: none;",
            ]
        )
        if current.strip():
            if override not in current:
                label.setStyleSheet(current.rstrip() + "\n" + override)
        else:
            label.setStyleSheet(override)

        # Setting a stylesheet makes Qt re-enable WA_StyledBackground. Clear
        # it afterwards or transparent labels paint their Window palette role
        # (the page canvas) as a visible rectangle over elevated cards.
        label.setAutoFillBackground(False)
        label.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        label.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
    except Exception:
        return


def enforce_transparent_labels(root: QWidget) -> None:
    """Force all QLabel descendants to paint with transparent backgrounds.

    This counters QFluentWidgets (or other code) applying per-widget styles that
    can result in visible background rectangles behind text.
    """

    try:
        from qfluentwidgets import CheckBox

        # Normalize all QLabel widgets (includes BodyLabel, CaptionLabel, etc.)
        for label in root.findChildren(QLabel):
            _normalize_label_widget(label)

        # Also normalize all CheckBox widgets
        for checkbox in root.findChildren(CheckBox):
            try:
                checkbox.setStyleSheet("QCheckBox { background: transparent; } QCheckBox::indicator { background: transparent; }")
            except Exception:
                pass

        # Qt may polish a stylesheet on the next event-loop turn and restore
        # WA_StyledBackground. Clear only the paint flags once that deferred
        # polish has completed; changing the flags does not trigger restyling.
        QTimer.singleShot(0, lambda: _clear_transparent_label_paint_flags(root))
    except Exception:
        return


def _clear_transparent_label_paint_flags(root: QWidget) -> None:
    """Finish label normalization after Qt's deferred stylesheet polish."""

    try:
        for label in root.findChildren(QLabel):
            if bool(label.property("ubAllowBg")):
                continue
            label.setAutoFillBackground(False)
            label.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
            label.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
    except RuntimeError:
        # The page may have been destroyed before the queued normalization.
        return


def enforce_responsive_text(root: QWidget) -> None:
    """Allow explanatory labels to wrap instead of widening whole pages."""
    try:
        for label in root.findChildren(QLabel):
            if bool(label.property("ubNoWrap")):
                continue
            text = (label.text() or "").strip()
            if len(text) < 48 and "\n" not in text:
                continue
            label.setWordWrap(True)
            label.setMinimumWidth(0)
            # QLabel's minimum size hint can still be the unwrapped text width.
            # Ignoring the horizontal hint lets the parent layout choose the
            # available width, after which Qt wraps the text normally.
            label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    except Exception:
        return


def apply_screen_palette(root: QWidget) -> None:
    """Give every page a theme canvas without replacing local stylesheets.

    This is a fallback for older and inherited pages that do not call
    ``apply_screen_theme`` themselves. Explicit card and table styles still win.
    """
    try:
        is_dark = isDarkTheme()
        canvas = QColor(get_surface_color(is_dark, 'canvas'))
        surface = QColor(get_surface_color(is_dark))
        alternate = QColor(get_surface_color(is_dark, 'alternate'))
        selected = QColor(get_surface_color(is_dark, 'selected'))
        primary = QColor(get_text_color(is_dark, 'primary'))
        secondary = QColor(get_text_color(is_dark, 'secondary'))
        disabled = QColor(get_text_color(is_dark, 'disabled'))
        palette = root.palette()
        palette.setColor(QPalette.ColorRole.Window, canvas)
        palette.setColor(QPalette.ColorRole.WindowText, primary)
        palette.setColor(QPalette.ColorRole.Text, primary)
        palette.setColor(QPalette.ColorRole.ButtonText, primary)
        palette.setColor(QPalette.ColorRole.Base, surface)
        palette.setColor(QPalette.ColorRole.AlternateBase, alternate)
        palette.setColor(QPalette.ColorRole.ToolTipBase, surface)
        palette.setColor(QPalette.ColorRole.ToolTipText, primary)
        palette.setColor(QPalette.ColorRole.PlaceholderText, secondary)
        palette.setColor(QPalette.ColorRole.Highlight, selected)
        palette.setColor(QPalette.ColorRole.HighlightedText, primary)
        for role in (
            QPalette.ColorRole.WindowText,
            QPalette.ColorRole.Text,
            QPalette.ColorRole.ButtonText,
        ):
            palette.setColor(QPalette.ColorGroup.Disabled, role, disabled)
        root.setPalette(palette)
        root.setAutoFillBackground(True)
    except Exception:
        return


def get_screen_background() -> str:
    return get_surface_color(isDarkTheme(), 'canvas')


def get_responsive_margins(breakpoint: str) -> tuple:
    """Return appropriate margins for breakpoint.

    Args:
        breakpoint: Current breakpoint ('xs', 'sm', 'md', 'lg', 'xl', 'xxl')

    Returns:
        Tuple of (left, top, right, bottom) margins in pixels
    """
    if breakpoint == 'xs':
        return (SPACING['lg'], SPACING['md'], SPACING['lg'], SPACING['md'])  # 20, 12, 20, 12
    elif breakpoint == 'sm':
        return (SPACING['xl'], SPACING['lg'], SPACING['xl'], SPACING['lg'])  # 24, 20, 24, 20
    else:
        return PAGE_MARGINS  # 40, 20, 40, 20


def get_responsive_spacing(breakpoint: str) -> int:
    """Return layout spacing for breakpoint.

    Args:
        breakpoint: Current breakpoint ('xs', 'sm', 'md', 'lg', 'xl', 'xxl')

    Returns:
        Spacing value in pixels
    """
    if breakpoint == 'xs':
        return SPACING['md']  # 12 - Compact
    else:
        return PAGE_SPACING  # 20 - Normal


def get_responsive_card_max_width(breakpoint: str, card_type: str = 'form') -> int | None:
    """Return max card width for breakpoint, or None for full-width.

    Args:
        breakpoint: Current breakpoint ('xs', 'sm', 'md', 'lg', 'xl', 'xxl')
        card_type: Type of card ('form', 'options', or other)

    Returns:
        Maximum width in pixels, or None for full width
    """
    if breakpoint in ('xs', 'sm'):
        return None  # Full width on narrow screens
    elif card_type == 'form':
        return SIZES['form_card_max_width']  # 1600
    elif card_type == 'options':
        return SIZES['options_card_max_width']  # 760
    else:
        return SIZES['form_card_max_width']


def apply_screen_theme(
    screen: QWidget,
    selector: str,
    *,
    scroll: Optional[ScrollArea] = None,
    content: Optional[QWidget] = None,
    transparent_labels: bool = True,
    label_radius_px: int | None = None,
) -> None:
    """Apply consistent background styling.

    Args:
        screen: The screen root widget.
        selector: QSS selector to scope styling (usually the class name, e.g. "AccountScreen").
        scroll: Optional QFluent ScrollArea instance.
        content: Optional widget used as the ScrollArea content.
        transparent_labels: When True, forces QLabel-like widgets to be transparent.
    """

    is_dark = isDarkTheme()
    bg_color = get_screen_background()
    text_color = get_text_color(is_dark, 'primary')
    secondary_text = get_text_color(is_dark, 'secondary')

    # Ensure the widget actually paints its background, including when a local
    # selector stops matching after a subclass is introduced.
    apply_screen_palette(screen)

    label_rules = ""
    if transparent_labels or label_radius_px is not None:
        label_rules = f"""
            {selector} QLabel,
            {selector} BodyLabel,
            {selector} CaptionLabel,
            {selector} StrongBodyLabel,
            {selector} TitleLabel {{
                color: {text_color};
                {('background: transparent; background-color: transparent; border: none;' if transparent_labels else '')}
                {f'border-radius: {int(label_radius_px)}px;' if label_radius_px is not None else ''}
            }}
            {selector} CaptionLabel {{
                color: {secondary_text};
            }}
        """

    screen.setStyleSheet(
        f"""
            {selector} {{
                background-color: {bg_color};
                color: {text_color};
                font-family: {FONTS['family']};
            }}
            {label_rules}
        """
    )

    if scroll is not None:
        # Some screens need explicit viewport painting to avoid white/light defaults.
        scroll.setStyleSheet(
            f"""
                QScrollArea {{
                    border: none;
                    background-color: {bg_color};
                    color: {text_color};
                }}
                QScrollArea QWidget#qt_scrollarea_viewport {{
                    background-color: {bg_color};
                    color: {text_color};
                }}
            """
        )

    if content is not None:
        content.setStyleSheet(f"background-color: {bg_color}; color: {text_color};")

    # Enforce transparent labels even when individual widgets override styles
    if transparent_labels:
        enforce_transparent_labels(screen)
    enforce_responsive_text(screen)
