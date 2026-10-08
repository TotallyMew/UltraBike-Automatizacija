"""Reusable navigation and page containers for Orbea workflow tabs."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QSizePolicy, QTabBar, QVBoxLayout, QWidget
from PySide6.QtWidgets import QHBoxLayout
from qfluentwidgets import PushButton

from GUI_Qt.styles.screen_theme import CONTENT_SPACING


class OrbeaSectionTabs(QTabBar):
    keyChanged = Signal(str)
    KEYS = ("automation", "tools")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("orbeaTabs")
        self.setDrawBase(False)
        self.setExpanding(False)
        self.setMovable(False)
        for label in ("Automation", "Extra tools"):
            self.addTab(label)
        self.currentChanged.connect(
            lambda index: self.keyChanged.emit(self.KEYS[index])
        )

    def select_key(self, key: str) -> str:
        key = {"setup": "automation", "progress": "automation", "results": "automation",
               "upload": "automation", "photos": "tools", "descriptions": "tools"}.get(key, key)
        normalized = key if key in self.KEYS else self.KEYS[0]
        index = self.KEYS.index(normalized)
        if self.currentIndex() != index:
            self.setCurrentIndex(index)
        return normalized


class OrbeaSectionPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.content_layout = QVBoxLayout(self)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(CONTENT_SPACING)


class OrbeaDisclosure(QWidget):
    """Keep optional controls out of the main flow until the user expands them."""
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.header_layout = QHBoxLayout()
        self.toggle = PushButton(self)
        self.toggle.setCheckable(True)
        self.header_layout.addWidget(self.toggle)
        self.header_layout.addStretch(1)
        layout.addLayout(self.header_layout)
        self.body = QWidget(self)
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 4, 0, 0)
        self.body_layout.setSpacing(CONTENT_SPACING)
        layout.addWidget(self.body)
        self.body.hide()
        self._title = ""
        self.toggle.toggled.connect(self.set_expanded)

    def set_title(self, title):
        self._title = title
        self._update_text()

    def set_expanded(self, expanded):
        self.toggle.setChecked(bool(expanded))
        self.body.setVisible(bool(expanded))
        self._update_text()

    def _update_text(self):
        self.toggle.setText(f"{'−' if self.toggle.isChecked() else '+'} {self._title}")
