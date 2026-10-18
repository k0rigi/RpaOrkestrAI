"""Ajanın soruları ve onayları Telegram'a; yanıt ve karar Telegram'dan Studio'ya döner.

Studio açıkken çalışır: bot güncellemelerini Studio kendisi çeker (getUpdates), dışarıdan erişilebilir bir adres
gerekmez. Yalnız kayıtlı özel sohbetten (kişinin bota yazdığı kendi sohbeti) gelen yanıt ve düğme kabul edilir.
Soru Studio'da yanıtlanırsa Telegram'daki geç yanıt reddedilir. Onay düğmeleri yalnız onay yetkisi olan hesaba
gönderilir ve karar Studio'daki kararla aynı denetimlerden geçer (oturum, ofis, merkezi onay).
Mesajdaki metinler kayıtlı gizli değerler maskelenerek gönderilir; iş bilgisi Telegram'a gider.
"""

from __future__ import annotations

import json
import queue
import secrets
import threading
import time
from datetime import datetime
from pathlib import Path

from pydantic import Field

from ..config import atomic_json
from ..models import Model

API = "https://api.telegram.org/bot{token}/{method}"
PRIVATE_CHAT = r"^[1-9][0-9]{0,19}$"
POLL_SECONDS = 20
MAX_OPEN = 50
MAX_OPTIONS = 8
MAX_INPUTS = 12
CLOSED = "\n\n— Kapandı: yanıt veya karar Studio'da verildi ya da süresi doldu."


class TelegramSettings(Model):
    connection_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    # Only a private chat: the person who wrote /start to the bot; groups are refused.
    chat_id: str = Field(pattern=PRIVATE_CHAT)
    questions: bool = True
    approvals: bool = True


def telegram_call(token: str, method: str, payload: dict, timeout: float) -> tuple[int, dict]:
    from ..actions.transfer import _post_json

    return _post_json(API.format(token=token, method=method), payload, {}, timeout)


def _clock(value: str | None) -> str:
    try:
        return datetime.fromisoformat(str(value)).astimezone().strftime("%H:%M")
    except (TypeError, ValueError):
        return ""


