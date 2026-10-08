"""Layout existing lookup, URL and image tools inside tabbed workspaces."""
from PySide6.QtWidgets import QWidget, QVBoxLayout
from qfluentwidgets import IconWidget
from GUI_Qt.widgets.workspace import WorkspaceColumns, ancestor_card, card, clear_layout, heading, move_widget


def _hide_layout_widgets(layout):
    for index in range(layout.count()):
        item = layout.itemAt(index)
        if item.widget():
            item.widget().hide()
        elif item.layout():
            _hide_layout_widgets(item.layout())


def arrange_table_tool(panel):
    layout = panel._layout
    _hide_layout_widgets(layout.itemAt(0).layout())
    toolbar = ancestor_card(panel._start_btn)
    clear_layout(layout)
    workspace = WorkspaceColumns()
    panel._workspace = workspace
    layout.addWidget(workspace)
    workspace.main_layout.addWidget(toolbar)
    if hasattr(panel, "_drop_zone"):
        workspace.main_layout.addWidget(panel._drop_zone)
        panel._drop_zone.setMinimumHeight(112)
        panel._drop_zone.setMaximumHeight(160)
        for icon in panel._drop_zone.findChildren(IconWidget):
            icon.setFixedSize(32, 32)
        panel._drop_zone.layout().setSpacing(8)
    table_card, table_box = card()
    table_box.addWidget(panel._table)
    panel._table.setMinimumHeight(320)
    workspace.main_layout.addWidget(table_card)
    run, run_box = card()
    run_box.addWidget(heading(panel.main, "layout.run"))
    for name in ("_browser_label", "_browser_combo", "_status_label", "_start_btn", "_progress_label"):
        widget = getattr(panel, name, None)
        if widget is not None:
            move_widget(widget, run_box)
    workspace.side_layout.addWidget(run)
    output, output_box = card()
    output_box.addWidget(heading(panel.main, "layout.output"))
    move_widget(panel._export_btn, output_box)
    workspace.side_layout.addWidget(output)
    workspace.main_layout.addStretch()
    workspace.side_layout.addStretch()
    panel.layout().setContentsMargins(0, 0, 0, 0)


def arrange_image_tool(panel):
    if hasattr(panel, "_table"):
        arrange_table_tool(panel)
        return
    root = panel.content_widget.layout()
    _hide_layout_widgets(root.itemAt(0).layout())
    # Record the source/progress cards before removing their old columns.
    source = ancestor_card(panel.url_field)
    output = ancestor_card(panel.output_field)
    progress = ancestor_card(getattr(panel, "main_progress", panel.run_btn))
    clear_layout(root)
    root.setContentsMargins(0, 0, 0, 0)
    workspace = WorkspaceColumns()
    panel._workspace = workspace
    root.addWidget(workspace)
    panel.layout().setContentsMargins(0, 0, 0, 0)
    workspace.main_layout.addWidget(source)
    if output is not source:
        workspace.main_layout.addWidget(output)
    if hasattr(panel, "variant_card"):
        move_widget(panel.variant_card, workspace.main_layout)
    if hasattr(panel, "summary_card"):
        move_widget(panel.summary_card, workspace.main_layout)
    if hasattr(panel, "right_panel"):
        workspace.main_layout.addWidget(panel.right_panel)
        panel.log.setMinimumHeight(240)
    if progress not in (source, output):
        workspace.side_layout.addWidget(progress)
    run, run_box = card()
    run_box.addWidget(heading(panel.main, "layout.run"))
    move_widget(panel.run_btn, run_box)
    move_widget(panel.progress_ring, run_box)
    workspace.side_layout.insertWidget(0, run)
    if hasattr(panel, "detail_log"):
        move_widget(panel.detail_log, workspace.main_layout)
    workspace.main_layout.addStretch()
    workspace.side_layout.addStretch()
