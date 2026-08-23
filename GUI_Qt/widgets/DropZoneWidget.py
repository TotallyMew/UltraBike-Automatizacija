"""
GUI_Qt/widgets/DropZoneWidget.py

Drag-and-drop zone for Excel (.xlsx) files.
Shared across all batch screens.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QVBoxLayout, QWidget
from qfluentwidgets import (
    CaptionLabel,
    IconWidget,
    FluentIcon,
    StrongBodyLabel,
    isDarkTheme,
)

from GUI_Qt.styles.theme_config import (
    COLORS,
    FONTS,
    RADII,
    SIZES,
    SPACING,
    get_hover_bg,
    get_text_color,
)


class DropZoneWidget(QWidget):
    """Drag-and-drop zone for Excel files.

    Emits ``file_dropped`` with a file path when a valid .xlsx is dropped,
    or the sentinel ``"__browse__"`` when the widget is clicked (so the
    parent can open a file dialog).
    """

    file_dropped = Signal(str)

    def __init__(self, tr, parent=None):
        super().__init__(parent)
        self.tr = tr
        self.title_label = None
        self.subtitle_label = None
        self.setAcceptDrops(True)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(SPACING['base'])

        icon = IconWidget(FluentIcon.DOCUMENT)
        icon.setFixedSize(SIZES["icon_huge"], SIZES["icon_huge"])

        self.title_label = StrongBodyLabel("")
        self.title_label.setStyleSheet(
            f"font-size: {FONTS['size_subtitle_2']}; color: {get_text_color(isDarkTheme())};"
        )

        self.subtitle_label = CaptionLabel("")
        self.subtitle_label.setStyleSheet(
            f"color: {get_text_color(isDarkTheme(), 'secondary')};"
        )

        layout.addStretch()
        layout.addWidget(icon, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title_label, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.subtitle_label, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addStretch()

        self._apply_style()
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.retranslate_ui()

    def retranslate_ui(self):
        if self.title_label is not None:
            self.title_label.setText(self.tr("batch.drop.title"))
        if self.subtitle_label is not None:
            self.subtitle_label.setText(self.tr("batch.drop.subtitle"))

    # -- Drag & drop ---------------------------------------------------------

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if len(urls) == 1 and urls[0].toLocalFile().endswith(".xlsx"):
                event.acceptProposedAction()
                self._apply_style(is_drag_active=True)

    def dragLeaveEvent(self, event):
        self._apply_style()

    def dropEvent(self, event: QDropEvent):
        files = [u.toLocalFile() for u in event.mimeData().urls()]
        if files and files[0].endswith(".xlsx"):
            self.file_dropped.emit(files[0])
        self._apply_style()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.file_dropped.emit("__browse__")

    # -- Styling -------------------------------------------------------------

    def _apply_style(self, is_drag_active: bool = False):
        is_dark = isDarkTheme()
        self.title_label.setStyleSheet(
            f"font-size: {FONTS['size_subtitle_2']}; color: {get_text_color(is_dark)};"
        )
        self.subtitle_label.setStyleSheet(
            f"color: {get_text_color(is_dark, 'secondary')};"
        )
        border = COLORS["lavender_grey"] if is_dark else COLORS["space_indigo"]
        dashed = COLORS["lavender_grey"]
        hover_bg = get_hover_bg(is_dark)

        if is_drag_active:
            self.setStyleSheet(f"""
                DropZoneWidget {{
                    background-color: {hover_bg};
                    border: 2px solid {border};
                    border-radius: {RADII['lg']}px;
                }}
            """)
            return

        self.setStyleSheet(f"""
            DropZoneWidget {{
                background-color: transparent;
                border: 2px dashed {dashed};
                border-radius: {RADII['lg']}px;
            }}
            DropZoneWidget:hover {{
                border-color: {border};
                background-color: {hover_bg};
            }}
        """)