class TelegramBridge:
    def __init__(self, service, connections, *, transport=telegram_call):
        self.service = service
        self.connections = connections
        self.transport = transport
        self.path = Path(service.settings.data_dir) / "agent_telegram.json"
        self._lock = threading.RLock()
        # token -> what one Telegram message stands for; kept only in memory.
        self._open: dict[str, dict] = {}
        self._outbox: queue.Queue = queue.Queue()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._offset: int | None = None
        self._threads: list[threading.Thread] = []

    # ----- settings of the signed-in account ----------------------------------------------------
    def _read(self) -> dict:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    def settings(self, actor) -> TelegramSettings | None:
        value = self._read().get(f"{actor.company_id}:{actor.user_id}")
        try:
            return TelegramSettings(**value) if isinstance(value, dict) else None
        except ValueError:
            return None

    def _connection(self, connection_id: str) -> dict:
        item = self.connections().get(connection_id)
        config = item.get("config") or {}
        if item.get("type") != "webhook" or config.get("service") != "telegram" or not config.get("token"):
            raise ValueError("Seçilen bağlantı bot anahtarı kayıtlı bir Telegram bağlantısı değil.")
        return item

    def public(self, actor) -> dict:
        settings = self.settings(actor)
        choices = [{"id": item["id"], "name": item["name"], "chat_id": item.get("chat_id", ""), "ready": item.get("has_token", False)}
                   for item in self.connections().list() if item.get("type") == "webhook" and item.get("service") == "telegram"]
        return {"configured": settings is not None, "connections": choices,
                **(settings.model_dump() if settings else {"connection_id": "", "chat_id": "", "questions": True,
                                                           "approvals": True})}

    def save(self, actor, settings: TelegramSettings) -> dict:
        self._connection(settings.connection_id)
        with self._lock:
            stored = self._read()
            stored[f"{actor.company_id}:{actor.user_id}"] = settings.model_dump()
            atomic_json(self.path, stored)
        self._wake.set()
        return self.public(actor)

    def remove(self, actor) -> dict:
        with self._lock:
            stored = self._read()
            stored.pop(f"{actor.company_id}:{actor.user_id}", None)
            atomic_json(self.path, stored)
            self._open.clear()
        return self.public(actor)

    def test(self, actor, settings: TelegramSettings) -> dict:
        token = self._connection(settings.connection_id)["config"]["token"]
        status, answer = self.transport(token, "sendMessage", {
            "chat_id": settings.chat_id, "disable_web_page_preview": True,
            "text": "RpaOrkestrAI: Bu sohbet ajan sorularını ve onaylarını alacak. Soruları bu mesajlara yanıt "
                    "vererek veya düğmelerle yanıtlayabilirsiniz."}, 15)
        if status != 200 or answer.get("ok") is not True:
            raise ValueError("Deneme mesajı gönderilemedi. Bot anahtarını ve sohbet kimliğini kontrol edin; kişi bota "
                             "önce /start yazmalıdır.")
        return {"sent": True}

    # ----- runs tell the bridge what waits for the person -------------------------------------
    def notify(self, kind: str, context, payload: dict) -> None:
        """Called by the agent runtime; it only queues and returns at once."""
        if kind in {"question", "approval", "closed"}:
            self._outbox.put((kind, context, dict(payload)))
            self.start()

    def start(self) -> None:
        with self._lock:
            if self._threads or self._stop.is_set():
                return
            for target, name in ((self._send_loop, "rpa-telegram-gonder"), (self._poll_loop, "rpa-telegram-al")):
                thread = threading.Thread(target=target, name=name, daemon=True)
                self._threads.append(thread)
                thread.start()

    def close(self) -> None:
        self._stop.set()
        self._wake.set()
        self._outbox.put(None)

    def _account(self):
        try:
            actor = self.service._authorize(None)
        except Exception:  # noqa: BLE001 - Without a licensed session nothing is sent or accepted.
            return None, None
        settings = self.settings(actor)
        if settings is None:
            return actor, None
        try:
            token = self._connection(settings.connection_id)["config"]["token"]
        except (KeyError, ValueError):
            return actor, None
        return actor, (settings, token)

    def _send_loop(self) -> None:
        while not self._stop.is_set():
            item = self._outbox.get()
            if item is None:
                return
            try:
                self._send(*item)
            except Exception:  # noqa: BLE001 - One failed message never stops the channel.
                pass

    def _send(self, kind: str, context, payload: dict) -> None:
        actor, ready = self._account()
        if kind == "closed":
            with self._lock:
                key = next((key for key, item in self._open.items()
                            if item["run_id"] == context.run.id and item["item_id"] == payload["id"]), None)
                item = self._open.pop(key, None) if key else None
            if item and ready:
                self._edit(ready[0], ready[1], item, item["text"] + CLOSED)
            return
        if ready is None or actor is None or (actor.company_id, actor.user_id) != (
                context.run.actor.company_id, context.run.actor.user_id):
            return
        settings, token = ready
        office_actor = actor.in_office(context.run.office_id) if context.run.office_id else actor
        if office_actor is None:
            return
        redactor = context.redactor
        where = f" ({office_actor.office_name} ofisi)" if office_actor.office_name else ""
        if kind == "question":
            if not settings.questions:
                return
            options = [str(item)[:60] for item in (payload.get("options") or [])][:MAX_OPTIONS]
            text = (f"❓ {redactor.text(context.agent.name)}{where} soruyor:\n\n{redactor.text(payload['question'])}\n\n"
                    + ("Seçeneklerden birine dokunun ya da bu mesajı yanıtlayarak (Yanıtla) yazın."
                       if options else "Yanıtınızı bu mesajı yanıtlayarak (Yanıtla) yazın.")
                    + (f"\nSon süre: {_clock(payload.get('expires_at'))}" if payload.get("expires_at") else ""))
            token_key = secrets.token_urlsafe(9)
            keyboard = [[{"text": option, "callback_data": f"q:{token_key}:{index}"}] for index, option in enumerate(options)]
        else:
            if not settings.approvals or not office_actor.can_approve:
                return
            inputs = redactor.sanitize(payload.get("inputs") or {})
            lines = [f"• {key}: {value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)}"[:220]
                     for key, value in list(inputs.items())[:MAX_INPUTS]]
            text = (f"⚠️ Onay gerekiyor: {redactor.text(context.agent.name)}{where}\n"
                    f"Akış: {redactor.text(str(payload.get('workflow_name') or ''))}\n"
                    f"Neden: {redactor.text(str(payload.get('reason') or ''))}\n"
                    + ("Girdiler:\n" + "\n".join(lines) + "\n" if lines else "")
                    + (f"Son süre: {_clock(payload.get('expires_at'))}\n" if payload.get("expires_at") else "")
                    + "Girdileri düzenlemek için Studio'daki onay kartını kullanın.")
            token_key = secrets.token_urlsafe(9)
            keyboard = [[{"text": "✅ Onayla", "callback_data": f"a:{token_key}:y"},
                         {"text": "❌ Reddet", "callback_data": f"a:{token_key}:n"}]]
        message = {"chat_id": settings.chat_id, "text": text[:4000], "disable_web_page_preview": True}
        if keyboard:
            message["reply_markup"] = {"inline_keyboard": keyboard}
        status, answer = self.transport(token, "sendMessage", message, 15)
        if status != 200 or answer.get("ok") is not True:
            return
        with self._lock:
            if len(self._open) >= MAX_OPEN:
                self._open.pop(next(iter(self._open)))
            self._open[token_key] = {
                "kind": kind, "run_id": context.run.id, "item_id": payload["id"], "office": context.run.office_id,
                "options": [item for item in (payload.get("options") or [])][:MAX_OPTIONS], "text": text[:4000],
                "message_id": (answer.get("result") or {}).get("message_id"), "sent": time.time(),
                "chat_id": settings.chat_id}
        self._wake.set()

    def _edit(self, settings, token, item, text) -> None:
        if not item.get("message_id"):
            return
        self.transport(token, "editMessageText", {"chat_id": settings.chat_id, "message_id": item["message_id"],
                                                  "text": text[:4000]}, 15)

    # ----- answers come back --------------------------------------------------------------------
    def _poll_loop(self) -> None:
        while not self._stop.is_set():
            with self._lock:
                waiting = bool(self._open)
            actor, ready = self._account()
            if not waiting or ready is None:
                self._wake.wait(5)
                self._wake.clear()
                continue
            settings, token = ready
            payload = {"timeout": POLL_SECONDS, "allowed_updates": ["message", "callback_query"]}
            if self._offset is not None:
                payload["offset"] = self._offset
            try:
                status, answer = self.transport(token, "getUpdates", payload, POLL_SECONDS + 10)
            except Exception:  # noqa: BLE001 - The connection comes back; nothing is lost on Telegram's side.
                status, answer = 0, {}
            if status != 200 or answer.get("ok") is not True:
                self._stop.wait(10)
                continue
            for update in answer.get("result") or []:
                if isinstance(update, dict) and isinstance(update.get("update_id"), int):
                    self._offset = update["update_id"] + 1
                    try:
                        self.handle(update, settings, token)
                    except Exception:  # noqa: BLE001 - A broken update never stops the channel.
                        pass

    def _reply(self, settings, token, text, reply_to=None) -> None:
        message = {"chat_id": settings.chat_id, "text": text[:4000]}
        if reply_to:
            message["reply_parameters"] = {"message_id": reply_to}
        self.transport(token, "sendMessage", message, 15)

    def handle(self, update: dict, settings: TelegramSettings, token: str) -> None:
        """One update from the bot; only the registered private chat may answer or decide."""
        callback = update.get("callback_query")
        if isinstance(callback, dict):
            chat = ((callback.get("message") or {}).get("chat") or {}).get("id")
            sender = (callback.get("from") or {}).get("id")
            answer = {"callback_query_id": str(callback.get("id") or "")}
            if str(chat) != settings.chat_id or str(sender) != settings.chat_id:
                return
            parts = str(callback.get("data") or "").split(":")
            with self._lock:
                item = self._open.get(parts[1]) if len(parts) == 3 else None
            if item is None:
                self.transport(token, "answerCallbackQuery", {**answer, "text": "Bu soru veya onay artık beklemiyor."}, 15)
                return
            if item["kind"] == "question":
                try:
                    choice = item["options"][int(parts[2])]
                except (ValueError, IndexError):
                    return
                result = self._answer(item, choice)
            elif parts[2] in {"y", "n"}:
                result = self._decide(item, parts[2] == "y")
            else:
                return
            self.transport(token, "answerCallbackQuery", {**answer, "text": result[:190]}, 15)
            self._edit(settings, token, item, item["text"] + "\n\n— " + result)
            return
        message = update.get("message")
        if not isinstance(message, dict):
            return
        chat, sender = (message.get("chat") or {}).get("id"), (message.get("from") or {}).get("id")
        text = message.get("text")
        if str(chat) != settings.chat_id or str(sender) != settings.chat_id or not isinstance(text, str):
            return
        if text.strip().startswith("/"):
            self._reply(settings, token, "RpaOrkestrAI bağlı. Ajan sorduğunda soru buraya gelir; mesajı yanıtlayarak "
                                         "veya düğmelerle yanıt verirsiniz.")
            return
        replied = (message.get("reply_to_message") or {}).get("message_id")
        written = message.get("date", 0)
        with self._lock:
            questions = [item for item in self._open.values() if item["kind"] == "question"]
            oldest = min((item["sent"] for item in self._open.values()), default=None)
            # A plain message answers only a question that was sent before it, and only when it is the one open.
            target = (next((item for item in questions if item["message_id"] == replied), None) if replied
                      else questions[0] if len(questions) == 1 and written >= questions[0]["sent"] - 5
                      else None)
        if target is None:
            if oldest is None or written < oldest - 5:
                return  # Written before anything waited here; it answers nothing and needs no reply.
            self._reply(settings, token, "Birden fazla soru açık veya bu mesaj bir soruya ait değil. Yanıtlamak "
                                         "istediğiniz sorunun mesajını Yanıtla ile seçip yazın.", message.get("message_id"))
            return
        result = self._answer(target, text.strip()[:4000])
        self._reply(settings, token, result, message.get("message_id"))
        if result.startswith("Yanıtınız"):
            self._edit(settings, token, target, target["text"] + "\n\n— " + result)

    def _close(self, item) -> None:
        with self._lock:
            for key, value in list(self._open.items()):
                if value is item:
                    self._open.pop(key)

    def _answer(self, item, value) -> str:
        from .runner import AgentServiceError

        try:
            self.service.answer(item["run_id"], item["item_id"], value, office=item["office"])
        except AgentServiceError as exc:
            self._close(item)
            return f"Yanıt iletilemedi: {exc}"
        self._close(item)
        return f"Yanıtınız ajana iletildi: {value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)}"[:300]

    def _decide(self, item, approved: bool) -> str:
        from .runner import AgentServiceError

        try:
            self.service.approve(item["run_id"], item["item_id"], approved, office=item["office"])
        except AgentServiceError as exc:
            self._close(item)
            return f"Karar iletilemedi: {exc}"
        self._close(item)
        return "Onaylandı; ajan işleme devam ediyor." if approved else "Reddedildi; işlem başlatılmadı."
