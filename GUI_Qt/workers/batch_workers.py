"""
GUI_Qt/workers/batch_workers.py

All batch worker QThread classes relocated from the individual batch screen files.
Workers are kept unchanged — only imports are adjusted.

Workers:
  - BatchUploadWorker / ParallelBatchUploadWorker
  - BatchDescriptionsWorker / ParallelBatchDescriptionsWorker
  - BatchTitlesWorker / ParallelBatchTitlesWorker
"""

from __future__ import annotations

import json
import time
from datetime import datetime

from PySide6.QtCore import QThread, Signal

from Config.Selectors import ProductEditorSelectors, ProductListSelectors
from Managers.DescriptionManager import DescriptionManager
from Utilities.ProductNavigationHandler import ProductNavigationHandler
from Utilities.WebIntercationHandler import WebInteractionHandler


# ---------------------------------------------------------------------------
# Helpers shared across workers
# ---------------------------------------------------------------------------

def _ensure_products_page(driver) -> None:
    """Navigate the sidebar to the Products list so the product table is visible."""
    try:
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.support.ui import WebDriverWait

        products_link = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located(ProductListSelectors.NAV_PRODUCTS)
        )
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", products_link)
        products_link.click()
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located(ProductListSelectors.PRODUCT_TABLE)
        )
    except Exception:
        pass


def _calc_eta(processed_times: list[float], idx: int, total: int):
    """Return (speed, eta_seconds) or None if not enough data."""
    if len(processed_times) < 2:
        return None
    recent = processed_times[1:]
    avg = sum(recent) / len(recent)
    remaining = total - idx
    eta = avg * remaining
    speed = 1.0 / avg if avg > 0 else 0
    return speed, eta


# ============================================================================
# Upload workers
# ============================================================================

class BatchUploadWorker(QThread):
    """Sequential batch upload worker."""

    row_update = Signal(int, str, str)
    log = Signal(str, str)
    done = Signal(int, int)
    progress_update = Signal(int, int, float, float)

    def __init__(self, rows_data, main_window, master_password=None, table_row_indices=None):
        super().__init__()
        self.rows_data = rows_data
        self.main_window = main_window
        self.master_password = master_password
        self.table_row_indices = table_row_indices
        self._stop = False
        self._processed_times: list[float] = []

    def stop(self):
        self._stop = True

    def run(self):
        from Utilities.BatchProcessor import BatchProcessor

        driver = getattr(self.main_window, "driver", None)
        if driver is None:
            for idx in range(len(self.rows_data)):
                table_row = self.table_row_indices[idx] if self.table_row_indices else idx
                self.row_update.emit(table_row, "✗ Failed", "No browser session")
            self.done.emit(0, len(self.rows_data))
            return

        batch_processor = BatchProcessor(
            driver=driver,
            db_manager=self.main_window.db,
            logger=self.main_window.logger,
        )

        ok = 0
        total = len(self.rows_data)

        for idx, row_data in enumerate(self.rows_data):
            if self._stop:
                break

            table_row = self.table_row_indices[idx] if self.table_row_indices else idx
            item_start = time.perf_counter()

            try:
                self.row_update.emit(table_row, "Processing...", "")
                self.log.emit("BatchUpload", f"Processing {row_data['code']} ({idx + 1}/{total})")

                items = [{
                    "brand": row_data["brand"],
                    "code": row_data["code"],
                    "url": row_data["url"],
                    "description_name": row_data.get("description_name"),
                    "frameset_only": row_data.get("frameset_only", False),
                    "append_disclaimer": row_data.get("append_disclaimer", False),
                    "attribute_values": row_data.get("attribute_values", []),
                }]

                result = batch_processor.process_batch(items, master_password=self.master_password)

                if result and result.get("success", 0) > 0:
                    self.row_update.emit(table_row, "✓ Success", "")
                    ok += 1
                else:
                    failed = result.get("results", [])
                    error_msg = failed[0].get("error", "Unknown error") if failed else "Unknown error"
                    self.row_update.emit(table_row, "✗ Failed", error_msg)
            except Exception as e:
                self.row_update.emit(table_row, "✗ Failed", str(e))
                self.log.emit("BatchUpload", f"Error on row {idx}: {e}")

            dur = time.perf_counter() - item_start
            self._processed_times.append(dur)
            eta = _calc_eta(self._processed_times, idx + 1, total)
            if eta:
                self.progress_update.emit(idx + 1, total, eta[0], eta[1])

        self.done.emit(ok, total)


