"""Reusable earnings calendar, chart, and metric widgets."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from PySide6.QtCore import (
    QDate,
    QEasingCurve,
    QEvent,
    QParallelAnimationGroup,
    QPoint,
    QPropertyAnimation,
    QRectF,
    QSequentialAnimationGroup,
    QSize,
    Qt,
    QTimer,
    QVariantAnimation,
)
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QTextCharFormat
from PySide6.QtWidgets import (
    QAbstractItemView,
    QAbstractSpinBox,
    QCalendarWidget,
    QCheckBox,
    QDateEdit,
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGraphicsOpacityEffect,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressBar,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QTabBar,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTableView,
    QToolButton,
    QToolTip,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    Action,
    BodyLabel,
    CaptionLabel,
    CheckBox,
    ComboBox,
    DateEdit as FluentDateEdit,
    DoubleSpinBox as FluentDoubleSpinBox,
    FluentIcon,
    InfoBar,
    InfoBarPosition,
    LineEdit,
    MessageBox,
    PrimaryPushButton,
    PushButton,
    RoundMenu,
    ScrollArea,
    SpinBox as FluentSpinBox,
    StrongBodyLabel,
    TitleLabel,
    isDarkTheme,
    qconfig,
)

from GUI_Qt.styles.screen_theme import apply_screen_theme
from GUI_Qt.styles.theme_config import (
    COLORS,
    COMPONENT_COLORS,
    FONTS,
    PADDINGS,
    RADII,
    SIZES,
    SPACING,
    get_dialog_button_style,
    get_dialog_danger_button_style,
    get_dialog_section_style,
    get_dialog_table_style,
    get_calendar_popup_style,
    get_form_dialog_style,
    get_form_input_style,
    get_activity_heatmap_colors,
    get_selection_bg,
    get_status_text_color,
    get_subtle_border,
    get_subtle_item_hover_bg,
    get_text_color,
    rgba_from_hex,
)
from GUI_Qt.widgets.ResponsiveWidget import ResponsiveWidget
from Managers.EarningsManager import (
    ActiveGoalError,
    ActiveSessionError,
    EarningsManager,
    GoalStatus,
    ProductType,
)


from GUI_Qt.earnings.presentation import money

class EarningsChart(QWidget):
    """Compact theme-aware bar chart with hover values."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.data: list[dict[str, Any]] = []
        self._bar_rects: list[QRectF] = []
        self.setMinimumHeight(160)
        self.setMouseTracking(True)

    def set_data(self, data: list[dict[str, Any]]) -> None:
        self.data = data
        self.update()

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        text = QColor(COLORS["text_primary_dark"] if isDarkTheme() else COLORS["text_primary_light"])
        secondary = QColor(get_text_color(isDarkTheme(), "secondary"))
        accent = QColor(COLORS.get("primary", COLORS["space_indigo"]))
        grid = QColor(COLORS["border_dark"] if isDarkTheme() else COLORS["border_light"])
        plot = self.rect().adjusted(54, 16, -16, -42)
        self._bar_rects = []
        if not self.data:
            painter.setPen(secondary)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No earning data yet")
            return
        maximum = max(1, max(int(item.get("cents", 0)) for item in self.data))
        painter.setPen(QPen(grid, 1))
        for i in range(5):
            y = plot.bottom() - plot.height() * i / 4
            painter.drawLine(plot.left(), int(y), plot.right(), int(y))
            painter.setPen(secondary)
            painter.drawText(2, int(y) - 8, 48, 18, Qt.AlignmentFlag.AlignRight, money(maximum * i / 4))
            painter.setPen(QPen(grid, 1))
        slot = plot.width() / max(1, len(self.data))
        bar_width = max(3.0, min(28.0, slot * 0.66))
        label_step = max(1, math.ceil(len(self.data) / 10))
        for index, item in enumerate(self.data):
            value = int(item.get("cents", 0))
            height = plot.height() * value / maximum
            x = plot.left() + index * slot + (slot - bar_width) / 2
            rect = QRectF(x, plot.bottom() - height, bar_width, max(1.5, height))
            self._bar_rects.append(rect)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(accent)
            painter.drawRoundedRect(rect, 3, 3)
            if index % label_step == 0 or index == len(self.data) - 1:
                painter.setPen(text)
                painter.save()
                font = painter.font()
                font.setPointSize(8)
                painter.setFont(font)
                painter.drawText(
                    QRectF(x - slot / 2, plot.bottom() + 8, slot * 2, 24),
                    Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                    str(item.get("label", "")),
                )
                painter.restore()

    def mouseMoveEvent(self, event):  # noqa: N802
        point = event.position()
        for index, rect in enumerate(self._bar_rects):
            if rect.contains(point):
                item = self.data[index]
                QToolTip.showText(
                    event.globalPosition().toPoint(),
                    f"{item.get('label', '')}\n{money(item.get('cents', 0))} • {item.get('count', 0)} products",
                    self,
                )
                return
        QToolTip.hideText()


