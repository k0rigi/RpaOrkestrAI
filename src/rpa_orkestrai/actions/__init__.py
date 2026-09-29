"""Step handlers registered by action type; native libraries load only inside handlers."""

from __future__ import annotations

import importlib
from collections.abc import Callable
from typing import Any

HANDLERS: dict[str, Callable[[Any, dict], Any]] = {}
MODULES = ("inputs", "windows", "screen", "system", "files", "data", "dialogs", "web")


def handler(*action_types: str):
    def register(function):
        for action_type in action_types:
            HANDLERS[action_type] = function
        return function
    return register


_loaded = False


def get(action_type: str) -> Callable[[Any, dict], Any] | None:
    # A module imported on its own (e.g. by the package check) must not stop the others loading.
    global _loaded
    if not _loaded:
        for name in MODULES:
            importlib.import_module(f"{__name__}.{name}")
        _loaded = True
    return HANDLERS.get(action_type)
