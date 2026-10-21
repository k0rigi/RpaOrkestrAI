"""Telegram'dan görev ve soru: kime gideceği yazılan ofis ve ajan adından bulunur, tahmin edilmez.

Biçim: «/gorev [Ofis:] [Ajan:] metin» ve «/sor [Ofis:] [Ajan:] soru». Ajan yazılmazsa iş ofisin yöneticisine gider.
Birden fazla ofisi olan hesap ofisi yazmadan iş veremez; aynı ad birden fazla ofiste varsa ofis sorulur.
"""

from __future__ import annotations

from dataclasses import dataclass

MAX_TEXT = 4000


class TargetError(ValueError):
    """Why the message could not be routed; the text is sent back to the person."""


@dataclass(frozen=True)
class Target:
    agent_id: str
    agent_name: str
    office_id: str | None
    office_name: str
    text: str


def fold(value: str) -> str:
    """Turkish-aware comparison: İ/I and i/ı written either way still match."""
    return " ".join(str(value).replace("İ", "i").replace("I", "ı").casefold().split())


def offices_of(actor) -> list[tuple[str | None, str]]:
    """The offices the account works in: (id, name). A firm without offices has one unnamed office."""
    rows = [(item[0], item[1]) for item in (actor.offices or ())]
    return rows or [(actor.office_id, actor.office_name or "")]


def office_actor(actor, office_id):
    return actor if office_id is None or office_id == actor.office_id else actor.in_office(office_id)


def team(service, actor) -> dict[str | None, list]:
    """Each office's agents the account can see, managers first."""
    agents = service.agent_store.agents()
    result = {}
    for office_id, _ in offices_of(actor):
        viewer = office_actor(actor, office_id)
        if viewer is None:
            continue
        visible = [agent for agent in agents if service._sees_agent(viewer, agent)]
        result[office_id] = sorted(visible, key=lambda agent: (agent.role != "manager", fold(agent.name)))
    return result


def _split(text: str) -> tuple[str, str] | None:
    head, separator, rest = text.partition(":")
    return (head.strip(), rest.strip()) if separator and head.strip() else None


def route(service, actor, text: str) -> Target:
    """Find the agent a message is for. Raises TargetError with a Turkish explanation."""
    text = str(text or "").strip()
    offices = offices_of(actor)
    names = {office_id: name for office_id, name in offices}
    members = team(service, actor)
    office_id, chosen = None, False
    split = _split(text)
    if split and len(offices) > 1:
        found = [identity for identity, name in offices if name and fold(name) == fold(split[0])]
        if found:
            office_id, chosen, text = found[0], True, split[1]
    if not chosen:
        office_id = offices[0][0] if len(offices) == 1 else None
    agent = None
    split = _split(text)
    if split:
        pool = members.get(office_id, []) if chosen or len(offices) == 1 else [
            agent for items in members.values() for agent in items]
        matches = [item for item in pool if fold(item.name) == fold(split[0])]
        if len(matches) > 1:
            raise TargetError(f"“{split[0]}” adında birden fazla ajan var. Başına ofis adını yazın: Ofis adı: "
                              f"{split[0]}: ...")
        if matches:
            agent, text = matches[0], split[1]
            office_id = agent.office_id if not chosen and len(offices) > 1 else office_id
    if not text:
        raise TargetError("Görev veya soru metni boş. Örnek: /gorev bugünkü bekleyen işleri özetle")
    if len(text) > MAX_TEXT:
        raise TargetError(f"Metin en fazla {MAX_TEXT} karakter olabilir.")
    if agent is None:
        if len(offices) > 1 and not chosen:
            listed = ", ".join(name for _, name in offices if name)
            raise TargetError(f"Birden fazla ofisiniz var; mesajı ofis adıyla başlatın (ör. {offices[0][1]}: ...). "
                              f"Ofisleriniz: {listed}.")
        managers = [item for item in members.get(office_id, []) if item.role == "manager"]
        if not managers:
            raise TargetError("Bu ofiste yönetici ajan yok; ajanın adını yazın: Ajan adı: ... (/ajanlar listeyi gösterir).")
        agent = managers[0]
    return Target(agent_id=agent.id, agent_name=agent.name, office_id=office_id,
                  office_name=names.get(office_id, "") or "", text=text)


def listing(service, actor) -> str:
    """The /ajanlar reply: every office with its agents."""
    members = team(service, actor)
    lines = []
    for office_id, name in offices_of(actor):
        agents = members.get(office_id, [])
        lines.append(f"{name} ofisi" if name else "Ajanlarınız")
        if not agents:
            lines.append("  (ajan yok)")
        for agent in agents:
            role = "yönetici" if agent.role == "manager" else agent.department or "departman"
            lines.append(f"  • {agent.name} ({role})")
        lines.append("")
    return "\n".join(lines).strip()
