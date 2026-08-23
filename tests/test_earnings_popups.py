from __future__ import annotations

import os
from datetime import timezone

import pytest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QItemSelectionModel, Qt
from PySide6.QtWidgets import QAbstractItemView, QApplication, QCheckBox, QWidget
from qfluentwidgets import DoubleSpinBox, PrimaryPushButton, RoundMenu, SpinBox

from Database.DatabaseManager import DatabaseManager
from Database.SettingsManager import SettingsManager
from GUI_Qt.screens.EarningsScreen import (
    BrandManagerDialog,
    BrandNameDialog,
    BulkEarningEditDialog,
    EarningsScreen,
    EarningsSettingsDialog,
)
from GUI_Qt.styles.theme_config import SIZES
from Managers.EarningsManager import EarningsManager


class _I18n:
    @staticmethod
    def tr(key, **_kwargs):
        return key


class _Main(QWidget):
    def __init__(self, db, settings, manager):
        super().__init__()
        self.db = db
        self.settings = settings
        self.earnings_manager = manager
        self.i18n = _I18n()


@pytest.fixture
def earnings_context():
    app = QApplication.instance() or QApplication([])
    db = DatabaseManager(":memory:")
    settings = SettingsManager(db)
    manager = EarningsManager(db, settings, local_tz=timezone.utc)
    yield app, db, settings, manager
    db.close()


def test_settings_dialog_groups_fluent_controls_and_preserves_save_contract(earnings_context):
    app, _db, _settings, manager = earnings_context
    dialog = EarningsSettingsDialog(manager)
    dialog.show()
    app.processEvents()

    sections = dialog.findChildren(QWidget, "earningsDialogSection")
    assert dialog.width() == 680
    assert dialog.height() <= 640
    assert len(sections) == 4
    spin_controls = [
        control
        for control in dialog._settings_controls
        if isinstance(control, (DoubleSpinBox, SpinBox))
    ]
    assert len(spin_controls) == 9
    assert all(control.height() == SIZES["input_height"] for control in spin_controls)
    assert isinstance(dialog.celebration_animations, QCheckBox)
    assert dialog.celebration_animations.isChecked()
    assert not dialog.celebration_sound.isChecked()
    assert dialog.sound_volume.value() == 45
    assert not dialog.sound_volume.isEnabled()
    assert isinstance(dialog.save_button, PrimaryPushButton)
    assert dialog.save_button.isDefault()
    assert not dialog.cancel_button.autoDefault()

    dialog.rates["bicycle"].setValue(2.50)
    dialog.daily_money.setValue(12.00)
    dialog.weekly_money.setValue(60.00)
    dialog.daily_minutes.setValue(90)
    dialog.weekly_minutes.setValue(450)
    dialog.workday_hours.setValue(7.5)
    dialog.workdays_per_week.setValue(5)
    dialog.celebration_animations.setChecked(False)
    dialog.celebration_sound.setChecked(True)
    dialog.sound_volume.setValue(70)
    dialog.save()

    assert manager.get_rate_cents("bicycle") == 250
    assert manager.performance_targets() == {
        "daily_earning_goal_cents": 1200,
        "weekly_earning_goal_cents": 6000,
        "daily_work_goal_minutes": 90,
        "weekly_work_goal_minutes": 450,
    }
    assert manager.work_schedule() == {
        "workday_minutes": 450,
        "workdays_per_week": 5,
    }
    assert manager.engagement_settings() == {
        "animations_enabled": False,
        "sound_enabled": True,
    }
    assert manager.celebration_sound_volume() == 70

    dialog.close()
    dialog.deleteLater()
    app.processEvents()