class ParallelBatchUploadWorker(QThread):
    """Parallel batch upload using browser session pool."""

    row_update = Signal(int, str, str)
    log = Signal(str, str)
    done = Signal(int, int)
    session_status = Signal(dict)

    def __init__(self, rows_data, session_manager, main_window, master_password=None, table_row_indices=None):
        super().__init__()
        self.rows_data = rows_data
        self.session_manager = session_manager
        self.main_window = main_window
        self.master_password = master_password
        self.table_row_indices = table_row_indices or list(range(len(rows_data)))
        self._stop = False
        self._lock = __import__("threading").Lock()
        self._ok_count = 0
        self._work_index = 0

    def stop(self):
        self._stop = True

    def run(self):
        import threading

        if not self.session_manager or not self.session_manager.is_ready():
            for table_row in self.table_row_indices:
                self.row_update.emit(table_row, "✗ Failed", "Session pool not available")
            self.done.emit(0, len(self.rows_data))
            return

        total = len(self.rows_data)
        pool_size = self.session_manager.pool_size
        self.log.emit("ParallelBatchUpload", f"Starting parallel processing with {pool_size} browsers")

        threads = []
        for wid in range(pool_size):
            t = threading.Thread(target=self._worker_thread, args=(wid,))
            t.daemon = True
            threads.append(t)
            t.start()
        for t in threads:
            t.join()

        self.log.emit("ParallelBatchUpload", f"Completed. Success: {self._ok_count}/{total}")
        self.done.emit(self._ok_count, total)

    def _worker_thread(self, worker_id: int):
        from Utilities.BatchProcessor import BatchProcessor

        while not self._stop:
            with self._lock:
                if self._work_index >= len(self.rows_data):
                    break
                idx = self._work_index
                self._work_index += 1

            row_data = self.rows_data[idx]
            table_row = self.table_row_indices[idx]

            session = self.session_manager.acquire_session(timeout=60.0)
            if session is None:
                self.row_update.emit(table_row, "✗ Failed", "Could not acquire browser session")
                continue

            try:
                self.row_update.emit(table_row, "Processing...", "")
                self.log.emit("ParallelWorker", f"Worker {worker_id} processing {row_data['code']} (session {session.session_id})")
                self.session_status.emit(self.session_manager.get_session_stats())

                bp = BatchProcessor(
                    driver=session.driver,
                    db_manager=self.main_window.db,
                    logger=self.main_window.logger,
                )

                items = [{
                    "brand": row_data["brand"],
                    "code": row_data["code"],
                    "url": row_data["url"],
                    "description_name": row_data.get("description_name"),
                    "frameset_only": row_data.get("frameset_only", False),
                    "append_disclaimer": row_data.get("append_disclaimer", False),
                    "attribute_values": row_data.get("attribute_values", []),
                }]

                result = bp.process_batch(items, master_password=self.master_password)

                if result and result.get("success", 0) > 0:
                    self.row_update.emit(table_row, "✓ Success", "")
                    with self._lock:
                        self._ok_count += 1
                else:
                    failed = result.get("results", [])
                    error_msg = failed[0].get("error", "Unknown error") if failed else "Unknown error"
                    self.row_update.emit(table_row, "✗ Failed", error_msg)
                    session.error_count += 1
            except Exception as e:
                self.row_update.emit(table_row, "✗ Failed", str(e))
                self.log.emit("ParallelWorker", f"Worker {worker_id} error: {e}")
                session.error_count += 1
                if session.error_count >= 3:
                    self.log.emit("ParallelWorker", f"Resetting session {session.session_id} due to errors")
                    self.session_manager.reset_session(session)
            finally:
                self.session_manager.release_session(session)
                self.session_status.emit(self.session_manager.get_session_stats())


# ============================================================================
# Descriptions workers
# ============================================================================

