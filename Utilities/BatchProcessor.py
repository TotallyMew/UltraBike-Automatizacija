import time
from datetime import datetime

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
    
    def add_to_queue(self, brand, product_code, url_or_code):
        """Add item to processing queue"""
        self.queue.append({
            'brand': brand,
            'product_code': product_code,
            'url_or_code': url_or_code
        })
        self._log("Item added to queue", brand=brand, code=product_code)
    
    def clear_queue(self):
        """Clear all items from queue"""
        self.queue = []
        self.current_index = 0
        self.results = []
        self._log("Queue cleared")
    
    def get_queue_size(self):
        """Get total items in queue"""
        return len(self.queue)
    
    def get_progress(self):
        """
        Get current progress
        Returns: (current, total, percentage)
        """
        total = len(self.queue)
        current = self.current_index
        percentage = (current / total * 100) if total > 0 else 0
        return current, total, percentage
    
    def start_batch(self, uploader_factory):
        """
        Start processing batch
        
        Args:
            uploader_factory: Function that takes (driver, brand, code, url) 
                            and returns uploader instance
        """
        if self.is_processing:
            raise RuntimeError("Batch already processing")
        
        if not self.queue:
            raise ValueError("Queue is empty")
        
        # Generate batch ID
        self.batch_id = f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self._log("Starting batch", batch_id=self.batch_id, items=len(self.queue))
        
        self.is_processing = True
        self.should_stop = False
        self.current_index = 0
        self.results = []
        
        # Process each item
        for idx, item in enumerate(self.queue):
            if self.should_stop:
                self._log("Batch processing stopped by user", at_index=idx)
                break
            
            self.current_index = idx
            self._log("Processing item", index=idx+1, total=len(self.queue), 
                     brand=item['brand'], code=item['product_code'])
            
            try:
                # Create uploader instance
                uploader = uploader_factory(
                    self.driver,
                    item['brand'],
                    item['product_code'],
                    item['url_or_code'],
                    self.db,
                    self.batch_id  # Pass batch_id to uploader
                )
                
                # Run upload
                uploader.run()
                
                # Record success
                self.results.append({
                    'code': item['product_code'],
                    'brand': item['brand'],
                    'status': 'success',
                    'error': None
                })
                self._log("Item succeeded", code=item['product_code'])
                
            except Exception as e:
                # Record failure
                error_msg = str(e)
                self.results.append({
                    'code': item['product_code'],
                    'brand': item['brand'],
                    'status': 'failed',
                    'error': error_msg
                })
                self._log("Item failed", code=item['product_code'], error=error_msg)
                
                # Continue to next item (don't stop batch)
        
        self.current_index = len(self.queue)  # Mark as complete
        self.is_processing = False
        
        # Summary
        success_count = sum(1 for r in self.results if r['status'] == 'success')
        failed_count = sum(1 for r in self.results if r['status'] == 'failed')
        
        self._log("Batch complete", batch_id=self.batch_id, 
                 success=success_count, failed=failed_count)
        
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
    
    def get_results(self):
        """Get current results"""
        return self.results
    
    def get_failed_items(self):
        """Get list of failed items for retry/export"""
        return [r for r in self.results if r['status'] == 'failed']