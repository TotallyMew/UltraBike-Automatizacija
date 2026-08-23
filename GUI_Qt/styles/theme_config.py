"""
Fluent Design System Theme Configuration
Colors, spacing, and typography standards
Premium Space Indigo & Lavender palette
"""

from qfluentwidgets import Theme, isDarkTheme, qconfig, setTheme, setThemeColor
from PySide6.QtGui import QColor


def rgba_from_hex(hex_color: str, alpha: float) -> str:
    """Return a CSS rgba(r,g,b,a) string from a hex color."""
    if not hex_color:
        return f"rgba(0, 0, 0, {alpha})"

    h = hex_color.strip().lstrip('#')
    if len(h) == 3:
        h = ''.join([c * 2 for c in h])
    if len(h) != 6:
        return f"rgba(0, 0, 0, {alpha})"

    r = int(h[0:2], 16)
    g = int(h[2:4], 16)
    b = int(h[4:6], 16)
    return f"rgba({r}, {g}, {b}, {alpha})"


def rgba_rgb(r: int, g: int, b: int, alpha: float) -> str:
    """Return a CSS rgba(r,g,b,a) string from RGB values."""
    return f"rgba({r}, {g}, {b}, {alpha})"


def get_hover_bg(is_dark: bool) -> str:
    """Return the neutral hover overlay for the active theme."""
    return COLORS['hover_layer_dark'] if is_dark else COLORS['hover_layer_light']


def get_pressed_bg(is_dark: bool) -> str:
    """Return the neutral pressed/active overlay for the active theme."""
    return COLORS['pressed_layer_dark'] if is_dark else COLORS['pressed_layer_light']


def get_details_card_bg(is_dark: bool) -> str:
    """Background tint for small details/info cards."""
    return get_surface_color(is_dark, 'alternate')


def get_embedded_input_border(is_dark: bool) -> str:
    return (
        rgba_from_hex(COLORS['lavender_grey'], 0.85)
        if is_dark
        else rgba_from_hex(COLORS['space_indigo'], 0.45)
    )


def get_selection_bg(is_dark: bool) -> str:
    """Return the selected-item surface for the active theme."""
    return COLORS['selected_surface_dark'] if is_dark else COLORS['selected_surface_light']


def get_subtle_border(is_dark: bool) -> str:
    return COLORS['stroke_dark'] if is_dark else COLORS['stroke_light']


def get_subtle_item_hover_bg(is_dark: bool) -> str:
    return get_hover_bg(is_dark)


def get_scrollbar_handle_bg(is_dark: bool) -> str:
    return (
        rgba_from_hex(COLORS['lavender_grey'], 0.3)
        if is_dark
        else rgba_from_hex(COLORS['space_indigo'], 0.2)
    )


def get_scrollbar_handle_hover_bg(is_dark: bool) -> str:
    return (
        rgba_from_hex(COLORS['lavender_grey'], 0.5)
        if is_dark
        else rgba_from_hex(COLORS['space_indigo'], 0.3)
    )


def get_card_border_light() -> str:
    return COLORS['stroke_light']

# Brand swatches are stable; UI code should consume the mode-aware roles below.
CORE_SWATCHES = {
    'space_indigo': '#2B2D42',
    'lavender_grey': '#8D99AE',
    'platinum': '#EDF2F4',
    'blush_rose': '#E36588',
    'blush_rose_dark': '#C94A6E',
    'flag_red': '#C81D25',
}


