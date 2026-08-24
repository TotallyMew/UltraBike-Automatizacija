from __future__ import annotations

import os
from datetime import datetime, timezone


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QByteArray, QBuffer, QDate, QIODevice
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QAbstractSpinBox, QApplication, QLayout, QWidget
from qfluentwidgets import CheckBox, DateEdit, DoubleSpinBox, PrimaryPushButton, PushButton

from Database.DatabaseManager import DatabaseManager
from Database.SettingsManager import SettingsManager
from GUI_Qt.screens.EarningsScreen import (
    EarningsScreen, GoalAdjustmentDialog, GoalDialog, goal_level_state,
    goal_progress_state,
)
from Managers.EarningsManager import EarningsManager


class _I18n:
    @staticmethod
    def tr(key, **values):
        templates = {
            "earnings.goal.progress": "{current} of {target}",
            "earnings.goal.reached": "Goal reached",
            "earnings.goal.above": "{amount} above goal",
            "earnings.goal.remaining": "{amount} remaining",
            "earnings.goal.quest.level": "Level {level} of {levels}",
            "earnings.goal.quest.next": "{amount} to Level {level}",
            "earnings.goal.quest.remaining": "{amount} to goal",
        }
        return templates.get(key, key).format(**values)


class _Main(QWidget):
    def __init__(self):
        super().__init__()
        self.db = DatabaseManager(":memory:")
        self.settings = SettingsManager(self.db)
        self.earnings_manager = EarningsManager(
            self.db,
            self.settings,
            local_tz=timezone.utc,
        )
        self.i18n = _I18n()


def _at(hour: int) -> datetime:
    return datetime(2026, 8, 17, hour, tzinfo=timezone.utc)


def _image_bytes() -> bytes:
    image = QImage(40, 30, QImage.Format.Format_ARGB32)
    image.fill(QColor("#E36588"))
    encoded = QByteArray()
    buffer = QBuffer(encoded)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    assert image.save(buffer, "PNG")
    buffer.close()
    return bytes(encoded)


def test_goal_progress_state_keeps_incomplete_progress_muted_and_uncapped_textual_value():
    state = goal_progress_state(4_900, 50_000)

    assert state == {
        "percent": 9.8,
        "visual_percent": 9.8,
        "reached": False,
        "remaining_cents": 45_100,
        "above_cents": 0,
    }


def test_goal_progress_state_marks_exact_completion():
    state = goal_progress_state(50_000, 50_000)

    assert state["percent"] == 100.0
    assert state["visual_percent"] == 100.0
    assert state["reached"] is True
    assert state["remaining_cents"] == 0
    assert state["above_cents"] == 0


def test_goal_progress_state_caps_only_the_visual_bar_when_over_target():
    state = goal_progress_state(54_000, 50_000)

    assert state["percent"] == 108.0
    assert state["visual_percent"] == 100.0
    assert state["reached"] is True
    assert state["above_cents"] == 4_000


def test_goal_progress_state_handles_invalid_target_without_dividing_by_zero():
    state = goal_progress_state(100, 0)

    assert state["percent"] == 0.0
    assert state["visual_percent"] == 0.0
    assert state["reached"] is False


def test_goal_level_state_tracks_the_next_ten_percent_milestone():
    state = goal_level_state(28_575, 50_000)

    assert state == {
        "level": 5,
        "levels": 10,
        "next_level": 6,
        "next_level_cents": 1_425,
        "complete": False,
    }


def test_goal_level_state_reaches_max_level_at_the_target():
    state = goal_level_state(50_000, 50_000)

    assert state == {
        "level": 10,
        "levels": 10,
        "next_level": 10,
        "next_level_cents": 0,
        "complete": True,
    }


