# Standard library
import os
import sys
import time
import traceback
from datetime import datetime
from typing import List, Dict, Tuple, Optional

# Local
from uploaderFactory import getUploaderClass

class BatchProcessor:
    """
    Processes multiple bikes sequentially with progress tracking
    """

    def __init__(self, driver, db_manager, logger=None):
        self.driver = driver
        self.db = db_manager
        self.logger = logger
        self.queue = []  # List of {brand, code, url}
        self.current_index = 0
        self.results = []  # List of {code, status, error}
        self.batch_id = None
        self.is_processing = False
        self.should_stop = False
    
    def _log(self, message, **context):
        if self.logger:
            self.logger.log("BatchProcessor", message, **context)

    def _log_error(self, message, exception=None, **context):
        if not self.logger:
            return
        if hasattr(self.logger, "error"):
            self.logger.error("BatchProcessor", message, exception=exception, **context)
        else:
            # Fallback if a custom logger is injected.
            if exception is not None:
                context = dict(context)
                context.setdefault("exception", f"{type(exception).__name__}: {exception}")
            self.logger.log("BatchProcessor", message, **context)
    
    # Utilities/BatchProcessor.py
    # Function: add_to_queue

    def add_to_queue(self, brand, product_code, url_or_code, brand_options=None):
        brand_options = brand_options or {}

        # --- NORMALIZE DESCRIPTION ---
        description_name = brand_options.get("description_name")
        if isinstance(description_name, str):
            description_name = description_name.strip()
            if description_name == "":
                description_name = None

        # --- NORMALIZE DISCLAIMER ---
        raw_disclaimer = brand_options.get("append_disclaimer", False)

        if isinstance(raw_disclaimer, str):
            raw_disclaimer = raw_disclaimer.strip().lower()
            append_disclaimer = raw_disclaimer in ("yes", "true", "1")
        else:
            append_disclaimer = bool(raw_disclaimer)

        # --- NORMALIZE ORDER NOTE (SHORT DESCRIPTION) ---
        raw_order_note = brand_options.get("append_order_note", False)

        if isinstance(raw_order_note, str):
            raw_order_note = raw_order_note.strip().lower()
            append_order_note = raw_order_note in ("yes", "true", "1")
        else:
            append_order_note = bool(raw_order_note)

        # --- PRESERVE ALL BRAND OPTIONS ---
        # Start with all original options (preserves brand-specific options)
        normalized_brand_options = dict(brand_options)

        # Override with normalized values
        normalized_brand_options["description_name"] = description_name
        normalized_brand_options["append_disclaimer"] = append_disclaimer
        normalized_brand_options["append_order_note"] = append_order_note

        # This preserves brand-specific options like:
        # - frameset_only (Pinarello)
        # - variant_index (Rascal)
        # - Any future brand-specific options

        self.queue.append({
            "brand": brand,
            "product_code": product_code,
            "url_or_code": url_or_code,
            "brand_options": normalized_brand_options
        })

        self._log(
            "Item added to queue",
            brand=brand,
            code=product_code,
            description=description_name,
            disclaimer=append_disclaimer,
            order_note=append_order_note,
        )


    
    def clear_queue(self):
        """Clear all items from queue"""
        self.queue = []
        self.current_index = 0
        self.results = []
        self._log("Queue cleared")
    
    def get_queue_size(self):
        """Get total items in queue"""
        return len(self.queue)
    
    def get_progress(self) -> Tuple[int, int, float]:
        """
        Get current progress
        Returns: (current, total, percentage)
        """
        total = len(self.queue)
        # `current_index` is treated as the number of items completed.
        current = self.current_index
        percentage = (current / total * 100) if total > 0 else 0
        return current, total, percentage
    
    # Utilities/BatchProcessor.py
    # Function: start_batch

    def start_batch(self, uploader_factory):
        """
        Start processing batch

        Args:
            uploader_factory: Function that takes
                (driver, brand, code, url, db, batch_id, brand_options)
                and returns uploader instance
        """
        if self.is_processing:
            raise RuntimeError("Batch already processing")

        if not self.queue:
            raise ValueError("Queue is empty")

        self.batch_id = f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        total = len(self.queue)
        self._log("Starting batch", batch_id=self.batch_id, items=total)

        self.is_processing = True
        self.should_stop = False
        self.current_index = 0
        self.results = []

        for idx, item in enumerate(self.queue):
            if self.should_stop:
                self._log("Batch processing stopped by user", at_index=idx)
                break

            # Progress semantics: current_index == completed count.
            self.current_index = idx
            self._log(
                "Processing item",
                index=idx + 1,
                total=total,
                brand=item['brand'],
                code=item['product_code']
            )

            try:
                started = time.perf_counter()
                uploader = uploader_factory(
                    self.driver,
                    item['brand'],
                    item['product_code'],
                    item['url_or_code'],
                    self.db,
                    self.batch_id,
                    item.get('brand_options', {})
                )

                uploader.run()

                duration_seconds = time.perf_counter() - started

                self.current_index = idx + 1

                self.results.append({
                    'code': item['product_code'],
                    'brand': item['brand'],
                    'status': 'success',
                    'error': None,
                    'duration_seconds': duration_seconds,
                    'traceback': None,
                })
                self._log("Item succeeded", code=item['product_code'])

            except Exception as e:
                duration_seconds = None
                try:
                    duration_seconds = time.perf_counter() - started
                except Exception:
                    pass

                error_msg = str(e)
                tb = None
                try:
                    tb = traceback.format_exc()
                except Exception:
                    pass

                self.results.append({
                    'code': item['product_code'],
                    'brand': item['brand'],
                    'status': 'failed',
                    'error': error_msg,
                    'duration_seconds': duration_seconds,
                    'traceback': tb,
                })
                self._log_error(
                    "Item failed",
                    exception=e,
                    code=item['product_code'],
                    error=error_msg,
                )

        self.current_index = len(self.queue)
        self.is_processing = False

        success_count = sum(1 for r in self.results if r['status'] == 'success')
        failed_count = sum(1 for r in self.results if r['status'] == 'failed')

        self._log(
            "Batch complete",
            batch_id=self.batch_id,
            success=success_count,
            failed=failed_count
        )

        return {
            'batch_id': self.batch_id,
            'total': len(self.queue),
            'success': success_count,
            'failed': failed_count,
            'results': self.results
        }

    
    def stop_batch(self):
        """Request to stop batch processing after current item"""
        self.should_stop = True
        self._log("Stop requested")

    def process_batch(self, items, master_password=None):
        """Convenience wrapper used by GUI to process a batch list.

        Args:
            items: List of dicts with keys: brand, code, url, description_name, frameset_only, append_disclaimer
            master_password: Optional master password (used to decrypt external brand credentials).
        """
        self.clear_queue()

        for it in items:
            brand_options = {
                "description_name": it.get("description_name") or None,
                "frameset_only": bool(it.get("frameset_only")) if it.get("frameset_only") is not None else False,
                "append_disclaimer": bool(it.get("append_disclaimer")) if it.get("append_disclaimer") is not None else False,
                "append_order_note": bool(it.get("append_order_note")) if it.get("append_order_note") is not None else False,
            }
            self.add_to_queue(it.get("brand"), it.get("code"), it.get("url"), brand_options=brand_options)

        # Add project root to path if not already there (for uploaderFactory import)
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if project_root not in sys.path:
            sys.path.insert(0, project_root)

        def uploader_factory(driver, brand, code, url_or_code, db, batch_id, brand_options):
            uploader_class = getUploaderClass(brand)
            return uploader_class(
                driver=driver,
                brand_name=brand,
                product_code=code,
                url_or_code=url_or_code,
                db_manager=db,
                brand_options=brand_options,
                logger=self.logger,
                batch_id=batch_id,
                master_password=master_password,
            )

        return self.start_batch(uploader_factory)
    
    def get_results(self) -> List[Dict[str, any]]:
        """Get current results"""
        return self.results
    
    def get_failed_items(self) -> List[Dict[str, any]]:
        """Get list of failed items for retry/export"""
        return [r for r in self.results if r['status'] == 'failed']