class BatchDescriptionsWorker(QThread):
    """Sequential batch descriptions worker."""

    row_update = Signal(int, str, str)
    log = Signal(str)
    done = Signal(int, int)
    progress_update = Signal(int, int, float, float)

    def __init__(self, main_window, items: list[dict]):
        super().__init__()
        self.main = main_window
        self.items = items
        self._processed_times: list[float] = []

    def run(self):
        tr = self.main.i18n.tr
        driver = getattr(self.main, "driver", None)
        if driver is None:
            for it in self.items:
                self.row_update.emit(it["row"], tr("batchdesc.status.failed"), tr("batchdesc.no_session"))
            self.done.emit(0, len(self.items))
            return

        desc_manager = DescriptionManager(self.main.db, logger=self.main.logger)
        nav = ProductNavigationHandler(driver, logger=self.main.logger)
        web = WebInteractionHandler(driver)

        ok = 0
        total = len(self.items)
        batch_id = f"batchdesc_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        for idx, it in enumerate(self.items, start=1):
            row = it["row"]
            brand = it["brand"]
            code = it["code"]
            desc = it["description"]
            disclaimer = bool(it.get("append_disclaimer"))

            self.row_update.emit(row, tr("batchdesc.status.running"), "")
            self.log.emit(tr("batchdesc.progress.open", current=idx, total=total, code=code))

            t0 = time.perf_counter()
            try:
                _ensure_products_page(driver)
                nav.navigate_to_product(brand, code)

                if desc:
                    self.log.emit(tr("batchdesc.progress.upload", current=idx, total=total, code=code))
                    uploaded = desc_manager.upload_description(
                        driver, product_code=code, name=desc, append_disclaimer=disclaimer,
                    )
                    if not uploaded:
                        self.row_update.emit(row, tr("batchdesc.status.failed"), tr("batchdesc.item.failed_upload"))
                        self._record_history(batch_id, brand, code, desc, disclaimer, t0, "failed", "upload_description", tr("batchdesc.item.failed_upload"))
                        continue

                # Focus title field before saving
                try:
                    from selenium.webdriver.support.ui import WebDriverWait
                    from selenium.webdriver.support import expected_conditions as EC
                    from Config.LanguageConfig import LANG_CODE_TO_PLATFORM_ID
                    last_lang_id = LANG_CODE_TO_PLATFORM_ID["lv"]
                    title_field = WebDriverWait(driver, 3).until(
                        EC.presence_of_element_located(ProductEditorSelectors.name_field(last_lang_id))
                    )
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", title_field)
                    try:
                        title_field.click()
                    except Exception:
                        driver.execute_script("arguments[0].click();", title_field)
                except Exception:
                    pass

                self.log.emit(tr("batchdesc.progress.save", current=idx, total=total, code=code))
                web.save_information()
                time.sleep(0.5)

                ok += 1
                self.row_update.emit(row, tr("batchdesc.status.ok"), "")
                self._record_history(batch_id, brand, code, desc, disclaimer, t0, "success")
            except Exception as e:
                self.row_update.emit(row, tr("batchdesc.status.failed"), str(e))
                self._record_history(batch_id, brand, code, desc, disclaimer, t0, "failed", "batch_descriptions", str(e))

            dur = time.perf_counter() - t0
            self._processed_times.append(dur)
            eta = _calc_eta(self._processed_times, idx, total)
            if eta:
                self.progress_update.emit(idx, total, eta[0], eta[1])

        self.done.emit(ok, total)

    def _record_history(self, batch_id, brand, code, desc, disclaimer, t0, status, failed_stage=None, error_msg=None):
        try:
            details = {
                "workflow": "batch_descriptions",
                "batch_id": batch_id,
                "append_disclaimer": disclaimer,
                "description_template": desc or None,
            }
            params = [brand, code, None, status]
            sql = """INSERT INTO processing_history
                     (brand, product_code, url_or_code, status"""
            if error_msg:
                sql += ", error_message"
                params.append(error_msg)
            sql += """, duration_seconds, failed_stage, batch_id, details_json, processed_at)
                     VALUES (""" + ", ".join(["?"] * (len(params) + 4)) + ")"
            params.extend([
                float(time.perf_counter() - t0),
                failed_stage,
                batch_id,
                json.dumps(details, ensure_ascii=False),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ])
            self.main.db.conn.execute(sql, params)
            self.main.db.conn.commit()
        except Exception:
            pass


