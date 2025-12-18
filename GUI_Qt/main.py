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


def main():
    """Main application entry point"""

    # Enable High DPI scaling for modern displays
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    # Create application
    app = QApplication(sys.argv)
    app.setApplicationName("UltraBike Automatizacija")
    app.setOrganizationName("UltraBike")

    # Apply Fluent Design theme
    apply_theme(app)

    # Create and show main window
    window = MainWindow()
    window.show()

    # Run application
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
