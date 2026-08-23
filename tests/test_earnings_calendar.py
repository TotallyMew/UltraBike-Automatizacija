from __future__ import annotations

import os


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QDate, QDateTime, QRect, Qt, QTime
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QCalendarWidget,
    QDateTimeEdit,
    QToolButton,
)

from GUI_Qt.screens.EarningsScreen import (
    FluentCalendarWidget,
    configure_earnings_datetime_edit,
)
from GUI_Qt.styles.theme_config import COLORS, SIZES


def test_earnings_datetime_configuration_preserves_value_and_range():
    app = QApplication.instance() or QApplication([])
    editor = QDateTimeEdit()
    selected = QDateTime(QDate(2026, 8, 17), QTime(14, 6))
    minimum = QDateTime(QDate(2025, 1, 1), QTime(0, 0))
    maximum = QDateTime(QDate(2027, 12, 31), QTime(23, 59))
    editor.setDateTimeRange(minimum, maximum)
    editor.setDateTime(selected)

    configure_earnings_datetime_edit(editor)
    app.processEvents()

    calendar = editor.calendarWidget()
    assert editor.dateTime() == selected
    assert editor.minimumDateTime() == minimum
    assert editor.maximumDateTime() == maximum
    assert editor.displayFormat() == "dd MMM yyyy, HH:mm"
    assert editor.height() == SIZES["input_height"]
    assert editor.buttonSymbols() == QAbstractSpinBox.ButtonSymbols.NoButtons
    assert isinstance(calendar, FluentCalendarWidget)
    assert calendar.sizeHint().width() == 320
    assert calendar.sizeHint().height() == 320
    assert not calendar.isGridVisible()
    assert (
        calendar.verticalHeaderFormat()
        == QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader
    )

    editor.deleteLater()
    app.processEvents()


def test_calendar_uses_fluent_navigation_and_non_semantic_weekend_color():
    app = QApplication.instance() or QApplication([])
    calendar = FluentCalendarWidget()
    app.processEvents()

    previous = calendar.findChild(QToolButton, "qt_calendar_prevmonth")
    following = calendar.findChild(QToolButton, "qt_calendar_nextmonth")
    assert previous is not None and not previous.icon().isNull()
    assert following is not None and not following.icon().isNull()
    assert previous.accessibleName() == "Previous month"
    assert following.accessibleName() == "Next month"
    assert previous.minimumWidth() >= 32
    assert following.minimumWidth() >= 32

    saturday = calendar.weekdayTextFormat(Qt.DayOfWeek.Saturday)
    sunday = calendar.weekdayTextFormat(Qt.DayOfWeek.Sunday)
    expected = calendar._secondary_color
    assert saturday.foreground().color() == expected
    assert sunday.foreground().color() == expected
    assert saturday.foreground().color() != QColor(COLORS["flag_red"])

    calendar.deleteLater()
    app.processEvents()


def test_selected_calendar_cell_uses_filled_lavender_state():
    app = QApplication.instance() or QApplication([])
    calendar = FluentCalendarWidget()
    selected = QDate(2026, 8, 17)
    calendar.setCurrentPage(2026, 8)
    calendar.setSelectedDate(selected)

    image = QImage(44, 44, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    calendar.paintCell(painter, QRect(0, 0, 44, 44), selected)
    painter.end()

    assert image.pixelColor(7, 22) == QColor(COLORS["lavender_grey"])

    calendar.deleteLater()
    app.processEvents()