# Canonical role map.  Keeping light and dark values together makes role
# reversals (especially the primary accent) explicit and reviewable.
MODE_COLOR_ROLES = {
    'light': {
        # Neutral ramp / elevation
        'canvas': '#F8FAFC',
        'surface': '#FFFFFF',
        'surface_alt': '#F1F5F9',
        'stroke': '#E2E8F0',
        'stroke_subtle': '#F1F5F9',

        # Brand interaction ramp
        'accent': '#2B2D42',
        'accent_hover': '#3D405B',
        'accent_pressed': '#202234',
        'accent_text': '#FFFFFF',
        'focus_ring': '#4338CA',

        # Text roles
        'text_primary': '#0F172A',
        'text_secondary': '#475569',
        'text_tertiary': '#64748B',
        'text_disabled': '#CBD5E1',

        # Neutral interaction states
        'hover_layer': 'rgba(0, 0, 0, 0.04)',
        'pressed_layer': 'rgba(0, 0, 0, 0.08)',
        'selected_surface': '#E0E7FF',
        'disabled_surface': '#F1F5F9',

        # Semantic fills and accessible foregrounds
        'success_fill': '#10B981',
        'success_text': '#047857',
        'success_on_fill': '#062A20',
        'warning_fill': '#F59E0B',
        'warning_text': '#8A4B08',
        'warning_on_fill': '#2B2D42',
        'error_fill': '#DC2626',
        'error_text': '#B4232C',
        'error_on_fill': '#FFFFFF',
        'info_fill': '#3B82F6',
        'info_text': '#1D4ED8',
        'info_on_fill': '#0F172A',
        'success_bg': '#ECFDF5',
        'warning_bg': '#FFFBEB',
        'error_bg': '#FEF2F2',
        'info_bg': '#EFF6FF',
    },
    'dark': {
        # Neutral ramp / elevation
        'canvas': '#13151F',
        'surface': '#1F2332',
        'surface_alt': '#282C3F',
        'stroke': '#2E344A',
        'stroke_subtle': '#222636',

        # The accent deliberately reverses brightness in dark mode.
        'accent': '#9DA8B9',
        'accent_hover': '#B8C2D1',
        'accent_pressed': '#8793A6',
        'accent_text': '#13151F',
        'focus_ring': '#A5B0C1',

        # Text roles
        'text_primary': '#F1F5F9',
        'text_secondary': '#94A3B8',
        'text_tertiary': '#64748B',
        'text_disabled': '#475569',

        # Neutral interaction states
        'hover_layer': 'rgba(255, 255, 255, 0.06)',
        'pressed_layer': 'rgba(255, 255, 255, 0.12)',
        'selected_surface': '#2E3558',
        'disabled_surface': '#282C3F',

        # Semantic fills and accessible foregrounds
        'success_fill': '#10B981',
        'success_text': '#6EE7B7',
        'success_on_fill': '#062A20',
        'warning_fill': '#F59E0B',
        'warning_text': '#FCD34D',
        'warning_on_fill': '#2B2D42',
        'error_fill': '#EF4444',
        'error_text': '#FDA4AF',
        'error_on_fill': '#13151F',
        'info_fill': '#60A5FA',
        'info_text': '#93C5FD',
        'info_on_fill': '#13151F',
        'success_bg': 'rgba(16, 185, 129, 0.12)',
        'warning_bg': 'rgba(245, 158, 11, 0.12)',
        'error_bg': 'rgba(239, 68, 68, 0.12)',
        'info_bg': 'rgba(96, 165, 250, 0.12)',
    },
}


# Ordered data-visualization scale: no activity, then four increasing levels.
# These are opaque by design. Alpha-composited lavender steps collapsed into
# nearly identical greys on dark surfaces and made the heatmap unreadable.
ACTIVITY_HEATMAP_LEVELS = {
    'light': ('#E2E8F0', '#CBD5E1', '#A5B4FC', '#818CF8', '#4338CA'),
    'dark': ('#30384F', '#49597A', '#697DA5', '#91A4CF', '#C2CCE0'),
}


# QColor roles used by Qt/Fluent APIs.  The top-level mode key prevents a dark
# screen from accidentally receiving the light-only Space Indigo primary.
THEME_COLORS = {
    mode: {
        'primary': QColor(roles['accent']),
        'primary_hover': QColor(roles['accent_hover']),
        'primary_pressed': QColor(roles['accent_pressed']),
        'on_primary': QColor(roles['accent_text']),
        'canvas': QColor(roles['canvas']),
        'surface': QColor(roles['surface']),
        'secondary_text': QColor(roles['text_secondary']),
        'focus_ring': QColor(roles['focus_ring']),
    }
    for mode, roles in MODE_COLOR_ROLES.items()
}


