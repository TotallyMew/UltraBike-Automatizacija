"""Reusable setup/review and run/output columns for application screens."""
from PySide6.QtCore import Qt, QEvent
from PySide6.QtWidgets import QBoxLayout, QVBoxLayout, QWidget, QSizePolicy, QTabWidget, QTabBar, QLayout, QAbstractScrollArea
from qfluentwidgets import CardWidget, CaptionLabel, PushButton, StrongBodyLabel, qconfig, isDarkTheme, FlowLayout

from GUI_Qt.styles.screen_theme import CARD_MARGINS
from GUI_Qt.styles.theme_config import RADII, SPACING, get_accent_colors, get_surface_color, get_text_color


def clear_layout(layout):
    """Remove layout items without destroying the existing controls."""
    while layout.count():
        item = layout.takeAt(0)
        if item.layout():
            clear_layout(item.layout())


def card():
    widget = CardWidget()
    widget.setBorderRadius(RADII["md"])
    box = QVBoxLayout(widget)
    box.setContentsMargins(*CARD_MARGINS)
    box.setSpacing(SPACING["md"])
    return widget, box


def connect_signal(signal, receiver, callback):
    """Disconnect closure slots when their owning widget is destroyed."""
    signal.connect(callback)
    def disconnect(*_args):
        try:
            signal.disconnect(callback)
        except (RuntimeError, TypeError):
            pass
    receiver.destroyed.connect(disconnect)


def bind_text(widget, main, key):
    def update(*_args):
        widget.setText(main.i18n.tr(key))
    update()
    if hasattr(main.i18n, "languageChanged"):
        connect_signal(main.i18n.languageChanged, widget, update)
    return widget


def heading(main, key):
    return bind_text(StrongBodyLabel(), main, key)


def move_widget(widget, layout, *, show=None):
    # Adding an existing widget to another layout preserves its signal connections.
    hidden = widget.isHidden()
    layout.addWidget(widget)
    widget.setVisible(not hidden if show is None else show)


def ancestor_card(widget):
    while widget is not None and not isinstance(widget, CardWidget):
        widget = widget.parentWidget()
    return widget


class WorkspaceColumns(QWidget):
    """A wide review column and a 340px action column that stack on small windows."""
    def __init__(self, parent=None, *, sidebar_width=340, threshold=940):
        super().__init__(parent)
        self.setObjectName("workspaceColumns")
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._viewport = None
        self._sidebar_width = sidebar_width
        self._threshold = threshold
        self.columns = QBoxLayout(QBoxLayout.Direction.LeftToRight, self)
        self.columns.setContentsMargins(0, 0, 0, 0)
        self.columns.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        self.columns.setSpacing(SPACING["base"])
        self.main = QWidget()
        self.sidebar = QWidget()
        self.main.setMinimumWidth(0)
        self.sidebar.setMinimumWidth(0)
        self.main.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.main_layout = QVBoxLayout(self.main)
        self.side_layout = QVBoxLayout(self.sidebar)
        for layout in (self.main_layout, self.side_layout):
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
            layout.setSpacing(SPACING["base"])
            layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.columns.addWidget(self.main, 1)
        self.columns.addWidget(self.sidebar)

    def _available_width(self):
        if self._viewport is None:
            return self.width()
        gutters = 0
        widget = self.parentWidget()
        while widget is not None and widget is not self._viewport:
            layout = widget.layout()
            if layout is not None:
                margins = layout.contentsMargins()
                gutters += margins.left() + margins.right()
            widget = widget.parentWidget()
        return max(0, self._viewport.width() - gutters)

    def showEvent(self, event):
        widget = self.parentWidget()
        while widget is not None:
            if isinstance(widget, QAbstractScrollArea):
                self._viewport = widget.viewport()
                self._viewport.installEventFilter(self)
                break
            widget = widget.parentWidget()
        self.set_compact(self._available_width() < self._threshold)
        super().showEvent(event)

    def eventFilter(self, watched, event):
        if watched is self._viewport and event.type() == QEvent.Type.Resize:
            self.set_compact(self._available_width() < self._threshold)
        return super().eventFilter(watched, event)

    def resizeEvent(self, event):
        self.set_compact(self._available_width() < self._threshold)
        super().resizeEvent(event)

    def set_compact(self, compact):
        direction = QBoxLayout.Direction.TopToBottom if compact else QBoxLayout.Direction.LeftToRight
        self.columns.setDirection(direction)
        self.sidebar.setMinimumWidth(0 if compact else self._sidebar_width)
        self.sidebar.setMaximumWidth(16777215 if compact else self._sidebar_width)