def test_completed_goal_remains_visible_with_success_summary():
    app = QApplication.instance() or QApplication([])
    main = _Main()
    main.earnings_manager.create_goal(100, now=_at(8))
    main.earnings_manager.create_entry("BIKE-1", "bicycle", now=_at(9))

    screen = EarningsScreen(main)
    app.processEvents()

    assert screen.goal_title.text() == "€1.00 of €1.00"
    assert screen.goal_percentage.text() == "100%"
    assert screen.goal_remaining.text() == "Goal reached"
    assert screen.goal_progress.value() == 1000
    assert screen.goal_forecast_block.isHidden()
    assert not screen.goal_create.isHidden()
    assert screen.goal_edit.isHidden()
    assert screen.goal_adjust.isHidden()
    assert screen.goal_quest_level.text() == "Level 10 of 10"
    assert screen.goal_quest_progress.value() == 1000
    assert not screen.goal_quest_create.isHidden()
    assert screen.goal_quest_adjust.isHidden()

    screen.deleteLater()
    main.db.close()
    main.deleteLater()
    app.processEvents()


def test_goal_only_adjustment_is_visible_without_changing_earnings_metrics():
    app = QApplication.instance() or QApplication([])
    main = _Main()
    goal_id = main.earnings_manager.create_goal(5_000, now=_at(8))
    main.earnings_manager.add_goal_adjustment(goal_id, 1_250, "opening balance", now=_at(9))

    screen = EarningsScreen(main)
    app.processEvents()

    assert screen.goal_title.text() == "€12.50 of €50.00"
    assert screen.goal_adjustment_summary.text() == "earnings.goal.adjust.summary"
    assert screen.goal_adjustment_note.text() == "earnings.goal.adjust.note.latest"
    assert not screen.goal_adjustment_block.isHidden()
    assert (
        screen.goal_panel.layout().sizeConstraint()
        == QLayout.SizeConstraint.SetMinimumSize
    )
    assert not screen.goal_adjust.isHidden()
    assert screen.goal_quest_level.text() == "Level 2 of 10"
    assert screen.goal_quest_next.text() == "€2.50 to Level 3"
    assert screen.goal_quest_remaining.text() == "€37.50 to goal"
    assert screen.goal_quest_progress.value() == 250
    assert not screen.goal_quest_adjust.isHidden()
    assert main.earnings_manager.summary()["all_cents"] == 0
    assert main.earnings_manager.summary()["all_count"] == 0

    screen.deleteLater()
    main.db.close()
    main.deleteLater()
    app.processEvents()


def test_custom_goal_title_and_picture_are_visible_in_both_goal_views():
    app = QApplication.instance() or QApplication([])
    main = _Main()
    main.earnings_manager.create_goal(
        5_000,
        title="Dream bike fund",
        image_data=_image_bytes(),
        now=_at(8),
    )

    screen = EarningsScreen(main)
    app.processEvents()

    assert screen.goal_custom_title.text() == "Dream bike fund"
    assert screen.goal_quest_title.text() == "Dream bike fund"
    assert not screen.goal_image.isHidden()
    assert not screen.goal_image.pixmap().isNull()
    assert not screen.goal_quest_image.isHidden()
    assert not screen.goal_quest_image.pixmap().isNull()

    screen.deleteLater()
    main.db.close()
    main.deleteLater()
    app.processEvents()


def test_over_target_goal_reports_actual_percentage_and_above_amount():
    app = QApplication.instance() or QApplication([])
    main = _Main()
    main.earnings_manager.create_goal(50, now=_at(8))
    main.earnings_manager.create_entry("BIKE-1", "bicycle", now=_at(9))

    screen = EarningsScreen(main)
    app.processEvents()

    assert screen.goal_percentage.text() == "200%"
    assert screen.goal_remaining.text() == "€0.50 above goal"
    assert screen.goal_progress.value() == 1000

    screen.deleteLater()
    main.db.close()
    main.deleteLater()
    app.processEvents()


