"""Studio için güvenli özetler ve yalnız yöneticinin düzenlediği sağlayıcılar."""

from __future__ import annotations

import threading
import time
from typing import Literal

from fastapi import APIRouter, HTTPException, Response
from pydantic import Field, SecretStr

from ..errors import WorkflowError
from ..models import Model, now, uid
from .contracts import infer_contract
from .models import ProviderConnection
from .policy import inspect_workflow
from .provider_adapters import LocalModelError
from .providers import ProviderError
from .risk import workflow_risk
from .runner import AgentServiceError


class ConnectionInput(Model):
    name: str = Field(min_length=1, max_length=120)
    provider: Literal["openai", "gemini", "anthropic", "ollama", "local_openai", "shared"]
    model: str = Field(default="", max_length=200)
    base_url: str | None = Field(default=None, max_length=2000)


class ConnectionKey(Model):
    key: SecretStr = Field(min_length=1, max_length=1000)


class ConnectionTest(Model):
    model: str | None = Field(default=None, min_length=1, max_length=200)


def router(service, connections, *, shared_client=None) -> APIRouter:
    result = APIRouter(prefix="/api/agents", tags=["Ajan ayarları"])

    def call(function, *args, **kwargs):
        try:
            return function(*args, **kwargs)
        except AgentServiceError as exc:
            raise HTTPException(exc.status_code, str(exc)) from None
        except KeyError:
            raise HTTPException(404, "Bağlantı veya akış bulunamadı.") from None
        except LocalModelError as exc:
            raise HTTPException(422, str(exc)) from None
        except ProviderError:
            raise HTTPException(422, "Model bağlantısı doğrulanamadı. Adres, model ve kayıtlı anahtarı kontrol edin.") from None
        except (ValueError, OSError):
            raise HTTPException(422, "Sağlayıcı kaydı veya istek biçimi geçersiz.") from None

    def actor(permission="agents.use"):
        return call(service._authorize, permission)

    @result.get("/session")
    def session():
        identity = actor()
        return {"actor": {"user_id": identity.user_id, "company_id": identity.company_id, "name": identity.name},
                "can_manage": "agents.manage" in identity.permissions, "can_approve": identity.can_approve}

    @result.get("/office")
    def office():
        from .office import snapshot

        return call(snapshot, service)

    @result.get("/workflows")
    def workflows():
        actor()
        redactor = service._new_redactor()
        loaded = {}
        for entry in service.store.workflows():
            # Store.workflows returns full models; no step values or connection metadata enter this DTO.
            loaded[entry.id] = entry
        items = []
        for workflow in loaded.values():
            supported, reason = True, ""
            capability = {"requires_roots": False, "dependencies": []}
            try:
                capability = inspect_workflow(workflow.id, service.store)
            except (WorkflowError, KeyError, ValueError):
                supported, reason = False, "Bu akışın adımları veya kaynak izinleri ajan sınırına uygun değil."
            contract = infer_contract(workflow, loaded).as_dict()
            items.append({"id": workflow.id, "name": redactor.text(workflow.name),
                          "description": redactor.text(workflow.description),
                          "department": redactor.text(workflow.department), "risk": workflow_risk(workflow, loaded),
                          "agent_supported": supported, "blocked_reason": reason,
                          **capability, **redactor.sanitize(contract)})
        return items

    @result.get("/connections")
    def list_connections():
        identity = actor()
        values = call(connections.list, identity.company_id)
        return [call(connections.public, item.id, identity.company_id) for item in values]

    def save(body, identity, old=None):
        connection = ProviderConnection(**body.model_dump(), company_id=identity.company_id,
                                        id=old.id if old else uid(),
                                        created_at=old.created_at if old else now())
        call(connections.save, connection, identity.company_id)
        return call(connections.public, connection.id, identity.company_id)

    @result.post("/connections", status_code=201)
    def create_connection(body: ConnectionInput):
        return call(save, body, actor("agents.manage"))

    @result.put("/connections/{connection_id}")
    def update_connection(connection_id: str, body: ConnectionInput):
        identity = actor("agents.manage")
        old = call(connections.get, connection_id, identity.company_id)
        return call(save, body, identity, old)

    @result.delete("/connections/{connection_id}", status_code=204)
    def delete_connection(connection_id: str):
        identity = actor("agents.manage")
        if any(agent.provider_connection_id == connection_id for agent in service.agents()):
            raise HTTPException(409, "Bu bağlantıyı kullanan ajan var. Önce ajanın bağlantısını değiştirin.")
        call(connections.delete, connection_id, identity.company_id)
        return Response(status_code=204)

    @result.put("/connections/{connection_id}/key")
    def write_key(connection_id: str, body: ConnectionKey):
        identity = actor("agents.manage")
        call(connections.set_key, connection_id, body.key.get_secret_value(), identity.company_id)
        return {"has_key": True}

    @result.delete("/connections/{connection_id}/key")
    def remove_key(connection_id: str):
        identity = actor("agents.manage")
        call(connections.delete_key, connection_id, identity.company_id)
        return {"has_key": False}

    @result.post("/connections/{connection_id}/test")
    def test_connection(connection_id: str, body: ConnectionTest):
        identity = actor("agents.manage")
        connection = call(connections.get, connection_id, identity.company_id)
        redactor = call(service._new_redactor)
        selected_model = body.model or connection.model
        if redactor.contains_secret(selected_model):
            raise HTTPException(422, "Model adı kayıtlı bir gizli değer içeremez.")
        if connection.provider == "shared":
            from .shared_provider import SharedProvider

            if shared_client is None:
                raise HTTPException(503, "Kurum modeli henüz etkin değil.")
            response = call(SharedProvider(shared_client).complete,
                            [{"role": "user", "content": "Bağlantı testi. Kısaca tamam yaz."}], [],
                            model=selected_model, max_tokens=64,
                            cancel=threading.Event(), deadline=time.monotonic() + 30)
            return {"ok": True, "message": "Kurum modeli bağlantısı doğrulandı.",
                    "input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens}
        return call(connections.test_connection, connection_id, identity.company_id, model=body.model)

    return result
