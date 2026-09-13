"""Operações sobre tenants (clínicas): visão para admin e configurações da própria clínica."""

from __future__ import annotations

from typing import Any

from app.db import db
from app.domain.niches import NICHES, niche_view
from app.domain.plans import Plan, feature_access_view, limits_for, plan_public_view
from app.errors import ConflictError, NotFoundError
from app.services import audit
from generated_prisma.errors import UniqueViolationError

ALLOWED_TENANT_STATUSES = {"PENDING", "ACTIVE", "PAST_DUE", "CANCELED", "SUSPENDED"}


def tenant_public(t) -> dict:
    return {
        "id": t.id,
        "name": t.name,
        "whatsapp": t.whatsapp,
        "whatsappConnected": t.whatsappConnected,
        "status": str(t.status),
        "plan": str(t.plan),
        "timezone": t.timezone,
        "niche": niche_view(getattr(t, "niche", None)),
        "createdAt": t.createdAt.isoformat(),
    }


def tenant_settings_view(t) -> dict:
    return {
        **tenant_public(t),
        "prompt": t.prompt,
        "tone": t.tone,
        "prices": t.prices,
        "businessHours": t.businessHours,
        "upsellEnabled": t.upsellEnabled,
        "upsellMessage": t.upsellMessage,
        "upsellDays": t.upsellDays,
        "slotMinutes": t.slotMinutes,
        "features": t.features or {},
        "featureAccess": feature_access_view(t),
        "planLimits": plan_public_view(Plan(str(t.plan))),
    }


def is_tenant_operational(t) -> tuple[bool, str | None]:
    """Define se a IA deve responder pacientes deste tenant."""
    status = str(t.status)
    if status in ("PENDING", "PAST_DUE", "CANCELED", "SUSPENDED"):
        return False, f"tenant_{status.lower()}"
    return True, None


async def get_tenant_or_404(tenant_id: str):
    tenant = await db.tenant.find_unique(where={"id": tenant_id})
    if tenant is None:
        raise NotFoundError("Clínica não encontrada.")
    return tenant


async def update_settings(tenant_id: str, data: dict[str, Any], *, actor_user_id: str, ip: str | None) -> dict:
    tenant = await get_tenant_or_404(tenant_id)
    payload = {k: v for k, v in data.items() if v is not None}
    if "upsellEnabled" in payload and payload["upsellEnabled"] and not limits_for(str(tenant.plan)).upsell_campaigns:
        raise ConflictError("Campanhas de upsell não estão disponíveis no seu plano.", code="plan_feature_locked")
    updated = await db.tenant.update(where={"id": tenant_id}, data=payload)
    await audit.record(
        action="tenant.settings_updated",
        resource_type="tenant",
        resource_id=tenant_id,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        metadata={"fields": sorted(payload)},
        ip=ip,
    )
    return tenant_settings_view(updated)


# ----------------------------- SUPER ADMIN -----------------------------


async def admin_list_tenants(*, search: str | None, status: str | None, limit: int, offset: int) -> dict:
    where: dict[str, Any] = {}
    if search:
        where["OR"] = [
            {"name": {"contains": search, "mode": "insensitive"}},
            {"whatsapp": {"contains": search}},
        ]
    if status:
        where["status"] = status
    total = await db.tenant.count(where=where)
    rows = await db.query_raw(
        """
        SELECT t.id, t.name, t.whatsapp, t.status::text AS status, t.plan::text AS plan, t.niche,
               t."whatsappConnected", t."createdAt",
               COALESCE(a.cnt, 0) AS "appointmentCount", COALESCE(p.cnt, 0) AS "patientCount",
               COALESCE(m.cnt, 0) AS "memberCount"
        FROM "Tenant" t
        LEFT JOIN (SELECT "tenantId", COUNT(*) cnt FROM "Appointment" GROUP BY "tenantId") a ON a."tenantId" = t.id
        LEFT JOIN (SELECT "tenantId", COUNT(*) cnt FROM "Patient" GROUP BY "tenantId") p ON p."tenantId" = t.id
        LEFT JOIN (SELECT "tenantId", COUNT(*) cnt FROM "Membership" GROUP BY "tenantId") m ON m."tenantId" = t.id
        WHERE ($1::text IS NULL OR t.name ILIKE '%' || $1 || '%' OR t.whatsapp LIKE '%' || $1 || '%')
          AND ($2::text IS NULL OR t.status::text = $2)
        ORDER BY t."createdAt" DESC
        LIMIT $3 OFFSET $4
        """,
        search,
        status,
        limit,
        offset,
    )
    items = []
    for r in rows:
        items.append(
            {
                "id": r["id"],
                "name": r["name"],
                "whatsapp": r["whatsapp"],
                "status": r["status"],
                "plan": r["plan"],
                "niche": r.get("niche") or "clinica",
                "whatsappConnected": bool(r["whatsappConnected"]),
                "createdAt": _iso(r.get("createdAt")),
                "appointmentCount": int(r["appointmentCount"] or 0),
                "patientCount": int(r["patientCount"] or 0),
                "memberCount": int(r["memberCount"] or 0),
            }
        )
    return {"items": items, "total": total, "limit": limit, "offset": offset}