def test_goal_dialog_uses_fluent_vertical_form_and_preserves_existing_values():
    app = QApplication.instance() or QApplication([])
    dialog = GoalDialog(
        {
            "target_cents": 50_000,
            "deadline_date": "2026-08-20",
            "title": "Dream bike fund",
            "image_data": _image_bytes(),
        }
    )
    dialog.show()
    app.processEvents()

    margins = dialog.layout().contentsMargins()
    assert dialog.windowTitle() == "Edit money goal"
    assert dialog.width() == 440
    assert (margins.left(), margins.top(), margins.right(), margins.bottom()) == (24, 24, 24, 24)
    assert isinstance(dialog.amount, DoubleSpinBox)
    assert isinstance(dialog.deadline_enabled, CheckBox)
    assert isinstance(dialog.deadline, DateEdit)
    assert isinstance(dialog.cancel_button, PushButton)
    assert isinstance(dialog.save_button, PrimaryPushButton)
    assert dialog.amount.height() == 40
    assert dialog.deadline.height() == 40
    assert dialog.amount.buttonSymbols() == QAbstractSpinBox.ButtonSymbols.NoButtons
    assert dialog.deadline.displayFormat() == "dd MMM yyyy"
    assert dialog.deadline_enabled.isChecked()
    assert dialog.deadline.isEnabled()
    assert dialog.title.text() == "Dream bike fund"
    assert not dialog.image_preview.pixmap().isNull()
    assert dialog.save_button.isDefault()
    assert not dialog.cancel_button.autoDefault()
    assert dialog.values() == (
        50_000,
        QDate(2026, 8, 20).toPython(),
        "Dream bike fund",
        _image_bytes(),
    )

    dialog.close()
    dialog.deleteLater()
    app.processEvents()


def test_goal_dialog_deadline_toggle_preserves_enabled_state_and_value_contract():
    app = QApplication.instance() or QApplication([])
    dialog = GoalDialog()

    assert not dialog.deadline_enabled.isChecked()
    assert not dialog.deadline.isEnabled()
    assert dialog.values()[1] is None

    dialog.amount.setValue(125.75)
    dialog.deadline_enabled.setChecked(True)
    dialog.deadline.setDate(QDate(2026, 8, 24))

    assert dialog.deadline.isEnabled()
    dialog.title.setText("  New   workshop bike  ")
    assert dialog.values() == (
        12_575,
        QDate(2026, 8, 24).toPython(),
        "New workshop bike",
        None,
    )

    dialog.close()
    dialog.deleteLater()
    app.processEvents()


def test_goal_adjustment_dialog_returns_money_and_normalized_optional_note():
    app = QApplication.instance() or QApplication([])
    dialog = GoalAdjustmentDialog()

    dialog.amount.setValue(125.75)
    dialog.note.setText("  opening   balance  ")

    assert isinstance(dialog.cancel_button, PushButton)
    assert isinstance(dialog.save_button, PrimaryPushButton)
    assert dialog.values() == (
        GoalAdjustmentDialog.ADD_AMOUNT,
        12_575,
        "opening balance",
    )

    dialog.note.clear()
    assert dialog.values() == (GoalAdjustmentDialog.ADD_AMOUNT, 12_575, None)

    dialog.close()
    dialog.deleteLater()
    app.processEvents()


def test_goal_adjustment_dialog_can_switch_between_delta_and_current_total():
    app = QApplication.instance() or QApplication([])
    dialog = GoalAdjustmentDialog(current_progress_cents=28_575)

    dialog.amount.setValue(14.25)
    dialog.mode_selector.widget(GoalAdjustmentDialog.SET_TOTAL).click()

    assert dialog.values() == (GoalAdjustmentDialog.SET_TOTAL, 30_000, None)
    assert dialog.amount_label.text() == "New current total"
    assert dialog.amount_hint.text() == (
        "Current progress: €285.75. The app will add €14.25."
    )

    dialog.mode_selector.widget(GoalAdjustmentDialog.ADD_AMOUNT).click()
    assert dialog.values() == (GoalAdjustmentDialog.ADD_AMOUNT, 1_425, None)
    assert dialog.amount_label.text() == "Amount to add"

    dialog.close()
    dialog.deleteLater()
    app.processEvents()
