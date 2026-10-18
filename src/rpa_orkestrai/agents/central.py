"""Studio hesaplarının ortak görev ve onay hizmetine sınırlı HTTPS bağlantısı."""

from __future__ import annotations

import hashlib
import json
import re
import ssl
import time
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener

import certifi

from ..models import uid
from .models import Actor, validate_json_value
from .policy import canonical

BASE_URL = "https://orkestrai.net/api/studio/ekip"
IDENTIFIER = re.compile(r"^[a-f0-9]{32}$")
PATH = re.compile(r"^/(?:ben|uyeler|ofis|ofisim(?:/(?:ad|ayril|uyeler(?:/[1-9][0-9]{0,9}/cikar)?))?|"
                  r"gorevler(?:/[a-f0-9]{32}(?:/(?:durum|ata|sil))?)?|"
                  r"onaylar(?:/[a-f0-9]{32}(?:/(?:karar|tuket|iptal))?)?|"
                  r"llm/(?:models|jobs(?:/[a-f0-9]{32})?))$")
RESPONSE_LIMIT = 512 * 1024


class CentralError(RuntimeError):
    def __init__(self, message="Kurum görev hizmetine ulaşılamadı. İnternet bağlantısını kontrol edin.", status=503):
        super().__init__(message)
        self.status = status


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        raise CentralError("Kurum hizmeti beklenmeyen bir adrese yönlendirdi; bağlantı durduruldu.")


def urlopen(request, *, timeout, context):
    return build_opener(ProxyHandler({}), NoRedirect(), HTTPSHandler(context=context)).open(request, timeout=timeout)


def identity_key(actor):
    return actor.company_id, actor.user_id, actor.session_id


def record_id(value):
    if not isinstance(value, str) or IDENTIFIER.fullmatch(value) is None:
        raise CentralError("Kayıt kimliği geçersiz.", 422)
    return value


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


class CentralClient:
    def __init__(self, licensing, *, opener=None):
        self.licensing = licensing
        self.opener = opener

    def actor(self):
        try:
            actor = self.licensing.agent_actor()
        except Exception:
            actor = None
        if not isinstance(actor, Actor) or "agents.use" not in actor.permissions:
            raise CentralError("Ajan lisansı veya kullanıcı oturumu doğrulanamadı.", 403)
        return actor

    def request(self, method, path, body=None, *, expected_actor=None, cancel=None, deadline=None):
        metric_path = False
        if isinstance(path, str) and path.startswith("/metrics?") and method == "GET":
            from .metrics import interval

            parsed = urlsplit(path)
            query = parse_qs(parsed.query, keep_blank_values=True)
            try:
                metric_path = (parsed.path == "/metrics" and not parsed.fragment and set(query) == {"start", "end"}
                               and all(len(value) == 1 and len(value[0]) <= 40 for value in query.values()))
                if metric_path:
                    interval(query["start"][0], query["end"][0])
            except ValueError:
                metric_path = False
        if (method not in {"GET", "POST", "DELETE"} or not isinstance(path, str)
                or (path == "/ofis" and method != "GET")
                or not (PATH.fullmatch(path) or metric_path)):
            raise CentralError("Kurum hizmeti isteği geçersiz.", 422)
        actor = self.actor()
        if expected_actor is not None and identity_key(actor) != identity_key(expected_actor):
            raise CentralError("Kullanıcı oturumu değişti; istek gönderilmedi.", 403)
        deadline = min(deadline or time.monotonic() + 8, time.monotonic() + 8)
        if (cancel is not None and cancel.is_set()) or time.monotonic() >= deadline:
            raise CentralError("İstek iptal edildi veya süresi doldu.", 409)
        try:
            if body is not None:
                validate_json_value(body, max_bytes=64 * 1024)
            raw = None if body is None else canonical(body).encode("utf-8")
            token = self.licensing.agent_access_token()
            if not isinstance(token, str) or not token or len(token) > 8192 or any(ord(c) < 32 for c in token):
                raise ValueError
            request = Request(BASE_URL + path, method=method, data=raw, headers={
                "Authorization": "Bearer " + token, "Content-Type": "application/json", "Accept": "application/json",
            })
            context = ssl.create_default_context(cafile=certifi.where())
            with (self.opener or urlopen)(request, timeout=max(0.1, deadline - time.monotonic()), context=context) as response:
                if response.geturl() != BASE_URL + path or response.getcode() not in {200, 201, 202}:
                    raise CentralError("Kurum hizmeti beklenmeyen bir yanıt verdi.")
                data = response.read(RESPONSE_LIMIT + 1)
                if len(data) > RESPONSE_LIMIT:
                    raise CentralError("Kurum hizmeti yanıtı boyut sınırını aşıyor.")
                result = json.loads(data)
                validate_json_value(result, max_bytes=RESPONSE_LIMIT)
                if not isinstance(result, dict) or result.get("success") is not True:
                    raise CentralError("Kurum hizmeti isteği doğrulanamadı.")
        except HTTPError as exc:
            # The response body can contain credentials or reflected inputs; never display it.
            code = exc.code
            exc.close()
            messages = {401: "Kurum oturumunun süresi doldu. Lisansı yenileyip tekrar deneyin.",
                        403: "Bu kurum işlemi için hesabınızın yetkisi yok.",
                        404: "Kurum kaydı bulunamadı veya bu hesaba ait değil.",
                        409: "Kayıt değişti veya işlem daha önce tamamlandı. Listeyi yenileyin.",
                        422: "Kurum hizmeti isteğin alanlarını kabul etmedi.",
                        429: "Kurum hizmetinin istek sınırına ulaşıldı. Bir süre bekleyin.",
                        503: "Kurum hizmeti henüz etkin değil veya şu anda kullanılamıyor."}
            raise CentralError(messages.get(code, "Kurum hizmeti isteği tamamlanamadı."),
                               code if code in messages else 503) from None
        except CentralError:
            raise
        except (OSError, URLError, ValueError, TypeError, RuntimeError):
            raise CentralError() from None
        if identity_key(self.actor()) != identity_key(actor):
            raise CentralError("Kullanıcı oturumu değişti; yanıt kullanılmadı.", 403)
        if (cancel is not None and cancel.is_set()) or time.monotonic() >= deadline:
            raise CentralError("İstek iptal edildi veya süresi doldu.", 409)
        return result


