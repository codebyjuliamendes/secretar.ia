"""Profissionais da conta (várias agendas em um só WhatsApp): "quero com a Paula".

Sem profissionais cadastrados nada muda. Com N ativos, a agenda aceita N atendimentos simultâneos e a
assistente/página pública deixam a pessoa escolher com quem.
"""

from __future__ import annotations

import unicodedata
from typing import Any

from app.db import db
from app.errors import ConflictError, NotFoundError
from app.services import audit
from generated_prisma.errors import UniqueViolationError


def view(p) -> dict:
    return {"id": p.id, "name": p.name, "active": p.active, "sortOrder": p.sortOrder}


async def list_professionals(tenant_id: str, *, only_active: bool = False) -> list[dict]:
    where: dict[str, Any] = {"tenantId": tenant_id}
    if only_active:
        where["active"] = True
    rows = await db.professional.find_many(where=where, order=[{"sortOrder": "asc"}, {"name": "asc"}])
    return [view(p) for p in rows]


def professionals_text(items: list[dict]) -> str | None:
    names = [p["name"] for p in items if p.get("active", True)]
    return ", ".join(names) if names else None


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower().strip()


def match_professional(items: list[dict], name: str | None) -> dict | None:
    """Casa o nome dito pela pessoa/IA com o cadastro (sem acento, prefixo ou contido)."""
    if not name:
        return None
    n = _norm(name)
    if not n:
        return None
    for p in items:
        if _norm(p["name"]) == n:
            return p
    for p in items:
        pn = _norm(p["name"])
        if pn.startswith(n) or n in pn or pn.split()[0] == n.split()[0]:
            return p
    return None


async def create_professional(tenant_id: str, data: dict[str, Any], *, actor_user_id: str, ip: str | None) -> dict:
    try:
        p = await db.professional.create(data={"tenantId": tenant_id, **data})
    except UniqueViolationError as exc:
        raise ConflictError("Já existe um profissional com este nome.", code="professional_exists") from exc
    await audit.record(
        action="professional.created",
        resource_type="professional",
        resource_id=p.id,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        metadata={"name": p.name},
        ip=ip,
    )
    return view(p)


async def update_professional(
    tenant_id: str, professional_id: str, data: dict[str, Any], *, actor_user_id: str, ip: str | None
) -> dict:
    p = await db.professional.find_first(where={"id": professional_id, "tenantId": tenant_id})
    if p is None:
        raise NotFoundError("Profissional não encontrado.")
    try:
        updated = await db.professional.update(where={"id": p.id}, data=data)
    except UniqueViolationError as exc:
        raise ConflictError("Já existe um profissional com este nome.", code="professional_exists") from exc
    await audit.record(
        action="professional.updated",
        resource_type="professional",
        resource_id=p.id,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        metadata={"fields": sorted(data)},
        ip=ip,
    )
    return view(updated)


async def delete_professional(tenant_id: str, professional_id: str, *, actor_user_id: str, ip: str | None) -> None:
    p = await db.professional.find_first(where={"id": professional_id, "tenantId": tenant_id})
    if p is None:
        raise NotFoundError("Profissional não encontrado.")
    await db.professional.delete(where={"id": p.id})  # agendamentos ficam (professionalId vira null)
    await audit.record(
        action="professional.deleted",
        resource_type="professional",
        resource_id=p.id,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        metadata={"name": p.name},
        ip=ip,
    )
