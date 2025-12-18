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

    # Background colors
    'bg_dark': '#1E1E1E',              # Dark background
    'bg_light': '#FFFFFF',             # Light background
    'bg_alt_dark': '#2A2A2A',          # Alternate dark background
    'bg_alt_light': '#F9FAFB',         # Alternate light background

    # Border colors
    'border_dark': '#3A3A3A',
    'border_light': '#E5E7EB',
}

# Spacing System
SPACING = {
    'xs': 4,
    'sm': 8,
    'md': 16,
    'lg': 24,
    'xl': 32,
}

# Typography System
FONTS = {
    'family': 'Segoe UI, Inter, -apple-system, BlinkMacSystemFont, sans-serif',
    'family_mono': 'JetBrains Mono, Consolas, Monaco, Courier New, monospace',
    'size_title': '28px',
    'size_subtitle': '20px',
    'size_body': '14px',
    'size_caption': '12px',
    'weight_regular': 400,
    'weight_medium': 500,
    'weight_semibold': 600,
    'weight_bold': 700,
}

def apply_theme(app):
    """Apply Fluent Design theme to the application"""
    setTheme(Theme.AUTO)  # Respects system light/dark mode
    # Use Lavender Grey as the primary accent color - sophisticated and modern
    setThemeColor(THEME_COLORS['secondary'])
