# GUI_Qt/components/accessibility package
# Accessibility helpers for WCAG 2.1 AA compliance

from .AccessibleWidget import AccessibleWidget
from .KeyboardNavigation import KeyboardNavigationMixin, add_focus_indicator_style

__all__ = [
    'AccessibleWidget',
    'KeyboardNavigationMixin',
    'add_focus_indicator_style'
]
