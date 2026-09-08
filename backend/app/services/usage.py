"""Medição de consumo por tenant e verificação de quotas por plano."""

from __future__ import annotations

from datetime import UTC, datetime

from app.db import db
from app.domain.plans import limits_for, within_limit

AI_MESSAGES = "ai_messages"


def current_period(now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    return f"{now.year:04d}-{now.month:02d}"


async def get_count(tenant_id: str, metric: str, period: str | None = None) -> int:
    row = await db.usagecounter.find_unique(
        where={
            "tenantId_period_metric": {
                "tenantId": tenant_id,
                "period": period or current_period(),
                "metric": metric,
            }
        }
    )
    return row.count if row else 0


async def increment(tenant_id: str, metric: str, amount: int = 1) -> int:
    """Incremento atômico (UPSERT ... ON CONFLICT) para evitar race entre webhooks simultâneos."""
    rows = await db.query_raw(
        """
        INSERT INTO "UsageCounter" (id, "tenantId", period, metric, count)
        VALUES (gen_random_uuid()::text, $1, $2, $3, $4)
        ON CONFLICT ("tenantId", period, metric) DO UPDATE SET count = "UsageCounter".count + EXCLUDED.count
        RETURNING count
        """,
        tenant_id,
        current_period(),
        metric,
        amount,
    )
    return int(rows[0]["count"]) if rows else amount


async def ai_quota_available(tenant_id: str, plan: str) -> tuple[bool, int, int]:
    """Retorna (dentro_da_quota, usado, limite)."""
    limit = limits_for(plan).ai_messages_per_month
    used = await get_count(tenant_id, AI_MESSAGES)
    return within_limit(used, limit), used, limit


async def usage_summary(tenant_id: str, plan: str) -> dict:
    lim = limits_for(plan)
    used = await get_count(tenant_id, AI_MESSAGES)
    patients = await db.patient.count(where={"tenantId": tenant_id})
    members = await db.membership.count(where={"tenantId": tenant_id})
    return {
        "period": current_period(),
        "aiMessages": {"used": used, "limit": lim.ai_messages_per_month},
        "patients": {"used": patients, "limit": lim.max_patients},
        "members": {"used": members, "limit": lim.max_members},
    }
