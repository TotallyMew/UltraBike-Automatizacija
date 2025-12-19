"""
UltraBike Qt Application Entry Point
PySide6 + QFluentWidgets (Fluent Design System)
"""

import sys
import os

# Add project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from qfluentwidgets import setTheme, Theme

from GUI_Qt.MainWindow import MainWindow
from GUI_Qt.styles.theme_config import apply_theme
from PySide6.QtGui import QIcon

from Utilities.ResourcePaths import resource_path


def _set_windows_appusermodel_id(app_id: str) -> None:
    """Set AppUserModelID so Windows taskbar uses the correct icon/grouping."""
    if not sys.platform.startswith("win"):
        return

    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
    except Exception:
        # Best-effort; failure here should never block startup.
        pass


def main():
    """Main application entry point"""

    # Helps Windows taskbar icon + grouping (especially for pinned shortcuts)
    _set_windows_appusermodel_id("UltraBike_Automatizacija")

    # Enable High DPI scaling for modern displays
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    # Create application
    app = QApplication(sys.argv)
    app.setApplicationName("UltraBike Automatizacija")
    app.setOrganizationName("UltraBike")
    try:
        app.setApplicationDisplayName("UltraBike Automatizacija")
    except Exception:
        pass

    # Application icon (optional)
    app_icon = None
    try:
        icon_file = resource_path("might work.ico")
        if icon_file.exists():
            app_icon = QIcon(str(icon_file))
            app.setWindowIcon(app_icon)
    except Exception:
        app_icon = None

    # Apply Fluent Design theme
    apply_theme(app)

    # Create and show main window
    window = MainWindow()
    try:
        if app_icon is not None:
            window.setWindowIcon(app_icon)
    except Exception:
        pass
    window.show()

    # Run application
    app.exec()


if __name__ == "__main__":
    main()
