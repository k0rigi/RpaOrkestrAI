"""Public workflow errors and control-flow signals shared by the engine and actions."""

from __future__ import annotations


class WorkflowError(ValueError):
    """An actionable, public error that does not embed connection credentials."""


class Cancelled(Exception):
    pass


class BreakLoop(Exception):
    """Leave the innermost loop."""


class ContinueLoop(Exception):
    """Skip to the innermost loop's next iteration."""


class StopWorkflow(Exception):
    def __init__(self, succeeded: bool, message: str):
        super().__init__(message)
        self.succeeded, self.message = succeeded, message
