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
from PySide6.QtGui import QIcon,QPixmap


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

    icon_path = os.path.join(project_root, "might work.ico")
    # Debug: icon existence and absolute path can be logged if needed
        #Set the application icon
    icon_path = os.path.join(project_root, "might work.ico")  # path to your ICO
    app.setWindowIcon(QIcon(icon_path))
    # Debug: QPixmap null check can be logged if needed

    # Apply Fluent Design theme
    apply_theme(app)

    # Create and show main window
    window = MainWindow()
    window.setWindowIcon(QIcon(icon_path))
    window.show()

    # Run application
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