class ParallelBatchDescriptionsWorker(QThread):
    """Parallel batch descriptions using browser session pool."""

    row_update = Signal(int, str, str)
    log = Signal(str)
    done = Signal(int, int)
    session_status = Signal(dict)

    def __init__(self, main_window, session_manager, items: list[dict]):
        super().__init__()
        self.main = main_window
        self.session_manager = session_manager
        self.items = items
        self._stop = False
        self._lock = __import__("threading").Lock()
        self._ok_count = 0
        self._work_index = 0
        self._batch_id = f"batchdesc_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    def stop(self):
        self._stop = True

    def run(self):
        import threading

        if not self.session_manager or not self.session_manager.is_ready():
            tr = self.main.i18n.tr
            for it in self.items:
                self.row_update.emit(it["row"], tr("batchdesc.status.failed"), "Session pool not available")
            self.done.emit(0, len(self.items))
            return

        total = len(self.items)
        pool_size = self.session_manager.pool_size
        self.log.emit(f"Starting parallel processing with {pool_size} browsers")

        threads = []
        for wid in range(pool_size):
            t = threading.Thread(target=self._worker_thread, args=(wid,))
            t.daemon = True
            threads.append(t)
            t.start()
        for t in threads:
            t.join()

        self.log.emit(f"Completed. Success: {self._ok_count}/{total}")
        self.done.emit(self._ok_count, total)

    def _worker_thread(self, worker_id: int):
        tr = self.main.i18n.tr

        while not self._stop:
            with self._lock:
                if self._work_index >= len(self.items):
                    break
                idx = self._work_index
                self._work_index += 1

            it = self.items[idx]
            row, brand, code = it["row"], it["brand"], it["code"]
            desc = it["description"]
            disclaimer = bool(it.get("append_disclaimer"))
            t0 = time.perf_counter()

            session = self.session_manager.acquire_session(timeout=60.0)
            if session is None:
                self.row_update.emit(row, tr("batchdesc.status.failed"), "Could not acquire browser session")
                continue

            try:
                self.row_update.emit(row, tr("batchdesc.status.running"), "")
                self.log.emit(tr("batchdesc.progress.open", current=idx + 1, total=len(self.items), code=code))
                self.session_status.emit(self.session_manager.get_session_stats())

                desc_manager = DescriptionManager(self.main.db, logger=self.main.logger)
                nav = ProductNavigationHandler(session.driver, logger=self.main.logger)
                web = WebInteractionHandler(session.driver)

                _ensure_products_page(session.driver)
                nav.navigate_to_product(brand, code)

                if desc:
                    self.log.emit(tr("batchdesc.progress.upload", current=idx + 1, total=len(self.items), code=code))
                    uploaded = desc_manager.upload_description(
                        session.driver, product_code=code, name=desc, append_disclaimer=disclaimer,
                    )
                    if not uploaded:
                        self.row_update.emit(row, tr("batchdesc.status.failed"), tr("batchdesc.item.failed_upload"))
                        continue

                # Focus title field before saving
                try:
                    from selenium.webdriver.support.ui import WebDriverWait
                    from selenium.webdriver.support import expected_conditions as EC
                    from Config.LanguageConfig import LANG_CODE_TO_PLATFORM_ID
                    last_lang_id = LANG_CODE_TO_PLATFORM_ID["lv"]
                    title_field = WebDriverWait(session.driver, 3).until(
                        EC.presence_of_element_located(ProductEditorSelectors.name_field(last_lang_id))
                    )
                    session.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", title_field)
                    try:
                        title_field.click()
                    except Exception:
                        session.driver.execute_script("arguments[0].click();", title_field)
                except Exception:
                    pass

                self.log.emit(tr("batchdesc.progress.save", current=idx + 1, total=len(self.items), code=code))
                web.save_information()
                time.sleep(0.5)

                self.row_update.emit(row, tr("batchdesc.status.ok"), "")
                with self._lock:
                    self._ok_count += 1
            except Exception as e:
                self.row_update.emit(row, tr("batchdesc.status.failed"), str(e))
                session.error_count += 1
                if session.error_count >= 3:
                    self.log.emit(f"Resetting session {session.session_id} due to errors")
                    self.session_manager.reset_session(session)
            finally:
                self.session_manager.release_session(session)
                self.session_status.emit(self.session_manager.get_session_stats())


