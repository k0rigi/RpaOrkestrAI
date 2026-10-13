"""Kurum modelini kısa kuyruk istekleriyle kullanır; sunucu yerel araç çalıştırmaz."""

from __future__ import annotations

import json
import time

from ..models import uid
from .central import CentralError, record_id
from .models import validate_json_value
from .providers import (
    ProviderCancelled,
    ProviderError,
    ProviderResponse,
    ProviderTimeout,
    RequestLimits,
    ToolCall,
    Usage,
)


def shared_prompt_bytes(messages, tools):
    """Mirror the advertised utf8_bytes estimator after the server's Ollama conversion."""
    converted = []
    for message in messages:
        item = {"role": message["role"], "content": message.get("content", "")}
        if message["role"] == "tool":
            item["tool_name"] = message["name"]
        if message.get("tool_calls"):
            item["tool_calls"] = [{"type": "function", "function": {
                "name": call["name"], "arguments": call["arguments"],
            }} for call in message["tool_calls"]]
        converted.append(item)
    functions = [{"type": "function", "function": {"name": tool["name"],
                  "description": tool.get("description", ""), "parameters": tool["parameters"]}}
                 for tool in tools]
    return len(json.dumps({"messages": converted, "tools": functions}, ensure_ascii=False,
                          sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8"))


class SharedProvider:
    def __init__(self, client):
        self.client = client
        self._limits = {}

    def request_limits(self, model, *, cancel, deadline):
        if cancel.is_set():
            raise ProviderCancelled()
        if time.monotonic() >= deadline:
            raise ProviderTimeout()
        actor = self.client.actor()
        key = (actor.company_id, actor.user_id, actor.session_id, model)
        if key in self._limits:
            return self._limits[key]
        try:
            answer = self.client.request("GET", "/llm/models", expected_actor=actor,
                                         cancel=cancel, deadline=deadline)
            models = answer.get("models")
            if (answer.get("enabled") is not True or type(models) is not list
                    or not all(type(name) is str for name in models) or model not in models
                    or answer.get("estimation") != "utf8_bytes"):
                raise ValueError
            limits = RequestLimits(context_tokens=answer["context_tokens"],
                                   max_output_tokens=answer["max_output_tokens"],
                                   reserve_tokens=answer["reserve_tokens"], prompt_size=shared_prompt_bytes)
        except (CentralError, ValueError, TypeError, KeyError):
            raise ProviderError() from None
        self._limits[key] = limits
        return limits

    def complete(self, messages, tools, *, model, max_tokens, cancel, deadline):
        actor = self.client.actor()
        job_id = None

        def check():
            if cancel.is_set():
                raise ProviderCancelled()
            if time.monotonic() >= deadline:
                raise ProviderTimeout()

        try:
            check()
            limits = self.request_limits(model, cancel=cancel, deadline=deadline)
            if limits.output_budget(messages, tools, max_tokens) != max_tokens:
                raise ProviderError()
            payload = {"request_id": uid(), "model": model, "messages": messages,
                       "tools": tools, "max_tokens": max_tokens}
            validate_json_value(payload, max_bytes=64 * 1024)
            job = self.client.request("POST", "/llm/jobs", payload, expected_actor=actor,
                                      cancel=cancel, deadline=deadline).get("job", {})
            job_id = record_id(job.get("id"))
            while True:
                check()
                if job.get("status") == "succeeded":
                    result = self._response(job.get("result"))
                    job_id = None
                    return result
                if job.get("status") in {"failed", "cancelled"}:
                    raise ProviderError("Kurum modeli yanıtı tamamlayamadı; çalışma durduruldu.")
                if job.get("status") not in {"queued", "running"}:
                    raise ProviderError("Kurum modeli geçersiz bir çalışma durumu döndürdü.")
                cancel.wait(min(1, max(0, deadline - time.monotonic())))
                check()
                job = self.client.request("GET", "/llm/jobs/" + job_id, expected_actor=actor,
                                          cancel=cancel, deadline=deadline).get("job", {})
                if job.get("id") != job_id:
                    raise ProviderError("Kurum modeli yanıtının çalışma kimliği doğrulanamadı.")
        except CentralError as exc:
            raise ProviderError(str(exc)) from None
        except (TypeError, ValueError, KeyError):
            raise ProviderError("Kurum modeli yanıtı veya isteği geçersiz.") from None
        finally:
            if job_id is not None:
                try:
                    self.client.request("DELETE", "/llm/jobs/" + job_id, expected_actor=actor,
                                        deadline=time.monotonic() + 2)
                except CentralError:
                    pass

    @staticmethod
    def _response(value):
        validate_json_value(value, max_bytes=128 * 1024)
        if not isinstance(value, dict) or set(value) - {"text", "tool_calls", "usage"}:
            raise ValueError
        text, calls, usage = value.get("text", ""), value.get("tool_calls", []), value.get("usage")
        if not isinstance(text, str) or len(text) > 32_000 or not isinstance(calls, list) or len(calls) > 32:
            raise ValueError
        if not isinstance(usage, dict) or any(type(usage.get(key)) is not int or usage[key] < 0
                                               for key in ("input_tokens", "output_tokens")):
            raise ValueError
        if (type(usage.get("total_tokens")) is not int or usage["total_tokens"] <= 0
                or usage["total_tokens"] != usage["input_tokens"] + usage["output_tokens"]):
            raise ValueError
        response = ProviderResponse(text=text, tool_calls=[ToolCall(**call) for call in calls],
                                    usage=Usage(usage["input_tokens"], usage["output_tokens"]))
        return response