class AnimatedSubmitButton(PrimaryPushButton):
    """Primary action with a compact native spring animation on success."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self.setText(text)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._success_animation: QSequentialAnimationGroup | None = None

    def sizeHint(self):  # noqa: N802
        return QSize(150, 38)

    def minimumSizeHint(self):  # noqa: N802
        return QSize(132, 34)

    def animate_success(self) -> None:
        if self._success_animation is not None:
            self._success_animation.stop()

        start = self.geometry()
        if start.width() <= 0 or start.height() <= 0:
            return
        pressed = start.adjusted(5, 2, -5, -2)

        compress = QPropertyAnimation(self, b"geometry")
        compress.setDuration(75)
        compress.setStartValue(start)
        compress.setEndValue(pressed)
        compress.setEasingCurve(QEasingCurve.Type.OutQuad)

        spring = QPropertyAnimation(self, b"geometry")
        spring.setDuration(260)
        spring.setStartValue(pressed)
        spring.setEndValue(start)
        spring.setEasingCurve(QEasingCurve.Type.OutBack)

        animation = QSequentialAnimationGroup(self)
        animation.addAnimation(compress)
        animation.addAnimation(spring)
        self._success_animation = animation
        animation.start()


class EarningsBurstBadge(QLabel):
    """One-second earning badge that floats upward from a submit control."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("earningBurstBadge")
        self.setProperty("ubAllowBg", True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setStyleSheet(
            "QLabel#earningBurstBadge {"
            f" background-color: {COLORS['success']}; color: {COLORS['on_success']}; border: none;"
            " border-radius: 9px; padding: 4px 9px; font-weight: 700; }"
        )
        self._opacity = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity)
        self._animation: QParallelAnimationGroup | None = None
        self.hide()

    def show_amount(self, cents: int, anchor: QWidget) -> None:
        if self._animation is not None:
            self._animation.stop()

        self.setText(f"+{money(cents)}")
        self.adjustSize()
        anchor_top = anchor.mapTo(self.parentWidget(), QPoint(0, 0))
        start = QPoint(
            anchor_top.x() + (anchor.width() - self.width()) // 2,
            max(2, anchor_top.y() - self.height() + 4),
        )
        end = start - QPoint(0, 34)
        self.move(start)
        self._opacity.setOpacity(1.0)
        self.show()
        self.raise_()

        movement = QPropertyAnimation(self, b"pos")
        movement.setDuration(1000)
        movement.setStartValue(start)
        movement.setEndValue(end)
        movement.setEasingCurve(QEasingCurve.Type.OutCubic)

        fade = QPropertyAnimation(self._opacity, b"opacity")
        fade.setDuration(1000)
        fade.setStartValue(1.0)
        fade.setKeyValueAt(0.42, 1.0)
        fade.setEndValue(0.0)
        fade.setEasingCurve(QEasingCurve.Type.InCubic)

        animation = QParallelAnimationGroup(self)
        animation.addAnimation(movement)
        animation.addAnimation(fade)
        animation.finished.connect(self.hide)
        self._animation = animation
        animation.start()


