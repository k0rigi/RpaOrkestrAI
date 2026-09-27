"""Optional external services with lazy connections."""

from .browser import BrowserService
from .sheets import SheetsService

__all__ = ["BrowserService", "SheetsService"]
