"""GUI-thread presentation for structured errors and worker prompts."""

import queue

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QDialog, QLineEdit
from qfluentwidgets import InfoBar, InfoBarPosition, MessageBox, isDarkTheme

from GUI_Qt.styles.theme_config import SIZES, get_input_style
from Utilities.ErrorManager import ErrorManager


class ErrorPresentationService:
    def __init__(self, main_window):
        self.main = main_window
        self.queue = queue.Queue()
        self.timer = None

    def start(self) -> None:
        ErrorManager.set_prompt_queue(self.queue)
        ErrorManager.configure(
            notification_queue=self.queue,
            logger=self.main.logger,
            translator=self.main.i18n.tr,
        )
        self.timer = QTimer(self.main)
        self.timer.setInterval(150)
        self.timer.timeout.connect(self.process)
        self.timer.start()
        # Retain these names for callers/tests that used the former window fields.
        self.main._prompt_queue = self.queue
        self.main._prompt_timer = self.timer

    def process(self) -> None:
        try:
            while not self.queue.empty():
                request = self.queue.get_nowait()
                if request and request[0] == "notification":
                    self._notification(*request[1:])
                    continue
                prompt_type, _operation_name, response_queue = request
                if prompt_type == "retry":
                    self._retry(response_queue)
                elif prompt_type == "continue":
                    self._continue(response_queue)
                elif prompt_type == "exit_or_retry":
                    self._exit_or_retry(response_queue)
                else:
                    response_queue.put(False)
        except Exception as error:
            try:
                self.main.logger.error(
                    "ErrorPresentation", "Could not present a queued request", exception=error
                )
            except Exception:
                pass

    def _notification(self, level: str, message: str, _code: str) -> None:
        presenter = {
            "error": InfoBar.error,
            "warning": InfoBar.warning,
            "success": InfoBar.success,
            "info": InfoBar.info,
        }.get(level, InfoBar.info)
        title_key = {
            "error": "common.error",
            "warning": "common.warning",
            "success": "common.success",
            "info": "common.info",
        }.get(level, "common.info")
        presenter(
            title=self.main.i18n.tr(title_key),
            content=message,
            orient=Qt.Orientation.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=5000 if level == "error" else 3000,
            parent=self.main,
        )

    def _retry(self, response_queue) -> None:
        dialog = MessageBox(self.main.i18n.tr("prompt.retry.title"), "", self.main)
        try:
            dialog.textLayout.removeWidget(dialog.contentLabel)
            dialog.contentLabel.deleteLater()
        except Exception:
            pass
        input_widget = QLineEdit()
        input_widget.setPlaceholderText(self.main.i18n.tr("prompt.retry.placeholder"))
        input_widget.setStyleSheet(get_input_style(isDarkTheme()))
        input_widget.setMinimumWidth(SIZES["panel_min_width"])
        dialog.textLayout.addWidget(input_widget)
        dialog.yesButton.setText(self.main.i18n.tr("prompt.retry.yes"))
        dialog.cancelButton.setText(self.main.i18n.tr("prompt.retry.cancel"))

        def finished(result_code):
            if result_code != QDialog.Accepted:
                response_queue.put(False)
                return
            response_queue.put(input_widget.text().strip() or True)

        dialog.finished.connect(finished)
        dialog.show()

    def _continue(self, response_queue) -> None:
        dialog = MessageBox(
            self.main.i18n.tr("prompt.continue.title"),
            self.main.i18n.tr("prompt.continue.content"),
            self.main,
        )
        dialog.yesButton.setText(self.main.i18n.tr("prompt.continue.yes"))
        dialog.cancelButton.setText(self.main.i18n.tr("prompt.continue.no"))
        response_queue.put(bool(dialog.exec()))

    def _exit_or_retry(self, response_queue) -> None:
        dialog = MessageBox(
            self.main.i18n.tr("prompt.exit_or_retry.title"),
            self.main.i18n.tr("prompt.exit_or_retry.content"),
            self.main,
        )
        dialog.yesButton.setText(self.main.i18n.tr("prompt.exit_or_retry.retry"))
        dialog.cancelButton.setText(self.main.i18n.tr("prompt.exit_or_retry.exit"))
        response_queue.put("retry" if dialog.exec() else "exit")