# Flat stylesheet tokens.  Mode-aware roles are generated from the canonical
# map; the aliases at the bottom remain for gradual migration of older screens.
COLORS = {
    **CORE_SWATCHES,
    **{
        f'{role}_{mode}': value
        for mode, roles in MODE_COLOR_ROLES.items()
        for role, value in roles.items()
    },

    # Legacy aliases (prefer the explicit role helpers in new code).
    'success': MODE_COLOR_ROLES['light']['success_fill'],
    'warning': MODE_COLOR_ROLES['light']['warning_fill'],
    'error': MODE_COLOR_ROLES['light']['error_fill'],
    'info': MODE_COLOR_ROLES['light']['info_fill'],
    'on_success': MODE_COLOR_ROLES['light']['success_on_fill'],
    'on_warning': MODE_COLOR_ROLES['light']['warning_on_fill'],
    'on_error': MODE_COLOR_ROLES['light']['error_on_fill'],
    'on_info': MODE_COLOR_ROLES['light']['info_on_fill'],
    'focus_ring': MODE_COLOR_ROLES['light']['focus_ring'],
    'text_white': '#FFFFFF',
    'bg_dark': MODE_COLOR_ROLES['dark']['canvas'],
    'bg_light': MODE_COLOR_ROLES['light']['surface'],
    'bg_alt_dark': MODE_COLOR_ROLES['dark']['surface_alt'],
    'bg_alt_light': MODE_COLOR_ROLES['light']['surface_alt'],
    'border_dark': MODE_COLOR_ROLES['dark']['stroke'],
    'border_light': MODE_COLOR_ROLES['light']['stroke'],

    # Excel export colors (for consistency)
    'excel_header_bg': '#2B2D42',
    'excel_header_text': '#8D99AE',
    'excel_highlight': '#8D99AE',

    # Standard opacity values for consistency
    'hover_opacity_dark': '0.15',
    'hover_opacity_light': '0.05',
    'card_bg_opacity_dark': '0.03',
    'card_bg_opacity_light': '0.02',

    # Status background tints (for validation/highlight states)
    'status_success_bg_light': MODE_COLOR_ROLES['light']['success_bg'],
    'status_success_bg_dark': MODE_COLOR_ROLES['dark']['success_bg'],
    'status_warning_bg_light': MODE_COLOR_ROLES['light']['warning_bg'],
    'status_warning_bg_dark': MODE_COLOR_ROLES['dark']['warning_bg'],
    'status_error_bg_light': MODE_COLOR_ROLES['light']['error_bg'],
    'status_error_bg_dark': MODE_COLOR_ROLES['dark']['error_bg'],
    'status_info_bg_light': MODE_COLOR_ROLES['light']['info_bg'],
    'status_info_bg_dark': MODE_COLOR_ROLES['dark']['info_bg'],
}

# Shared layout/shape tokens (avoid magic numbers in QSS)
RADII = {
    'xs': 4,
    'sm': 6,
    'md': 8,
    'lg': 12,
}

PADDINGS = {
    # Common QSS padding strings
    'input': '8px 12px',
    'combo': '6px 10px',
    'combo_item': '8px 10px',
    'table_cell': '8px 12px',
    'table_header': '12px 12px',
    'xs': '4px',
    'badge': '6px 16px',
    'pill': '8px 16px',
    'tab': '10px 20px',
    'tree_item': '6px 6px',
}


def get_text_color(is_dark: bool, role: str = 'primary') -> str:
    """Return a theme-aware text color.

    Roles: primary | secondary | tertiary/muted | disabled | inverse
    """
    role = (role or 'primary').strip().lower()

    if role == 'primary':
        return COLORS['text_primary_dark'] if is_dark else COLORS['text_primary_light']
    if role == 'secondary':
        return COLORS['text_secondary_dark'] if is_dark else COLORS['text_secondary_light']
    if role in ('tertiary', 'muted'):
        return COLORS['text_tertiary_dark'] if is_dark else COLORS['text_tertiary_light']
    if role in ('disabled', 'inactive'):
        return COLORS['text_disabled_dark'] if is_dark else COLORS['text_disabled_light']
    if role == 'inverse':
        return COLORS['text_white']

    # Fallback to primary to avoid unreadable text
    return COLORS['text_primary_dark'] if is_dark else COLORS['text_primary_light']


def get_focus_color(is_dark: bool) -> str:
    """Return a focus-ring color with contrast against the current canvas."""
    return COLORS['focus_ring_dark'] if is_dark else COLORS['focus_ring_light']


def get_status_text_color(status: str, is_dark: bool = False) -> str:
    """Return a theme-aware semantic status foreground color."""
    status = (status or '').strip().lower()
    if status in ('success', 'saved_manually', 'ok', 'valid'):
        return COLORS['success_text_dark'] if is_dark else COLORS['success_text_light']
    if status in ('ready_for_review', 'warning', 'warn', 'mixed'):
        return COLORS['warning_text_dark'] if is_dark else COLORS['warning_text_light']
    if status in ('error', 'danger', 'invalid'):
        return COLORS['error_text_dark'] if is_dark else COLORS['error_text_light']
    if status in ('info', 'information', 'neutral'):
        return COLORS['info_text_dark'] if is_dark else COLORS['info_text_light']
    return get_text_color(is_dark, 'tertiary')