class BatchProgressTicks(QWidget):
    """Ten-step SKU batch counter with a short completion pulse."""

    SEGMENTS = 10

    def __init__(self, parent=None):
        super().__init__(parent)
        self._count = 0
        self._pulse = 0.0
        self._pulse_animation: QVariantAnimation | None = None
        self.setMinimumSize(176, 24)
        self.setMaximumHeight(28)
        self.setAccessibleName("Batch progress: 0 of 10 SKUs")

    @property
    def count(self) -> int:
        return self._count

    def advance(self) -> None:
        if self._count >= self.SEGMENTS:
            self._count = 0
        self._count += 1
        if self._count < self.SEGMENTS:
            self._update_accessibility()
            self.update()
            return

        self._count = self.SEGMENTS
        self._update_accessibility()
        self.update()
        self._start_completion_pulse()
        QTimer.singleShot(300, self._reset_completed_batch)

    def _start_completion_pulse(self) -> None:
        if self._pulse_animation is not None:
            self._pulse_animation.stop()
        animation = QVariantAnimation(self)
        animation.setDuration(300)
        animation.setStartValue(0.0)
        animation.setKeyValueAt(0.45, 1.0)
        animation.setEndValue(0.0)
        animation.valueChanged.connect(self._set_pulse)
        self._pulse_animation = animation
        animation.start()

    def _set_pulse(self, value) -> None:
        self._pulse = float(value)
        self.update()

    def _reset_completed_batch(self) -> None:
        if self._count == self.SEGMENTS:
            self._count = 0
            self._update_accessibility()
            self.update()

    def _update_accessibility(self) -> None:
        self.setAccessibleName(f"Batch progress: {self._count} of {self.SEGMENTS} SKUs")

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        dark = isDarkTheme()
        accent = QColor(COLORS["lavender_grey" if dark else "space_indigo"])
        empty = QColor(COLORS["border_dark" if dark else "border_light"])
        success = QColor(COLORS["success"])
        text = QColor(get_text_color(dark, "secondary"))

        label_width = 42
        gap = 3
        available = max(80, self.width() - label_width - 8)
        segment_width = max(4.0, (available - gap * (self.SEGMENTS - 1)) / self.SEGMENTS)
        segment_height = 8 + (2 * self._pulse)
        top = (self.height() - segment_height) / 2
        for index in range(self.SEGMENTS):
            rect = QRectF(index * (segment_width + gap), top, segment_width, segment_height)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(success if self._count == self.SEGMENTS else (accent if index < self._count else empty))
            painter.drawRoundedRect(rect, 2.5, 2.5)

        painter.setPen(text)
        painter.drawText(
            QRectF(self.width() - label_width, 0, label_width, self.height()),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            f"{self._count}/{self.SEGMENTS}",
        )


class GoalMilestoneBar(QProgressBar):
    """Animated goal progress with fixed money milestone notches."""

    DEFAULT_MILESTONES = (10_000, 25_000, 50_000)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRange(0, 1000)
        self.setTextVisible(False)
        self._target_cents = 0
        self._current_cents: int | None = None
        self._milestones: tuple[int, ...] = ()
        self._pulse = 0.0
        self._fill_animation: QVariantAnimation | None = None
        self._pulse_animation: QVariantAnimation | None = None

    @property
    def milestones(self) -> tuple[int, ...]:
        return self._milestones

    def set_progress(self, current_cents: int, target_cents: int) -> None:
        current = max(0, int(current_cents))
        target = max(0, int(target_cents))
        previous = self._current_cents
        target_changed = target != self._target_cents
        self._target_cents = target
        self._milestones = tuple(value for value in self.DEFAULT_MILESTONES if value <= target)
        goal_value = min(1000, int(round(current * 1000 / target))) if target else 0

        if previous is None or target_changed:
            QProgressBar.setValue(self, goal_value)
        elif goal_value != self.value():
            self._animate_fill(goal_value)

        if not target_changed and previous is not None and any(
            previous < milestone <= current for milestone in self._milestones
        ):
            self._start_milestone_pulse()
        self._current_cents = current
        milestone_text = ", ".join(money(value) for value in self._milestones)
        self.setToolTip(f"Milestones: {milestone_text}" if milestone_text else "")
        self.setAccessibleName(
            f"Money goal progress: {money(current)} of {money(target)}"
        )
        self.update()

    def _animate_fill(self, end_value: int) -> None:
        if self._fill_animation is not None:
            self._fill_animation.stop()
        animation = QVariantAnimation(self)
        animation.setDuration(420)
        animation.setStartValue(self.value())
        animation.setEndValue(end_value)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.valueChanged.connect(
            lambda value: QProgressBar.setValue(self, int(round(float(value))))
        )
        self._fill_animation = animation
        animation.start()

    def _start_milestone_pulse(self) -> None:
        if self._pulse_animation is not None:
            self._pulse_animation.stop()
        animation = QVariantAnimation(self)
        animation.setDuration(320)
        animation.setStartValue(0.0)
        animation.setKeyValueAt(0.45, 1.0)
        animation.setEndValue(0.0)
        animation.valueChanged.connect(self._set_pulse)
        self._pulse_animation = animation
        animation.start()

    def _set_pulse(self, value) -> None:
        self._pulse = float(value)
        self.update()

    def paintEvent(self, event):  # noqa: N802
        super().paintEvent(event)
        if self._target_cents <= 0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        bounds = self.rect().adjusted(1, 1, -1, -1)

        if self._pulse > 0 and self.value() > 0:
            flash = QColor(COLORS["success"])
            flash.setAlphaF(0.42 * self._pulse)
            fill_width = int(bounds.width() * self.value() / 1000)
            painter.fillRect(bounds.adjusted(0, 0, -(bounds.width() - fill_width), 0), flash)

        notch = QColor("#FFFFFF" if isDarkTheme() else COLORS["space_indigo"])
        notch.setAlphaF(0.78 if isDarkTheme() else 0.56)
        painter.setPen(QPen(notch, 1.25))
        for milestone in self._milestones:
            ratio = min(1.0, milestone / self._target_cents)
            x = bounds.left() + int(round(bounds.width() * ratio))
            x = min(bounds.right() - 1, max(bounds.left() + 1, x))
            painter.drawLine(x, bounds.top() + 2, x, bounds.bottom() - 2)


