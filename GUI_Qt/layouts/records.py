"""Activity and upload history keep tables beside selected-record details."""
from datetime import datetime
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QHBoxLayout, QGridLayout, QWidget
from qfluentwidgets import BodyLabel, PushButton, isDarkTheme, qconfig
from GUI_Qt.earnings.widgets import MetricCard
from GUI_Qt.widgets.workspace import WorkspaceColumns, card, heading, bind_text, move_widget, clear_layout, connect_signal
from Managers.OperationTracker import OperationStatus, TERMINAL_STATUSES


def arrange_activity(screen):
    root = screen.layout()
    while root.count() > 1:
        root.takeAt(1)
    filters = QHBoxLayout()
    screen._activity_filter = "all"
    screen._filter_buttons = {}
    for value, key in (("all", "layout.all"), ("running", "layout.running"),
                       ("attention", "layout.attention"), ("done", "layout.done")):
        button = bind_text(PushButton(), screen.main, key)
        button.setCheckable(True)
        button.setChecked(value == "all")
        def change(_checked=False, value=value):
            screen._activity_filter = value
            for item, control in screen._filter_buttons.items():
                control.setChecked(item == value)
            screen.refresh()
        button.clicked.connect(change)
        screen._filter_buttons[value] = button
        filters.addWidget(button)
    filters.addStretch()
    root.addLayout(filters)
    workspace = WorkspaceColumns()
    screen._workspace = workspace
    root.addWidget(workspace, 1)
    table_card, table_box = card()
    table_box.addWidget(screen.table)
    screen.table.setMinimumHeight(400)
    screen.table.setColumnHidden(5, True)
    screen.table.setColumnHidden(7, True)
    for column, width in ((0, 160), (1, 100), (2, 110), (3, 130)):
        screen.table.setColumnWidth(column, width)
    workspace.main_layout.addWidget(table_card)
    details, details_box = card()
    details_box.addWidget(heading(screen.main, "layout.selected_job"))
    screen._job_details = BodyLabel()
    screen._job_details.setWordWrap(True)
    details_box.addWidget(screen._job_details)
    for control in (screen.open_workflow_button, screen.open_output_button,
                    screen.copy_button, screen.cancel_button):
        move_widget(control, details_box)
    workspace.side_layout.addWidget(details)
    workspace.side_layout.addStretch()
    def filter_records(records):
        status = screen._activity_filter
        if status == "all":
            return records
        if status == "running":
            return [r for r in records if r.status not in TERMINAL_STATUSES]
        if status == "attention":
            return [r for r in records if r.status in (
                OperationStatus.PARTIAL, OperationStatus.FAILED, OperationStatus.INTERRUPTED)]
        return [r for r in records if r.status in (
            OperationStatus.SUCCEEDED, OperationStatus.CANCELLED)]
    screen._filter_records = filter_records
    def update_details():
        record = screen._selected()
        tr = screen.main.i18n.tr
        if not record:
            screen._job_details.setText(tr("layout.select_job"))
            return
        parts = [tr("activity.kind." + record.kind.value),
                 tr("activity.status." + record.status.value)]
        for key, value in (("stage", record.stage), ("message", record.message),
                ("output", record.output_path)):
            if value:
                parts.append(tr("activity.column." + key) + ": " + str(value))
        if record.error_summary:
            parts.append(record.error_summary)
        screen._job_details.setText("\n\n".join(parts))
    screen._update_job_details = update_details
    update_details()