def test_brand_manager_exposes_actions_only_for_custom_brands(earnings_context):
    app, _db, _settings, manager = earnings_context
    custom_id = manager.add_brand("Custom test brand")
    dialog = BrandManagerDialog(manager)
    dialog.show()
    app.processEvents()

    assert dialog.table.rowCount() == 10
    assert not dialog.table.showGrid()
    assert dialog.table.verticalHeader().isHidden()
    assert dialog.count_label.text() == "10 brands"

    built_in_row = None
    custom_row = None
    for row in range(dialog.table.rowCount()):
        data = dialog.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        if data["is_builtin"] and built_in_row is None:
            built_in_row = row
        if data["id"] == custom_id:
            custom_row = row
    assert built_in_row is not None and custom_row is not None

    dialog.table.selectRow(built_in_row)
    app.processEvents()
    assert not dialog.rename_button.isEnabled()
    assert not dialog.archive_button.isEnabled()

    dialog.table.selectRow(custom_row)
    app.processEvents()
    assert dialog.rename_button.isEnabled()
    assert dialog.archive_button.isEnabled()

    dialog.new_name.setText("Another custom brand")
    app.processEvents()
    assert dialog.add_button.isEnabled()
    dialog._add()
    assert any(row["name"] == "Another custom brand" for row in manager.list_brands())

    dialog.close()
    dialog.deleteLater()
    app.processEvents()


def test_brand_rename_dialog_uses_validated_fluent_primary_action(earnings_context):
    app, *_rest = earnings_context
    dialog = BrandNameDialog("Original")
    assert dialog.width() == 420
    assert dialog.value() == "Original"
    assert dialog.save_button.isDefault()

    dialog.name_input.setText("   ")
    app.processEvents()
    assert not dialog.save_button.isEnabled()
    dialog.name_input.setText("Renamed")
    app.processEvents()
    assert dialog.save_button.isEnabled()
    assert dialog.value() == "Renamed"

    dialog.close()
    dialog.deleteLater()
    app.processEvents()


def test_bulk_edit_dialog_only_submits_enabled_fields(earnings_context):
    app, _db, _settings, manager = earnings_context
    brand_id = manager.add_brand("Bulk test")
    dialog = BulkEarningEditDialog(manager, 3)
    dialog.show()
    app.processEvents()

    assert dialog.width() == 560
    assert not dialog.save_button.isEnabled()
    assert not dialog.brand.isEnabled()
    assert not dialog.type.isEnabled()
    assert not dialog.when.isEnabled()

    dialog.brand_toggle.setChecked(True)
    dialog.brand.setCurrentIndex(dialog.brand.findData(brand_id))
    dialog.type_toggle.setChecked(True)
    dialog.type.setCurrentIndex(dialog.type.findData("frameset"))
    app.processEvents()

    assert dialog.save_button.isEnabled()
    assert dialog.values() == {
        "update_brand": True,
        "brand_id": brand_id,
        "product_type": "frameset",
        "earned_at": None,
    }

    dialog.close()
    dialog.deleteLater()
    app.processEvents()


def test_history_table_supports_multi_row_selection_and_bulk_action(earnings_context):
    app, db, settings, manager = earnings_context
    manager.create_entry("ONE", "bicycle")
    manager.create_entry("TWO", "bicycle")
    main = _Main(db, settings, manager)
    screen = EarningsScreen(main)
    screen._switch_section("history")
    app.processEvents()

    assert (
        screen.entries_table.selectionMode()
        == QAbstractItemView.SelectionMode.ExtendedSelection
    )
    selection = screen.entries_table.selectionModel()
    flags = (
        QItemSelectionModel.SelectionFlag.Select
        | QItemSelectionModel.SelectionFlag.Rows
    )
    selection.select(screen.entries_table.model().index(0, 0), flags)
    selection.select(screen.entries_table.model().index(1, 0), flags)
    app.processEvents()

    assert len(screen._selected_entries()) == 2
    assert not screen.bulk_edit_button.isHidden()
    assert screen.edit_entry_button.isHidden()
    assert screen.delete_entry_button.isHidden()

    screen.deleteLater()
    main.deleteLater()
    app.processEvents()


def test_export_uses_fluent_menu_and_keeps_both_export_routes(earnings_context):
    app, db, settings, manager = earnings_context
    main = _Main(db, settings, manager)
    screen = EarningsScreen(main)
    app.processEvents()

    assert isinstance(screen.export_menu, RoundMenu)
    assert screen.export_menu.accessibleName() == "Export options"
    assert screen.export_menu.minimumWidth() >= 248
    assert not screen.export_filtered_action.icon().isNull()
    assert not screen.export_all_action.icon().isNull()

    calls = []
    screen._export = lambda filtered: calls.append(filtered)
    screen.export_filtered_action.trigger()
    screen.export_all_action.trigger()
    assert calls == [True, False]

    screen.deleteLater()
    main.deleteLater()
    app.processEvents()