class QuestCheckpointBar(QProgressBar):
    """Animated quest fill with four visible checkpoint notches."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRange(0, 1000)
        self.setValue(0)
        self.setTextVisible(False)
        self.setFixedHeight(12)
        self._animation: QVariantAnimation | None = None

    def set_percent(self, percent: float, *, animated: bool = True) -> None:
        target = max(0, min(1000, int(round(float(percent) * 10))))
        if not animated or not self.isVisible():
            self.setValue(target)
            return
        if target == self.value():
            return
        if self._animation is not None:
            self._animation.stop()
        animation = QVariantAnimation(self)
        animation.setDuration(360)
        animation.setStartValue(self.value())
        animation.setEndValue(target)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.valueChanged.connect(
            lambda value: QProgressBar.setValue(self, int(round(float(value))))
        )
        self._animation = animation
        animation.start()

    def paintEvent(self, event):  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        bounds = self.rect().adjusted(1, 1, -1, -1)
        marker = QColor("#FFFFFF" if isDarkTheme() else COLORS["space_indigo"])
        marker.setAlphaF(0.78 if isDarkTheme() else 0.48)
        painter.setPen(QPen(marker, 1.1))
        for fraction in (0.25, 0.50, 0.75, 1.0):
            x = bounds.left() + int(round(bounds.width() * fraction))
            x = min(bounds.right() - 1, max(bounds.left() + 1, x))
            painter.drawLine(x, bounds.top() + 2, x, bounds.bottom() - 2)


class QuestProgressWidget(QWidget):
    """Compact live quest summary used inside the timer card."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("earningsQuestProgress")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 9, 12, 9)
        layout.setSpacing(5)
        header = QHBoxLayout()
        header.setSpacing(6)
        self.title = StrongBodyLabel("")
        self.badge = CaptionLabel("")
        self.badge.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        header.addWidget(self.title, 1)
        header.addWidget(self.badge)
        layout.addLayout(header)
        self.bar = QuestCheckpointBar(self)
        layout.addWidget(self.bar)
        self.detail = CaptionLabel("")
        self.detail.setWordWrap(True)
        layout.addWidget(self.detail)
        self.hide()

    def set_state(
        self,
        *,
        title: str,
        badge: str,
        detail: str,
        percent: float,
        animated: bool,
        complete: bool,
    ) -> None:
        self.title.setText(title)
        self.badge.setText(badge)
        self.detail.setText(detail)
        self.badge.setProperty("complete", complete)
        self.bar.set_percent(percent, animated=animated)
        self.setAccessibleName(f"{title}: {badge}. {detail}")
        self.show()

    def clear(self) -> None:
        self.hide()
        self.bar.set_percent(0, animated=False)


