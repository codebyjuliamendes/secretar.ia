"""Notificações internas da clínica (Inbox). Evita duplicatas recentes para o mesmo evento."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.db import db


async def notify(
    tenant_id: str,
    *,
    type_: str,
    title: str,
    body: str,
    phone: str | None = None,
    dedupe_minutes: int = 0,
) -> bool:
    if dedupe_minutes:
        recent = await db.notification.find_first(
            where={
                "tenantId": tenant_id,
                "type": type_,
                "phone": phone,
                "title": title,
                "createdAt": {"gte": datetime.now(UTC) - timedelta(minutes=dedupe_minutes)},
            }
        )
        if recent:
            return False
    await db.notification.create(
        data={"tenantId": tenant_id, "type": type_, "title": title, "body": body, "phone": phone}
    )
    return True


async def list_notifications(tenant_id: str, *, unread_only: bool, limit: int, cursor: str | None) -> list[dict]:
    where: dict = {"tenantId": tenant_id}
    if unread_only:
        where["readAt"] = None
    kwargs: dict = {"where": where, "order": [{"createdAt": "desc"}, {"id": "desc"}], "take": limit}
    if cursor:
        kwargs["cursor"] = {"id": cursor}
        kwargs["skip"] = 1
    rows = await db.notification.find_many(**kwargs)
    return [
        {
            "id": n.id,
            "type": n.type,
            "title": n.title,
            "body": n.body,
            "phone": n.phone,
            "readAt": n.readAt.isoformat() if n.readAt else None,
            "createdAt": n.createdAt.isoformat(),
        }
        for n in rows
    ]


async def unread_count(tenant_id: str) -> int:
    return await db.notification.count(where={"tenantId": tenant_id, "readAt": None})


async def mark_read(tenant_id: str, notification_id: str | None) -> int:
    where: dict = {"tenantId": tenant_id, "readAt": None}
    if notification_id:
        where["id"] = notification_id
    return await db.notification.update_many(where=where, data={"readAt": datetime.now(UTC)})
