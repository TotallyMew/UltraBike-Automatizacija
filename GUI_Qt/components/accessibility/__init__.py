# GUI_Qt/components/accessibility package
# Accessibility helpers for WCAG 2.1 AA compliance

from .AccessibleWidget import AccessibleWidget, apply_accessibility_defaults
from .KeyboardNavigation import KeyboardNavigationMixin, add_focus_indicator_style

__all__ = [
    'AccessibleWidget',
    'apply_accessibility_defaults',
    'KeyboardNavigationMixin',
    'add_focus_indicator_style'
]
