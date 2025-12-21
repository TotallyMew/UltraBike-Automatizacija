import os
from datetime import datetime

class Logger:
    def __init__(self, log_dir=None):
        if log_dir is None:
            from Utilities.AppPaths import get_default_logs_dir
            log_dir = str(get_default_logs_dir())

        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)
        
        # Create new log file for this session
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.log_file = os.path.join(log_dir, f"ultrabike_{timestamp}.log")
        
        # Write session start
        self._write_separator()
        self._write(f"SESSION START: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self._write_separator()
    
    def _write_separator(self):
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
    
    def _write(self, message):
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(message + "\n")
    
    def _format_timestamp(self):
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    
    def log(self, module, message, **context):
        """General log entry with optional context"""
        timestamp = self._format_timestamp()
        log_entry = f"[{timestamp}] [{module}] {message}"
        
        if context:
            log_entry += "\n    Context: " + ", ".join(f"{k}={v}" for k, v in context.items())
        
        self._write(log_entry)
    
    def error(self, module, message, exception=None, **context):
        """Log error with exception details"""
        timestamp = self._format_timestamp()
        log_entry = f"[{timestamp}] [ERROR] [{module}] {message}"
        
        if exception:
            log_entry += f"\n    Exception: {type(exception).__name__}: {str(exception)}"
        
        if context:
            log_entry += "\n    Context: " + ", ".join(f"{k}={v}" for k, v in context.items())
        
        self._write(log_entry)
    
    def start_operation(self, operation_name, **context):
        """Log the start of an operation"""
        self.log("OPERATION", f"START: {operation_name}", **context)
    
    def end_operation(self, operation_name, success=True, **context):
        """Log the end of an operation"""
        status = "SUCCESS" if success else "FAILED"
        self.log("OPERATION", f"END ({status}): {operation_name}", **context)
    
    def session_end(self):
        """Mark end of session"""
        self._write_separator()
        self._write(f"SESSION END: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self._write_separator()