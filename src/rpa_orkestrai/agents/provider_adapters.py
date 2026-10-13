"""Resmî HTTP protokolleri; sağlayıcı yanıtı hiçbir yerel işlemi doğrudan başlatmaz.

Protocol references (checked 2026-10-13):
https://developers.openai.com/api/docs/guides/function-calling
https://ai.google.dev/api/generate-content
https://platform.claude.com/docs/en/agents-and-tools/tool-use/handle-tool-calls
https://docs.ollama.com/api/chat
https://docs.ollama.com/faq#how-do-i-disable-ollama-cloud-features
https://github.com/ollama/ollama/blob/main/api/client.go
https://github.com/ollama/ollama/blob/main/api/types.go
"""

from __future__ import annotations

import copy
import hashlib
import ipaddress
import json
import ssl
import threading
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener
from uuid import uuid4

import certifi

from .models import ProviderConnection, validate_json_value
from .providers import ProviderCancelled, ProviderError, ProviderResponse, ProviderTimeout, ToolCall, Usage

REQUEST_LIMIT = 256 * 1024
RESPONSE_LIMIT = 1024 * 1024
CONTINUATION_LIMIT = 512 * 1024
CLOUD_URLS = {"openai": "https://api.openai.com/v1/responses",
              "anthropic": "https://api.anthropic.com/v1/messages"}


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        raise ProviderError()


class ProviderProtocolError(ProviderError):
    def __init__(self, *, usage=False):
        RuntimeError.__init__(self, "Sağlayıcı token kullanımını doğrulanabilir biçimde bildirmedi; işlem başlatılmadı."
                              if usage else "Modelin araç çağırma yanıtı geçersiz veya desteklenmiyor; işlem başlatılmadı.")


class LocalModelError(ProviderError):
    def __init__(self):
        RuntimeError.__init__(self, "Ollama'nın yalnız yerel çalıştığı doğrulanamadı. "
                              "Güncel Ollama'da OLLAMA_NO_CLOUD=1 ayarlayıp sunucuyu yeniden başlatın "
                              "ve bilgisayara indirilmiş, araç çağırmayı destekleyen bir model seçin.")


def urlopen(request, *, timeout, context):
    """Module boundary deliberately injectable in offline tests; no ambient proxy or redirect."""
    opener = build_opener(ProxyHandler({}), _NoRedirect(), HTTPSHandler(context=context))
    return opener.open(request, timeout=timeout)


def local_endpoint(base_url: str | None, *, provider="ollama") -> str:
    default = "http://127.0.0.1:11434" if provider == "ollama" else "http://127.0.0.1:1234"
    try:
        parsed = urlsplit(base_url or default)
        host = parsed.hostname
        if (parsed.scheme not in {"http", "https"} or not host or parsed.username is not None
                or parsed.password is not None or parsed.query or parsed.fragment
                or parsed.path not in {"", "/"} or parsed.port == 0):
            raise ValueError
        if host.casefold() == "localhost":
            host = "127.0.0.1"  # Do not allow hosts-file/DNS remapping of localhost.
        if not ipaddress.ip_address(host).is_loopback:
            raise ValueError
        authority = f"[{host}]" if ":" in host else host
        if parsed.port:
            authority += f":{parsed.port}"
        return urlunsplit((parsed.scheme, authority, "", "", ""))
    except (TypeError, ValueError):
        raise ValueError("Yerel model yalnız bu bilgisayarın loopback adresinde kullanılabilir. "
                         "Ortak sunucu için doğrulanmış kurum bağlantısı gerekir.") from None


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _check(cancel, deadline):
    if cancel.is_set():
        raise ProviderCancelled()
    if time.monotonic() >= deadline:
        raise ProviderTimeout()


