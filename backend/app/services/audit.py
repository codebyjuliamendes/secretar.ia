"""Trilha de auditoria: quem fez o quê, em qual recurso, quando."""

from __future__ import annotations

from typing import Any

from app.db import db
from app.logging import get_logger
from generated_prisma import Json

log = get_logger("audit")


async def record(
    *,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    tenant_id: str | None = None,
    actor_user_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    ip: str | None = None,
) -> None:
    try:
        data: dict[str, Any] = {
            "action": action,
            "resourceType": resource_type,
            "resourceId": resource_id,
            "tenantId": tenant_id,
            "actorUserId": actor_user_id,
            "ip": ip,
        }
        if metadata is not None:
            data["metadata"] = Json(metadata)
        await db.auditlog.create(data=data)
    except Exception as exc:  # noqa: BLE001 - auditoria nunca derruba a operação principal
        log.error("audit_write_failed", action=action, error=str(exc))
    log.info("audit", action=action, resource_type=resource_type, resource_id=resource_id)


async def list_for_tenant(tenant_id: str, *, limit: int = 50, cursor: str | None = None) -> list[dict]:
    kwargs: dict[str, Any] = {
        "where": {"tenantId": tenant_id},
        "order": {"createdAt": "desc"},
        "take": limit,
        "include": {"actor": True},
    }
    if cursor:
        kwargs["cursor"] = {"id": cursor}
        kwargs["skip"] = 1
    rows = await db.auditlog.find_many(**kwargs)
    return [
        {
            "id": r.id,
            "action": r.action,
            "resourceType": r.resourceType,
            "resourceId": r.resourceId,
            "actor": {"id": r.actor.id, "name": r.actor.name, "email": r.actor.email} if r.actor else None,
            "metadata": r.metadata,
            "createdAt": r.createdAt.isoformat(),
        }
        for r in rows
    ]
