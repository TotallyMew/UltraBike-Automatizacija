"""
Responsive Widget Base Class
Provides breakpoint-driven layout management for all screens.
"""

from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QResizeEvent


class ResponsiveWidget(QWidget):
    """Base class for responsive screens with breakpoint-driven layouts.

    This class provides:
    - Breakpoint detection based on window width
    - Automatic layout updates on breakpoint changes
    - Helper methods for column count and spacing
    - Debouncing to prevent excessive layout rebuilds

    Usage:
        1. Inherit from ResponsiveWidget instead of QWidget
        2. Override _on_breakpoint_changed(breakpoint) to handle layout changes
        3. Use get_column_count() to determine appropriate column count
        4. Use get_spacing_scale() to adjust spacing for compact layouts
    """

    # Breakpoint definitions (in pixels)
    BREAKPOINT_XS = 640    # Extra small - minimum usable width
    BREAKPOINT_SM = 768    # Small - tablets portrait, small laptops
    BREAKPOINT_MD = 1024   # Medium - tablets landscape, standard laptops
    BREAKPOINT_LG = 1280   # Large - desktop, larger laptops
    BREAKPOINT_XL = 1440   # Extra large - full HD displays
    BREAKPOINT_XXL = 1920  # 2xl - wide displays

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_breakpoint = None
        self._last_width = 0
        self._initialized = False

    def showEvent(self, event):
        """Trigger initial breakpoint detection when widget is first shown."""
        super().showEvent(event)
        if not self._initialized:
            self._initialized = True
            # Trigger initial breakpoint detection
            current_width = self.width()
            if current_width > 0:
                self._last_width = current_width
                self._current_breakpoint = self._get_breakpoint(current_width)
                self._on_breakpoint_changed(self._current_breakpoint)

    def resizeEvent(self, event: QResizeEvent):
        """Handle resize and trigger layout updates on breakpoint changes."""
        super().resizeEvent(event)
        new_width = event.size().width()

        # Only update if width changed significantly (avoid flicker)
        # 10px threshold prevents excessive layout rebuilds
        if abs(new_width - self._last_width) < 10:
            return

        self._last_width = new_width
        new_breakpoint = self._get_breakpoint(new_width)

        # Only trigger layout update if breakpoint actually changed
        if new_breakpoint != self._current_breakpoint:
            self._current_breakpoint = new_breakpoint
            self._on_breakpoint_changed(new_breakpoint)

    def _get_breakpoint(self, width: int) -> str:
        """Return current breakpoint name based on width.

        Args:
            width: Current widget width in pixels

        Returns:
            Breakpoint name: 'xs', 'sm', 'md', 'lg', 'xl', or 'xxl'
        """
        if width < self.BREAKPOINT_SM:
            return 'xs'
        elif width < self.BREAKPOINT_MD:
            return 'sm'
        elif width < self.BREAKPOINT_LG:
            return 'md'
        elif width < self.BREAKPOINT_XL:
            return 'lg'
        elif width < self.BREAKPOINT_XXL:
            return 'xl'
        else:
            return 'xxl'

    def _on_breakpoint_changed(self, breakpoint: str):
        """Override in subclasses to respond to breakpoint changes.

        This method is called whenever the window crosses a breakpoint threshold.
        Use it to adjust layouts, margins, column counts, etc.

        Args:
            breakpoint: New breakpoint name ('xs', 'sm', 'md', 'lg', 'xl', 'xxl')
        """
        pass

    def get_column_count(self) -> int:
        """Return appropriate column count for current breakpoint.

        Returns:
            1 for xs/sm (narrow screens)
            2 for md/lg (medium screens)
            3 for xl/xxl (wide screens)
        """
        if self._current_breakpoint in ('xs', 'sm'):
            return 1
        elif self._current_breakpoint in ('md', 'lg'):
            return 2
        else:
            return 3

    def get_spacing_scale(self) -> float:
        """Return spacing multiplier for current breakpoint.

        Returns:
            0.75 for xs (compact spacing on very narrow screens)
            1.0 for all other breakpoints (normal spacing)
        """
        if self._current_breakpoint == 'xs':
            return 0.75  # Compact spacing
        else:
            return 1.0   # Normal spacing

    def get_current_breakpoint(self) -> str:
        """Get the current breakpoint name.

        Returns:
            Current breakpoint: 'xs', 'sm', 'md', 'lg', 'xl', or 'xxl'
            None if not yet initialized
        """
        return self._current_breakpoint