def arrange_history(screen):
    root = screen.content_widget.layout()
    root.removeWidget(screen.table)
    metrics = QGridLayout()
    metrics.setSpacing(16)
    screen._upload_metrics = [MetricCard("") for _ in range(4)]
    for index, widget in enumerate(screen._upload_metrics):
        metrics.addWidget(widget, 0, index)
        metrics.setColumnStretch(index, 1)
    root.insertLayout(1, metrics)
    from GUI_Qt.styles.theme_config import get_surface_color, get_subtle_border
    def metric_theme(*_args):
        dark = isDarkTheme()
        for widget in screen._upload_metrics:
            widget.setStyleSheet(f"#earningsMetric {{ background: {get_surface_color(dark, 'surface')}; "
                f"border: 1px solid {get_subtle_border(dark)}; border-radius: 8px; }}")
    metric_theme()
    connect_signal(qconfig.themeChangedFinished, screen, metric_theme)
    box = screen.filter_card.layout()
    clear_layout(box)
    fields = QGridLayout()
    fields.setHorizontalSpacing(16)
    fields.setVerticalSpacing(8)
    fields.addWidget(screen.search_label, 0, 0)
    fields.addWidget(screen.search_input, 1, 0, 1, 4)
    for column, (label, control) in enumerate((
        (screen.brand_label, screen.brand_filter), (screen.status_label, screen.status_filter),
        (screen.type_label, screen.type_filter), (screen.date_label, screen.date_filter),
    )):
        control.setMinimumWidth(0)
        fields.addWidget(label, 2, column)
        fields.addWidget(control, 3, column)
        fields.setColumnStretch(column, 1)
    box.addLayout(fields)
    actions = QHBoxLayout()
    actions.addWidget(screen.results_label)
    actions.addStretch()
    for widget in (screen.refresh_btn, screen.clear_filters_btn, screen.export_btn):
        actions.addWidget(widget)
    box.addLayout(actions)
    workspace = WorkspaceColumns()
    screen._workspace = workspace
    root.addWidget(workspace, 1)
    table_card, table_box = card()
    table_box.addWidget(screen.table)
    screen.table.setMinimumHeight(400)
    workspace.main_layout.addWidget(table_card)
    for column in (0, 1, 6, 7, 8, 9, 10):
        screen.table.setColumnHidden(column, True)
    header = screen.table.horizontalHeader()
    header.moveSection(header.visualIndex(11), 0)
    details, detail_box = card()
    detail_box.addWidget(heading(screen.main, "layout.selected_upload"))
    screen._upload_details = BodyLabel()
    screen._upload_details.setWordWrap(True)
    screen._open_upload = bind_text(PushButton(), screen.main, "layout.open_pimbo")
    screen._open_upload.setEnabled(False)
    detail_box.addWidget(screen._upload_details)
    detail_box.addWidget(screen._open_upload)
    workspace.side_layout.addWidget(details)
    workspace.side_layout.addStretch()
    def selected_record():
        item = screen.table.item(screen.table.currentRow(), 3)
        return item.data(Qt.ItemDataRole.UserRole) if item else None
    def update_details():
        record = selected_record()
        screen._open_upload.setEnabled(bool(record and str(record["url_or_code"] or "").startswith(("http://", "https://"))))
        if not record:
            screen._upload_details.setText(screen.main.i18n.tr("layout.select_upload"))
            return
        parts = [str(record["brand"] or "") + " · " + str(record["product_code"] or "")]
        for column, field in ((4, "status"), (9, "failed_stage"), (8, "error_message"),
                              (7, "images_uploaded"), (6, "features_uploaded"), (10, "url_or_code")):
            value = record[field]
            if value not in (None, ""):
                parts.append(screen.table.horizontalHeaderItem(column).text() + ": " + str(value))
        screen._upload_details.setText("\n\n".join(parts))
    screen._update_upload_details = update_details
    screen.table.itemSelectionChanged.connect(update_details)
    def open_record():
        record = selected_record()
        if record and str(record["url_or_code"] or "").startswith(("http://", "https://")):
            QDesktopServices.openUrl(QUrl(record["url_or_code"]))
    screen._open_upload.clicked.connect(open_record)
    def update_metrics():
        rows = screen.all_history
        count = len(rows)
        success = sum(r["status"] in ("success", "saved_manually") for r in rows)
        today = sum(str(r["processed_at"] or "").startswith(datetime.now().strftime("%Y-%m-%d")) for r in rows)
        durations = [float(r["duration_seconds"]) for r in rows if r["duration_seconds"] is not None]
        values = (str(count), f"{success / count * 100:.0f}%" if count else "—",
                  str(today), f"{sum(durations) / len(durations):.1f}s" if durations else "—")
        for widget, key, value in zip(screen._upload_metrics,
                ("layout.upload.total", "layout.upload.success_rate", "layout.upload.today", "layout.upload.duration"), values):
            widget.title.setText(screen.main.i18n.tr(key))
            widget.value.setText(value)
    screen._refresh_upload_metrics = update_metrics
    update_details()
