"""GUI_Qt/screens/CastelliImageDownloaderScreen.py

Downloads Castelli PDP mosaic images into per-code folders.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

import openpyxl
import requests
from bs4 import BeautifulSoup

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QFileDialog, QHeaderView, QTableWidgetItem

from qfluentwidgets import FluentIcon, InfoBar, InfoBarPosition, isDarkTheme

from Config.Selectors import CastelliImageSelectors
from GUI_Qt.screens.CastelliUrlGetterScreen import CastelliUrlGetterScreen
from GUI_Qt.widgets import show_file_saved_bar
from GUI_Qt.styles.theme_config import get_status_text_color, get_text_color


def sanitize_folder_name(name: str) -> str:
    safe = re.sub(r'[\\/:*?"<>|]', "_", (name or "").strip())
    safe = re.sub(r"\s+", " ", safe).strip(" ._")
    return safe or "product"


def image_extension(url: str) -> str:
    path = urlparse(url).path
    suffix = Path(path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp"}:
        return suffix
    return ".jpg"


class CastelliImageDownloaderWorker(QThread):
    row_update = Signal(int, str, str, str)
    progress_update = Signal(int, int)
    done = Signal(int, int)
    log = Signal(str)

    def __init__(self, rows: list[dict[str, str]], output_dir: str):
        super().__init__()
        self.rows = rows
        self.output_dir = output_dir
        self._stop = False

    def request_stop(self):
        self._stop = True

    def run(self):
        ok_count = 0
        error_count = 0

        for idx, row in enumerate(self.rows):
            if self._stop:
                self.row_update.emit(idx, "Skipped", "", "")
                continue

            code = row["code"]
            url = row["url"]
            self.progress_update.emit(idx + 1, len(self.rows))
            self.row_update.emit(idx, "Downloading", "", "")
            self.log.emit(f"Downloading Castelli images for {code}")

            try:
                folder, count = self._download_product(code, url)
                if count:
                    ok_count += 1
                    self.row_update.emit(idx, "Done", str(count), folder)
                else:
                    error_count += 1
                    self.row_update.emit(idx, "No images", "0", folder)
            except Exception as e:
                error_count += 1
                self.row_update.emit(idx, f"Error: {e}", "", "")

        self.done.emit(ok_count, error_count)

    def _download_product(self, code: str, url: str) -> tuple[str, int]:
        product_dir = Path(self.output_dir) / sanitize_folder_name(code)
        product_dir.mkdir(parents=True, exist_ok=True)

        image_urls = self._scrape_image_urls(url)
        if not image_urls:
            return str(product_dir), 0

        saved = 0
        for index, image_url in enumerate(image_urls, start=1):
            ext = image_extension(image_url)
            filename = self._image_filename(image_url, index, ext)
            target = self._unique_path(product_dir / filename)
            self._download_file(image_url, target)
            saved += 1

        return str(product_dir), saved

    def _scrape_image_urls(self, page_url: str) -> list[str]:
        response = requests.get(page_url, timeout=25, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125 Safari/537.36",
        })
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        images = []
        seen = set()

        for img in soup.select(CastelliImageSelectors.PRODUCT_IMAGE):
            src = (img.get("src") or "").strip()
            if not src:
                continue
            full_url = urljoin(page_url, src)
            if full_url in seen:
                continue
            seen.add(full_url)
            images.append(full_url)

        return images

    def _download_file(self, url: str, target: Path):
        response = requests.get(url, stream=True, timeout=30, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125 Safari/537.36",
        })
        response.raise_for_status()
        with open(target, "wb") as handle:
            for chunk in response.iter_content(1024 * 64):
                if chunk:
                    handle.write(chunk)

    def _image_filename(self, url: str, index: int, ext: str) -> str:
        stem = Path(urlparse(url).path).stem
        if not stem:
            stem = f"image_{index:02d}"
        stem = re.sub(r'[\\/:*?"<>|]', "_", stem).strip(" ._") or f"image_{index:02d}"
        return f"{index:02d}_{stem}{ext}"

    def _unique_path(self, path: Path) -> Path:
        if not path.exists():
            return path
        stem = path.stem
        suffix = path.suffix
        for idx in range(1, 1000):
            candidate = path.with_name(f"{stem}_{idx}{suffix}")
            if not candidate.exists():
                return candidate
        raise RuntimeError(f"Could not create unique filename for {path.name}")


class CastelliImageDownloaderScreen(CastelliUrlGetterScreen):
    def __init__(self, main_window):
        self._output_dir = ""
        super().__init__(main_window)
        self._worker: CastelliImageDownloaderWorker | None = None

    def _build_ui(self):
        super()._build_ui()

        self._export_btn.setIcon(FluentIcon.FOLDER)
        try:
            self._export_btn.clicked.disconnect()
        except Exception:
            pass
        self._export_btn.clicked.connect(self._browse_output_folder)
        self._export_btn.setEnabled(True)

        self._table.setColumnCount(5)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self._table.setColumnWidth(1, 170)
        self._table.setColumnWidth(3, 110)

    def retranslate_ui(self):
        self._title.setText(self.tr("castelliimages.title"))
        self._subtitle.setText(self.tr("castelliimages.subtitle"))
        self._browse_btn.setText(self.tr("castelliimages.browse_excel"))
        self._start_btn.setText(self.tr("castelliimages.start"))
        self._export_btn.setText(self.tr("castelliimages.output"))
        self._table.setHorizontalHeaderLabels([
            self.tr("castelliimages.col.index"),
            self.tr("castelliimages.col.code"),
            self.tr("castelliimages.col.url"),
            self.tr("castelliimages.col.status"),
            self.tr("castelliimages.col.folder"),
        ])
        if not self._output_dir:
            self._file_label.setText(self.tr("castelliimages.no_output"))

    def _browse_output_folder(self):
        folder = QFileDialog.getExistingDirectory(self, self.tr("castelliimages.output_title"), "")
        if folder:
            self._output_dir = folder
            file_part = os.path.basename(self._file_path) if self._file_path else self.tr("castelliimages.no_excel")
            self._file_label.setText(f"{file_part} -> {folder}")
            self._start_btn.setEnabled(bool(self._rows))

    def _load_file(self, path: str):
        try:
            wb = openpyxl.load_workbook(path, read_only=True)
            ws = wb.active
            rows: list[dict[str, str]] = []

            for excel_row in ws.iter_rows(min_row=1, values_only=True):
                values = [str(v).strip() for v in excel_row if v is not None and str(v).strip()]
                if len(values) < 2:
                    continue

                lower_values = {v.lower() for v in values}
                if lower_values & {"code", "product code", "sku"} and lower_values & {"url", "link", "product url"}:
                    continue

                url = next((v for v in values if v.lower().startswith(("http://", "https://"))), "")
                code = next((v for v in values if v != url), "")
                if not code or not url:
                    continue

                rows.append({"code": code, "url": url})
            wb.close()

            if not rows:
                InfoBar.warning(
                    self.tr("common.error"),
                    self.tr("castelliimages.no_rows"),
                    parent=self,
                    position=InfoBarPosition.TOP,
                    duration=3000,
                )
                return

            self._rows = rows
            self._file_path = path
            label = os.path.basename(path)
            if self._output_dir:
                label = f"{label} -> {self._output_dir}"
            self._file_label.setText(label)
            self._table.setRowCount(len(rows))

            for idx, row in enumerate(rows):
                self._table.setItem(idx, 0, QTableWidgetItem(str(idx + 1)))
                self._table.setItem(idx, 1, QTableWidgetItem(row["code"]))
                self._table.setItem(idx, 2, QTableWidgetItem(row["url"]))
                status = QTableWidgetItem(self.tr("batchdesc.status.pending"))
                status.setForeground(QColor(get_text_color(isDarkTheme(), "secondary")))
                self._table.setItem(idx, 3, status)
                self._table.setItem(idx, 4, QTableWidgetItem(""))

            self._start_btn.setEnabled(bool(self._output_dir))
            self._drop_zone.setVisible(False)
            self._progress_label.setText(self.tr("castelliimages.loaded", count=len(rows)))
        except Exception as e:
            InfoBar.error(
                self.tr("common.error"),
                str(e),
                parent=self,
                position=InfoBarPosition.TOP,
                duration=5000,
            )

    def _on_start_stop(self):
        if self._worker and self._worker.isRunning():
            self._worker.request_stop()
            self._start_btn.setEnabled(False)
            return

        if not self._rows:
            return

        if not self._output_dir:
            InfoBar.warning(
                self.tr("common.error"),
                self.tr("castelliimages.no_output_selected"),
                parent=self,
                position=InfoBarPosition.TOP,
                duration=3000,
            )
            return

        for idx in range(self._table.rowCount()):
            status = QTableWidgetItem(self.tr("batchdesc.status.pending"))
            status.setForeground(QColor(get_text_color(isDarkTheme(), "secondary")))
            self._table.setItem(idx, 3, status)
            self._table.setItem(idx, 4, QTableWidgetItem(""))

        self._start_btn.setText(self.tr("castelliimages.stop"))
        self._start_btn.setIcon(FluentIcon.CLOSE)
        self._browse_btn.setEnabled(False)
        self._export_btn.setEnabled(False)

        self._worker = CastelliImageDownloaderWorker(self._rows, self._output_dir)
        self._worker.row_update.connect(self._on_row_update)
        self._worker.progress_update.connect(self._on_progress)
        self._worker.done.connect(self._on_done)
        self._worker.log.connect(lambda msg: print(f"[CastelliImageDownloader] {msg}"))
        if hasattr(self.main, "track_worker"):
            self.main.track_worker(
                self._worker,
                "image_tool",
                "castelli_images",
                total=len(self._rows),
                output_path=self._output_dir,
            )
        self._worker.start()

    def _on_row_update(self, row: int, status: str, count: str, folder: str):
        item = QTableWidgetItem(status if not count else f"{status} ({count})")
        if status == "Done":
            item.setForeground(QColor(get_status_text_color("success", isDarkTheme())))
        elif status in ("Downloading", "Skipped"):
            item.setForeground(QColor(get_status_text_color("warning", isDarkTheme())))
        else:
            item.setForeground(QColor(get_status_text_color("error", isDarkTheme())))

        self._table.setItem(row, 3, item)
        self._table.setItem(row, 4, QTableWidgetItem(folder))
        self._table.scrollToItem(item)

    def _on_progress(self, current: int, total: int):
        self._progress_label.setText(self.tr("castelliimages.progress", current=current, total=total))

    def _on_done(self, ok_count: int, error_count: int):
        self._start_btn.setText(self.tr("castelliimages.start"))
        self._start_btn.setIcon(FluentIcon.PLAY)
        self._start_btn.setEnabled(True)
        self._browse_btn.setEnabled(True)
        self._export_btn.setEnabled(True)

        total = ok_count + error_count
        text = self.tr("castelliimages.done", done=ok_count, errors=error_count, total=total)
        self._progress_label.setText(text)
        InfoBar.success(
            self.tr("castelliimages.done_title"),
            text,
            parent=self,
            position=InfoBarPosition.TOP,
            duration=5000,
        )
        show_file_saved_bar(self, self.tr("common.success"), self.tr("castelliimages.exported"), self._output_dir)