def get_semantic_colors(status: str, is_dark: bool = False) -> dict[str, str]:
    """Return fill, text, on-fill, and subtle-background semantic roles."""
    status = (status or '').strip().lower()
    aliases = {
        'ok': 'success',
        'valid': 'success',
        'saved_manually': 'success',
        'warn': 'warning',
        'mixed': 'warning',
        'ready_for_review': 'warning',
        'danger': 'error',
        'invalid': 'error',
        'failed': 'error',
        'information': 'info',
        'neutral': 'info',
    }
    semantic = aliases.get(status, status)
    if semantic not in ('success', 'warning', 'error', 'info'):
        semantic = 'info'
    suffix = 'dark' if is_dark else 'light'
    return {
        'fill': COLORS[f'{semantic}_fill_{suffix}'],
        'text': COLORS[f'{semantic}_text_{suffix}'],
        'on_fill': COLORS[f'{semantic}_on_fill_{suffix}'],
        'background': COLORS[f'{semantic}_bg_{suffix}'],
    }


def get_status_row_style(is_dark: bool, status: str) -> str:
    """QSS for row validation highlighting used in batch Excel preview."""
    status = (status or '').strip().lower()

    if status in ('success', 'saved_manually', 'ok', 'valid'):
        bg = get_semantic_colors('success', is_dark)['background']
    elif status in ('ready_for_review', 'warning', 'warn', 'mixed'):
        bg = get_semantic_colors('warning', is_dark)['background']
    elif status in ('error', 'failed', 'danger', 'invalid'):
        bg = get_semantic_colors('error', is_dark)['background']
    elif status in ('info', 'information', 'neutral'):
        bg = get_semantic_colors('info', is_dark)['background']
    else:
        bg = 'transparent'

    return f"background-color: {bg}; border-radius: {RADII['xs']}px; padding: {PADDINGS['xs']};"

# Spacing System - Fluent Design 2 (4px base unit, 40epx grid)
SPACING = {
    'xxs': 2,   # Icon alignment
    'xs': 4,    # Minimal spacing
    'sm': 8,    # Tight spacing
    'md': 12,   # Default spacing
    'base': 16, # Standard spacing
    'lg': 20,   # Comfortable spacing
    'xl': 24,   # Card padding
    'xxl': 32,  # Section spacing
    'xxxl': 40, # Screen margins (Fluent standard)
}

# Shared UI size tokens (pixels)
# Keep this small: add only values repeated across the app.
SIZES = {
    # Common icon / button sizes
    'icon_xs': 16,
    'icon_sm': 20,
    'icon_md': 24,
    'icon_action': 28,
    'icon_lg': 32,
    'icon_xl': 40,
    'icon_huge': 96,

    # Activity indicators
    'progress_ring': 28,
    'progress_ring_lg': 32,
    'spinner': 80,

    # Form/control sizing
    'input_height': 40,
    'button_height': 40,
    'button_height_sm': 36,

    # Tables
    'table_header_height': 48,
    'table_row_height': 44,
    'table_row_height_lg': 64,

    # Scrollbars (QSS metrics)
    'scrollbar_thickness': 12,
    'scrollbar_handle_min': 30,

    # Common table column widths (used by batch screens)
    'col_w_56': 56,
    'col_w_60': 60,
    'col_w_120': 120,
    'col_w_140': 140,
    'col_w_160': 160,
    'col_w_180': 180,
    'col_w_200': 200,
    'col_w_240': 240,
    'col_w_260': 260,
    'col_w_280': 280,
    'col_w_320': 320,
    'col_w_420': 420,

    # Tree views
    'tree_indent': 18,

    # Common fixed widths
    'browse_button_width': 100,
    'items_per_page_width': 80,
    'label_min_width': 100,
    'field_min_width_sm': 120,
    'field_min_width_md': 200,
    'panel_min_width': 420,
    'panel_min_width_lg': 440,
    'left_panel_min_width': 320,
    'sidebar_min_width': 250,
    'dialog_min_width': 360,
    'field_min_width_lg': 260,
    'check_col_width': 70,
    'check_col_width_sm': 50,
    'filter_min_width': 140,
    'stat_card_height': 110,
    'history_card_min_height': 160,
    'tree_min_height': 220,
    'form_card_max_width': 1600,
    'options_card_max_width': 760,
    'divider_thickness': 1,
    'center_form_max_width': 400,
}

# Typography System - Fluent Design 2 Type Ramp
FONTS = {
    'family': 'Segoe UI, Inter, -apple-system, BlinkMacSystemFont, sans-serif',
    'family_mono': 'JetBrains Mono, Consolas, Monaco, Courier New, monospace',

    # Fluent Design 2 Type Ramp (Web)
    'size_display': '68px',
    'size_large_title': '40px',
    'size_title_1': '32px',
    'size_title_2': '28px',
    'size_title_3': '24px',
    'size_subtitle_1': '20px',
    'size_subtitle_2': '16px',
    'size_body': '14px',        # Default body text
    # Common in-app sizes (kept to avoid visual regressions while removing magic numbers)
    'size_body_sm': '13px',
    'size_body_lg': '15px',
    'size_caption': '12px',
    'size_caption_sm': '11px',
    'size_caption_2': '10px',

    # Line heights
    'lineheight_title': '1.4',
    'lineheight_body': '1.5',
    'lineheight_caption': '1.4',
    'weight_regular': 400,
    'weight_medium': 500,
    'weight_semibold': 600,
    'weight_bold': 700,
}

