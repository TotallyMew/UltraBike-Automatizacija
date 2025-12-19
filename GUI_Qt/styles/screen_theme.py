"""Shared screen theming helpers.

Centralizes the common pattern used across screens:
- Apply a consistent background (space_indigo/platinum)
- Ensure ScrollArea and its viewport paint the same background
- Keep QFluent label widgets transparent to avoid "text blocks"

Keep this small and dependency-free so screens can adopt it incrementally.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QLabel, QWidget

from qfluentwidgets import ScrollArea, isDarkTheme

from GUI_Qt.styles.theme_config import COLORS, FONTS


class _TransparentLabelEventFilter(QObject):
    """Keeps label widgets transparent even if QFluent re-styles them."""

    def __init__(self, owner: QWidget):
        super().__init__(owner)
        self._owner = owner

    def eventFilter(self, watched, event):  # noqa: N802 (Qt naming)
        if isinstance(watched, QLabel):
            t = event.type()
            if t in (
                QEvent.Type.Polish,
                QEvent.Type.StyleChange,
                QEvent.Type.PaletteChange,
                QEvent.Type.Show,
                QEvent.Type.DynamicPropertyChange,
            ):
                _normalize_label_widget(watched)
        return super().eventFilter(watched, event)


def _normalize_label_widget(label: QLabel) -> None:
    """Apply the strongest safe transparency settings to a label."""

    try:
        label.setAutoFillBackground(False)
        label.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        label.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)

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
    except Exception:
        return


def enforce_transparent_labels(root: QWidget) -> None:
    """Force all QLabel descendants to paint with transparent backgrounds.

    This counters QFluentWidgets (or other code) applying per-widget styles that
    can result in visible background rectangles behind text.
    """

    try:
        flt = getattr(root, "_ub_transparent_label_filter", None)
        if flt is None:
            flt = _TransparentLabelEventFilter(root)
            setattr(root, "_ub_transparent_label_filter", flt)

        for label in root.findChildren(QLabel):
            _normalize_label_widget(label)
            try:
                label.installEventFilter(flt)
            except Exception:
                pass
    except Exception:
        return


def get_screen_background() -> str:
    return COLORS["space_indigo"] if isDarkTheme() else COLORS["platinum"]


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

    bg_color = get_screen_background()

    # Ensure the widget actually paints its background.
    try:
        screen.setAutoFillBackground(True)
    except Exception:
        pass

    label_rules = ""
    if transparent_labels or label_radius_px is not None:
        label_rules = f"""
            {selector} QLabel,
            {selector} BodyLabel,
            {selector} CaptionLabel,
            {selector} StrongBodyLabel,
            {selector} TitleLabel {{
                {('background: transparent; background-color: transparent; border: none;' if transparent_labels else '')}
                {f'border-radius: {int(label_radius_px)}px;' if label_radius_px is not None else ''}
            }}
        """

    screen.setStyleSheet(
        f"""
            {selector} {{
                background-color: {bg_color};
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
                }}
                QScrollArea QWidget#qt_scrollarea_viewport {{
                    background-color: {bg_color};
                }}
            """
        )

    if content is not None:
        content.setStyleSheet(f"background-color: {bg_color};")