class JsonTransport:
    def __init__(self, *, opener=None, retries=2):
        self.opener = opener
        self.retries = max(0, min(int(retries), 2))

    def post(self, url, payload, headers, *, cancel, deadline):
        return self._request("POST", url, payload, headers, cancel=cancel, deadline=deadline)

    def get(self, url, headers, *, cancel, deadline):
        return self._request("GET", url, None, headers, cancel=cancel, deadline=deadline)

    def _request(self, method, url, payload, headers, *, cancel, deadline):
        try:
            validate_json_value(payload, max_bytes=REQUEST_LIMIT)
            data = None if payload is None else _json(payload).encode("utf-8")
            context = ssl.create_default_context(cafile=certifi.where())
            request = Request(url, data=data, method=method, headers={
                "Content-Type": "application/json", "Accept": "application/json", **headers,
            })
        except Exception:
            raise ProviderError() from None
        for attempt in range(self.retries + 1):
            _check(cancel, deadline)
            delay = min(0.25 * 2**attempt, 2)
            try:
                open_request = self.opener or urlopen
                with open_request(request, timeout=min(30, deadline - time.monotonic()), context=context) as response:
                    if response.getcode() != 200 or response.geturl() != url:
                        raise ProviderError()
                    if sum(len(str(key)) + len(str(value)) for key, value in response.headers.items()) > 16_384:
                        raise ProviderError()
                    length = response.headers.get("Content-Length")
                    if length is not None and (not length.isdigit() or int(length) > RESPONSE_LIMIT):
                        raise ProviderError()
                    chunks, size = [], 0
                    while True:
                        _check(cancel, deadline)
                        chunk = response.read(min(65_536, RESPONSE_LIMIT - size + 1))
                        if not chunk:
                            break
                        size += len(chunk)
                        if size > RESPONSE_LIMIT:
                            raise ProviderError()
                        chunks.append(chunk)
                    value = json.loads(b"".join(chunks).decode("utf-8"))
                    validate_json_value(value, max_bytes=RESPONSE_LIMIT)
                    if type(value) is not dict:
                        raise ProviderError()
                    _check(cancel, deadline)
                    return value
            except HTTPError as exc:
                code = exc.code
                # Inspect machine codes only; never propagate server-controlled error text/URLs.
                try:
                    body = json.loads(exc.read(4096))
                    quota = body.get("error", {}).get("code") in {"insufficient_quota", "billing_hard_limit_reached"}
                except (ValueError, TypeError, AttributeError):
                    quota = False
                raw_delay = exc.headers.get("Retry-After", "") if exc.headers else ""
                if raw_delay.isdigit():
                    delay = min(float(raw_delay), 10)
                elif raw_delay:
                    try:
                        after = parsedate_to_datetime(raw_delay)
                        if after.tzinfo is None:
                            after = after.replace(tzinfo=timezone.utc)
                        delay = max(0, min((after - datetime.now(timezone.utc)).total_seconds(), 10))
                    except (TypeError, ValueError, OverflowError):
                        pass
                exc.close()
                if quota or code != 429 and not 500 <= code < 600 or attempt == self.retries:
                    raise ProviderError() from None
            except (URLError, TimeoutError, OSError):
                if attempt == self.retries:
                    raise ProviderError() from None
            except ProviderError:
                raise
            except Exception:
                raise ProviderError() from None
            _check(cancel, deadline)
            if cancel.wait(min(delay, max(0, deadline - time.monotonic()))):
                raise ProviderCancelled()
        raise ProviderError()


def _token(value):
    if type(value) is not int or not 0 <= value <= 1_000_000_000:
        raise ProviderProtocolError(usage=True)
    return value


def _calls(message):
    calls = message.get("tool_calls", [])
    if type(calls) is not list:
        raise ProviderError()
    result = []
    for call in calls:
        if type(call) is not dict:
            raise ProviderError()
        # The application's canonical representation is deliberately provider independent.
        result.append(ToolCall(call.get("id"), call.get("name"), call.get("arguments", {})))
    return result


def _content(message):
    value = message.get("content", "")
    return value if isinstance(value, str) else _json(value)


def _assistant_signature(text, calls):
    return _fingerprint({"text": text, "calls": [{"id": c.id, "name": c.name, "arguments": c.arguments} for c in calls]})