# Component-specific colors (for consistent theming)
COMPONENT_COLORS = {
    'input': {
        'bg_dark': COLORS['surface_alt_dark'],
        'bg_light': COLORS['surface_light'],
        'border_dark': COLORS['stroke_dark'],
        'border_light': COLORS['stroke_light'],
        'text_dark': COLORS['text_primary_dark'],
        'text_light': COLORS['text_primary_light'],
        'placeholder_dark': COLORS['text_secondary_dark'],
        'placeholder_light': COLORS['text_tertiary_light'],
    },
    'button': {
        # Legacy static values. New code should use get_accent_colors().
        'primary_bg': COLORS['accent_light'],
        'primary_hover': COLORS['accent_hover_light'],
        'primary_text': COLORS['accent_text_light'],
        'secondary_bg_dark': COLORS['surface_alt_dark'],
        'secondary_bg_light': COLORS['surface_alt_light'],
        'secondary_hover_dark': COLORS['selected_surface_dark'],
        'secondary_hover_light': COLORS['selected_surface_light'],
        'secondary_text_dark': COLORS['text_primary_dark'],
        'secondary_text_light': COLORS['text_primary_light'],
    },
    'card': {
        'bg_dark': COLORS['surface_dark'],
        'bg_light': COLORS['surface_light'],
        'border_dark': COLORS['stroke_dark'],
        'border_light': COLORS['stroke_light'],
    },
    'table': {
        'header_bg_dark': COLORS['surface_alt_dark'],
        'header_bg_light': COLORS['accent_light'],
        'header_text_dark': COLORS['text_primary_dark'],
        'header_text_light': COLORS['accent_text_light'],
        'row_bg_dark': COLORS['surface_dark'],
        'row_bg_light': COLORS['surface_light'],
        'row_alt_bg_dark': COLORS['surface_alt_dark'],
        'row_alt_bg_light': COLORS['surface_alt_light'],
        'border_dark': COLORS['stroke_dark'],
        'border_light': COLORS['stroke_light'],
    },
}


def get_accent_colors(is_dark: bool) -> dict[str, str]:
    """Return the interactive accent ramp and its accessible foreground."""
    suffix = 'dark' if is_dark else 'light'
    return {
        'base': COLORS[f'accent_{suffix}'],
        'hover': COLORS[f'accent_hover_{suffix}'],
        'pressed': COLORS[f'accent_pressed_{suffix}'],
        'text': COLORS[f'accent_text_{suffix}'],
    }


def get_theme_colors(is_dark: bool) -> dict[str, QColor]:
    """Return QColor theme roles without flattening light and dark values."""
    return THEME_COLORS['dark' if is_dark else 'light']


def get_activity_heatmap_colors(is_dark: bool) -> tuple[str, ...]:
    """Return five clearly separated activity levels for the active mode."""
    return ACTIVITY_HEATMAP_LEVELS['dark' if is_dark else 'light']


def get_surface_color(is_dark: bool, role: str = 'surface') -> str:
    """Return a canvas/surface role for the active theme."""
    role = (role or 'surface').strip().lower()
    suffix = 'dark' if is_dark else 'light'
    if role == 'canvas':
        return COLORS[f'canvas_{suffix}']
    if role in ('alternate', 'alt', 'subtle'):
        return COLORS[f'surface_alt_{suffix}']
    if role in ('stroke', 'border', 'separator'):
        return COLORS[f'stroke_{suffix}']
    if role in ('stroke_subtle', 'border_subtle', 'separator_subtle'):
        return COLORS[f'stroke_subtle_{suffix}']
    if role in ('selected', 'selection'):
        return COLORS[f'selected_surface_{suffix}']
    if role in ('disabled', 'inactive'):
        return COLORS[f'disabled_surface_{suffix}']
    return COLORS[f'surface_{suffix}']

def apply_theme(app):
    """Apply Fluent Design theme to the application"""
    setTheme(Theme.AUTO)  # Respects system light/dark mode
    setThemeColor(QColor(get_accent_colors(isDarkTheme())['base']))


