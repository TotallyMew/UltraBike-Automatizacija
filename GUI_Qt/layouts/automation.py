"""Presentation of the existing supplier automation controls."""
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QWidget, QVBoxLayout
from qfluentwidgets import CaptionLabel
from GUI_Qt.widgets.workspace import (
    WorkspaceColumns, Disclosure, ancestor_card, bind_text, clear_layout,
    grouped_stages, heading, move_widget, card, merge_contents, WorkspaceTabBar, connect_signal,
)


def _field(label, control, button=None):
    widget = QWidget()
    widget.setObjectName("workspaceField")
    widget.setStyleSheet("#workspaceField { background: transparent; }")
    box = QVBoxLayout(widget)
    box.setContentsMargins(0, 0, 0, 0)
    box.setSpacing(4)
    box.addWidget(label)
    row = QHBoxLayout()
    row.addWidget(control, 1)
    if button is not None:
        row.addWidget(button)
    box.addLayout(row)
    return widget


def _filter_summary(screen, disclosure, combos):
    summary = CaptionLabel()
    summary.setWordWrap(True)
    disclosure.layout().insertWidget(0, summary)
    def update(*_args):
        summary.setText(" · ".join(combo.currentText() for combo in combos if combo.currentText()))
    for combo in combos:
        combo.currentIndexChanged.connect(update)
    update()


def arrange_kross(screen):
    sources = ancestor_card(screen._output_input)
    filters = ancestor_card(screen._filters_title)
    collection = ancestor_card(screen._collection_title)
    results = ancestor_card(screen._results_title)
    upload = ancestor_card(screen._upload_title)
    log = ancestor_card(screen._log_title)
    while screen._layout.count() > 1:
        screen._layout.takeAt(1)
    workspace = WorkspaceColumns(sidebar_width=360)
    screen._workspace = workspace
    screen._layout.addWidget(workspace)
    input_card, input_box = card()
    input_box.addWidget(heading(screen.main, "layout.input"))
    modes = WorkspaceTabBar()
    modes.setExpanding(False)
    modes.addTab(screen.main.i18n.tr("layout.scan_mode"))
    modes.addTab(screen.main.i18n.tr("layout.paste_mode"))
    input_box.addWidget(modes)
    filter_details = Disclosure(screen.main, "layout.filters")
    _filter_summary(screen, filter_details, [
        screen._family_combo, screen._category_combo, screen._source_combo,
        screen._locale_combo, screen._sort_combo,
    ])
    move_widget(filters, filter_details.body_layout)
    input_box.addWidget(filter_details)
    merge_contents(sources, input_box)
    merge_contents(collection, input_box)
    workspace.main_layout.addWidget(input_card)
    workspace.main_layout.addWidget(results)
    run_card, run_box = card()
    run_box.addWidget(heading(screen.main, "layout.run"))
    for widget in (screen._collect_button, screen._collect_skus_button,
            screen._load_pasted_local_button, screen._stop_button):
        move_widget(widget, run_box)
    workspace.side_layout.addWidget(run_card)
    workspace.side_layout.addWidget(log)
    workspace.side_layout.addWidget(upload)
    # The existing manual and filtered collectors remain separate execution paths.
    def change_mode(index):
        manual = index == 1
        filter_details.setVisible(not manual)
        screen._manual_skus_label.setVisible(manual)
        screen._manual_skus_input.setVisible(manual)
        screen._collect_button.setVisible(not manual)
        screen._collect_skus_button.setVisible(manual)
        screen._load_pasted_local_button.setVisible(manual)
    def translate(*_args):
        for index, key in enumerate(("layout.scan_mode", "layout.paste_mode")):
            modes.setTabText(index, screen.main.i18n.tr(key))
    modes.currentChanged.connect(change_mode)
    if hasattr(screen.main.i18n, "languageChanged"):
        connect_signal(screen.main.i18n.languageChanged, modes, translate)
    change_mode(0)
    screen._source_modes = modes
    upload_box = upload.layout()
    stage_flow = upload_box.takeAt(3).layout()
    clear_layout(stage_flow)
    upload_box.insertWidget(3, grouped_stages(screen.main, screen._stage_checks))
    stage_header = upload_box.itemAt(2).layout()
    clear_layout(stage_header)
    stage_header.addWidget(screen._stages_label)
    stage_header.addStretch()
    bind_text(screen._select_all_stages_button, screen.main, "layout.all")
    bind_text(screen._clear_stages_button, screen.main, "layout.clear")
    stage_header.addWidget(screen._select_all_stages_button)
    stage_header.addWidget(screen._clear_stages_button)
    for widget in (screen._upload_button, screen._progress, screen._progress_label):
        move_widget(widget, upload_box)
    screen._log.setFixedHeight(120)
    screen._table.setMinimumHeight(360)
    workspace.main_layout.addStretch()
    workspace.side_layout.addStretch()
