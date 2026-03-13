"""
Fluent Design System Theme Configuration
Colors, spacing, and typography standards
Premium Space Indigo & Lavender palette
"""

from qfluentwidgets import Theme, setTheme, setThemeColor
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
    return rgba_from_hex(COLORS['lavender_grey'], 0.10 if is_dark else 0.06)


def get_details_card_bg(is_dark: bool) -> str:
    """Background tint for small details/info cards."""
    return (
        rgba_from_hex(COLORS['lavender_grey'], 0.10)
        if is_dark
        else rgba_from_hex(COLORS['space_indigo'], 0.04)
    )


def get_embedded_input_border(is_dark: bool) -> str:
    return (
        rgba_from_hex(COLORS['lavender_grey'], 0.85)
        if is_dark
        else rgba_from_hex(COLORS['space_indigo'], 0.45)
    )


def get_selection_bg() -> str:
    # Keep existing value (RGB 139,153,174) to avoid visual regressions.
    return rgba_rgb(139, 153, 174, 0.2)


def get_subtle_border(is_dark: bool) -> str:
    return (
        rgba_from_hex(COLORS['lavender_grey'], 0.55)
        if is_dark
        else rgba_from_hex(COLORS['space_indigo'], 0.35)
    )


def get_subtle_item_hover_bg(is_dark: bool) -> str:
    return (
        rgba_from_hex(COLORS['lavender_grey'], 0.20)
        if is_dark
        else rgba_from_hex(COLORS['space_indigo'], 0.08)
    )


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
    return rgba_from_hex(COLORS['lavender_grey'], 0.28)

# Premium Color Palette (inspired by Space Indigo/Lavender Grey)
THEME_COLORS = {
    'primary': QColor(43, 45, 66),       # Space Indigo (#2B2D42) - Deep, sophisticated
    'secondary': QColor(141, 153, 174),  # Lavender Grey (#8D99AE) - Elegant accent
    'accent': QColor(237, 242, 244),     # Platinum (#EDF2F4) - Light, clean
    'blush': QColor(227, 101, 136),      # Blush Rose (#E36588) - Vibrant highlight
    'flag': QColor(200, 29, 37),         # Flag Red (#C81D25) - Bold accent

    # Functional colors
    'success': QColor(16, 185, 129),     # Emerald Green (#10B981) - Success states
    'warning': QColor(245, 158, 11),     # Amber (#F59E0B) - Warning states
    'error': QColor(200, 29, 37),        # Flag Red (matches palette)
    'background': QColor(243, 243, 243), # Light gray
    'surface': QColor(255, 255, 255),    # White
}