def set_mode_aware_theme(is_dark: bool, *, lazy: bool = True) -> bool:
    """Switch mode and accent with one QFluent stylesheet refresh.

    Priming ``themeColor`` before ``setTheme`` avoids the usual second full
    widget-tree restyle that would otherwise be caused by ``setThemeColor``.
    Returns whether the light/dark mode itself changed.
    """

    is_dark = bool(is_dark)
    accent = QColor(get_accent_colors(is_dark)['base'])
    current_accent = QColor(qconfig.get(qconfig.themeColor))

    if is_dark == isDarkTheme():
        if current_accent != accent:
            setThemeColor(accent, lazy=lazy)
        return False

    if current_accent != accent:
        # setTheme() below performs the stylesheet update using this value.
        qconfig.set(qconfig.themeColor, accent)
    setTheme(Theme.DARK if is_dark else Theme.LIGHT, lazy=lazy)
    return True

def get_input_style(is_dark: bool, has_error: bool = False, is_valid: bool = False) -> str:
    """Generate consistent input field stylesheet"""
    colors = COMPONENT_COLORS['input']
    bg = colors['bg_dark'] if is_dark else colors['bg_light']
    border = colors['border_dark'] if is_dark else colors['border_light']
    text = colors['text_dark'] if is_dark else colors['text_light']

    border_color = border
    if has_error:
        border_color = COLORS['error']
    elif is_valid:
        border_color = COLORS['success']

    return f"""
        background-color: {bg};
        color: {text};
        border: 1px solid {border_color};
        border-radius: {RADII['sm']}px;
        padding: {PADDINGS['input']};
        font-family: {FONTS['family']};
        font-size: {FONTS['size_body']};
    """


def get_form_input_style(is_dark: bool, selector: str, *, calendar: bool = False) -> str:
    """Return a complete themed style for spin/date controls in form dialogs."""
    input_colors = COMPONENT_COLORS['input']
    input_text = input_colors['text_dark'] if is_dark else input_colors['text_light']
    disabled_bg = get_surface_color(is_dark, 'disabled')
    disabled_text = get_text_color(is_dark, 'disabled')
    border = COLORS['border_dark'] if is_dark else COLORS['border_light']
    focus = get_focus_color(is_dark)
    calendar_rules = ""
    if calendar:
        icon_color = 'white' if is_dark else 'black'
        calendar_rules = f"""
            {selector}::drop-down {{
                subcontrol-origin: border;
                subcontrol-position: top right;
                width: 36px;
                background: transparent;
                border: none;
            }}
            {selector}::down-arrow {{
                image: url(:/qfluentwidgets/images/icons/Calendar_{icon_color}.svg);
                width: {SIZES['icon_xs']}px;
                height: {SIZES['icon_xs']}px;
            }}
            QCalendarWidget QWidget {{
                background-color: {COLORS['bg_dark'] if is_dark else COLORS['bg_light']};
                color: {get_text_color(is_dark, 'primary')};
            }}
            QCalendarWidget QToolButton {{
                color: {get_text_color(is_dark, 'primary')};
                background: transparent;
                border: none;
            }}
            QCalendarWidget QAbstractItemView {{
                color: {get_text_color(is_dark, 'primary')};
                background-color: {COLORS['bg_dark'] if is_dark else COLORS['bg_light']};
                selection-background-color: {get_selection_bg(is_dark)};
                selection-color: {get_text_color(is_dark, 'primary')};
                outline: none;
            }}
        """

    return f"""
        {selector} {{
            {get_input_style(is_dark)}
            padding: 0 {SPACING['md']}px;
            selection-background-color: {get_selection_bg(is_dark)};
            selection-color: {input_text};
        }}

        {selector}:hover {{
            border-color: {get_subtle_border(is_dark)};
        }}

        {selector}:focus {{
            border: 2px solid {focus};
        }}

        {selector}:disabled {{
            background-color: {disabled_bg};
            color: {disabled_text};
            border-color: {border};
        }}

        {calendar_rules}
    """