class HttpProvider:
    """One instance belongs to one AgentRun; continuation never crosses users or companies."""

    def __init__(self, connection: ProviderConnection, key: str | None = None, *, transport=None):
        self.connection = ProviderConnection.model_validate(connection.model_dump())
        self.kind = connection.provider
        if self.kind not in {"openai", "gemini", "anthropic", "ollama", "local_openai"}:
            raise ProviderError()
        if self.kind in {"openai", "gemini", "anthropic"}:
            if not isinstance(key, str) or not key or len(key) > 1000 or any(ord(c) < 32 for c in key):
                raise ProviderError()
        self._key = key
        self.base = local_endpoint(connection.base_url, provider=self.kind) if self.kind in {"ollama", "local_openai"} else None
        self.transport = transport or JsonTransport()
        self._continuations = {}
        self._issued: dict[str, str] = {}
        self._synthetic_ids: set[str] = set()
        self._lock = threading.Lock()

    def _cache(self, text, calls, continuation):
        if not calls:
            return
        signature = _assistant_signature(text, calls)
        if any(call.id in self._issued for call in calls):
            raise ProviderError()
        pending = {**self._continuations, signature: continuation}
        validate_json_value(pending, max_bytes=CONTINUATION_LIMIT)
        self._continuations = pending
        self._issued.update({call.id: signature for call in calls})

    def _continuation(self, message):
        calls = _calls(message)
        signature = _assistant_signature(_content(message), calls)
        if any(call.id in self._issued and self._issued[call.id] != signature for call in calls):
            # Never replay raw cached business values after the runtime redacted/changed a message.
            raise ProviderError()
        return copy.deepcopy(self._continuations.get(signature))

    def complete(self, messages, tools, *, model, max_tokens, cancel, deadline):
        _check(cancel, deadline)
        if not isinstance(model, str) or not model.strip() or len(model) > 200 or type(max_tokens) is not int or max_tokens <= 0:
            raise ProviderError()
        try:
            validate_json_value({"messages": messages, "tools": tools}, max_bytes=REQUEST_LIMIT)
            if type(messages) is not list or type(tools) is not list or len(tools) > 100:
                raise ProviderError()
            names = set()
            for tool in tools:
                if (type(tool) is not dict or set(tool) - {"type", "name", "description", "parameters"}
                        or tool.get("type", "function") != "function"
                        or not isinstance(tool.get("name"), str) or type(tool.get("parameters")) is not dict):
                    raise ProviderError()
                if tool["name"] in names:
                    raise ProviderError()
                names.add(tool["name"])
            for message in messages:
                if type(message) is not dict or message.get("role") not in {"system", "user", "assistant", "tool"}:
                    raise ProviderError()
            with self._lock:
                if self.kind == "ollama":
                    self._verify_local_model(model.strip(), bool(tools), cancel, deadline)
                url, payload, headers = self._request(messages, tools, model.strip(), max_tokens)
                raw = self.transport.post(url, payload, headers, cancel=cancel, deadline=deadline)
                result = self._parse(raw)
                if any(call.name not in names for call in result.tool_calls):
                    raise ProviderError()
                _check(cancel, deadline)
                return result
        except ProviderError:
            raise
        except Exception:
            raise ProviderError() from None

    def _verify_local_model(self, model, needs_tools, cancel, deadline):
        # No task text is sent until the daemon and selected model both pass.
        # Recheck every turn: changing the daemon config must not keep a cached permission alive.
        try:
            state = self.transport.get(self.base + "/api/status", {}, cancel=cancel, deadline=deadline)
            if type(state.get("cloud")) is not dict or state["cloud"].get("disabled") is not True:
                raise LocalModelError()
            info = self.transport.post(self.base + "/api/show", {"model": model}, {}, cancel=cancel, deadline=deadline)
            capabilities = info.get("capabilities")
            if (info.get("remote_host") or info.get("remote_model") or type(info.get("model_info")) is not dict
                    or not info["model_info"] or needs_tools and (type(capabilities) is not list or "tools" not in capabilities)):
                raise LocalModelError()
        except (ProviderCancelled, ProviderTimeout):
            raise
        except Exception:
            raise LocalModelError() from None

    def _request(self, messages, tools, model, max_tokens):
        if self.kind == "openai":
            items = []
            for message in messages:
                role = message["role"]
                if role == "tool":
                    items.append({"type": "function_call_output", "call_id": message["tool_call_id"], "output": _content(message)})
                elif role == "assistant" and message.get("tool_calls"):
                    continuation = self._continuation(message)
                    if continuation is not None:
                        items.extend(continuation)
                    else:
                        if _content(message):
                            items.append({"role": "assistant", "content": _content(message)})
                        items.extend({"type": "function_call", "call_id": call.id, "name": call.name,
                                      "arguments": _json(call.arguments)} for call in _calls(message))
                else:
                    items.append({"role": role, "content": _content(message)})
            return CLOUD_URLS[self.kind], {"model": model, "input": items, "store": False,
                "max_output_tokens": max_tokens, "tools": [{"type": "function", **tool, "strict": False} for tool in tools]}, \
                {"Authorization": f"Bearer {self._key}"}
        if self.kind == "gemini":
            system, contents, ids = [], [], {}
            for message in messages:
                role = message["role"]
                if role == "system":
                    system.append({"text": _content(message)})
                    continue
                if role == "assistant":
                    calls = _calls(message)
                    ids.update({call.id: call.name for call in calls})
                    parts = self._continuation(message) if calls else None
                    if parts is None:
                        parts = ([{"text": _content(message)}] if _content(message) else [])
                        parts.extend({"functionCall": {"id": c.id, "name": c.name, "args": c.arguments}} for c in calls)
                    contents.append({"role": "model", "parts": parts})
                elif role == "tool":
                    call_id = message["tool_call_id"]
                    part = {"functionResponse": {"name": ids[call_id], "response": {"data": message.get("content")}}}
                    # Older Gemini models omit call IDs. The synthetic application ID is not sent back.
                    if call_id not in self._synthetic_ids:
                        part["functionResponse"]["id"] = call_id
                    if contents and contents[-1]["role"] == "user" and "functionResponse" in contents[-1]["parts"][0]:
                        contents[-1]["parts"].append(part)
                    else:
                        contents.append({"role": "user", "parts": [part]})
                else:
                    contents.append({"role": "user", "parts": [{"text": _content(message)}]})
            payload = {"contents": contents, "generationConfig": {"maxOutputTokens": max_tokens}}
            if system:
                payload["systemInstruction"] = {"parts": system}
            if tools:
                payload["tools"] = [{"functionDeclarations": [{"name": tool["name"], "description": tool.get("description", ""),
                                      "parametersJsonSchema": tool["parameters"]} for tool in tools]}]
            endpoint = "https://generativelanguage.googleapis.com/v1beta/models/" + quote(model.removeprefix("models/"), safe="") + ":generateContent"
            return endpoint, payload, {"x-goog-api-key": self._key}
        if self.kind == "anthropic":
            system, history = [], []
            for message in messages:
                role = message["role"]
                if role == "system":
                    system.append(_content(message))
                    continue
                if role == "tool":
                    block = {"type": "tool_result", "tool_use_id": message["tool_call_id"], "content": _content(message)}
                    if history and history[-1]["role"] == "user" and history[-1]["content"][0].get("type") == "tool_result":
                        history[-1]["content"].append(block)
                    else:
                        history.append({"role": "user", "content": [block]})
                elif role == "assistant":
                    blocks = self._continuation(message) if message.get("tool_calls") else None
                    if blocks is None:
                        blocks = ([{"type": "text", "text": _content(message)}] if _content(message) else [])
                        blocks.extend({"type": "tool_use", "id": c.id, "name": c.name, "input": c.arguments} for c in _calls(message))
                    history.append({"role": "assistant", "content": blocks})
                else:
                    history.append({"role": "user", "content": [{"type": "text", "text": _content(message)}]})
            payload = {"model": model, "max_tokens": max_tokens, "messages": history,
                       "tools": [{"name": tool["name"], "description": tool.get("description", ""),
                                  "input_schema": tool["parameters"]} for tool in tools]}
            if system:
                payload["system"] = "\n".join(system)
            return CLOUD_URLS[self.kind], payload, {"x-api-key": self._key, "anthropic-version": "2023-06-01"}
        history, ids = [], {}
        for message in messages:
            role = message["role"]
            item = {"role": role, "content": _content(message)}
            if role == "assistant":
                calls = _calls(message)
                ids.update({call.id: call.name for call in calls})
                if calls:
                    item["tool_calls"] = [{"type": "function", "function": {
                        "name": call.name, "arguments": call.arguments if self.kind == "ollama" else _json(call.arguments),
                    }, **({"id": call.id} if self.kind == "local_openai" else {})} for call in calls]
            elif role == "tool":
                if self.kind == "ollama":
                    item["tool_name"] = ids[message["tool_call_id"]]
                else:
                    item["tool_call_id"] = message["tool_call_id"]
            history.append(item)
        payload = {"model": model, "messages": history, "stream": False,
                   "tools": [{"type": "function", "function": {key: value for key, value in tool.items() if key != "type"}}
                             for tool in tools]}
        if self.kind == "ollama":
            payload["options"] = {"num_predict": max_tokens}
            # Tool calling remains available; hidden thinking is not requested or persisted.
            payload["think"] = False
            payload["truncate"] = False
            return self.base + "/api/chat", payload, {}
        payload["max_tokens"] = max_tokens
        return self.base + "/v1/chat/completions", payload, ({"Authorization": f"Bearer {self._key}"} if self._key else {})

    def _parse(self, raw):
        texts, calls, continuation = [], [], []
        required_usage = {"openai": ("usage", ("input_tokens", "output_tokens")),
                          "gemini": ("usageMetadata", ("promptTokenCount", "totalTokenCount")),
                          "anthropic": ("usage", ("input_tokens", "output_tokens")),
                          "local_openai": ("usage", ("prompt_tokens", "completion_tokens"))}
        if self.kind in required_usage:
            field, keys = required_usage[self.kind]
            if type(raw.get(field)) is not dict or any(key not in raw[field] for key in keys):
                raise ProviderProtocolError(usage=True)
        elif any(key not in raw for key in ("prompt_eval_count", "eval_count")):
            raise ProviderProtocolError(usage=True)
        if self.kind == "openai":
            usage = raw["usage"]
            usage = Usage(_token(usage["input_tokens"]), _token(usage["output_tokens"]))
            if raw.get("status", "completed") != "completed":
                raise ProviderError()
            for item in raw["output"]:
                kind = item.get("type")
                if kind == "message":
                    for part in item["content"]:
                        if part.get("type") == "output_text":
                            texts.append(part["text"])
                        elif part.get("type") == "refusal":
                            raise ProviderError()
                    continuation.append(copy.deepcopy(item))
                elif kind == "function_call":
                    calls.append(ToolCall(item["call_id"], item["name"], json.loads(item["arguments"])))
                    continuation.append(copy.deepcopy(item))
                elif kind == "reasoning":
                    continuation.append(copy.deepcopy(item))
                else:
                    raise ProviderError()
        elif self.kind == "gemini":
            counts = raw["usageMetadata"]
            input_tokens, total = _token(counts["promptTokenCount"]), _token(counts["totalTokenCount"])
            if total < input_tokens:
                raise ProviderError()
            usage = Usage(input_tokens, total - input_tokens)
            candidates = raw["candidates"]
            if len(candidates) != 1 or candidates[0].get("finishReason") != "STOP":
                raise ProviderError()
            for part in candidates[0]["content"]["parts"]:
                if "functionCall" in part:
                    call = part["functionCall"]
                    call_id = call.get("id")
                    if not call_id:
                        call_id = "local_" + uuid4().hex
                        self._synthetic_ids.add(call_id)
                    calls.append(ToolCall(call_id, call["name"], call.get("args", {})))
                elif "text" in part and not part.get("thought"):
                    texts.append(part["text"])
                elif "text" not in part:
                    raise ProviderError()
                continuation.append(copy.deepcopy(part))
        elif self.kind == "anthropic":
            counts = raw["usage"]
            input_tokens = _token(counts["input_tokens"]) + _token(counts.get("cache_creation_input_tokens", 0)) + _token(counts.get("cache_read_input_tokens", 0))
            usage = Usage(input_tokens, _token(counts["output_tokens"]))
            if raw.get("stop_reason") not in {"end_turn", "tool_use", "stop_sequence"}:
                raise ProviderError()
            for block in raw["content"]:
                kind = block.get("type")
                if kind == "text":
                    texts.append(block["text"])
                elif kind == "tool_use":
                    calls.append(ToolCall(block["id"], block["name"], block["input"]))
                elif kind not in {"thinking", "redacted_thinking"}:
                    raise ProviderError()
                continuation.append(copy.deepcopy(block))
        else:
            if self.kind == "ollama":
                if (raw.get("done") is not True or raw.get("done_reason", "stop") == "length"
                        or raw.get("remote_host") or raw.get("remote_model")):
                    raise ProviderError()
                usage = Usage(_token(raw["prompt_eval_count"]), _token(raw["eval_count"]))
                message = raw["message"]
            else:
                counts = raw["usage"]
                usage = Usage(_token(counts["prompt_tokens"]), _token(counts["completion_tokens"]))
                choices = raw["choices"]
                if len(choices) != 1 or choices[0].get("finish_reason") not in {"stop", "tool_calls"}:
                    raise ProviderError()
                message = choices[0]["message"]
            if message.get("content"):
                texts.append(message["content"])
            for call in message.get("tool_calls", []):
                function = call["function"]
                arguments = function["arguments"]
                if self.kind == "local_openai":
                    arguments = json.loads(arguments)
                calls.append(ToolCall(call.get("id") or "local_" + uuid4().hex, function["name"], arguments))
        text = "\n".join(texts)
        if not text and not calls:
            raise ProviderProtocolError()
        if not usage.total_tokens:
            raise ProviderProtocolError(usage=True)
        response = ProviderResponse(text, calls, usage)
        self._cache(text, calls, continuation)
        return response


def create_provider(connection: ProviderConnection, key: str | None = None, *, transport=None):
    return HttpProvider(connection, key, transport=transport)
