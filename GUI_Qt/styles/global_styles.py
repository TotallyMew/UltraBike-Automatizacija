"""
Global stylesheet overrides for consistent theming
"""

from qfluentwidgets import isDarkTheme
from GUI_Qt.styles.theme_config import (
    COLORS,
    COMPONENT_COLORS,
    RADII,
    PADDINGS,
    SPACING,
    SIZES,
    get_card_border_light,
    get_scrollbar_handle_bg,
    get_scrollbar_handle_hover_bg,
    get_subtle_border,
    get_subtle_item_hover_bg,
)


def get_global_stylesheet():
    """Get global stylesheet with theme-aware colors"""
    is_dark = isDarkTheme()
    input_colors = COMPONENT_COLORS['input']
    btn_colors = COMPONENT_COLORS['button']

    return f"""
        /* =====================
           Inputs (global)
           ===================== */

        /* QFluent LineEdit / PasswordLineEdit / SearchLineEdit */
        LineEdit, PasswordLineEdit, SearchLineEdit, QLineEdit {{
            background-color: {input_colors['bg_dark'] if is_dark else input_colors['bg_light']};
            color: {input_colors['text_dark'] if is_dark else input_colors['text_light']};
            border: 1px solid {input_colors['border_dark'] if is_dark else input_colors['border_light']};
            border-bottom: 1px solid {input_colors['border_dark'] if is_dark else input_colors['border_light']};
            border-radius: {RADII['sm']}px;
            padding: {PADDINGS['input']};
        }}

        LineEdit:hover, PasswordLineEdit:hover, SearchLineEdit:hover, QLineEdit:hover {{
            border: 1px solid {get_subtle_border(is_dark)};
            border-bottom: 1px solid {get_subtle_border(is_dark)};
        }}

        LineEdit:focus, PasswordLineEdit:focus, SearchLineEdit:focus, QLineEdit:focus {{
            border: 1px solid {COLORS['lavender_grey'] if is_dark else COLORS['space_indigo']};
            border-bottom: 1px solid {COLORS['lavender_grey'] if is_dark else COLORS['space_indigo']};
        }}

        /* Placeholder text */
        LineEdit::placeholder, PasswordLineEdit::placeholder, SearchLineEdit::placeholder, QLineEdit::placeholder {{
            color: {input_colors['placeholder_dark'] if is_dark else input_colors['placeholder_light']};
        }}

        /* ComboBox - make the control itself readable */
        ComboBox, QComboBox {{
            background-color: {input_colors['bg_dark'] if is_dark else input_colors['bg_light']};
            color: {input_colors['text_dark'] if is_dark else input_colors['text_light']};
            border: 1px solid {input_colors['border_dark'] if is_dark else input_colors['border_light']};
            border-radius: {RADII['sm']}px;
            padding: {PADDINGS['combo']};
        }}

        ComboBox:hover, QComboBox:hover {{
            border: 1px solid {get_subtle_border(is_dark)};
        }}

        ComboBox:focus, QComboBox:focus {{
            border: 1px solid {COLORS['lavender_grey'] if is_dark else COLORS['space_indigo']};
        }}

        /* ComboBox dropdown list */
        QComboBox QAbstractItemView {{
            background-color: {COLORS['bg_dark'] if is_dark else COLORS['bg_light']};
            color: {COLORS['text_primary_dark'] if is_dark else COLORS['text_primary_light']};
            border: 1px solid {COLORS['border_dark'] if is_dark else COLORS['border_light']};
            selection-background-color: {btn_colors['secondary_bg_dark'] if is_dark else btn_colors['secondary_bg_light']};
            selection-color: {COLORS['text_primary_dark'] if is_dark else COLORS['text_primary_light']};
            outline: 0;
        }}

        QComboBox QAbstractItemView::item {{
            padding: {PADDINGS['combo_item']};
        }}

        QComboBox QAbstractItemView::item:hover {{
            background-color: {get_subtle_item_hover_bg(is_dark)};
        }}

        /* CardWidget - add subtle separation in light theme */
        CardWidget {{
            border-radius: {RADII['md']}px;
            border: 1px solid {COLORS['border_dark'] if is_dark else get_card_border_light()};
        }}

        /* Avoid white-on-white scroll areas in light theme */
        QScrollArea {{
            background: transparent;
        }}

        /* Global ScrollBar Styling - Fluent Design System */
        QScrollBar:vertical {{
            background: transparent;
            width: {SIZES['scrollbar_thickness']}px;
            margin: 0px;
            border: none;
        }}

        QScrollBar::handle:vertical {{
            background: {get_scrollbar_handle_bg(is_dark)};
            border-radius: {RADII['sm']}px;
            min-height: {SIZES['scrollbar_handle_min']}px;
            margin: 0px {SPACING['xxs']}px;
        }}

        QScrollBar::handle:vertical:hover {{
            background: {get_scrollbar_handle_hover_bg(is_dark)};
        }}

        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
            border: none;
        }}

        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
            background: none;
        }}

        QScrollBar:horizontal {{
            background: transparent;
            height: {SIZES['scrollbar_thickness']}px;
            margin: 0px;
            border: none;
        }}

        QScrollBar::handle:horizontal {{
            background: {get_scrollbar_handle_bg(is_dark)};
            border-radius: {RADII['sm']}px;
            min-width: {SIZES['scrollbar_handle_min']}px;
            margin: {SPACING['xxs']}px 0px;
        }}

        QScrollBar::handle:horizontal:hover {{
            background: {get_scrollbar_handle_hover_bg(is_dark)};
        }}

        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
            width: 0px;
            border: none;
        }}

        QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
            background: none;
        }}
    """