class Disclosure(QWidget):
    def __init__(self, main, key, parent=None, *, expanded=False):
        super().__init__(parent)
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(8)
        self.toggle = bind_text(PushButton(), main, key)
        self.toggle.setCheckable(True)
        self.toggle.setChecked(expanded)
        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(10)
        self.body.setVisible(expanded)
        self.toggle.toggled.connect(self.body.setVisible)
        box.addWidget(self.toggle)
        box.addWidget(self.body)


def grouped_stages(main, checks):
    """Present the same stage checkboxes under task-oriented headings."""
    groups = (
        ("layout.stages.setup", ("product_family", "brand", "save")),
        ("layout.stages.content", ("description_source", "description_magic_ai",
             "description", "specifications_prefill", "specifications_magic_ai",
             "category_magic_ai")),
        ("layout.stages.images", ("product_photos", "size_tables", "geometry",
             "local_images", "local_tables", "dimensions", "size_height")),
        ("layout.stages.translation", ("translations",)),
    )
    container = QWidget()
    container.setObjectName("workspaceStageGroups")
    container.setStyleSheet("#workspaceStageGroups { background: transparent; }")
    box = QVBoxLayout(container)
    box.setContentsMargins(0, 0, 0, 0)
    box.setSpacing(10)
    used = set()
    for key, names in groups:
        names = [name for name in names if name in checks]
        if names:
            box.addWidget(heading(main, key))
            for name in names:
                used.add(name)
                move_widget(checks[name], box)
    for name, check in checks.items():
        if name not in used:
            move_widget(check, box)
    count = CaptionLabel()
    box.addWidget(count)
    def update(*_args):
        count.setText(main.i18n.tr("layout.stages.count",
            selected=sum(c.isChecked() for c in checks.values()), total=len(checks)))
    for check in checks.values():
        check.stateChanged.connect(update)
    if hasattr(main.i18n, "languageChanged"):
        connect_signal(main.i18n.languageChanged, container, update)
    update()
    return container


def merge_contents(source, destination):
    layout = source.layout()
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            destination.addWidget(item.widget())
        elif item.layout():
            child = item.layout()
            if isinstance(child, FlowLayout):
                widgets = []
                while child.count():
                    widget = child.takeAt(0)
                    widget.removeEventFilter(child)
                    widgets.append(widget)
                replacement = FlowLayout()
                replacement.setHorizontalSpacing(SPACING["md"])
                replacement.setVerticalSpacing(SPACING["sm"])
                destination.addLayout(replacement)
                for widget in widgets:
                    replacement.addWidget(widget)
            else:
                destination.addLayout(child)
    source.hide()


def _tab_style():
    dark = isDarkTheme()
    accent = get_accent_colors(dark)["base"]
    text = get_text_color(dark)
    secondary = get_text_color(dark, "secondary")
    hover = get_surface_color(dark, "alternate")
    return f"""
        QTabWidget::pane {{ border: none; background: transparent; }}
        QTabBar {{ background: transparent; border: none; }}
        QTabBar::tab {{
            background: transparent; color: {secondary};
            border: none; border-bottom: 2px solid transparent;
            padding: 12px 16px; margin-right: 4px; font-size: 13px;
        }}
        QTabBar::tab:hover {{ background: {hover}; color: {text}; }}
        QTabBar::tab:selected {{
            color: {accent}; border-bottom: 2px solid {accent};
        }}
        QTabBar::tab:disabled {{ color: {secondary}; }}
    """


class WorkspaceTabs(QTabWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDocumentMode(True)
        self._apply_theme()
        qconfig.themeChangedFinished.connect(self._apply_theme)

    def _apply_theme(self):
        self.setStyleSheet(_tab_style())


class WorkspaceTabBar(QTabBar):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDrawBase(False)
        self.setExpanding(False)
        self._apply_theme()
        qconfig.themeChangedFinished.connect(self._apply_theme)

    def _apply_theme(self):
        self.setStyleSheet(_tab_style())
