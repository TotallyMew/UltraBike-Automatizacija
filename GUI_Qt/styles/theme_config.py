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

    # Theme roles. Keep brand swatches above stable and use these roles in UI
    # code so canvases and surfaces do not drift between feature screens.
    'canvas_dark': '#1B1E2B',
    'canvas_light': '#EDF2F4',
    'surface_dark': '#242737',
    'surface_light': '#FFFFFF',
    'surface_alt_dark': '#292D40',
    'surface_alt_light': '#F7F9FB',
    'accent_light': '#2B2D42',
    'accent_dark': '#8D99AE',
    'accent_hover_light': '#3B3E59',
    'accent_hover_dark': '#A5B0C1',
    'accent_pressed_light': '#202234',
    'accent_pressed_dark': '#758197',
    'accent_text_light': '#FFFFFF',
    'accent_text_dark': '#2B2D42',

    # Functional colors
    'success': '#10B981',      # Emerald green (fills / charts)
    'warning': '#F59E0B',      # Amber (fills / charts)
    'error': '#C81D25',        # Flag red
    'on_success': '#062A20',   # Foreground on bright success fills
    'on_warning': '#2B2D42',   # Foreground on bright warning fills
    'focus_ring': '#8D99AE',   # Lavender grey - for accessibility focus indicators

    # Accessible foreground variants.  Bright semantic fills do not provide
    # sufficient contrast as text on the light app canvas, so foreground roles
    # are deliberately separate from chart/fill colors.
    'success_text_light': '#047857',
    'success_text_dark': '#6EE7B7',
    'warning_text_light': '#8A4B08',
    'warning_text_dark': '#FCD34D',
    'error_text_light': '#B4232C',
    'error_text_dark': '#FDA4AF',
    'focus_ring_light': '#46548A',
    'focus_ring_dark': '#C3CCE0',

    # Text colors
    'text_primary_dark': '#E0E0E0',    # Light gray for dark theme
    'text_primary_light': '#1F2937',   # Dark gray for light theme
    'text_secondary': '#6B7280',       # Gray for secondary text
    'text_tertiary': '#9CA3AF',        # Light gray for tertiary text
    'text_white': '#FFFFFF',           # Pure white for high contrast

    # Theme-aware text roles (preferred over non-specific grays)
    'text_secondary_dark': '#BFC4CC',   # Secondary text on dark surfaces
    'text_secondary_light': '#596273',  # Secondary text on light surfaces
    'text_tertiary_dark': '#9CA3AF',    # Tertiary text on dark surfaces
    'text_tertiary_light': '#596273',   # Tertiary text on light surfaces

    # Background colors
    'bg_dark': '#1B1E2B',              # Dark app canvas
    'bg_light': '#FFFFFF',             # Light background
    'bg_alt_dark': '#292D40',           # Alternate dark surface
    'bg_alt_light': '#F7F9FB',          # Alternate light surface

    # Border colors
    'border_dark': '#3A4058',
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
    return get_text_color(is_dark, 'tertiary')


def get_status_row_style(is_dark: bool, status: str) -> str:
    """QSS for row validation highlighting used in batch Excel preview."""
    status = (status or '').strip().lower()

    if status in ('success', 'saved_manually', 'ok', 'valid'):
        bg = COLORS['status_success_bg_dark'] if is_dark else COLORS['status_success_bg_light']
    elif status in ('error', 'failed', 'danger', 'invalid'):
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
        'bg_dark': '#292D40',
        'bg_light': '#FFFFFF',
        'border_dark': '#3A4058',
        'border_light': '#D1D5DB',
        'text_dark': '#E7EAF0',
        'text_light': '#1F2937',
        'placeholder_dark': '#9CA3AF',
        'placeholder_light': '#6B7280',
    },
    'button': {
        # Legacy static values. New code should use get_accent_colors().
        'primary_bg': '#2B2D42',
        'primary_hover': '#3B3E59',
        'primary_text': '#FFFFFF',
        'secondary_bg_dark': '#292D40',
        'secondary_bg_light': '#F3F4F6',
        'secondary_hover_dark': '#34384F',
        'secondary_hover_light': '#E5E7EB',
        'secondary_text_dark': '#E7EAF0',
        'secondary_text_light': '#374151',
    },
    'card': {
        'bg_dark': '#242737',
        'bg_light': '#FFFFFF',
        'border_dark': '#363B52',
        'border_light': '#E5E7EB',
    },
    'table': {
        'header_bg_dark': '#34384F',
        'header_bg_light': '#2B2D42',
        'header_text_dark': '#F7F9FB',
        'header_text_light': '#FFFFFF',
        'row_bg_dark': '#242737',
        'row_bg_light': '#FFFFFF',
        'row_alt_bg_dark': '#292D40',
        'row_alt_bg_light': '#F7F9FB',
        'border_dark': '#3A4058',
        'border_light': '#E5E7EB',
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


def get_surface_color(is_dark: bool, role: str = 'surface') -> str:
    """Return a canvas/surface role for the active theme."""
    role = (role or 'surface').strip().lower()
    suffix = 'dark' if is_dark else 'light'
    if role == 'canvas':
        return COLORS[f'canvas_{suffix}']
    if role in ('alternate', 'alt', 'subtle'):
        return COLORS[f'surface_alt_{suffix}']
    return COLORS[f'surface_{suffix}']

def apply_theme(app):
    """Apply Fluent Design theme to the application"""
    setTheme(Theme.AUTO)  # Respects system light/dark mode
    # A deeper indigo keeps QFluent's white button/icon foregrounds accessible.
    # Theme-aware custom controls use get_accent_colors() in dark mode.
    setThemeColor(QColor(COLORS['focus_ring_light']))

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
    disabled_bg = COLORS['bg_alt_dark'] if is_dark else '#F1F3F5'
    border = COLORS['border_dark'] if is_dark else COLORS['border_light']
    secondary_text = get_text_color(is_dark, 'secondary')
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
                selection-background-color: {get_selection_bg()};
                selection-color: {get_text_color(is_dark, 'primary')};
                outline: none;
            }}
        """

    return f"""
        {selector} {{
            {get_input_style(is_dark)}
            padding: 0 {SPACING['md']}px;
            selection-background-color: {get_selection_bg()};
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
            color: {secondary_text};
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
                color: {get_text_color(is_dark, 'tertiary')};
                background-color: {COLORS['bg_alt_dark'] if is_dark else '#E6E9ED'};
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
        PushButton:pressed {{ background-color: {border}; }}
        PushButton:focus {{ border: 2px solid {focus}; }}
        PushButton:disabled {{
            color: {get_text_color(is_dark, 'tertiary')};
            background-color: {COLORS['bg_alt_dark'] if is_dark else '#E6E9ED'};
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
            color: {get_text_color(is_dark, 'tertiary')};
            background-color: {COLORS['bg_alt_dark'] if is_dark else '#E6E9ED'};
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
            selection-background-color: {get_selection_bg()};
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
            background-color: {get_selection_bg()};
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
            selection-background-color: {get_selection_bg()};
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
