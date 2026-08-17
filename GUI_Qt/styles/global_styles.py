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
    get_focus_color,
    get_text_color,
)


def get_global_stylesheet():
    """Get global stylesheet with theme-aware colors"""
    is_dark = isDarkTheme()
    input_colors = COMPONENT_COLORS['input']
    btn_colors = COMPONENT_COLORS['button']
    focus = get_focus_color(is_dark)
    text_primary = get_text_color(is_dark, 'primary')
    text_secondary = get_text_color(is_dark, 'secondary')
    surface = COLORS['bg_alt_dark'] if is_dark else COLORS['bg_light']
    border = COLORS['border_dark'] if is_dark else COLORS['border_light']

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
            border: 2px solid {focus};
            border-bottom: 2px solid {focus};
        }}

        LineEdit:disabled, PasswordLineEdit:disabled, SearchLineEdit:disabled, QLineEdit:disabled {{
            background-color: {COLORS['bg_alt_dark'] if is_dark else '#F1F3F5'};
            color: {text_secondary};
            border-color: {border};
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
            border: 2px solid {focus};
        }}

        ComboBox:disabled, QComboBox:disabled {{
            background-color: {COLORS['bg_alt_dark'] if is_dark else '#F1F3F5'};
            color: {text_secondary};
            border-color: {border};
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

        /* =====================
           Keyboard focus and control states
           ===================== */

        PushButton:focus, PrimaryPushButton:focus, TransparentToolButton:focus,
        QPushButton:focus, QToolButton:focus, CheckBox:focus, QCheckBox:focus,
        SwitchButton:focus, QSpinBox:focus, QDoubleSpinBox:focus,
        QTextEdit:focus, QPlainTextEdit:focus, QAbstractItemView:focus {{
            border: 2px solid {focus};
        }}

        PushButton:disabled, PrimaryPushButton:disabled, QPushButton:disabled,
        QToolButton:disabled {{
            color: {text_secondary};
            background-color: {COLORS['bg_alt_dark'] if is_dark else '#E6E9ED'};
            border-color: {border};
        }}

        QToolTip {{
            color: {text_primary};
            background-color: {surface};
            border: 1px solid {focus};
            border-radius: {RADII['xs']}px;
            padding: {SPACING['sm']}px;
        }}

        QAbstractItemView {{
            color: {text_primary};
            background-color: {surface};
            alternate-background-color: {COLORS['bg_alt_dark'] if is_dark else COLORS['bg_alt_light']};
            border: 1px solid {border};
            selection-background-color: {get_subtle_item_hover_bg(is_dark)};
            selection-color: {text_primary};
        }}

        QAbstractItemView::item:focus {{
            border: 2px solid {focus};
        }}

        QHeaderView::section {{
            color: {COLORS['text_white']};
            background-color: {COLORS['lavender_grey'] if is_dark else COLORS['space_indigo']};
            border: none;
            border-right: 1px solid {COLORS['border_dark'] if is_dark else COLORS['lavender_grey']};
            padding: {PADDINGS['table_header']};
            font-weight: 600;
        }}

        QLineEdit[validationState="error"], PasswordLineEdit[validationState="error"] {{
            border: 2px solid {COLORS['error_text_dark'] if is_dark else COLORS['error_text_light']};
        }}

        QLineEdit[validationState="valid"], PasswordLineEdit[validationState="valid"] {{
            border: 2px solid {COLORS['success_text_dark'] if is_dark else COLORS['success_text_light']};
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

        /* =====================
           Table indicator-only CheckBox
           ===================== */

        /*
        QFluentWidgets' CheckBox paints its own indicator using the style's
        SE_CheckBoxIndicator rect, which is left-positioned by default.
        For "indicator-only" checkboxes used in tables (no label), we center
        the indicator subcontrol via a dynamic property.
        */
        CheckBox[ubTableCheck="true"],
        QCheckBox[ubTableCheck="true"] {{
            padding: 0px;
            margin: 0px;
        }}

        CheckBox[ubTableCheck="true"]::indicator,
        QCheckBox[ubTableCheck="true"]::indicator {{
            subcontrol-origin: content;
            subcontrol-position: center;
            margin: 0px;
        }}
    """
