"""Interaction coverage for the proposed grouped and responsive workspaces."""
import os
from types import SimpleNamespace
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QThread, QCoreApplication, QEvent, QTimer
from PySide6.QtWidgets import QApplication, QWidget, QLineEdit, QBoxLayout
from Database.DatabaseManager import DatabaseManager
from Database.SettingsManager import SettingsManager
from GUI_Qt.i18n import I18nManager
from GUI_Qt.widgets.workspace import WorkspaceColumns, bind_text
from GUI_Qt.screens.BrandToolsScreen import BrandUrlFinderScreen
from GUI_Qt.screens.CastelliUrlGetterScreen import CastelliUrlGetterScreen
from GUI_Qt.screens.AbusUrlGetterScreen import AbusUrlGetterScreen
from GUI_Qt.screens.ActivityScreen import ActivityScreen
from GUI_Qt.screens.FullHistoryScreen import FullHistoryScreen
from GUI_Qt.screens.EarningsScreen import EarningsScreen
from Managers.OperationTracker import OperationTracker, OperationKind, OperationStatus
from Managers.EarningsManager import EarningsManager
from GUI_Qt.services.shutdown import ShutdownService


@pytest.fixture
def context():
    app = QApplication.instance() or QApplication([])
    main = QWidget()
    main.db = DatabaseManager(":memory:")
    main.settings = SettingsManager(main.db)
    main.i18n = I18nManager()
    main.driver = None
    main.operation_tracker = OperationTracker(main.db)
    main.earnings_manager = EarningsManager(main.db, main.settings)
    widgets = []
    yield app, main, widgets
    for widget in widgets:
        for timer in widget.findChildren(QTimer):
            timer.stop()
        widget.hide()
    app.processEvents()
    for widget in widgets:
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    main.db.close()
    main.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()


def test_columns_stack_without_losing_form_state(context):
    app, _main, widgets = context
    workspace = WorkspaceColumns()
    widgets.append(workspace)
    field = QLineEdit("saved input")
    workspace.main_layout.addWidget(field)
    workspace.side_layout.addWidget(QLineEdit("run controls"))
    workspace.resize(1200, 500)
    workspace.show()
    app.processEvents()
    assert workspace.columns.direction() == QBoxLayout.Direction.LeftToRight
    workspace.resize(700, 600)
    app.processEvents()
    assert workspace.columns.direction() == QBoxLayout.Direction.TopToBottom
    assert field.text() == "saved input"
    workspace.resize(1200, 500)
    app.processEvents()
    assert workspace.columns.direction() == QBoxLayout.Direction.LeftToRight
    assert field.text() == "saved input"


class _RunningWorker(QThread):
    def __init__(self):
        super().__init__()
        self.running = True
        self.stopped = False

    def isRunning(self):
        return self.running

    def request_stop(self):
        self.stopped = True

    def wait(self, _ms):
        self.running = False
        return True


def test_brand_tabs_guard_navigation_overlap_and_shutdown(context, monkeypatch):
    _app, main, widgets = context
    host = BrandUrlFinderScreen(main)
    main.brand_url_screen = host
    widgets.append(host)
    worker = _RunningWorker()
    calls = []
    def start(panel):
        calls.append(panel)
        panel._worker = worker
    monkeypatch.setattr(AbusUrlGetterScreen, "_on_start_stop", start)
    monkeypatch.setattr(CastelliUrlGetterScreen, "_on_start_stop", start)
    monkeypatch.setattr("GUI_Qt.screens.BrandToolsScreen.InfoBar.warning", lambda **_: None)
    host.panels[0]._on_start_stop()
    assert not host.tabs.tabBar().isEnabled()
    assert not host.request_navigation_away()
    assert not host.select_mode(1)
    host.panels[1]._on_start_stop()
    assert calls == [host.panels[0]]
    assert list(ShutdownService(main).iter_workers()) == [(host, worker)]
    assert host.shutdown(wait_ms=1)
    assert worker.stopped
    worker.finished.emit()
    assert host.tabs.tabBar().isEnabled()
    assert host.select_mode(2)