class QuestCelebrationOverlay(QWidget):
    """A short, non-blocking ripple or completion particle burst."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self._progress = 0.0
        self._completion = False
        self._badge_text = ""
        self._animation: QVariantAnimation | None = None
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        parent.installEventFilter(self)
        self.setGeometry(parent.rect())
        self.hide()

    def eventFilter(self, watched, event):  # noqa: N802
        if watched is self.parentWidget() and event.type() == QEvent.Type.Resize:
            self.setGeometry(self.parentWidget().rect())
        return super().eventFilter(watched, event)

    def celebrate(self, *, completion: bool, badge_text: str = "") -> None:
        if self._animation is not None:
            self._animation.stop()
        self._completion = bool(completion)
        self._badge_text = badge_text
        self._progress = 0.0
        self.setGeometry(self.parentWidget().rect())
        self.show()
        self.raise_()
        animation = QVariantAnimation(self)
        animation.setDuration(1100 if completion else 520)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.valueChanged.connect(self._set_progress)
        animation.finished.connect(self.hide)
        self._animation = animation
        animation.start()

    def _set_progress(self, value) -> None:
        self._progress = float(value)
        self.update()

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        accent = QColor(COLORS["success"])
        fade = max(0.0, 1.0 - self._progress)
        center = self.rect().center()

        ring = QColor(accent)
        ring.setAlphaF(0.55 * fade)
        painter.setPen(QPen(ring, 3.0 if self._completion else 2.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        radius = 12 + self._progress * (min(self.width(), self.height()) * 0.48)
        painter.drawEllipse(center, radius, radius)

        if self._completion:
            painter.setPen(Qt.PenStyle.NoPen)
            count = 18
            travel = 22 + self._progress * 74
            for index in range(count):
                angle = (math.tau * index / count) + (index % 3) * 0.11
                particle = QColor(accent if index % 2 else QColor(COLORS["lavender_grey"]))
                particle.setAlphaF(0.88 * fade)
                painter.setBrush(particle)
                x = center.x() + math.cos(angle) * travel
                y = center.y() + math.sin(angle) * travel * 0.58
                size = 3.0 + (index % 3)
                painter.drawEllipse(QRectF(x - size / 2, y - size / 2, size, size))

            if self._badge_text and self._progress < 0.82:
                text_alpha = min(1.0, self._progress * 8.0) * min(1.0, fade * 3.0)
                badge = QColor(accent)
                badge.setAlphaF(text_alpha)
                badge_rect = QRectF(center.x() - 92, center.y() - 22, 184, 44)
                painter.setBrush(badge)
                painter.drawRoundedRect(badge_rect, 14, 14)
                painter.setPen(QColor("#FFFFFF"))
                font = painter.font()
                font.setBold(True)
                font.setPointSize(max(10, font.pointSize() + 2))
                painter.setFont(font)
                painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, self._badge_text)


class PerformanceTargetWidget(QWidget):
    """Compact target card with separate value, percentage, and progress hierarchy."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName("earningsTargetMetric")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMinimumHeight(92)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(13, 11, 13, 12)
        layout.setSpacing(7)
        header = QHBoxLayout()
        header.setSpacing(SPACING["sm"])
        self.title = CaptionLabel(title)
        self.title.setObjectName("earningsTargetTitle")
        self.percentage = CaptionLabel("0%")
        self.percentage.setObjectName("earningsTargetPercentage")
        self.percentage.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.percentage.setMinimumWidth(46)
        header.addWidget(self.title, 1)
        header.addWidget(self.percentage)
        layout.addLayout(header)

        values = QHBoxLayout()
        values.setSpacing(SPACING["xs"])
        self.current = QLabel("—")
        self.current.setObjectName("earningsTargetCurrent")
        self.target = CaptionLabel("")
        self.target.setObjectName("earningsTargetTotal")
        values.addWidget(self.current)
        values.addWidget(self.target, 1, Qt.AlignmentFlag.AlignBottom)
        layout.addLayout(values)

        self.progress = QProgressBar()
        self.progress.setObjectName("earningsTargetProgress")
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(8)
        layout.addWidget(self.progress)

    def set_title(self, title: str) -> None:
        self.title.setText(title)

    def set_progress(self, current_text: str, target_text: str, ratio: float) -> None:
        ratio = max(0.0, float(ratio))
        complete = ratio >= 1.0
        self.setProperty("complete", complete)
        self.current.setText(current_text)
        self.target.setText(f"/ {target_text}")
        self.percentage.setText(f"{int(round(ratio * 100))}%")
        self.progress.setValue(int(round(min(1.0, ratio) * 1000)))
        self.setAccessibleName(
            f"{self.title.text()}: {current_text} of {target_text}, "
            f"{int(round(ratio * 100))} percent"
        )