# Color Hex Values (for stylesheets)
COLORS = {
    # Primary palette
    'space_indigo': '#2B2D42',
    'lavender_grey': '#8D99AE',
    'platinum': '#EDF2F4',
    'blush_rose': '#E36588',
    'flag_red': '#C81D25',

    # Functional colors
    'success': '#10B981',      # Emerald green
    'warning': '#F59E0B',      # Amber
    'error': '#C81D25',        # Flag red
    'focus_ring': '#8D99AE',   # Lavender grey - for accessibility focus indicators

    # Text colors
    'text_primary_dark': '#E0E0E0',    # Light gray for dark theme
    'text_primary_light': '#1F2937',   # Dark gray for light theme
    'text_secondary': '#6B7280',       # Gray for secondary text
    'text_tertiary': '#9CA3AF',        # Light gray for tertiary text
    'text_white': '#FFFFFF',           # Pure white for high contrast

    # Theme-aware text roles (preferred over non-specific grays)
    'text_secondary_dark': '#BFC4CC',   # Secondary text on dark surfaces
    'text_secondary_light': '#6B7280',  # Secondary text on light surfaces
    'text_tertiary_dark': '#9CA3AF',    # Tertiary text on dark surfaces
    'text_tertiary_light': '#9CA3AF',   # Tertiary text on light surfaces

    # Background colors
    'bg_dark': '#1E1E1E',              # Dark background
    'bg_light': '#FFFFFF',             # Light background
    'bg_alt_dark': '#2A2A2A',          # Alternate dark background
    'bg_alt_light': '#F9FAFB',         # Alternate light background

    # Border colors
    'border_dark': '#3A3A3A',
    'border_light': '#E5E7EB',

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
    'status_success_bg_light': '#ECFDF5',
    'status_success_bg_dark': 'rgba(16, 185, 129, 0.12)',
    'status_error_bg_light': '#FEF2F2',
    'status_error_bg_dark': 'rgba(200, 29, 37, 0.12)',
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

    Roles: primary | secondary | tertiary | inverse
    """
    role = (role or 'primary').strip().lower()

    if role == 'primary':
        return COLORS['text_primary_dark'] if is_dark else COLORS['text_primary_light']
    if role == 'secondary':
        return COLORS['text_secondary_dark'] if is_dark else COLORS['text_secondary_light']
    if role == 'tertiary':
        return COLORS['text_tertiary_dark'] if is_dark else COLORS['text_tertiary_light']
    if role == 'inverse':
        return COLORS['text_white']

    # Fallback to primary to avoid unreadable text
    return COLORS['text_primary_dark'] if is_dark else COLORS['text_primary_light']


def get_status_text_color(status: str) -> str:
    """Return a semantic status color for foreground text (theme-independent)."""
    status = (status or '').strip().lower()
    if status in ('success', 'ok', 'valid'):
        return COLORS['success']
    if status in ('warning', 'warn', 'mixed'):
        return COLORS['warning']
    if status in ('error', 'danger', 'invalid'):
        return COLORS['error']
    return COLORS['text_tertiary']


def get_status_row_style(is_dark: bool, status: str) -> str:
    """QSS for row validation highlighting used in batch Excel preview."""
    status = (status or '').strip().lower()

    if status in ('success', 'ok', 'valid'):
        bg = COLORS['status_success_bg_dark'] if is_dark else COLORS['status_success_bg_light']
    elif status in ('error', 'danger', 'invalid'):
        bg = COLORS['status_error_bg_dark'] if is_dark else COLORS['status_error_bg_light']
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

    # Compatibility aliases (keep for existing code)
    'size_title': '28px',
    'size_subtitle': '20px',

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
        'bg_dark': '#2A2A2A',
        'bg_light': '#FFFFFF',
        'border_dark': '#3A3A3A',
        'border_light': '#D1D5DB',
        'text_dark': '#E0E0E0',
        'text_light': '#1F2937',
        'placeholder_dark': '#6B7280',
        'placeholder_light': '#9CA3AF',
    },
    'button': {
        'primary_bg': '#8D99AE',        # Lavender Grey
        'primary_hover': '#9BA7B8',
        'primary_text': '#FFFFFF',
        'secondary_bg_dark': '#2A2A2A',
        'secondary_bg_light': '#F3F4F6',
        'secondary_hover_dark': '#3A3A3A',
        'secondary_hover_light': '#E5E7EB',
        'secondary_text_dark': '#E0E0E0',
        'secondary_text_light': '#374151',
    },
    'card': {
        'bg_dark': '#1E1E1E',
        'bg_light': '#FFFFFF',
        'border_dark': '#2A2A2A',
        'border_light': '#E5E7EB',
    },
    'table': {
        'header_bg_dark': '#2A2A2A',
        'header_bg_light': '#F9FAFB',
        'row_bg_dark': '#1E1E1E',
        'row_bg_light': '#FFFFFF',
        'row_alt_bg_dark': '#252525',
        'row_alt_bg_light': '#F9FAFB',
        'border_dark': '#3A3A3A',
        'border_light': '#E5E7EB',
    },
}

def apply_theme(app):
    """Apply Fluent Design theme to the application"""
    setTheme(Theme.AUTO)  # Respects system light/dark mode
    # Use Lavender Grey as the primary accent color - sophisticated and modern
    setThemeColor(THEME_COLORS['secondary'])

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