def test_activity_filters_keep_the_selected_job_details(context):
    _app, main, widgets = context
    running = main.operation_tracker.create(OperationKind.ORBEA, "orbea")
    main.operation_tracker.start(running.id, stage="scan")
    failed = main.operation_tracker.create(OperationKind.URL_SCANNER, "abus_url_getter")
    main.operation_tracker.finish(failed.id, OperationStatus.FAILED, error_summary="Missing links")
    done = main.operation_tracker.create(OperationKind.IMAGE_TOOL, "basso_images")
    main.operation_tracker.finish(done.id, OperationStatus.SUCCEEDED)
    screen = ActivityScreen(main)
    widgets.append(screen)
    screen._filter_buttons["attention"].click()
    assert [record.id for record in screen._records] == [failed.id]
    screen.table.selectRow(0)
    assert "Missing links" in screen._job_details.text()
    assert screen.open_workflow_button.isEnabled()
    screen._filter_buttons["running"].click()
    assert [record.id for record in screen._records] == [running.id]
    screen._filter_buttons["done"].click()
    assert [record.id for record in screen._records] == [done.id]


def test_sorted_upload_rows_show_their_own_details(context):
    _app, main, widgets = context
    main.db.conn.executemany(
        """INSERT INTO processing_history
        (brand, product_code, status, duration_seconds, url_or_code, error_message,
         failed_stage, processed_at, images_uploaded, features_uploaded)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [("Orbea", "ZZ-1", "failed", 30, "https://example.test/1", "Photo failure",
          "photos", "2026-10-08T12:00:00", 2, 1),
         ("KROSS", "AA-2", "success", 10, "https://example.test/2", "",
          "", "2026-10-08T11:00:00", 4, 3)],
    )
    main.db.conn.commit()
    screen = FullHistoryScreen(main)
    widgets.append(screen)
    screen.table.sortItems(3)
    screen.table.selectRow(0)
    assert "AA-2" in screen._upload_details.text()
    assert "Photo failure" not in screen._upload_details.text()
    screen.table.selectRow(1)
    assert "ZZ-1" in screen._upload_details.text()
    assert "Photo failure" in screen._upload_details.text()
    assert screen._upload_metrics[0].value.text() == "2"
    assert screen._upload_metrics[1].value.text() == "50%"


def test_recent_earnings_and_shared_metrics_survive_record_filters(context):
    _app, main, widgets = context
    main.earnings_manager.create_entry("OLD-1", "bicycle", source="regular_upload")
    main.earnings_manager.create_entry("NEW-2", "bicycle")
    screen = EarningsScreen(main)
    widgets.append(screen)
    screen.filter_source.setCurrentIndex(1)
    assert len(screen._entries) == 1
    assert screen.recent_table.rowCount() == 2
    for section in screen.section_keys:
        screen._switch_section(section)
        assert all(not widget.isHidden() for widget in screen.metric_cards)
    main.i18n.set_language("lt")
    assert screen.recent_table.horizontalHeaderItem(0).text() == "Data ir laikas"


def test_language_binding_disconnects_when_its_widget_is_destroyed(context):
    app, main, _widgets = context
    label = bind_text(QLineEdit(), main, "layout.run")
    label.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    main.i18n.set_language("lt")
    app.processEvents()


@pytest.mark.parametrize("supplier", ("orbea", "kross"))
def test_supplier_columns_stack_inside_a_narrow_scroll_view(context, supplier):
    app, main, widgets = context
    from GUI_Qt.screens.OrbeaScreen import OrbeaScreen
    from GUI_Qt.screens.KrossScreen import KrossScreen
    screen = (OrbeaScreen if supplier == "orbea" else KrossScreen)(main)
    widgets.append(screen)
    screen.setParent(None)
    screen.resize(800, 920)
    screen.show()
    for _ in range(6):
        app.processEvents()
    assert screen._workspace.columns.direction() == QBoxLayout.Direction.TopToBottom
    assert screen._workspace.width() <= screen._scroll.viewport().width()
