"""Reusable navigation and page containers for Orbea workflow tabs."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QSizePolicy, QTabBar, QVBoxLayout, QWidget

from GUI_Qt.styles.screen_theme import CONTENT_SPACING


class OrbeaSectionTabs(QTabBar):
    keyChanged = Signal(str)
    KEYS = ("setup", "progress", "photos", "descriptions", "results")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("orbeaTabs")
        self.setDrawBase(False)
        self.setExpanding(False)
        self.setMovable(False)
        for label in ("Setup", "Progress", "Photos", "Descriptions", "Results"):
            self.addTab(label)
        self.currentChanged.connect(
            lambda index: self.keyChanged.emit(self.KEYS[index])
        )

    def select_key(self, key: str) -> str:
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
