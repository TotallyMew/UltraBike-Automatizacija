"""
Global stylesheet overrides for consistent theming
"""

from qfluentwidgets import isDarkTheme
from GUI_Qt.styles.theme_config import COLORS, COMPONENT_COLORS


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
            border-radius: 6px;
            padding: 8px 12px;
        }}

        LineEdit:hover, PasswordLineEdit:hover, SearchLineEdit:hover, QLineEdit:hover {{
            border: 1px solid {'rgba(141, 153, 174, 0.55)' if is_dark else 'rgba(43, 45, 66, 0.35)'};
            border-bottom: 1px solid {'rgba(141, 153, 174, 0.55)' if is_dark else 'rgba(43, 45, 66, 0.35)'};
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
            border-radius: 6px;
            padding: 6px 10px;
        }}

        ComboBox:hover, QComboBox:hover {{
            border: 1px solid {'rgba(141, 153, 174, 0.55)' if is_dark else 'rgba(43, 45, 66, 0.35)'};
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
            padding: 8px 10px;
        }}

        QComboBox QAbstractItemView::item:hover {{
            background-color: {'rgba(141, 153, 174, 0.20)' if is_dark else 'rgba(43, 45, 66, 0.08)'};
        }}

        /* CardWidget - add subtle separation in light theme */
        CardWidget {{
            border-radius: 8px;
            border: 1px solid {COLORS['border_dark'] if is_dark else "rgba(141, 153, 174, 0.28)"};
        }}

        /* Avoid white-on-white scroll areas in light theme */
        QScrollArea {{
            background: transparent;
        }}

        /* Global ScrollBar Styling - Fluent Design System */
        QScrollBar:vertical {{
            background: transparent;
            width: 12px;
            margin: 0px;
            border: none;
        }}

        QScrollBar::handle:vertical {{
            background: {'rgba(141, 153, 174, 0.3)' if is_dark else 'rgba(43, 45, 66, 0.2)'};
            border-radius: 6px;
            min-height: 30px;
            margin: 0px 2px;
        }}

        QScrollBar::handle:vertical:hover {{
            background: {'rgba(141, 153, 174, 0.5)' if is_dark else 'rgba(43, 45, 66, 0.3)'};
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
            height: 12px;
            margin: 0px;
            border: none;
        }}

        QScrollBar::handle:horizontal {{
            background: {'rgba(141, 153, 174, 0.3)' if is_dark else 'rgba(43, 45, 66, 0.2)'};
            border-radius: 6px;
            min-width: 30px;
            margin: 2px 0px;
        }}

        QScrollBar::handle:horizontal:hover {{
            background: {'rgba(141, 153, 174, 0.5)' if is_dark else 'rgba(43, 45, 66, 0.3)'};
        }}

        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
            width: 0px;
            border: none;
        }}

        QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
            background: none;
        }}
    """