class ActivityMetricTile(QWidget):
    """Small summary tile with deterministic theme surface painting."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._background_color = QColor("#FFFFFF")
        self._border_color = QColor("#E2E8F0")

    @property
    def background_color(self) -> QColor:
        return QColor(self._background_color)

    def set_theme_colors(self, background: str, border: str) -> None:
        self._background_color = QColor(background)
        self._border_color = QColor(border)
        self.update()

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(self._border_color, 1.0))
        painter.setBrush(self._background_color)
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 8, 8)


class ActivityLegend(QWidget):
    """Plain-language heatmap scale with real color swatches."""

    LEVELS = 5

    def __init__(self, translate=None, parent=None):
        super().__init__(parent)
        self._translate = translate
        self._fewer = "Fewer SKUs"
        self._more = "More SKUs"
        self.setFixedHeight(24)
        self.setMinimumWidth(200)
        self.setMaximumWidth(240)
        self.setAccessibleName("Activity intensity: fewer to more SKUs")
        self.retranslate_ui()

    def _tr(self, key: str, fallback: str, **values) -> str:
        if callable(self._translate):
            translated = self._translate(key, **values)
            if translated and translated != key:
                return translated
        return fallback.format(**values)

    def retranslate_ui(self) -> None:
        self._fewer = self._tr("earnings.activity_fewer", "Fewer SKUs")
        self._more = self._tr("earnings.activity_more", "More SKUs")
        self.setAccessibleName(f"{self._fewer} — {self._more}")
        self.update()

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        dark = isDarkTheme()
        text = QColor(get_text_color(dark, "secondary"))
        levels = tuple(QColor(value) for value in get_activity_heatmap_colors(dark))
        metrics = painter.fontMetrics()
        fewer_width = metrics.horizontalAdvance(self._fewer)
        painter.setPen(text)
        painter.drawText(
            QRectF(0, 0, fewer_width, self.height()),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self._fewer,
        )
        x = fewer_width + 8
        size = 10.0
        gap = 3.0
        for level in range(self.LEVELS):
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(levels[level])
            painter.drawRoundedRect(QRectF(x, (self.height() - size) / 2, size, size), 2, 2)
            x += size + gap
        painter.setPen(text)
        painter.drawText(
            QRectF(x + 3, 0, max(0, self.width() - x - 3), self.height()),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self._more,
        )


class ActivityHeatmap(QWidget):
    """Theme-aware 30-day product activity strip."""

    DAYS = 30
    ROWS = 1

    def __init__(self, translate=None, parent=None):
        super().__init__(parent)
        self._translate = translate
        self._data: list[dict[str, Any]] = []
        self._cell_rects: list[QRectF] = []
        self._axis_label_rects: tuple[QRectF, ...] = ()
        self._axis_start = "30 days ago"
        self._axis_today = "Today"
        self.setMinimumHeight(58)
        self.setMaximumHeight(64)
        self.setMinimumWidth(280)
        self.setMaximumWidth(16777215)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)
        self.retranslate_ui()

    def _tr(self, key: str, fallback: str, **values) -> str:
        if callable(self._translate):
            translated = self._translate(key, **values)
            if translated and translated != key:
                return translated
        return fallback.format(**values)

    def retranslate_ui(self) -> None:
        self._axis_start = self._tr("earnings.activity_start", "30 days ago")
        self._axis_today = self._tr("earnings.activity_today", "Today")
        self.setAccessibleName(
            self._tr(
                "earnings.activity_accessible",
                "Product activity for the last 30 days",
            )
        )
        self._update_accessibility()
        self.update()

    @property
    def data(self) -> list[dict[str, Any]]:
        return list(self._data)

    def set_data(self, data: list[dict[str, Any]]) -> None:
        values = list(data)[-self.DAYS :]
        if len(values) < self.DAYS:
            values = [
                {"label": "", "count": 0, "cents": 0}
                for _ in range(self.DAYS - len(values))
            ] + values
        self._data = values
        self._update_accessibility()
        self.update()

    def _update_accessibility(self) -> None:
        total = sum(int(item.get("count", 0)) for item in self._data)
        self.setAccessibleDescription(
            self._tr(
                "earnings.activity_accessible_count",
                "{count} SKUs logged over 30 days",
                count=total,
            )
        )

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        dark = isDarkTheme()
        levels = tuple(QColor(value) for value in get_activity_heatmap_colors(dark))
        text = QColor(get_text_color(dark, "secondary"))
        maximum = max((int(item.get("count", 0)) for item in self._data), default=0)
        columns = math.ceil(max(1, len(self._data)) / self.ROWS)
        spacing = 3.0
        available_width = max(1.0, self.width() - 2.0)
        cell = min(
            18.0,
            max(6.0, (available_width - spacing * (columns - 1)) / columns),
        )
        grid_width = columns * cell + (columns - 1) * spacing
        left = 1.0
        top = 3.0
        self._cell_rects = []

        for index, item in enumerate(self._data):
            column, row = divmod(index, self.ROWS)
            rect = QRectF(left + column * (cell + spacing), top + row * (cell + spacing), cell, cell)
            self._cell_rects.append(rect)
            count = int(item.get("count", 0))
            if count <= 0 or maximum <= 0:
                color = levels[0]
            else:
                level = max(1, min(4, math.ceil(count * 4 / maximum)))
                color = levels[level]
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(rect, 3, 3)

        painter.setPen(text)
        label_top = top + self.ROWS * cell + (self.ROWS - 1) * spacing + 5
        start_rect = QRectF(left, label_top, min(120, grid_width * 0.45), 18)
        painter.drawText(
            start_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self._axis_start,
        )
        today_width = min(90.0, max(55.0, grid_width * 0.35))
        today_left = max(left + start_rect.width() + 8, left + grid_width - today_width)
        today_rect = QRectF(today_left, label_top, today_width, 18)
        painter.drawText(
            today_rect,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            self._axis_today,
        )
        self._axis_label_rects = (start_rect, today_rect)

    def mouseMoveEvent(self, event):  # noqa: N802
        point = event.position()
        for index, rect in enumerate(self._cell_rects):
            if rect.contains(point) and index < len(self._data):
                item = self._data[index]
                count = int(item.get("count", 0))
                key = (
                    "earnings.activity_tooltip.one"
                    if count == 1
                    else "earnings.activity_tooltip.many"
                )
                QToolTip.showText(
                    event.globalPosition().toPoint(),
                    self._tr(
                        key,
                        "{date}\n{count} SKU logged"
                        if count == 1
                        else "{date}\n{count} SKUs logged",
                        date=item.get("label", ""),
                        count=count,
                    ),
                    self,
                )
                return
        QToolTip.hideText()

    def leaveEvent(self, event):  # noqa: N802
        QToolTip.hideText()
        super().leaveEvent(event)


class MetricCard(QWidget):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName("earningsMetric")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 11)
        layout.setSpacing(3)
        self.title = CaptionLabel(title)
        self.title.setWordWrap(True)
        self.value = QLabel("—")
        self.value.setFont(QFont(FONTS["family"], 27, QFont.Weight.DemiBold))
        self.subtitle = CaptionLabel("")
        self.subtitle.setWordWrap(True)
        layout.addWidget(self.title)
        layout.addWidget(self.value)
        layout.addWidget(self.subtitle)

    def set_values(self, value: str, subtitle: str = "") -> None:
        self.value.setText(value)
        self.subtitle.setText(subtitle)


class ProjectionMetric(QWidget):
    """Borderless value used inside the income-projection surface."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(68)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 10, 3)
        layout.setSpacing(2)
        self.title = CaptionLabel(title)
        self.value = QLabel("—")
        self.value.setFont(QFont(FONTS["family"], 22, QFont.Weight.DemiBold))
        self.subtitle = CaptionLabel("")
        self.subtitle.setWordWrap(True)
        layout.addWidget(self.title)
        layout.addWidget(self.value)
        layout.addWidget(self.subtitle)

    def set_values(self, value: str, subtitle: str = "") -> None:
        self.value.setText(value)
        self.subtitle.setText(subtitle)
        self.setAccessibleName(f"{self.title.text()}: {value}. {subtitle}")


