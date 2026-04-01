"""Reusable UI widgets and components"""

import os
import subprocess

from PySide6.QtCore import Qt
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


def _reveal_in_explorer(path: str):
    """Open file explorer with the given file selected."""
    path = os.path.normpath(path)
    subprocess.Popen(["explorer", "/select,", path])
