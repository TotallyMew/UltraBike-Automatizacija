"""
Global stylesheet overrides for consistent theming
"""

from qfluentwidgets import isDarkTheme


def get_global_stylesheet():
    """Get global stylesheet with theme-aware colors"""
    is_dark = isDarkTheme()

    return f"""
        /* LineEdit - Match button border colors */
        LineEdit {{
            border: 1px solid {'rgba(255, 255, 255, 0.08)' if is_dark else 'rgba(0, 0, 0, 0.08)'};
            border-bottom: 1px solid {'rgba(255, 255, 255, 0.08)' if is_dark else 'rgba(0, 0, 0, 0.08)'};
        }}

        LineEdit:hover {{
            border: 1px solid {'rgba(255, 255, 255, 0.13)' if is_dark else 'rgba(0, 0, 0, 0.13)'};
            border-bottom: 1px solid {'rgba(255, 255, 255, 0.13)' if is_dark else 'rgba(0, 0, 0, 0.13)'};
        }}

        LineEdit:focus {{
            border: 1px solid {'#8D99AE' if is_dark else '#2B2D42'};
            border-bottom: 1px solid {'#8D99AE' if is_dark else '#2B2D42'};
        }}

        /* ComboBox - Match button border colors */
        ComboBox {{
            border: 1px solid {'rgba(255, 255, 255, 0.08)' if is_dark else 'rgba(0, 0, 0, 0.08)'};
        }}

        ComboBox:hover {{
            border: 1px solid {'rgba(255, 255, 255, 0.13)' if is_dark else 'rgba(0, 0, 0, 0.13)'};
        }}

        ComboBox:focus {{
            border: 1px solid {'#8D99AE' if is_dark else '#2B2D42'};
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
