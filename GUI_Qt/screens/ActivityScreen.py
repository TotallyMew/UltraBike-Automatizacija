"""Persistent overview of long-running application work."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)
from qfluentwidgets import (
    BodyLabel,
    FluentIcon,
    InfoBar,
    InfoBarPosition,
    PushButton,
    TitleLabel,
)

from GUI_Qt.styles.screen_theme import PAGE_MARGINS, PAGE_SPACING
from GUI_Qt.widgets.ResponsiveWidget import ResponsiveWidget
from Managers.OperationTracker import OperationStatus, TERMINAL_STATUSES


class ActivityScreen(ResponsiveWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main = main_window
        self.tracker = main_window.operation_tracker
        self._records = []
        self._build_ui()
        self.tracker.operationChanged.connect(lambda _operation_id: self.refresh())
        self.main.i18n.languageChanged.connect(lambda _language: self.retranslate_ui())
        self.retranslate_ui()
        self.refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*PAGE_MARGINS)
        layout.setSpacing(PAGE_SPACING)

        header = QHBoxLayout()
        self.title_label = TitleLabel("")
        self.summary_label = BodyLabel("")
        self.refresh_button = PushButton(FluentIcon.SYNC, "")
        self.refresh_button.clicked.connect(self.refresh)
        header.addWidget(self.title_label)
        header.addStretch()
        header.addWidget(self.summary_label)
        header.addWidget(self.refresh_button)
        layout.addLayout(header)

        self.table = QTableWidget(0, 8)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self._update_actions)
        layout.addWidget(self.table, 1)

        actions = QHBoxLayout()
        self.cancel_button = PushButton(FluentIcon.CANCEL, "")
        self.open_workflow_button = PushButton(FluentIcon.APPLICATION, "")
        self.open_output_button = PushButton(FluentIcon.FOLDER, "")
        self.copy_button = PushButton(FluentIcon.COPY, "")
        self.cancel_button.clicked.connect(self._cancel)
        self.open_workflow_button.clicked.connect(self._open_workflow)
        self.open_output_button.clicked.connect(self._open_output)
        self.copy_button.clicked.connect(self._copy_diagnostics)
        actions.addStretch()
        for button in (
            self.cancel_button,
            self.open_workflow_button,
            self.open_output_button,
            self.copy_button,
        ):
            actions.addWidget(button)
        layout.addLayout(actions)
        self._update_actions()

    def _selected(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self._records):
            return None
        return self._records[row]

    def refresh(self) -> None:
        selected_id = self._selected().id if self._selected() else ""
        self._records = self.tracker.list(limit=500)
        self.table.setRowCount(len(self._records))
        selected_row = -1
        for row, record in enumerate(self._records):
            progress = (
                f"{record.current}/{record.total} ({record.progress_percent}%)"
                if record.total
                else (str(record.current) if record.current else "—")
            )
            values = (
                self.main.i18n.tr(f"activity.kind.{record.kind.value}"),
                self.main.i18n.tr(f"activity.status.{record.status.value}"),
                progress,
                record.stage,
                record.message or record.error_summary,
                record.source_route,
                record.updated_at.replace("T", " ")[:19],
                record.output_path,
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value or ""))
                item.setToolTip(str(value or ""))
                self.table.setItem(row, column, item)
            if record.id == selected_id:
                selected_row = row
        if selected_row >= 0:
            self.table.selectRow(selected_row)
        self.summary_label.setText(
            self.main.i18n.tr(
                "activity.summary",
                running=self.tracker.running_count(),
                total=len(self._records),
            )
        )
        self._update_actions()

    def _update_actions(self) -> None:
        record = self._selected()
        self.cancel_button.setEnabled(
            bool(record and record.status not in TERMINAL_STATUSES)
        )
        self.open_workflow_button.setEnabled(bool(record and record.source_route))
        self.open_output_button.setEnabled(
            bool(record and record.output_path and Path(record.output_path).exists())
        )
        self.copy_button.setEnabled(record is not None)

    def _cancel(self) -> None:
        record = self._selected()
        if record:
            self.tracker.request_cancel(record.id)

    def _open_workflow(self) -> None:
        record = self._selected()
        if record:
            self.main.open_route(record.source_route)

    def _open_output(self) -> None:
        record = self._selected()
        if not record or not record.output_path:
            return
        target = Path(record.output_path)
        if target.is_file():
            target = target.parent
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target.resolve())))

    def _copy_diagnostics(self) -> None:
        record = self._selected()
        if not record:
            return
        QGuiApplication.clipboard().setText(self.tracker.diagnostics(record.id))
        InfoBar.success(
            title=self.main.i18n.tr("common.success"),
            content=self.main.i18n.tr("activity.copied"),
            position=InfoBarPosition.TOP,
            duration=2000,
            parent=self,
        )

    def retranslate_ui(self) -> None:
        tr = self.main.i18n.tr
        self.title_label.setText(tr("activity.title"))
        self.refresh_button.setText(tr("activity.refresh"))
        self.cancel_button.setText(tr("activity.cancel"))
        self.open_workflow_button.setText(tr("activity.open_workflow"))
        self.open_output_button.setText(tr("activity.open_output"))
        self.copy_button.setText(tr("activity.copy_diagnostics"))
        self.table.setHorizontalHeaderLabels(
            [
                tr("activity.column.kind"), tr("activity.column.status"),
                tr("activity.column.progress"), tr("activity.column.stage"),
                tr("activity.column.message"), tr("activity.column.source"),
                tr("activity.column.updated"), tr("activity.column.output"),
            ]
        )
        self.refresh()
