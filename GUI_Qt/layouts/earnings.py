"""Earnings layouts using live metrics, timer, goals and records."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QTableWidget, QTableWidgetItem, QHeaderView, QSizePolicy, QWidget, QVBoxLayout
from qfluentwidgets import PushButton, CaptionLabel, qconfig, isDarkTheme
from GUI_Qt.earnings.presentation import local_datetime, money
from GUI_Qt.widgets.workspace import WorkspaceColumns, Disclosure, card, clear_layout, heading, bind_text, move_widget, connect_signal


def arrange_earnings(screen):
    root = screen.content.layout()
    root.setContentsMargins(32, 24, 32, 24)
    root.setSpacing(16)
    logging = screen.logging_page.layout()
    analytics = screen.analytics_page.layout()
    clear_layout(logging)
    clear_layout(analytics)
    # A single set of live headline metrics stays visible across all three tabs.
    root.insertLayout(2, screen.metrics_layout)
    screen._log_workspace = WorkspaceColumns(sidebar_width=360)
    logging.addWidget(screen._log_workspace)
    main = screen._log_workspace.main_layout
    side = screen._log_workspace.side_layout
    main.addWidget(screen.entry_panel)
    recent, box = card()
    box.addWidget(heading(screen.main, "layout.recent"))
    screen.recent_table = QTableWidget(0, 4)
    screen.recent_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    screen.recent_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    screen.recent_table.verticalHeader().hide()
    screen.recent_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    screen.recent_table.setShowGrid(False)
    screen.recent_table.setFixedHeight(248)
    box.addWidget(screen.recent_table)
    link = bind_text(PushButton(), screen.main, "layout.see_records")
    link.clicked.connect(lambda: screen._switch_section("history"))
    box.addWidget(link)
    main.addWidget(recent)
    side.addWidget(screen.timer_panel)
    side.addWidget(screen.goal_quest_panel)

    # The timer actions form a compact two-by-two group in the action column.
    timer_actions = QGridLayout()
    timer_actions.setSpacing(8)
    for index, button in enumerate((screen.timer_start, screen.timer_pause, screen.timer_finish, screen.timer_reset)):
        move_widget(button, timer_actions)
        timer_actions.addWidget(button, index // 2, index % 2)
    screen.timer_panel.layout().addLayout(timer_actions)
    entry_grid = screen.entry_panel.layout()
    date_field = screen.date_input.parentWidget()
    entry_grid.addWidget(date_field, 3, 0, 1, 2)
    old_button_wrapper = screen.add_button.parentWidget()
    entry_grid.removeWidget(old_button_wrapper)
    old_button_wrapper.hide()
    screen.batch_counter.setMaximumWidth(200)
    entry_grid.addWidget(screen.batch_counter, 5, 0, 1, 2, Qt.AlignmentFlag.AlignRight)
    screen.add_button.setMinimumWidth(0)
    screen.add_button.setMaximumWidth(16777215)
    screen.add_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    screen.add_button.setMinimumHeight(40)
    entry_grid.addWidget(screen.add_button, 4, 0, 1, 2)
    main.addStretch()
    side.addStretch()

    screen._analytics_workspace = WorkspaceColumns(sidebar_width=360)
    analytics.addWidget(screen._analytics_workspace)
    analytics_main = screen._analytics_workspace.main_layout
    analytics_side = screen._analytics_workspace.side_layout
    # Retain the existing chart and its real brand/type breakdowns.
    trend = screen.chart.parentWidget()
    analytics_main.addWidget(trend)
    details = Disclosure(screen.main, "layout.analytics_details")
    details.body_layout.addLayout(screen.analytics_metrics_layout)
    details.body_layout.addWidget(screen.goal_panel)
    analytics_main.addWidget(details)
    analytics_side.addWidget(screen.projection_panel)
    analytics_side.addWidget(screen.performance_panel)
    move_widget(screen.activity_block, analytics_main)
    screen._arrange_projection_metrics(compact=True)
    analytics_main.addStretch()
    analytics_side.addStretch()
    screen.entries_table.setColumnHidden(9, True)
    screen.history_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    screen.history_panel.layout().setAlignment(Qt.AlignmentFlag.AlignTop)
    screen.history_page.layout().setAlignment(Qt.AlignmentFlag.AlignTop)
    from GUI_Qt.styles.theme_config import get_surface_color, get_subtle_border
    def history_theme(*_args):
        dark = isDarkTheme()
        screen.history_panel.setStyleSheet(
            f"#earningsFlatSection {{ background: {get_surface_color(dark, 'surface')}; "
            f"border: 1px solid {get_subtle_border(dark)}; border-radius: 8px; }}")
    history_theme()
    connect_signal(qconfig.themeChangedFinished, screen, history_theme)
    screen.history_panel.layout().setContentsMargins(24, 16, 24, 16)
    for index in range(screen.history_tabs.count()):
        screen.history_tabs.widget(index).layout().setAlignment(Qt.AlignmentFlag.AlignTop)
    screen._record_filter_fields = []
    for key, control in (("layout.filter.search", screen.search),
            ("layout.filter.brand", screen.filter_brand), ("layout.filter.type", screen.filter_type),
            ("layout.filter.source", screen.filter_source), ("layout.filter.date", screen.filter_date)):
        field = QWidget()
        field.setObjectName("earningsField")
        field.setStyleSheet("#earningsField { background: transparent; }")
        field_box = QVBoxLayout(field)
        field_box.setContentsMargins(0, 0, 0, 0)
        field_box.setSpacing(4)
        field_box.addWidget(bind_text(CaptionLabel(), screen.main, key))
        control.setMinimumWidth(0)
        control.setMaximumWidth(16777215)
        field_box.addWidget(control)
        screen._record_filter_fields.append(field)
    screen._arrange_history_toolbar(compact=False)

    def refresh_recent(*_args):
        rows = screen.service.list_entries()[:5]
        table = screen.recent_table
        table.setRowCount(len(rows))
        for row, entry in enumerate(rows):
            values = (local_datetime(entry["earned_at"]), entry["sku"],
                      entry.get("brand_name") or "", money(entry["payout_cents"]))
            for column, value in enumerate(values):
                table.setItem(row, column, QTableWidgetItem(str(value)))
        table.setHorizontalHeaderLabels([
            screen.main.i18n.tr(key) for key in ("layout.recent.time", "layout.recent.sku",
                "layout.recent.brand", "layout.recent.earning")])
    from GUI_Qt.styles.screen_theme import CARD_MARGINS
    for panel in (screen.entry_panel, screen.timer_panel, screen.goal_quest_panel,
            screen.projection_panel, screen.performance_panel, trend):
        panel.layout().setContentsMargins(*CARD_MARGINS)
        panel.layout().setSpacing(12)
    screen._arrange_goal_quest_header(compact=True)
    screen._refresh_recent = refresh_recent
    if hasattr(screen.main.i18n, "languageChanged"):
        connect_signal(screen.main.i18n.languageChanged, screen, refresh_recent)
    refresh_recent()
