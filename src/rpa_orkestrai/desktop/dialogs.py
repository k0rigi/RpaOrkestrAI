"""Explicit visual/text dialog rules with prioritized, caller-owned handlers."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .controller import DesktopController, Region
from .vision import Match, Vision


@dataclass(frozen=True)
class DialogRule:
    name: str
    action: str
    contains: tuple[str, ...] = ()
    pattern: str | None = None
    template_path: str | Path | None = None
    priority: int = 0
    confidence: float = 0.85

    def __post_init__(self) -> None:
        if not self.name or not self.action:
            raise ValueError("Dialog rules require a name and action.")
        if not self.contains and not self.pattern and not self.template_path:
            raise ValueError("A dialog rule requires a text or visual condition.")
        if isinstance(self.contains, str) or any(not value.strip() for value in self.contains):
            raise ValueError("contains must be a sequence of non-empty words or phrases.")
        if self.pattern:
            re.compile(self.pattern)
        if not 0 < self.confidence <= 1:
            raise ValueError("Dialog confidence must be in (0, 1].")


@dataclass(frozen=True)
class DialogMatch:
    rule: DialogRule
    text: str
    visual_match: Match | None = None


class DialogDetector:
    def __init__(
        self, controller: DesktopController, rules: Sequence[DialogRule], *,
        region: Region | None = None, language: str = "eng",
        tesseract_cmd: str | None = None,
    ) -> None:
        if len({rule.name for rule in rules}) != len(rules):
            raise ValueError("Dialog rule names must be unique.")
        self.controller = controller
        self.rules = sorted(rules, key=lambda rule: rule.priority, reverse=True)
        self.region = region
        self.language = language
        self.tesseract_cmd = tesseract_cmd

    def inspect(self) -> DialogMatch | None:
        screenshot = self.controller.screenshot(self.region)
        text: str | None = None
        for rule in self.rules:
            visual = None
            if rule.template_path:
                visual = Vision.match_template(screenshot, rule.template_path, threshold=rule.confidence)
                if visual is None:
                    continue
                if self.region:
                    visual = Match(visual.x + self.region[0], visual.y + self.region[1], visual.width, visual.height, visual.confidence)
            if rule.contains or rule.pattern:
                if text is None:
                    text = Vision.read_text(screenshot, self.language, tesseract_cmd=self.tesseract_cmd)
                if rule.contains and not any(word.casefold() in text.casefold() for word in rule.contains):
                    continue
                if rule.pattern and re.search(rule.pattern, text, re.IGNORECASE) is None:
                    continue
            return DialogMatch(rule, text or "", visual)
        return None

    def dispatch(
        self, handlers: Mapping[str, Callable[[DialogMatch], Any]], *,
        default: Callable[[], Any] | None = None,
    ) -> Any:
        """Trigger only explicitly registered handlers; never auto-click OK."""
        match = self.inspect()
        if match is None:
            return default() if default else None
        if match.rule.action not in handlers:
            raise KeyError("No handler is registered for the detected dialog action.")
        return handlers[match.rule.action](match)
