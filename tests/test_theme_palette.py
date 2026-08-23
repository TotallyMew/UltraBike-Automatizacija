from __future__ import annotations

import pytest

from GUI_Qt.styles.theme_config import COLORS, get_accent_colors, get_surface_color


def _relative_luminance(hex_color: str) -> float:
    channels = [int(hex_color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [
        channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4
        for channel in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast(first: str, second: str) -> float:
    lighter, darker = sorted(
        (_relative_luminance(first), _relative_luminance(second)), reverse=True
    )
    return (lighter + 0.05) / (darker + 0.05)


@pytest.mark.parametrize("is_dark", [False, True])
def test_accent_foregrounds_meet_wcag_aa(is_dark: bool) -> None:
    accent = get_accent_colors(is_dark)
    assert _contrast(accent["base"], accent["text"]) >= 4.5


@pytest.mark.parametrize(
    ("fill", "foreground"),
    [
        (COLORS["success"], COLORS["on_success"]),
        (COLORS["warning"], COLORS["on_warning"]),
    ],
)
def test_semantic_fill_foregrounds_meet_wcag_aa(fill: str, foreground: str) -> None:
    assert _contrast(fill, foreground) >= 4.5


@pytest.mark.parametrize("is_dark", [False, True])
def test_canvas_and_cards_are_distinct_surfaces(is_dark: bool) -> None:
    assert get_surface_color(is_dark, "canvas") != get_surface_color(is_dark, "surface")
    assert get_surface_color(is_dark, "surface") != get_surface_color(is_dark, "alternate")