def get_dialog_button_style(is_dark: bool, *, primary: bool) -> str:
    """Return token-based primary or secondary dialog button styling."""
    button_colors = COMPONENT_COLORS['button']
    border = COLORS['border_dark'] if is_dark else COLORS['border_light']
    focus = get_focus_color(is_dark)
    if primary:
        accent = get_accent_colors(is_dark)
        return f"""
            PrimaryPushButton {{
                min-width: 96px;
                background-color: {accent['base']};
                color: {accent['text']};
                border: 1px solid {accent['base']};
                border-radius: {RADII['sm']}px;
                padding: 0 {SPACING['base']}px;
                font-weight: {FONTS['weight_semibold']};
            }}
            PrimaryPushButton:hover {{
                background-color: {accent['hover']};
                border-color: {accent['hover']};
            }}
            PrimaryPushButton:pressed {{
                background-color: {accent['pressed']};
                border-color: {accent['pressed']};
            }}
            PrimaryPushButton:focus {{ border: 2px solid {focus}; }}
            PrimaryPushButton:disabled {{
                color: {get_text_color(is_dark, 'disabled')};
                background-color: {get_surface_color(is_dark, 'disabled')};
                border-color: {border};
            }}
        """

    secondary_bg = (
        button_colors['secondary_bg_dark']
        if is_dark
        else button_colors['secondary_bg_light']
    )
    secondary_hover = (
        button_colors['secondary_hover_dark']
        if is_dark
        else button_colors['secondary_hover_light']
    )
    secondary_button_text = (
        button_colors['secondary_text_dark']
        if is_dark
        else button_colors['secondary_text_light']
    )
    return f"""
        PushButton {{
            min-width: 96px;
            background-color: {secondary_bg};
            color: {secondary_button_text};
            border: 1px solid {border};
            border-radius: {RADII['sm']}px;
            padding: 0 {SPACING['base']}px;
        }}
        PushButton:hover {{
            background-color: {secondary_hover};
            border-color: {get_subtle_border(is_dark)};
        }}
        PushButton:pressed {{ background-color: {get_pressed_bg(is_dark)}; }}
        PushButton:focus {{ border: 2px solid {focus}; }}
        PushButton:disabled {{
            color: {get_text_color(is_dark, 'disabled')};
            background-color: {get_surface_color(is_dark, 'disabled')};
            border-color: {border};
        }}
    """


def get_dialog_danger_button_style(is_dark: bool) -> str:
    """Return a restrained destructive treatment for dialog actions."""
    danger = get_status_text_color('error', is_dark)
    border = COLORS['border_dark'] if is_dark else COLORS['border_light']
    hover = COLORS['status_error_bg_dark'] if is_dark else COLORS['status_error_bg_light']
    focus = get_focus_color(is_dark)
    return f"""
        PushButton {{
            min-width: 96px;
            color: {danger};
            background: transparent;
            border: 1px solid {border};
            border-radius: {RADII['sm']}px;
            padding: 0 {SPACING['base']}px;
        }}
        PushButton:hover {{
            background-color: {hover};
            border-color: {danger};
        }}
        PushButton:pressed {{
            background-color: {rgba_from_hex(COLORS['flag_red'], 0.18)};
            border-color: {danger};
        }}
        PushButton:focus {{ border: 2px solid {focus}; }}
        PushButton:disabled {{
            color: {get_text_color(is_dark, 'disabled')};
            background-color: {get_surface_color(is_dark, 'disabled')};
            border-color: {border};
        }}
    """


def get_dialog_section_style(is_dark: bool) -> str:
    """Return a subtle grouped surface for settings and management dialogs."""
    border = COMPONENT_COLORS['card']['border_dark' if is_dark else 'border_light']
    return f"""
        QWidget#earningsDialogSection {{
            background-color: {get_details_card_bg(is_dark)};
            border: 1px solid {border};
            border-radius: {RADII['md']}px;
        }}
        QWidget#earningsDialogSection QLabel,
        QWidget#earningsDialogSection BodyLabel,
        QWidget#earningsDialogSection CaptionLabel,
        QWidget#earningsDialogSection StrongBodyLabel {{
            background: transparent;
            border: none;
        }}
    """


def get_dialog_table_style(is_dark: bool) -> str:
    """Return the compact Fluent table treatment used inside dialogs."""
    table = COMPONENT_COLORS['table']
    background = table['row_bg_dark' if is_dark else 'row_bg_light']
    alternate = table['row_alt_bg_dark' if is_dark else 'row_alt_bg_light']
    border = table['border_dark' if is_dark else 'border_light']
    text = get_text_color(is_dark, 'primary')
    header = table['header_bg_dark' if is_dark else 'header_bg_light']
    header_text = table['header_text_dark' if is_dark else 'header_text_light']
    hover = get_subtle_item_hover_bg(is_dark)
    return f"""
        QTableWidget {{
            color: {text};
            background-color: {background};
            alternate-background-color: {alternate};
            border: 1px solid {border};
            border-radius: {RADII['md']}px;
            gridline-color: transparent;
            outline: none;
            selection-background-color: {get_selection_bg(is_dark)};
            selection-color: {text};
        }}
        QTableWidget::viewport {{
            background-color: {background};
            border-radius: {RADII['md']}px;
        }}
        QTableWidget::item {{
            border: none;
            border-bottom: 1px solid {border};
            padding: {PADDINGS['table_cell']};
        }}
        QTableWidget::item:hover {{ background-color: {hover}; }}
        QTableWidget::item:selected {{
            color: {text};
            background-color: {get_selection_bg(is_dark)};
        }}
        QHeaderView::section {{
            color: {header_text};
            background-color: {header};
            border: none;
            border-right: 1px solid {get_subtle_border(is_dark)};
            padding: {PADDINGS['table_header']};
            font-weight: {FONTS['weight_semibold']};
        }}
        QTableCornerButton::section {{
            background-color: {header};
            border: none;
        }}
    """


