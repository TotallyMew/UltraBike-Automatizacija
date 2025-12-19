"""
Fluent Design System Theme Configuration
Colors, spacing, and typography standards
Premium Space Indigo & Lavender palette
"""

from qfluentwidgets import Theme, setTheme, setThemeColor
from PySide6.QtGui import QColor

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

    # Text colors
    'text_primary_dark': '#E0E0E0',    # Light gray for dark theme
    'text_primary_light': '#1F2937',   # Dark gray for light theme
    'text_secondary': '#6B7280',       # Gray for secondary text
    'text_tertiary': '#9CA3AF',        # Light gray for tertiary text
    'text_white': '#FFFFFF',           # Pure white for high contrast

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
}

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
    'size_caption': '12px',
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
        border-radius: 6px;
        padding: 8px 12px;
        font-family: {FONTS['family']};
        font-size: {FONTS['size_body']};
    """