def _iso(v) -> str | None:
    if v is None:
        return None
    return v.isoformat() if hasattr(v, "isoformat") else str(v)


async def admin_overview() -> dict:
    rows = await db.query_raw(
        """
        SELECT
          COUNT(*) FILTER (WHERE status = 'ACTIVE') AS active,
          COUNT(*) FILTER (WHERE status = 'PENDING') AS pending,
          COUNT(*) FILTER (WHERE status = 'PAST_DUE') AS past_due,
          COUNT(*) FILTER (WHERE status IN ('CANCELED','SUSPENDED')) AS inactive,
          COUNT(*) AS total
        FROM "Tenant"
        """
    )
    r = rows[0] if rows else {}
    plan_rows = await db.query_raw(
        """SELECT plan::text AS plan, COUNT(*) AS cnt FROM "Tenant" WHERE status = 'ACTIVE' GROUP BY plan"""
    )
    mrr_cents = sum(limits_for(pr["plan"]).price_cents_month * int(pr["cnt"]) for pr in plan_rows)
    msgs = await db.query_raw(
        """SELECT COALESCE(SUM(count),0) AS total FROM "UsageCounter"
           WHERE metric = 'ai_messages' AND period = to_char(NOW() AT TIME ZONE 'UTC', 'YYYY-MM')"""
    )
    failed_jobs = await db.job.count(where={"status": "FAILED"})
    return {
        "tenants": {
            "total": int(r.get("total") or 0),
            "active": int(r.get("active") or 0),
            "pending": int(r.get("pending") or 0),
            "pastDue": int(r.get("past_due") or 0),
            "inactive": int(r.get("inactive") or 0),
        },
        "mrrCents": mrr_cents,
        "aiMessagesThisMonth": int((msgs[0]["total"] if msgs else 0) or 0),
        "failedJobs": failed_jobs,
    }


async def admin_create_tenant(data: dict[str, Any], *, actor_user_id: str, ip: str | None) -> dict:
    try:
        tenant = await db.tenant.create(
            data={
                "name": data["name"],
                "whatsapp": data["whatsapp"],
                "prompt": data["prompt"],
                "prices": data.get("prices"),
                "businessHours": data.get("businessHours"),
                "plan": data.get("plan") or "BASIC",
                "tone": data.get("tone") or "acolhedor",
                "niche": data.get("niche") or "clinica",
                "status": data.get("status") or "ACTIVE",
            }
        )
    except UniqueViolationError as exc:
        raise ConflictError("Já existe uma clínica com este WhatsApp.", code="whatsapp_taken") from exc
    from app.services.scheduling import ensure_default_rules

    await ensure_default_rules(tenant.id)  # mesmas janelas padrão do cadastro (seg–sex 09–18)
    await audit.record(
        action="admin.tenant_created",
        resource_type="tenant",
        resource_id=tenant.id,
        tenant_id=tenant.id,
        actor_user_id=actor_user_id,
        ip=ip,
    )
    return tenant_public(tenant)


async def admin_update_tenant(tenant_id: str, data: dict[str, Any], *, actor_user_id: str, ip: str | None) -> dict:
    tenant = await get_tenant_or_404(tenant_id)
    payload = {k: v for k, v in data.items() if v is not None}
    if "status" in payload and payload["status"] not in ALLOWED_TENANT_STATUSES:
        raise ConflictError("Status inválido.", code="invalid_status")
    if "niche" in payload and payload["niche"] not in NICHES:
        raise ConflictError("Nicho inválido.", code="invalid_niche")
    if "plan" in payload and "status" not in payload and str(tenant.status) == "PENDING":
        payload["status"] = "ACTIVE"  # liberar o plano é o gesto de ativação
    updated = await db.tenant.update(where={"id": tenant_id}, data=payload)
    await audit.record(
        action="admin.tenant_updated",
        resource_type="tenant",
        resource_id=tenant_id,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        metadata=payload,
        ip=ip,
    )
    return tenant_public(updated)
