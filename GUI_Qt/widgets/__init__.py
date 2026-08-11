"""Reusable UI widgets and components"""

import os
import subprocess
import sys
import threading
import time

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QApplication, QMenu
from qfluentwidgets import InfoBar, InfoBarPosition, PushButton, FluentIcon


def show_file_saved_bar(parent, title: str, message: str, file_path: str,
                        open_label: str = "Open", duration: int = 5000):
    """Show a success InfoBar with an 'Open' button that highlights the file in Explorer."""
    bar = InfoBar.success(
        title,
        message,
        parent=parent,
        position=InfoBarPosition.TOP,
        duration=duration,
        isClosable=True,
    )
    open_btn = PushButton(FluentIcon.FOLDER, open_label)
    open_btn.setFixedHeight(30)
    open_btn.clicked.connect(lambda: _reveal_in_explorer(file_path))
    bar.addWidget(open_btn)
    return bar


def enable_table_copy(table):
    """Enable Ctrl+C and a context menu for copying table data."""
    shortcut = QShortcut(QKeySequence.StandardKey.Copy, table)
    shortcut.activated.connect(lambda: copy_table_selection(table))
    table._copy_table_shortcut = shortcut

    column_shortcut = QShortcut(QKeySequence("Ctrl+Shift+C"), table)
    column_shortcut.activated.connect(lambda: copy_table_current_column(table))
    table._copy_table_column_shortcut = column_shortcut

    cell_shortcut = QShortcut(QKeySequence("Ctrl+Alt+C"), table)
    cell_shortcut.activated.connect(lambda: copy_table_current_cell(table))
    table._copy_table_cell_shortcut = cell_shortcut

    table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    table.customContextMenuRequested.connect(lambda pos: _show_table_copy_menu(table, pos))


def copy_table_selection(table):
    """Copy selected cells as tab-separated text."""
    indexes = table.selectedIndexes()
    if not indexes:
        row = table.currentRow()
        col = table.currentColumn()
        if row >= 0 and col >= 0:
            _set_clipboard_text(_table_text(table, [row], [col]))
        return

    rows = sorted({idx.row() for idx in indexes})
    cols = sorted({idx.column() for idx in indexes})
    _set_clipboard_text(_table_text(table, rows, cols))


def copy_table_current_row(table):
    row = getattr(table, "_copy_context_row", -1)
    if row < 0:
        row = table.currentRow()
    if row < 0:
        indexes = table.selectedIndexes()
        if not indexes:
            return
        row = indexes[0].row()

    cols = [col for col in range(table.columnCount()) if not table.isColumnHidden(col)]
    _set_clipboard_text(_table_text(table, [row], cols))


def copy_table_current_column(table):
    col = getattr(table, "_copy_context_col", -1)
    if col < 0:
        col = table.currentColumn()
    if col < 0:
        indexes = table.selectedIndexes()
        if not indexes:
            return
        col = indexes[0].column()

    rows = [row for row in range(table.rowCount()) if not table.isRowHidden(row)]
    _set_clipboard_text(_table_text(table, rows, [col]))


def copy_table_current_cell(table):
    row = getattr(table, "_copy_context_row", -1)
    col = getattr(table, "_copy_context_col", -1)
    if row < 0:
        row = table.currentRow()
    if col < 0:
        col = table.currentColumn()
    if row >= 0 and col >= 0:
        _set_clipboard_text(_table_text(table, [row], [col]))


def _show_table_copy_menu(table, pos):
    index = table.indexAt(pos)
    if index.isValid():
        table._copy_context_row = index.row()
        table._copy_context_col = index.column()

    menu = QMenu(table)
    copy_selection = menu.addAction("Copy Selection")
    copy_cell = menu.addAction("Copy Cell")
    copy_row = menu.addAction("Copy Row")
    copy_column = menu.addAction("Copy Column")

    action = menu.exec(table.viewport().mapToGlobal(pos))
    if action == copy_selection:
        copy_table_selection(table)
    elif action == copy_cell:
        copy_table_current_cell(table)
    elif action == copy_row:
        copy_table_current_row(table)
    elif action == copy_column:
        copy_table_current_column(table)

    table._copy_context_row = -1
    table._copy_context_col = -1


def _table_text(table, rows, cols):
    lines = []
    for row in rows:
        values = []
        for col in cols:
            item = table.item(row, col)
            values.append(item.text() if item is not None else "")
        lines.append("\t".join(values))
    return "\n".join(lines)


def _set_clipboard_text(text: str):
    if text:
        QApplication.clipboard().setText(text)


def _reveal_in_explorer(path: str):
    """Open file explorer with the given file selected."""
    path = os.path.normpath(path)
    subprocess.Popen(["explorer", "/select,", path])
    if sys.platform.startswith("win"):
        threading.Thread(target=_focus_explorer_window, daemon=True).start()


def _focus_explorer_window():
    """Best-effort: bring the newly opened Explorer window to the foreground."""
    try:
        time.sleep(0.8)

        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        explorer_hwnds = []

        EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

        def _enum_proc(hwnd, _lparam):
            if not user32.IsWindowVisible(hwnd):
                return True

            class_name = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, class_name, len(class_name))
            if class_name.value in ("CabinetWClass", "ExploreWClass"):
                explorer_hwnds.append(hwnd)
            return True

        user32.EnumWindows(EnumWindowsProc(_enum_proc), 0)
        if not explorer_hwnds:
            return

        hwnd = explorer_hwnds[0]
        SW_RESTORE = 9
        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    except Exception:
        pass
