"""Desktop adapters import native screen libraries only when used."""

from .controller import DesktopController
from .dialogs import DialogDetector, DialogMatch, DialogRule
from .dropdown import DropdownIterator
from .vision import Match, Vision

__all__ = ["DesktopController", "DialogDetector", "DialogMatch", "DialogRule", "DropdownIterator", "Match", "Vision"]