# ============================================================================
# Titles workers
# ============================================================================

def _set_title(driver, main_window, lang_code: str, title: str) -> None:
    """Set a product title for a specific language via Selenium."""
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait
    from Config.LanguageConfig import LANG_CODE_TO_PLATFORM_ID, SUPPORTED_LANGUAGES
    from Managers.FeatureUploader.LanguageSwitcher import LanguageSwitcher

    if lang_code not in SUPPORTED_LANGUAGES:
        raise Exception(f"Unsupported language: {lang_code}")

    try:
        switcher = LanguageSwitcher(driver, logger=getattr(main_window, "logger", None))
        switcher.switchTo(lang_code)
        time.sleep(0.4)
    except Exception:
        pass

    lang_id_map = LANG_CODE_TO_PLATFORM_ID
    el = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located(ProductEditorSelectors.name_field(lang_id_map[lang_code]))
    )
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)

    try:
        driver.execute_script(
            """
            const el = arguments[0];
            const value = arguments[1];
            el.focus();
            el.value = value;
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
            """,
            el,
            title,
        )
        return
    except Exception:
        pass

    try:
        el.click()
    except Exception:
        driver.execute_script("arguments[0].click();", el)

    try:
        el.send_keys(Keys.CONTROL, "a")
        el.send_keys(Keys.BACKSPACE)
        el.send_keys(title)
    except Exception:
        try:
            el.clear()
        except Exception:
            pass
        el.send_keys(title)


class BatchTitlesWorker(QThread):
    """Sequential batch titles worker."""

    row_update = Signal(int, str, str)
    log = Signal(str)
    done = Signal(int, int)
    progress_update = Signal(int, int, float, float)

    def __init__(self, main_window, items: list[dict]):
        super().__init__()
        self.main = main_window
        self.items = items
        self._processed_times: list[float] = []

    def run(self):
        tr = self.main.i18n.tr
        driver = getattr(self.main, "driver", None)
        if driver is None:
            for it in self.items:
                self.row_update.emit(it["row"], tr("batchtitle.status.failed"), tr("batchtitle.no_session"))
            self.done.emit(0, len(self.items))
            return

        nav = ProductNavigationHandler(driver, logger=self.main.logger)
        web = WebInteractionHandler(driver)

        ok = 0
        total = len(self.items)
        batch_id = f"batchtitle_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        for idx, it in enumerate(self.items, start=1):
            row = it["row"]
            brand, code = it["brand"], it["code"]
            title_lt = it.get("title_lt") or ""
            title_en = it.get("title_en") or ""

            self.row_update.emit(row, tr("batchtitle.status.running"), "")
            self.log.emit(tr("batchtitle.progress.open", current=idx, total=total, code=code))

            t0 = time.perf_counter()
            try:
                _ensure_products_page(driver)
                nav.navigate_to_product(brand, code)

                if title_lt:
                    self.log.emit(tr("batchtitle.progress.fill", current=idx, total=total, code=code, lang="LT"))
                    _set_title(driver, self.main, "lt", title_lt)
                if title_en:
                    self.log.emit(tr("batchtitle.progress.fill", current=idx, total=total, code=code, lang="EN"))
                    _set_title(driver, self.main, "en", title_en)

                self.log.emit(tr("batchtitle.progress.save", current=idx, total=total, code=code))
                web.save_information()
                time.sleep(0.5)

                ok += 1
                self.row_update.emit(row, tr("batchtitle.status.ok"), "")
                self._record_history(batch_id, brand, code, title_lt, title_en, t0, "success")
            except Exception as e:
                self.row_update.emit(row, tr("batchtitle.status.failed"), str(e))
                self._record_history(batch_id, brand, code, title_lt, title_en, t0, "failed", "batch_titles", str(e))

            dur = time.perf_counter() - t0
            self._processed_times.append(dur)
            eta = _calc_eta(self._processed_times, idx, total)
            if eta:
                self.progress_update.emit(idx, total, eta[0], eta[1])

        self.done.emit(ok, total)

    def _record_history(self, batch_id, brand, code, title_lt, title_en, t0, status, failed_stage=None, error_msg=None):
        try:
            details = {
                "workflow": "batch_titles",
                "batch_id": batch_id,
                "set_lt": bool(title_lt),
                "set_en": bool(title_en),
            }
            params = [brand, code, None, status]
            sql = """INSERT INTO processing_history
                     (brand, product_code, url_or_code, status"""
            if error_msg:
                sql += ", error_message"
                params.append(error_msg)
            sql += """, duration_seconds, failed_stage, batch_id, details_json, processed_at)
                     VALUES (""" + ", ".join(["?"] * (len(params) + 4)) + ")"
            params.extend([
                float(time.perf_counter() - t0),
                failed_stage,
                batch_id,
                json.dumps(details, ensure_ascii=False),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            ])
            self.main.db.conn.execute(sql, params)
            self.main.db.conn.commit()
        except Exception:
            pass


