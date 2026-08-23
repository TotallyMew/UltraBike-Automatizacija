from __future__ import annotations

import os
from datetime import timezone

import pytest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QAbstractAnimation, Qt
from PySide6.QtGui import QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget
from qfluentwidgets import Theme, isDarkTheme, setTheme

from Database.DatabaseManager import DatabaseManager
from Database.SettingsManager import SettingsManager
from GUI_Qt.earnings.widgets import (
    ActivityHeatmap,
    ActivityLegend,
    BatchProgressTicks,
    GoalMilestoneBar,
    PerformanceTargetWidget,
)
from GUI_Qt.i18n import translate
from GUI_Qt.screens.EarningsScreen import EarningsScreen
from GUI_Qt.styles.theme_config import get_surface_color, get_text_color
from Managers.EarningsManager import EarningsManager


class _I18n:
    @staticmethod
    def tr(key, **values):
        return translate("en", key, **values)


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


def test_batch_counter_pulses_and_resets_after_ten(earnings_context):
    app, *_rest = earnings_context
    counter = BatchProgressTicks()
    counter.show()

    for _ in range(10):
        counter.advance()

    assert counter.count == 10
    assert counter._pulse_animation.state() == QAbstractAnimation.State.Running
    assert counter.accessibleName() == "Batch progress: 10 of 10 SKUs"

    QTest.qWait(340)
    app.processEvents()
    assert counter.count == 0

    counter.deleteLater()
    app.processEvents()


def test_goal_bar_exposes_notches_and_animates_a_crossed_milestone(earnings_context):
    app, *_rest = earnings_context
    progress = GoalMilestoneBar()
    progress.set_progress(9_900, 50_000)

    assert progress.milestones == (10_000, 25_000, 50_000)
    assert progress.value() == 198

    progress.set_progress(10_100, 50_000)
    assert progress._fill_animation.state() == QAbstractAnimation.State.Running
    assert progress._pulse_animation.state() == QAbstractAnimation.State.Running
    assert "€100.00" in progress.toolTip()

    progress.deleteLater()
    app.processEvents()


def test_heatmap_keeps_a_rolling_thirty_day_product_grid(earnings_context):
    app, *_rest = earnings_context
    heatmap = ActivityHeatmap()
    heatmap.set_data(
        [{"label": f"Day {day}", "count": day % 5, "cents": day * 100} for day in range(35)]
    )

    assert len(heatmap.data) == 30
    assert heatmap.data[0]["label"] == "Day 5"
    assert heatmap.data[-1]["label"] == "Day 34"
    assert heatmap.accessibleDescription() == "60 SKUs logged over 30 days"
    assert heatmap.maximumWidth() > 10_000
    heatmap.resize(600, 62)
    heatmap.show()
    app.processEvents()
    assert len(heatmap._cell_rects) == 30
    assert len(heatmap._axis_label_rects) == 2
    assert not heatmap._axis_label_rects[0].intersects(heatmap._axis_label_rects[1])

    legend = ActivityLegend()
    assert legend.accessibleName() == "Fewer SKUs — More SKUs"

    heatmap.deleteLater()
    legend.deleteLater()
    app.processEvents()


def test_performance_target_separates_value_percentage_and_progress(earnings_context):
    app, *_rest = earnings_context
    target = PerformanceTargetWidget("Weekly earnings")
    target.set_progress("€117.75", "€250.00", 117.75 / 250.0)

    assert target.current.text() == "€117.75"
    assert target.target.text() == "/ €250.00"
    assert target.percentage.text() == "47%"
    assert target.progress.value() == 471
    assert not target.progress.isTextVisible()
    assert "47 percent" in target.accessibleName()

    target.deleteLater()
    app.processEvents()


def test_manual_submit_updates_live_session_batch_badge_and_heatmap(earnings_context):
    app, db, settings, manager = earnings_context
    manager.start_session("stopwatch")
    main = _Main(db, settings, manager)
    screen = EarningsScreen(main)
    screen.show()
    app.processEvents()

    screen.sku_input.setText("LIVE-SESSION-SKU")
    screen._add_entry()
    app.processEvents()

    assert screen.session_earnings.text() == "Session earnings: €1.00"
    assert screen.session_products.text() == "SKUs logged this session: 1"
    assert screen.batch_counter.count == 1
    assert screen.earning_burst.text() == "+€1.00"
    assert not screen.earning_burst.isHidden()
    assert sum(int(item["count"]) for item in screen.activity_heatmap.data) == 1
    assert screen.activity_summary_widgets[0][0].text() == "1"
    assert screen.activity_summary_widgets[1][0].text() == "1"
    assert screen.activity_summary_widgets[2][0].text() == "1"

    screen.close()
    screen.deleteLater()
    main.deleteLater()
    app.processEvents()


def test_dark_theme_keeps_earnings_metric_text_readable_and_transparent(
    earnings_context,
):
    app, db, settings, manager = earnings_context
    original_theme = Theme.DARK if isDarkTheme() else Theme.LIGHT
    main = _Main(db, settings, manager)
    screen = None

    try:
        setTheme(Theme.LIGHT)
        screen = EarningsScreen(main)
        setTheme(Theme.DARK)
        screen._apply_theme()
        app.processEvents()

        expected = get_text_color(True, "primary").lower()
        metric_value = screen.metric_today.value
        assert (
            metric_value.palette().color(QPalette.ColorRole.WindowText).name().lower()
            == expected
        )
        assert not metric_value.testAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        assert not screen.metric_today.title.testAttribute(
            Qt.WidgetAttribute.WA_StyledBackground
        )
        assert (
            screen.activity_summary_cards[0].background_color.name().lower()
            == get_surface_color(True, "alternate").lower()
        )
    finally:
        if screen is not None:
            screen._tick_timer.stop()
            screen.close()
            screen.deleteLater()
        main.close()
        main.deleteLater()
        setTheme(original_theme)
        app.processEvents()
