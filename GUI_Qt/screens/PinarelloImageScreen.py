"""Pinarello Images Screen

Runs the Pinarello product image downloader:
- Creates per-variant folders
- Downloads variant images + product gallery images
- Converts to PNG and resizes oversized images
"""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFileDialog, QSizePolicy, QPlainTextEdit

from qfluentwidgets import (
    CardWidget,
    TitleLabel,
    BodyLabel,
    CaptionLabel,
    LineEdit,
    PrimaryPushButton,
    PushButton,
    TransparentToolButton,
    FluentIcon,
    InfoBar,
    InfoBarPosition,
    IndeterminateProgressRing,
    isDarkTheme,
    qconfig,
)

from GUI_Qt.styles.theme_config import COLORS, FONTS, RADII, PADDINGS, SIZES
from GUI_Qt.styles.screen_theme import PAGE_MARGINS, PAGE_SPACING, CARD_MARGINS, ICON_TEXT_GAP, ROW_SPACING, CONTENT_SPACING


DEFAULT_PINARELLO_URL_PLACEHOLDER = "pinarello.com/..."


class PinarelloImageWorker(QThread):
    progress = Signal(str)
    finished = Signal(bool, str, object)  # success, message, results

    def __init__(self, driver, url: str, output_dir: str, wait_s: int, tr):
        super().__init__()
        self.driver = driver
        self.url = url
        self.output_dir = output_dir
        self.wait_s = wait_s
        self.tr = tr

    def run(self):
        try:
            from pinarello_image_downloader import download_pinarello_variants_in_existing_browser

            if self.driver is None:
                self.finished.emit(False, self.tr("pinarello.images.no_session"), None)
                return

            if not self.url:
                self.finished.emit(False, self.tr("pinarello.images.url.invalid"), None)
                return

            if not self.output_dir:
                self.finished.emit(False, self.tr("pinarello.images.output.invalid"), [])
                return

            os.makedirs(self.output_dir, exist_ok=True)

            self.progress.emit(self.tr("pinarello.images.status.starting"))
            self.progress.emit(self.tr("pinarello.images.status.product", url=self.url))

            res = download_pinarello_variants_in_existing_browser(
                driver=self.driver,
                url=self.url,
                output_dir=self.output_dir,
                wait_s=self.wait_s,
                log=self.progress.emit,
            )

            self.finished.emit(True, self.tr("pinarello.images.done"), res)

        except Exception as e:
            self.finished.emit(False, self.tr("pinarello.images.failed", error=str(e)), [])