class FluentCalendarWidget(QCalendarWidget):
    """Theme-aware QCalendarWidget that preserves Qt's calendar behavior."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("earningsCalendar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setGridVisible(False)
        self.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
        self.setHorizontalHeaderFormat(QCalendarWidget.HorizontalHeaderFormat.ShortDayNames)
        self.setMinimumSize(320, 320)
        self.setMaximumSize(330, 340)
        if self.layout():
            self.layout().setContentsMargins(
                SPACING["sm"], SPACING["sm"], SPACING["sm"], SPACING["sm"]
            )
            self.layout().setSpacing(SPACING["xs"])

        self._hovered_date = QDate()
        self._calendar_view = self.findChild(QTableView, "qt_calendar_calendarview")
        if self._calendar_view is not None:
            self._calendar_view.setMouseTracking(True)
            self._calendar_view.viewport().setMouseTracking(True)
            self._calendar_view.viewport().installEventFilter(self)

        self.currentPageChanged.connect(self._clear_hover)
        qconfig.themeChangedFinished.connect(self.apply_theme)
        self.apply_theme()

    def sizeHint(self):  # noqa: N802
        return QSize(320, 320)

    def _clear_hover(self, *_args) -> None:
        previous = self._hovered_date
        self._hovered_date = QDate()
        if previous.isValid():
            self.updateCell(previous)

    def _date_for_index(self, row: int, column: int) -> QDate:
        if row < 1:
            return QDate()
        has_week_column = (
            self._calendar_view is not None
            and self._calendar_view.model().columnCount() == 8
        )
        date_column = column - 1 if has_week_column else column
        if not 0 <= date_column < 7:
            return QDate()
        month_start = QDate(self.yearShown(), self.monthShown(), 1)
        first_day = self.firstDayOfWeek().value
        leading_days = (month_start.dayOfWeek() - first_day) % 7
        return month_start.addDays(-leading_days + (row - 1) * 7 + date_column)

    def eventFilter(self, watched, event):  # noqa: N802
        if self._calendar_view is not None and watched is self._calendar_view.viewport():
            hovered = QDate()
            if event.type() == QEvent.Type.MouseMove:
                index = self._calendar_view.indexAt(event.position().toPoint())
                if index.isValid():
                    hovered = self._date_for_index(index.row(), index.column())
            elif event.type() != QEvent.Type.Leave:
                return super().eventFilter(watched, event)

            if hovered != self._hovered_date:
                previous = self._hovered_date
                self._hovered_date = hovered
                if previous.isValid():
                    self.updateCell(previous)
                if hovered.isValid():
                    self.updateCell(hovered)
        return super().eventFilter(watched, event)

    def apply_theme(self) -> None:
        dark = isDarkTheme()
        self._surface_color = QColor(
            COMPONENT_COLORS["card"]["bg_dark" if dark else "bg_light"]
        )
        self._text_color = QColor(get_text_color(dark, "primary"))
        self._secondary_color = QColor(get_text_color(dark, "secondary"))
        self._tertiary_color = QColor(get_text_color(dark, "tertiary"))
        self._selection_color = QColor(COLORS["lavender_grey"])
        self._selection_text_color = QColor(COLORS["text_white"])
        self._today_color = QColor(COLORS["lavender_grey"])
        self._hover_color = QColor(COLORS["lavender_grey"])
        self._hover_color.setAlphaF(0.20 if dark else 0.12)

        self.setStyleSheet(get_calendar_popup_style(dark, self.objectName()))
        weekday_format = QTextCharFormat()
        weekday_format.setForeground(QBrush(self._secondary_color))
        weekday_font = self.font()
        weekday_font.setPixelSize(12)
        weekday_font.setWeight(QFont.Weight.Medium)
        weekday_format.setFont(weekday_font)
        for day in range(1, 8):
            self.setWeekdayTextFormat(Qt.DayOfWeek(day), weekday_format)

        for object_name, icon, accessible_name in (
            ("qt_calendar_prevmonth", FluentIcon.LEFT_ARROW, "Previous month"),
            ("qt_calendar_nextmonth", FluentIcon.RIGHT_ARROW, "Next month"),
        ):
            button = self.findChild(QToolButton, object_name)
            if button is not None:
                button.setText("")
                button.setIcon(icon.icon())
                button.setIconSize(QSize(SIZES["icon_xs"], SIZES["icon_xs"]))
                button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
                button.setAccessibleName(accessible_name)
                button.setToolTip(accessible_name)
        self.updateCells()

    def paintCell(self, painter: QPainter, rect, date: QDate):  # noqa: N802
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(rect, self._surface_color)

        enabled = self.minimumDate() <= date <= self.maximumDate()
        selected = date == self.selectedDate()
        today = date == QDate.currentDate()
        current_month = date.month() == self.monthShown() and date.year() == self.yearShown()
        cell = rect.adjusted(SPACING["xs"], SPACING["xs"], -SPACING["xs"], -SPACING["xs"])

        if selected:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(self._selection_color)
            painter.drawRoundedRect(cell, RADII["sm"], RADII["sm"])
            text_color = self._selection_text_color
        else:
            if enabled and date == self._hovered_date:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(self._hover_color)
                painter.drawRoundedRect(cell, RADII["sm"], RADII["sm"])
            if today:
                painter.setPen(QPen(self._today_color, 1))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(cell, RADII["sm"], RADII["sm"])
            text_color = self._text_color if current_month else self._tertiary_color
            if not enabled:
                text_color = QColor(self._tertiary_color)
                text_color.setAlphaF(0.62)

        font = painter.font()
        font.setPixelSize(13)
        font.setWeight(QFont.Weight.Medium if selected else QFont.Weight.Normal)
        painter.setFont(font)
        painter.setPen(text_color)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, str(date.day()))
        painter.restore()


def configure_earnings_datetime_edit(editor: QDateTimeEdit) -> None:
    """Apply the shared Earnings date-time field and popup without changing its value."""
    editor.setObjectName("earningsDateTimeInput")
    editor.setCalendarPopup(True)
    editor.setCalendarWidget(FluentCalendarWidget(editor))
    editor.setDisplayFormat("dd MMM yyyy, HH:mm")
    editor.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
    editor.setFixedHeight(SIZES["input_height"])
    editor.setAccessibleName("Date and time")
    apply_earnings_datetime_theme(editor)


def apply_earnings_datetime_theme(editor: QDateTimeEdit) -> None:
    dark = isDarkTheme()
    editor.setStyleSheet(get_form_input_style(dark, "QDateTimeEdit", calendar=True))
    calendar = editor.calendarWidget()
    if isinstance(calendar, FluentCalendarWidget):
        calendar.apply_theme()
