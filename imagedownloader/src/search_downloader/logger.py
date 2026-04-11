# -*- coding: utf-8 -*-
# author: Yabin Zheng
# Email: sczhengyabin@hotmail.com

import sys
from threading import Lock


class Logger(object):
    def __init__(self):
        self.log_hooks = []
        self.saved_stdout = sys.stdout
        self.saved_stderr = sys.stderr
        self._lock = Lock()
        self._initialized = False
        self._redirect_enabled = False

    def initialize(self):
        """Initialize logger and optionally redirect stdout/stderr. 
        Call this after GUI is ready, not during module import."""
        if not self._initialized:
            with self._lock:
                if not self._initialized:
                    self._initialized = True
                    # Don't actually redirect stdout/stderr to avoid segfault issues
                    # Instead, we rely on direct logging via log_hooks
                    self._redirect_enabled = False

    def enable_capture(self):
        """Enable stdout/stderr capture. Use with caution."""
        if self._initialized and not self._redirect_enabled:
            with self._lock:
                try:
                    sys.stdout = self
                    sys.stderr = self
                    self._redirect_enabled = True
                except Exception:
                    pass

    def disable_capture(self):
        """Disable stdout/stderr capture."""
        if self._redirect_enabled:
            with self._lock:
                try:
                    sys.stdout = self.saved_stdout
                    sys.stderr = self.saved_stderr
                    self._redirect_enabled = False
                except Exception:
                    pass

    def log(self, log_str):
        """Log message safely with thread protection."""
        if not log_str or not log_str.strip():
            return
        
        try:
            with self._lock:
                logs = log_str.splitlines()
                for a_log in logs:
                    if a_log.strip():
                        for log_hook in self.log_hooks:
                            try:
                                log_hook(a_log)
                            except Exception:
                                # Prevent logging errors from crashing the app
                                pass
        except Exception:
            # Silently ignore logging errors
            pass

    def write(self, text):
        """Write method required by stdout/stderr protocol."""
        if text and text.strip():
            self.log(text)

    def flush(self):
        """Flush method required by stdout/stderr protocol."""
        try:
            if self._redirect_enabled:
                self.saved_stderr.flush()
        except Exception:
            pass


# Create logger instance but DON'T redirect stdout/stderr at import time
logger = Logger()
