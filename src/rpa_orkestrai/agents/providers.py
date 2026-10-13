"""Sağlayıcı sözleşmesi ve ağ kullanmayan senaryolu test sağlayıcısı."""

from __future__ import annotations

import copy
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from .models import ProviderConnection, validate_json_value


class ProviderError(RuntimeError):
    """Provider responses and exception details must not enter public error messages."""

    def __init__(self, message: str = "Yapay zekâ sağlayıcısı isteği tamamlayamadı."):
        # Do not accept provider-originated error text, even when a caller passes it accidentally.
        super().__init__("Yapay zekâ sağlayıcısı isteği tamamlayamadı.")


class ProviderUnavailable(ProviderError):
    def __init__(self):
        RuntimeError.__init__(self, "Bu sürümde gerçek yapay zekâ sağlayıcısı henüz etkin değil.")


class ProviderCancelled(ProviderError):
    def __init__(self):
        RuntimeError.__init__(self, "Yapay zekâ isteği durduruldu.")


class ProviderTimeout(ProviderError):
    def __init__(self):
        RuntimeError.__init__(self, "Yapay zekâ isteğinin süresi doldu.")


@dataclass(frozen=True)
class RequestLimits:
    """Server-advertised context boundary; prompt_size uses the server's exact estimator."""

    context_tokens: int
    max_output_tokens: int
    reserve_tokens: int
    prompt_size: Callable[[list[dict], list[dict]], int] = field(repr=False, compare=False)

    def __post_init__(self):
        if (any(type(value) is not int for value in
                (self.context_tokens, self.max_output_tokens, self.reserve_tokens))
                or not 512 <= self.context_tokens <= 1_048_576
                or not 1 <= self.max_output_tokens <= 4096
                or not 0 <= self.reserve_tokens < self.context_tokens
                or not callable(self.prompt_size)):
            raise ProviderError()

    def output_budget(self, messages, tools, requested: int) -> int:
        if type(requested) is not int or requested < 1:
            raise ProviderError()
        size = self.prompt_size(messages, tools)
        if type(size) is not int or size < 0:
            raise ProviderError()
        return max(0, min(requested, self.max_output_tokens,
                          self.context_tokens - self.reserve_tokens - size))


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not 1 <= len(self.id) <= 200:
            raise ProviderError()
        if not isinstance(self.name, str) or not 1 <= len(self.name) <= 100:
            raise ProviderError()
        if type(self.arguments) is not dict:
            raise ProviderError()
        try:
            validate_json_value(self.arguments)
        except ValueError:
            raise ProviderError() from None


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0

    def __post_init__(self) -> None:
        if (type(self.input_tokens) is not int or type(self.output_tokens) is not int
                or min(self.input_tokens, self.output_tokens) < 0):
            raise ProviderError()

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True)
class ProviderResponse:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)

    def __post_init__(self) -> None:
        if not isinstance(self.text, str) or len(self.text) > 64_000:
            raise ProviderError()
        if (type(self.tool_calls) is not list or len(self.tool_calls) > 100
                or not all(isinstance(call, ToolCall) for call in self.tool_calls)
                or not isinstance(self.usage, Usage)):
            raise ProviderError()
        if len({call.id for call in self.tool_calls}) != len(self.tool_calls):
            raise ProviderError()
        try:
            validate_json_value({"text": self.text, "tool_calls": [
                {"id": call.id, "name": call.name, "arguments": call.arguments} for call in self.tool_calls
            ]}, max_bytes=256 * 1024)
        except ValueError:
            raise ProviderError() from None


class Provider(Protocol):
    def complete(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]], *, model: str,
        max_tokens: int, cancel: threading.Event, deadline: float,
    ) -> ProviderResponse: ...


class ScriptedProvider:
    """Injected by tests only; a saved connection cannot activate this provider."""

    def __init__(
        self, responses: list[ProviderResponse], *,
        callback: Callable[[dict[str, Any]], ProviderResponse | None] | None = None,
    ):
        self._responses = copy.deepcopy(responses)
        self._callback = callback
        self._requests: list[dict[str, Any]] = []
        self._lock = threading.RLock()

    @property
    def requests(self) -> list[dict[str, Any]]:
        with self._lock:
            return copy.deepcopy(self._requests)

    @property
    def captured_requests(self) -> list[dict[str, Any]]:
        return self.requests

    def complete(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]], *, model: str,
        max_tokens: int, cancel: threading.Event, deadline: float,
    ) -> ProviderResponse:
        def check() -> None:
            if cancel.is_set():
                raise ProviderCancelled()
            if time.monotonic() >= deadline:
                raise ProviderTimeout()

        check()
        if type(max_tokens) is not int or max_tokens <= 0 or not isinstance(model, str) or len(model) > 200:
            raise ProviderError()
        request = {"messages": messages, "tools": tools, "model": model, "max_tokens": max_tokens}
        try:
            validate_json_value(request, max_bytes=256 * 1024)
        except ValueError:
            raise ProviderError() from None
        with self._lock:
            self._requests.append(copy.deepcopy(request))
            try:
                response = self._callback(copy.deepcopy(request)) if self._callback else None
            except ProviderError:
                raise
            except Exception:
                raise ProviderError() from None
            check()
            if response is None:
                if not self._responses:
                    raise ProviderError()
                response = self._responses.pop(0)
            if not isinstance(response, ProviderResponse):
                raise ProviderError()
            return copy.deepcopy(response)


def provider_for(connection: ProviderConnection | None) -> Provider:
    # Fake must never be selectable through a connection record or production API.
    raise ProviderUnavailable()
