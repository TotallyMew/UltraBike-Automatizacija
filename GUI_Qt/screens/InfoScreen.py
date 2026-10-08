"""A concise guide to the active application workspaces."""
from PySide6.QtWidgets import QWidget, QVBoxLayout
from qfluentwidgets import ScrollArea, TitleLabel, BodyLabel, CaptionLabel, qconfig
from GUI_Qt.styles.screen_theme import PAGE_MARGINS, PAGE_SPACING, apply_screen_theme
from GUI_Qt.widgets.ResponsiveWidget import ResponsiveWidget
from GUI_Qt.widgets.workspace import card, heading, bind_text, Disclosure


class InfoScreen(ResponsiveWidget):
    TOPICS = ("automation", "earnings", "lookup", "brands", "translations", "backups", "practice")

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main = main_window
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.scroll = ScrollArea()
        self.scroll.setWidgetResizable(True)
        root.addWidget(self.scroll)
        self.content = QWidget()
        self.content_widget = self.content
        self.scroll.setWidget(self.content)
        layout = QVBoxLayout(self.content)
        layout.setContentsMargins(*PAGE_MARGINS)
        layout.setSpacing(PAGE_SPACING)
        layout.addWidget(bind_text(TitleLabel(), self.main, "info.title"))
        overview, box = card()
        box.addWidget(heading(self.main, "info.overview.title"))
        for key, widget_type in (("info.overview.text", BodyLabel), ("info.overview.note", CaptionLabel)):
            label = bind_text(widget_type(), self.main, key)
            label.setWordWrap(True)
            box.addWidget(label)
        layout.addWidget(overview)
        topics, box = card()
        box.addWidget(heading(self.main, "layout.info.topics"))
        self.topic_disclosures = []
        for name in self.TOPICS:
            disclosure = Disclosure(self.main, "layout.info." + name + ".title")
            body = bind_text(BodyLabel(), self.main, "layout.info." + name + ".body")
            body.setWordWrap(True)
            disclosure.body_layout.addWidget(body)
            box.addWidget(disclosure)
            self.topic_disclosures.append(disclosure)
        layout.addWidget(topics)
        layout.addStretch()
        self._apply_theme()
        qconfig.themeChangedFinished.connect(self._apply_theme)

    def _apply_theme(self):
        apply_screen_theme(self, "InfoScreen", scroll=self.scroll, content=self.content)

    def retranslate_ui(self):
        # Each label is bound to the language signal by the shared helpers.
        pass
