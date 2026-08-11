"""
Browser Session Manager
Manages multiple browser instances for parallel batch processing
"""

from dataclasses import dataclass
from typing import Optional, List, Dict
from threading import Lock, Semaphore
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.edge.service import Service as EdgeService
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.firefox import GeckoDriverManager
from webdriver_manager.microsoft import EdgeChromiumDriverManager


@dataclass
class BrowserSession:
    """Represents a single browser session"""
    session_id: int
    driver: Optional[webdriver.Remote]
    browser_type: str
    is_busy: bool = False
    last_used: float = 0.0
    error_count: int = 0


class BrowserSessionManager:
    """Manages a pool of browser sessions for parallel processing"""

    def __init__(self, browser_type: str = "Chrome", pool_size: int = 2, logger=None):
        """
        Initialize browser session manager

        Args:
            browser_type: Type of browser ("Chrome", "Firefox", "Edge")
            pool_size: Number of browser instances to maintain (1-4)
            logger: Optional logger instance
        """
        self.browser_type = browser_type
        self.pool_size = max(1, min(4, pool_size))
        self.logger = logger

        self.sessions: List[BrowserSession] = []
        self.session_lock = Lock()
        self.semaphore = Semaphore(self.pool_size)

        self._initialized = False
        self._session_initializer = None

    def set_session_initializer(self, callback):
        """Set a callback(driver) used for login on create and reset."""
        self._session_initializer = callback

    def _log(self, message: str, **context):
        """Log a message if logger is available"""
        if self.logger:
            self.logger.log("BrowserSessionManager", message, **context)

    def initialize_pool(self) -> bool:
        """
        Initialize all browser instances in the pool

        Returns:
            True if all browsers initialized successfully, False otherwise
        """
        if self._initialized:
            self._log("Pool already initialized", pool_size=self.pool_size)
            return True

        self._log("Initializing browser pool", browser_type=self.browser_type, pool_size=self.pool_size)

        try:
            for i in range(self.pool_size):
                driver = self._create_driver(i)
                if driver is None:
                    self._log(f"Failed to create driver for session {i}", session_id=i)
                    self.shutdown_all()
                    return False
                if self._session_initializer and not self._session_initializer(driver):
                    try:
                        driver.quit()
                    except Exception:
                        pass
                    self._log(f"Session {i} initialization failed", session_id=i)
                    self.shutdown_all()
                    return False

                session = BrowserSession(
                    session_id=i,
                    driver=driver,
                    browser_type=self.browser_type,
                    is_busy=False,
                    last_used=time.time()
                )
                self.sessions.append(session)
                self._log(f"Created browser session {i}", session_id=i)

            self._initialized = True
            self._log("Browser pool initialized successfully", total_sessions=len(self.sessions))
            return True

        except Exception as e:
            self._log(f"Error initializing pool: {str(e)}", error=str(e))
            self.shutdown_all()
            return False

    def _create_driver(self, session_id: int) -> Optional[webdriver.Remote]:
        """
        Create a single browser driver instance

        Args:
            session_id: ID for this session (used for window positioning)

        Returns:
            WebDriver instance or None if creation failed
        """
        try:
            if self.browser_type == "Chrome":
                options = webdriver.ChromeOptions()
                options.add_experimental_option("excludeSwitches", ["enable-automation"])
                options.add_experimental_option('useAutomationExtension', False)

                # Position windows in a grid pattern
                window_offset = session_id * 50
                options.add_argument(f"--window-position={window_offset},{window_offset}")

                service = ChromeService(ChromeDriverManager().install())
                return webdriver.Chrome(service=service, options=options)

            elif self.browser_type == "Firefox":
                options = webdriver.FirefoxOptions()
                service = FirefoxService(GeckoDriverManager().install())
                return webdriver.Firefox(service=service, options=options)

            elif self.browser_type == "Edge":
                options = webdriver.EdgeOptions()
                options.add_experimental_option("excludeSwitches", ["enable-automation"])

                window_offset = session_id * 50
                options.add_argument(f"--window-position={window_offset},{window_offset}")

                service = EdgeService(EdgeChromiumDriverManager().install())
                return webdriver.Edge(service=service, options=options)

            else:
                self._log(f"Unsupported browser type: {self.browser_type}", browser=self.browser_type)
                return None

        except Exception as e:
            self._log(f"Error creating driver: {str(e)}", session_id=session_id, error=str(e))
            return None

    def acquire_session(self, timeout: float = 30.0) -> Optional[BrowserSession]:
        """
        Acquire an available browser session from the pool

        Args:
            timeout: Maximum time to wait for an available session (seconds)

        Returns:
            BrowserSession if available, None if timeout or pool not initialized
        """
        if not self._initialized:
            self._log("Pool not initialized, cannot acquire session")
            return None

        # Try to acquire from semaphore
        if not self.semaphore.acquire(timeout=timeout):
            self._log("Timeout waiting for available session", timeout=timeout)
            return None

        # Find an available session
        with self.session_lock:
            for session in self.sessions:
                if not session.is_busy:
                    session.is_busy = True
                    session.last_used = time.time()
                    self._log(f"Acquired session {session.session_id}", session_id=session.session_id)
                    return session

        # This should never happen if semaphore is working correctly
        self.semaphore.release()
        self._log("No available session found despite semaphore acquisition")
        return None

    def release_session(self, session: BrowserSession):
        """
        Release a browser session back to the pool

        Args:
            session: The session to release
        """
        if session is None:
            return

        with self.session_lock:
            session.is_busy = False
            self.semaphore.release()
            self._log(f"Released session {session.session_id}", session_id=session.session_id)

    def get_session_stats(self) -> Dict:
        """
        Get statistics about current session pool

        Returns:
            Dictionary with pool statistics
        """
        with self.session_lock:
            busy_count = sum(1 for s in self.sessions if s.is_busy)
            return {
                'total': len(self.sessions),
                'busy': busy_count,
                'available': len(self.sessions) - busy_count,
                'initialized': self._initialized,
                'browser_type': self.browser_type
            }

    def reset_session(self, session: BrowserSession) -> bool:
        """
        Reset a session that encountered an error

        Args:
            session: Session to reset

        Returns:
            True if reset successful, False otherwise
        """
        try:
            self._log(f"Resetting session {session.session_id}", session_id=session.session_id)

            # Close old driver
            if session.driver:
                try:
                    session.driver.quit()
                except Exception:
                    pass

            # Create new driver
            new_driver = self._create_driver(session.session_id)
            if new_driver is None:
                session.driver = None
                return False
            if self._session_initializer and not self._session_initializer(new_driver):
                try:
                    new_driver.quit()
                except Exception:
                    pass
                session.driver = None
                return False

            session.driver = new_driver
            session.error_count = 0
            self._log(f"Session {session.session_id} reset successfully", session_id=session.session_id)
            return True

        except Exception as e:
            self._log(f"Error resetting session: {str(e)}", session_id=session.session_id, error=str(e))
            return False

    def shutdown_all(self):
        """Shutdown all browser sessions and clean up resources"""
        self._log("Shutting down all browser sessions", total=len(self.sessions))

        with self.session_lock:
            for session in self.sessions:
                try:
                    if session.driver:
                        session.driver.quit()
                        self._log(f"Closed session {session.session_id}", session_id=session.session_id)
                except Exception as e:
                    self._log(f"Error closing session {session.session_id}: {str(e)}",
                             session_id=session.session_id, error=str(e))

            self.sessions.clear()
            self._initialized = False

        self._log("All browser sessions shut down")

    def is_ready(self) -> bool:
        """Check if pool is initialized and ready"""
        return (
            self._initialized
            and len(self.sessions) == self.pool_size
            and all(session.driver is not None for session in self.sessions)
        )