def get_form_dialog_style(is_dark: bool, object_name: str) -> str:
    """Return the shared surface treatment for compact vertical form dialogs."""
    surface = COLORS['bg_dark'] if is_dark else COLORS['bg_light']
    text = get_text_color(is_dark, 'primary')

    return f"""
        QDialog#{object_name} {{
            background-color: {surface};
            color: {text};
            font-family: {FONTS['family']};
            font-size: {FONTS['size_body']};
        }}

        QDialog#{object_name} QLabel,
        QDialog#{object_name} BodyLabel,
        QDialog#{object_name} CheckBox {{
            background: transparent;
            color: {text};
        }}
    """


def get_calendar_popup_style(is_dark: bool, object_name: str) -> str:
    """Return the shared Fluent surface/navigation style for a QCalendarWidget."""
    surface = COMPONENT_COLORS['card']['bg_dark' if is_dark else 'bg_light']
    border = COMPONENT_COLORS['card']['border_dark' if is_dark else 'border_light']
    text = get_text_color(is_dark, 'primary')
    secondary = get_text_color(is_dark, 'secondary')
    hover = get_hover_bg(is_dark)
    input_colors = COMPONENT_COLORS['input']
    input_bg = input_colors['bg_dark' if is_dark else 'bg_light']
    input_border = input_colors['border_dark' if is_dark else 'border_light']

    return f"""
        QCalendarWidget#{object_name} {{
            background-color: {surface};
            color: {text};
            border: 1px solid {border};
            border-radius: {RADII['md']}px;
            font-family: {FONTS['family']};
        }}

        QCalendarWidget#{object_name} QWidget#qt_calendar_navigationbar {{
            min-height: 44px;
            max-height: 44px;
            background-color: {surface};
            border: none;
            border-bottom: 1px solid {border};
        }}

        QCalendarWidget#{object_name} QToolButton {{
            min-height: 32px;
            color: {text};
            background: transparent;
            border: none;
            border-radius: {RADII['sm']}px;
            padding: 0 {SPACING['sm']}px;
            font-size: {FONTS['size_body']};
            font-weight: {FONTS['weight_semibold']};
        }}

        QCalendarWidget#{object_name} QToolButton:hover,
        QCalendarWidget#{object_name} QToolButton:pressed {{
            background-color: {hover};
        }}

        QCalendarWidget#{object_name} QToolButton#qt_calendar_prevmonth,
        QCalendarWidget#{object_name} QToolButton#qt_calendar_nextmonth {{
            min-width: 32px;
            max-width: 32px;
            padding: 0;
            font-size: 20px;
            font-weight: {FONTS['weight_medium']};
        }}

        QCalendarWidget#{object_name} QSpinBox#qt_calendar_yearedit {{
            min-height: 32px;
            max-height: 32px;
            background-color: {input_bg};
            color: {text};
            border: 1px solid {input_border};
            border-radius: {RADII['sm']}px;
            padding: 0 {SPACING['sm']}px;
            selection-background-color: {get_selection_bg(is_dark)};
            selection-color: {text};
        }}

        QCalendarWidget#{object_name} QMenu {{
            color: {text};
            background-color: {surface};
            border: 1px solid {border};
            border-radius: {RADII['sm']}px;
            padding: {SPACING['xs']}px;
        }}

        QCalendarWidget#{object_name} QMenu::item {{
            padding: {SPACING['sm']}px {SPACING['md']}px;
            border-radius: {RADII['xs']}px;
        }}

        QCalendarWidget#{object_name} QMenu::item:selected {{
            color: {text};
            background-color: {hover};
        }}

        QCalendarWidget#{object_name} QTableView#qt_calendar_calendarview {{
            color: {text};
            background-color: {surface};
            alternate-background-color: {surface};
            border: none;
            outline: none;
            selection-background-color: transparent;
            selection-color: {text};
            font-size: {FONTS['size_body_sm']};
        }}

        QCalendarWidget#{object_name} QHeaderView::section {{
            color: {secondary};
            background: transparent;
            border: none;
            font-size: {FONTS['size_caption']};
            font-weight: {FONTS['weight_medium']};
        }}
    """
