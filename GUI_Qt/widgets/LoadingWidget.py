"""
Loading Widget
Displays loading spinner with optional message
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtCore import Qt
from qfluentwidgets import IndeterminateProgressRing, BodyLabel, TitleLabel


class LoadingWidget(QWidget):
    """Loading screen with spinner and message"""

    def __init__(self, message=None, tr=None, parent=None):
        super().__init__(parent)

        self.tr = tr or (lambda k, **kw: k.format(**kw) if kw else k)
        self.message = message if message is not None else self.tr("loading.default")
        self._init_ui()

    def _init_ui(self):
        """Initialize UI components"""

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(24)

        # Title
        title = TitleLabel(self.tr("loading.title"))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # Loading spinner
        self.spinner = IndeterminateProgressRing(self)
        self.spinner.setFixedSize(80, 80)
        spinner_container = QWidget()
        spinner_layout = QVBoxLayout(spinner_container)
        spinner_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        spinner_layout.addWidget(self.spinner)
        layout.addWidget(spinner_container)

        # Message
        self.message_label = BodyLabel(self.message)
        self.message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.message_label)

        self.setLayout(layout)

    def set_message(self, message):
        """Update loading message"""
        self.message = message
        self.message_label.setText(message)
