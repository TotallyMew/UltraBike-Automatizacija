from __future__ import annotations

import pytest

from GUI_Qt.styles.theme_config import (
    COLORS,
    MODE_COLOR_ROLES,
    THEME_COLORS,
    get_accent_colors,
    get_activity_heatmap_colors,
    get_semantic_colors,
    get_surface_color,
    get_text_color,
)


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
    for state in ("base", "hover", "pressed"):
        assert _contrast(accent[state], accent["text"]) >= 4.5


@pytest.mark.parametrize("is_dark", [False, True])
@pytest.mark.parametrize("status", ["success", "warning", "error", "info"])
def test_semantic_roles_meet_wcag_aa(status: str, is_dark: bool) -> None:
    semantic = get_semantic_colors(status, is_dark)
    assert _contrast(semantic["fill"], semantic["on_fill"]) >= 4.5
    for surface_role in ("canvas", "surface", "alternate"):
        surface = get_surface_color(is_dark, surface_role)
        assert _contrast(semantic["text"], surface) >= 4.5


@pytest.mark.parametrize("is_dark", [False, True])
@pytest.mark.parametrize("text_role", ["primary", "secondary"])
def test_readable_text_roles_meet_wcag_aa_on_all_surfaces(
    text_role: str, is_dark: bool
) -> None:
    text = get_text_color(is_dark, text_role)
    for surface_role in ("canvas", "surface", "alternate"):
        assert _contrast(text, get_surface_color(is_dark, surface_role)) >= 4.5


@pytest.mark.parametrize("is_dark", [False, True])
def test_canvas_and_cards_are_distinct_surfaces(is_dark: bool) -> None:
    assert get_surface_color(is_dark, "canvas") != get_surface_color(is_dark, "surface")
    assert get_surface_color(is_dark, "surface") != get_surface_color(is_dark, "alternate")


@pytest.mark.parametrize("is_dark", [False, True])
def test_activity_heatmap_levels_have_clear_tonal_separation(is_dark: bool) -> None:
    levels = get_activity_heatmap_colors(is_dark)
    luminance = [_relative_luminance(color) for color in levels]

    assert len(levels) == 5
    assert len(set(levels)) == 5
    if is_dark:
        assert luminance == sorted(luminance)
        assert min(b - a for a, b in zip(luminance, luminance[1:])) >= 0.05
    else:
        assert luminance == sorted(luminance, reverse=True)
        assert min(a - b for a, b in zip(luminance, luminance[1:])) >= 0.12


def test_primary_role_reverses_brightness_between_modes() -> None:
    light_primary = THEME_COLORS["light"]["primary"].name().upper()
    dark_primary = THEME_COLORS["dark"]["primary"].name().upper()
    assert light_primary == COLORS["accent_light"]
    assert dark_primary == COLORS["accent_dark"]
    assert _relative_luminance(dark_primary) > _relative_luminance(light_primary)


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_complete_functional_role_map(mode: str) -> None:
    required_roles = {
        "canvas",
        "surface",
        "surface_alt",
        "stroke",
        "stroke_subtle",
        "accent",
        "accent_hover",
        "accent_pressed",
        "accent_text",
        "text_primary",
        "text_secondary",
        "text_tertiary",
        "text_disabled",
        "hover_layer",
        "pressed_layer",
        "selected_surface",
        "disabled_surface",
        "info_fill",
        "info_text",
    }
    assert required_roles <= MODE_COLOR_ROLES[mode].keys()