class PinarelloImageScreen(QWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main = main_window
        self.worker: PinarelloImageWorker | None = None
        self._init_ui()
        qconfig.themeChangedFinished.connect(self._on_theme_changed)

    def _apply_theme(self):
        is_dark = isDarkTheme()
        bg_color = COLORS["space_indigo"] if is_dark else COLORS["platinum"]
        self.setStyleSheet(
            f"""
            PinarelloImageScreen {{
                background-color: {bg_color};
                font-family: {FONTS['family']};
            }}
            """
        )

        if hasattr(self, 'log') and self.log is not None:
            self.log.setStyleSheet(
                f"""
                QPlainTextEdit {{
                    background-color: {COLORS['lavender_grey'] if is_dark else COLORS['bg_light']};
                    border-radius: {RADII['sm']}px;
                    padding: {PADDINGS['combo_item']};
                }}
                """
            )

    def _init_ui(self):
        self._apply_theme()
        self.setAutoFillBackground(True)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(*PAGE_MARGINS)
        main_layout.setSpacing(PAGE_SPACING)

        header = QHBoxLayout()
        title_container = QHBoxLayout()
        title_container.setSpacing(ICON_TEXT_GAP)

        title_icon = TransparentToolButton(FluentIcon.PHOTO, self)
        title_icon.setFixedSize(SIZES['icon_lg'], SIZES['icon_lg'])
        title_icon.setEnabled(False)

        self.title_label = TitleLabel("")
        title_container.addWidget(title_icon)
        title_container.addWidget(self.title_label)
        header.addLayout(title_container)
        header.addStretch()
        main_layout.addLayout(header)

        content_layout = QHBoxLayout()
        content_layout.setSpacing(PAGE_SPACING)

        # Left: controls
        left = CardWidget()
        left.setBorderRadius(RADII['md'])
        left.setMinimumWidth(SIZES['panel_min_width_lg'])
        left.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(*CARD_MARGINS)
        ll.setSpacing(CONTENT_SPACING)

        self.subtitle_label = BodyLabel("")
        self.subtitle_label.setWordWrap(True)
        ll.addWidget(self.subtitle_label)

        self.url_label = BodyLabel("")
        self.url_caption = CaptionLabel("")
        self.url_caption.setStyleSheet(f"color: {COLORS['text_secondary']};")
        self.url_caption.setWordWrap(True)
        ll.addWidget(self.url_label)
        ll.addWidget(self.url_caption)

        self.url_field = LineEdit()
        self.url_field.setPlaceholderText(DEFAULT_PINARELLO_URL_PLACEHOLDER)
        ll.addWidget(self.url_field)

        self.output_label = BodyLabel("")
        self.output_caption = CaptionLabel("")
        self.output_caption.setStyleSheet(f"color: {COLORS['text_secondary']};")
        ll.addWidget(self.output_label)
        ll.addWidget(self.output_caption)

        out_row = QHBoxLayout()
        out_row.setSpacing(ROW_SPACING)
        self.output_field = LineEdit()
        out_row.addWidget(self.output_field, 1)
        self.browse_btn = PushButton("")
        self.browse_btn.setIcon(FluentIcon.FOLDER_ADD.icon())
        self.browse_btn.clicked.connect(self._browse_output)
        out_row.addWidget(self.browse_btn)
        ll.addLayout(out_row)

        actions = QHBoxLayout()
        actions.setSpacing(CONTENT_SPACING)
        self.run_btn = PrimaryPushButton("")
        self.run_btn.setIcon(FluentIcon.PLAY.icon())
        self.run_btn.clicked.connect(self._run)

        self.progress_ring = IndeterminateProgressRing()
        self.progress_ring.setFixedSize(SIZES['progress_ring'], SIZES['progress_ring'])
        self.progress_ring.setVisible(False)

        actions.addWidget(self.run_btn)
        actions.addStretch(1)
        actions.addWidget(self.progress_ring)
        ll.addLayout(actions)

        ll.addStretch(1)
        content_layout.addWidget(left, 4)

        # Right: log
        right = CardWidget()
        right.setBorderRadius(RADII['md'])
        right.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        rl = QVBoxLayout(right)
        rl.setContentsMargins(*CARD_MARGINS)
        rl.setSpacing(ROW_SPACING)

        self.log_title = BodyLabel("")
        self.log_title.setStyleSheet(f"font-weight: 600; color: {COLORS['text_secondary']};")
        self.log_hint = CaptionLabel("")
        self.log_hint.setStyleSheet(f"color: {COLORS['text_secondary']};")
        self.log_hint.setWordWrap(True)
        rl.addWidget(self.log_title)
        rl.addWidget(self.log_hint)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self._apply_theme()
        rl.addWidget(self.log, 1)

        content_layout.addWidget(right, 6)
        main_layout.addLayout(content_layout, 1)

        self.retranslate_ui()

    def retranslate_ui(self):
        tr = self.main.i18n.tr
        self.title_label.setText(tr("pinarello.images.title"))
        self.subtitle_label.setText(tr("pinarello.images.subtitle"))
        self.url_label.setText(tr("pinarello.images.url.label"))
        self.url_caption.setText(tr("pinarello.images.url.caption"))
        self.url_field.setPlaceholderText(tr("pinarello.images.url.placeholder"))
        self.output_label.setText(tr("pinarello.images.output.label"))
        self.output_caption.setText(tr("pinarello.images.output.caption"))
        self.output_field.setPlaceholderText(tr("pinarello.images.output.placeholder"))
        self.browse_btn.setText(tr("pinarello.images.output.browse"))
        self.run_btn.setText(tr("pinarello.images.run"))
        self.log_title.setText(tr("pinarello.images.log.title"))
        self.log_hint.setText(tr("pinarello.images.log.hint"))

    def _on_theme_changed(self):
        self._apply_theme()

    def _browse_output(self):
        tr = self.main.i18n.tr
        folder = QFileDialog.getExistingDirectory(self, tr("pinarello.images.output.browse.title"), "")
        if folder:
            self.output_field.setText(folder)

    def _append_log(self, text: str):
        self.log.appendPlainText(text)

    def _set_busy(self, busy: bool):
        self.progress_ring.setVisible(busy)
        self.run_btn.setEnabled(not busy)
        self.browse_btn.setEnabled(not busy)
        self.url_field.setEnabled(not busy)
        self.output_field.setEnabled(not busy)

    def _run(self):
        tr = self.main.i18n.tr

        url = self.url_field.text().strip()
        output_dir = self.output_field.text().strip()

        if not url:
            InfoBar.error(
                title=tr("common.error"),
                content=tr("pinarello.images.url.invalid"),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3500,
                parent=self,
            )
            return
        if not output_dir:
            InfoBar.error(
                title=tr("common.error"),
                content=tr("pinarello.images.output.invalid"),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3500,
                parent=self,
            )
            return

        self.log.clear()
        self._append_log(tr("pinarello.images.status.starting"))
        self._set_busy(True)

        self.worker = PinarelloImageWorker(
            driver=getattr(self.main, "driver", None),
            url=url,
            output_dir=output_dir,
            wait_s=20,
            tr=tr,
        )
        self.worker.progress.connect(self._append_log)
        self.worker.finished.connect(self._on_finished)
        self.worker.start()

    def _on_finished(self, success: bool, message: str, results):
        tr = self.main.i18n.tr
        self._set_busy(False)

        self._append_log(message)

        if success:
            try:
                r = results if isinstance(results, dict) else None
                if r:
                    product_dir = r.get("product_dir")
                    title = r.get("title")
                    gallery_count = r.get("gallery_count")
                    variant_images = r.get("variant_images")
                    variants = r.get("variants")

                    if product_dir:
                        self._append_log(f"- {title or ''} => {product_dir}")
                        self._append_log(f"  gallery={gallery_count or 0} variants={variants or 0} variant_images={variant_images or 0}")
            except Exception:
                pass

            InfoBar.success(
                title=tr("common.success"),
                content=message,
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3500,
                parent=self,
            )
        else:
            InfoBar.error(
                title=tr("common.error"),
                content=message,
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=4500,
                parent=self,
            )