class CentralApprovalBackend:
    """The origin Studio must consume exactly the decision the human owner approved."""

    def __init__(self, client):
        self.client = client

    def request(self, context, prepared, reason, *, expires_in):
        preview = context.redactor.sanitize({"workflow_name": prepared.root.name, "inputs": prepared.inputs})
        body = {"request_id": uid(), "run_id": context.run.id, "workflow_id": prepared.root.id,
                "workflow_digest": prepared.digest, "inputs_digest": digest(prepared.inputs),
                "preview": preview, "reason": context.redactor.text(reason)[:2000],
                "attempt": context.attempts.get(prepared.digest, 0) + 1,
                "expires_in": max(1, min(900, int(expires_in)))}
        result = self.client.request("POST", "/onaylar", body, expected_actor=context.run.actor,
                                     cancel=context.cancel, deadline=context.deadline).get("approval")
        if not isinstance(result, dict):
            raise CentralError("Onay kaydı doğrulanamadı.")
        expected = {key: body[key] for key in ("run_id", "workflow_id", "workflow_digest", "inputs_digest", "attempt")}
        expected["preview_digest"] = digest(preview)
        if any(result.get(key) != value for key, value in expected.items()):
            raise CentralError("Onay kaydının akış veya girdi özeti uyuşmuyor.")
        return {**expected, "id": record_id(result.get("id")), "version": result.get("version"),
                "expires_at": result.get("expires_at")}

    def status(self, context, remote):
        result = self.client.request("GET", "/onaylar/" + record_id(remote["id"]),
                                     expected_actor=context.run.actor, cancel=context.cancel,
                                     deadline=context.deadline).get("approval")
        self._verify(remote, result)
        return result

    @staticmethod
    def _verify(remote, result):
        keys = ("id", "run_id", "workflow_id", "workflow_digest", "inputs_digest", "preview_digest", "attempt")
        if not isinstance(result, dict) or any(remote[key] != result.get(key) for key in keys):
            raise CentralError("Onayın çalışma veya girdi bağı doğrulanamadı.")

    def decide(self, remote_id, approved):
        actor = self.client.actor()
        if not actor.can_approve:
            raise CentralError("Riskli işlemi yalnız onay yetkilisi (ofislere ayrılmış firmada ofis yetkilisi) onaylayabilir.", 403)
        path = "/onaylar/" + record_id(remote_id)
        current = self.client.request("GET", path, expected_actor=actor).get("approval", {})
        if type(approved) is not bool or type(current.get("version")) is not int:
            raise CentralError("Onay kararı geçersiz.", 422)
        return self.client.request("POST", path + "/karar", {
            "decision": "approve" if approved else "reject", "expected_version": current["version"],
        }, expected_actor=actor)["approval"]

    def consume(self, context, remote, *, digest):
        if digest != remote["workflow_digest"]:
            raise CentralError("Onaylanan akış değişti; işlem başlatılmadı.", 409)
        body = {key: remote[key] for key in ("run_id", "workflow_id", "workflow_digest", "inputs_digest",
                                           "preview_digest", "attempt")}
        result = self.client.request("POST", "/onaylar/" + record_id(remote["id"]) + "/tuket", body,
                                     expected_actor=context.run.actor, cancel=context.cancel,
                                     deadline=context.deadline).get("approval")
        self._verify(remote, result)
        if result.get("status") != "consumed":
            raise CentralError("Tek kullanımlık onay tüketilemedi; akış başlatılmadı.", 409)
        # A lost acknowledgement deliberately does not lead to a second consume or workflow start.

    def cancel(self, context, remote):
        try:
            self.client.request("POST", "/onaylar/" + record_id(remote["id"]) + "/iptal", {},
                                expected_actor=context.run.actor, deadline=time.monotonic() + 2)
        except CentralError:
            # The local cancellation already prevents execution; the server expiry is the fallback.
            pass