class ParallelBatchTitlesWorker(QThread):
    """Parallel batch titles using browser session pool."""

    row_update = Signal(int, str, str)
    log = Signal(str)
    done = Signal(int, int)
    session_status = Signal(dict)

    def __init__(self, main_window, session_manager, items: list[dict]):
        super().__init__()
        self.main = main_window
        self.session_manager = session_manager
        self.items = items
        self._stop = False
        self._lock = __import__("threading").Lock()
        self._ok_count = 0
        self._work_index = 0
        self._batch_id = f"batchtitle_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    def stop(self):
        self._stop = True

    def run(self):
        import threading

        if not self.session_manager or not self.session_manager.is_ready():
            tr = self.main.i18n.tr
            for it in self.items:
                self.row_update.emit(it["row"], tr("batchtitle.status.failed"), "Session pool not available")
            self.done.emit(0, len(self.items))
            return

        total = len(self.items)
        pool_size = self.session_manager.pool_size
        self.log.emit(f"Starting parallel processing with {pool_size} browsers")

        threads = []
        for wid in range(pool_size):
            t = threading.Thread(target=self._worker_thread, args=(wid,))
            t.daemon = True
            threads.append(t)
            t.start()
        for t in threads:
            t.join()

        self.log.emit(f"Completed. Success: {self._ok_count}/{total}")
        self.done.emit(self._ok_count, total)

    def _worker_thread(self, worker_id: int):
        tr = self.main.i18n.tr

        while not self._stop:
            with self._lock:
                if self._work_index >= len(self.items):
                    break
                idx = self._work_index
                self._work_index += 1

            it = self.items[idx]
            row, brand, code = it["row"], it["brand"], it["code"]
            title_lt = it.get("title_lt") or ""
            title_en = it.get("title_en") or ""
            t0 = time.perf_counter()

            session = self.session_manager.acquire_session(timeout=60.0)
            if session is None:
                self.row_update.emit(row, tr("batchtitle.status.failed"), "Could not acquire browser session")
                continue

            try:
                self.row_update.emit(row, tr("batchtitle.status.running"), "")
                self.log.emit(tr("batchtitle.progress.open", current=idx + 1, total=len(self.items), code=code))
                self.session_status.emit(self.session_manager.get_session_stats())

                nav = ProductNavigationHandler(session.driver, logger=self.main.logger)
                web = WebInteractionHandler(session.driver)

                _ensure_products_page(session.driver)
                nav.navigate_to_product(brand, code)

                if title_lt:
                    self.log.emit(tr("batchtitle.progress.fill", current=idx + 1, total=len(self.items), code=code, lang="LT"))
                    _set_title(session.driver, self.main, "lt", title_lt)
                if title_en:
                    self.log.emit(tr("batchtitle.progress.fill", current=idx + 1, total=len(self.items), code=code, lang="EN"))
                    _set_title(session.driver, self.main, "en", title_en)

                self.log.emit(tr("batchtitle.progress.save", current=idx + 1, total=len(self.items), code=code))
                web.save_information()
                time.sleep(0.5)

                self.row_update.emit(row, tr("batchtitle.status.ok"), "")
                with self._lock:
                    self._ok_count += 1
            except Exception as e:
                self.row_update.emit(row, tr("batchtitle.status.failed"), str(e))
                session.error_count += 1
                if session.error_count >= 3:
                    self.log.emit(f"Resetting session {session.session_id} due to errors")
                    self.session_manager.reset_session(session)
            finally:
                self.session_manager.release_session(session)
                self.session_status.emit(self.session_manager.get_session_stats())
