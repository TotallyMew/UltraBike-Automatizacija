"""Window-level services kept independent from page widgets."""

from .navigation import NavigationService
from .shutdown import ShutdownService
from .updates import UpdateService
from .errors import ErrorPresentationService

__all__ = [
    "ErrorPresentationService", "NavigationService", "ShutdownService", "UpdateService"
]
