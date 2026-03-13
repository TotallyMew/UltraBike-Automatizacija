"""Basso Images Screen

Runs the Basso configurator layered-image capture and compositing process.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from io import BytesIO

import requests
from PIL import Image

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

from selenium import webdriver
from selenium.webdriver.common.by import By
from GUI_Qt.styles.screen_theme import PAGE_MARGINS, PAGE_SPACING, CARD_MARGINS, ICON_TEXT_GAP, ROW_SPACING, CONTENT_SPACING
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from webdriver_manager.chrome import ChromeDriverManager

from GUI_Qt.styles.theme_config import COLORS, FONTS, RADII, PADDINGS, SIZES


DEFAULT_BASSO_URL_PLACEHOLDER = "bassobikes.com/..."


@dataclass(frozen=True)
class BassoResult:
    color_name: str
    file_path: str


class BassoImageWorker(QThread):
    progress = Signal(str)
    finished = Signal(bool, str, object)  # success, message, results

    def __init__(self, url: str, output_dir: str, tr):
        super().__init__()
        self.url = url
        self.output_dir = output_dir
        self.tr = tr

    @staticmethod
    def _safe_filename(name: str) -> str:
        safe = name.strip().replace(" ", "_")
        for ch in ['<', '>', ':', '"', '/', '\\', '|', '?', '*']:
            safe = safe.replace(ch, '-')
        return safe or "image"

    @staticmethod
    def _get_layered_image_urls(driver) -> list[str]:
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, "#view_0 img")))
        img_elements = driver.find_elements(By.CSS_SELECTOR, "#view_0 img")
        return [img.get_attribute("src") for img in img_elements if img.get_attribute("src")]

    @staticmethod
    def _download_images(image_urls: list[str]) -> list[Image.Image]:
        images: list[Image.Image] = []
        for url in image_urls:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            img = Image.open(BytesIO(resp.content)).convert("RGBA")
            images.append(img)
        return images

    @staticmethod
    def _merge_images(images: list[Image.Image]) -> Image.Image:
        if not images:
            raise ValueError("No images provided for merging")
        base = images[0]
        base_size = base.size
        for overlay in images[1:]:
            if overlay.size != base_size:
                overlay = overlay.resize(base_size, Image.LANCZOS)
            base = Image.alpha_composite(base, overlay)
        return base

    def run(self):
        driver = None
        try:
            if not self.url:
                self.finished.emit(False, self.tr("basso.images.url.invalid"), [])
                return

            if not self.output_dir:
                self.finished.emit(False, self.tr("basso.images.output.invalid"), [])
                return

            os.makedirs(self.output_dir, exist_ok=True)

            self.progress.emit(self.tr("basso.images.status.starting"))

            options = ChromeOptions()
            options.add_argument("--headless=new")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_experimental_option('excludeSwitches', ['enable-logging'])

            driver = webdriver.Chrome(
                service=ChromeService(ChromeDriverManager().install()),
                options=options,
            )
            driver.get(self.url)

            WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, "#view_0")))
            WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, ".ColorRadio")))

            color_labels = driver.find_elements(By.CSS_SELECTOR, ".ColorRadio label")
            if not color_labels:
                self.finished.emit(False, self.tr("basso.images.no_colors"), [])
                return

            results: list[BassoResult] = []

            for i in range(len(color_labels)):
                color_labels = driver.find_elements(By.CSS_SELECTOR, ".ColorRadio label")
                option = color_labels[i]
                color_name = (option.text or "").strip().split("\n")[0].strip() or f"color_{i+1}"

                self.progress.emit(self.tr("basso.images.status.color", current=i + 1, total=len(color_labels), name=color_name))

                driver.execute_script("arguments[0].click();", option)
                time.sleep(2)

                layered_urls = self._get_layered_image_urls(driver)
                if not layered_urls:
                    continue

                images = self._download_images(layered_urls)
                composite = self._merge_images(images)

                filename = f"{self._safe_filename(color_name)}.png"
                out_path = os.path.join(self.output_dir, filename)
                composite.save(out_path)
                results.append(BassoResult(color_name=color_name, file_path=out_path))

            if not results:
                self.finished.emit(False, self.tr("basso.images.no_results"), [])
                return

            self.finished.emit(True, self.tr("basso.images.done", count=len(results)), results)

        except Exception as e:
            self.finished.emit(False, self.tr("basso.images.failed", error=str(e)), [])
        finally:
            try:
                if driver is not None:
                    driver.quit()
            except Exception:
                pass


class BassoImageScreen(QWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main = main_window
        self.worker: BassoImageWorker | None = None
        self._init_ui()
        qconfig.themeChangedFinished.connect(self._on_theme_changed)

    def _apply_theme(self):
        is_dark = isDarkTheme()
        bg_color = COLORS['space_indigo'] if is_dark else COLORS['platinum']
        self.setStyleSheet(f"""
            BassoImageScreen {{
                background-color: {bg_color};
                font-family: {FONTS['family']};
            }}
        """)

        if hasattr(self, 'log') and self.log is not None:
            self.log.setStyleSheet(f"""
                QPlainTextEdit {{
                    background-color: {COLORS['lavender_grey'] if is_dark else COLORS['bg_light']};
                    border-radius: {RADII['sm']}px;
                    padding: {PADDINGS['combo_item']};
                }}
            """)

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
        left.setMinimumWidth(SIZES['panel_min_width'])
        left.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(*CARD_MARGINS)
        ll.setSpacing(CONTENT_SPACING)

        self.subtitle_label = BodyLabel("")
        self.subtitle_label.setWordWrap(True)
        ll.addWidget(self.subtitle_label)

        self.url_label = BodyLabel("")
        self.url_caption = CaptionLabel("")
        self.url_caption.setStyleSheet(f"color: {COLORS['text_secondary']}; background: transparent; background-color: transparent;")
        ll.addWidget(self.url_label)
        ll.addWidget(self.url_caption)

        self.url_field = LineEdit()
        self.url_field.setPlaceholderText(DEFAULT_BASSO_URL_PLACEHOLDER)
        ll.addWidget(self.url_field)

        self.output_label = BodyLabel("")
        self.output_caption = CaptionLabel("")
        self.output_caption.setStyleSheet(f"color: {COLORS['text_secondary']}; background: transparent; background-color: transparent;")
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

        # Right: log/output
        right = CardWidget()
        right.setBorderRadius(RADII['md'])
        right.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        rl = QVBoxLayout(right)
        rl.setContentsMargins(*CARD_MARGINS)
        rl.setSpacing(ROW_SPACING)

        self.log_title = BodyLabel("")
        self.log_title.setStyleSheet(f"font-weight: 600; color: {COLORS['text_secondary']}; background: transparent; background-color: transparent;")
        self.log_hint = CaptionLabel("")
        self.log_hint.setStyleSheet(f"color: {COLORS['text_secondary']}; background: transparent; background-color: transparent;")
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
        self.title_label.setText(tr("basso.images.title"))
        self.subtitle_label.setText(tr("basso.images.subtitle"))
        self.url_label.setText(tr("basso.images.url.label"))
        self.url_caption.setText(tr("basso.images.url.caption"))
        self.url_field.setPlaceholderText(tr("basso.images.url.placeholder"))
        self.output_label.setText(tr("basso.images.output.label"))
        self.output_caption.setText(tr("basso.images.output.caption"))
        self.output_field.setPlaceholderText(tr("basso.images.output.placeholder"))
        self.browse_btn.setText(tr("basso.images.output.browse"))
        self.run_btn.setText(tr("basso.images.run"))
        self.log_title.setText(tr("basso.images.log.title"))
        self.log_hint.setText(tr("basso.images.log.hint"))

    def _on_theme_changed(self):
        self._apply_theme()

    def _browse_output(self):
        tr = self.main.i18n.tr
        folder = QFileDialog.getExistingDirectory(self, tr("basso.images.output.browse.title"), "")
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
                content=tr("basso.images.url.invalid"),
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
                content=tr("basso.images.output.invalid"),
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3500,
                parent=self,
            )
            return

        self.log.clear()
        self._append_log(tr("basso.images.status.starting"))
        self._set_busy(True)

        self.worker = BassoImageWorker(url=url, output_dir=output_dir, tr=tr)
        self.worker.progress.connect(self._append_log)
        self.worker.finished.connect(self._on_finished)
        self.worker.start()

    def _on_finished(self, success: bool, message: str, results):
        tr = self.main.i18n.tr
        self._set_busy(False)

        if success:
            self._append_log(message)
            try:
                for r in list(results or []):
                    # r may be BassoResult or a dict-like; be defensive
                    fp = getattr(r, 'file_path', None) or (r.get('file_path') if isinstance(r, dict) else None)
                    name = getattr(r, 'color_name', None) or (r.get('color_name') if isinstance(r, dict) else None)
                    if fp:
                        self._append_log(f"- {name or ''} {fp}")
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
            self._append_log(message)
            InfoBar.error(
                title=tr("common.error"),
                content=message,
                orient=Qt.Orientation.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=4500,
                parent=self,
            )
