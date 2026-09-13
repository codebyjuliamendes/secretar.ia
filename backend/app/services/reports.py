"""Relatório mensal automático: o número que justifica a mensalidade.

Todo dia a rotina diária chama `send_monthly_reports`; ela só envia para contas ativas cujo último relatório
(`Tenant.lastReportPeriod`) ainda não é o mês anterior, então dias perdidos ou réplicas repetidas não duplicam.
O texto vai por e-mail para os OWNERs da conta, no vocabulário do nicho.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.config import Settings
from app.db import db
from app.domain.niches import niche_for
from app.jobs.queue import enqueue
from app.jobs.tasks import SEND_EMAIL
from app.logging import get_logger

log = get_logger("reports")

MONTHS = [
    "janeiro",
    "fevereiro",
    "março",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
]


def previous_period(now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    year, month = (now.year, now.month - 1) if now.month > 1 else (now.year - 1, 12)
    return f"{year:04d}-{month:02d}"


def period_bounds(period: str) -> tuple[datetime, datetime]:
    year, month = int(period[:4]), int(period[5:7])
    start = datetime(year, month, 1, tzinfo=UTC)
    end = datetime(year + 1, 1, 1, tzinfo=UTC) if month == 12 else datetime(year, month + 1, 1, tzinfo=UTC)
    return start, end


def period_label(period: str) -> str:
    return f"{MONTHS[int(period[5:7]) - 1]} de {period[:4]}"


async def monthly_report_data(tenant_id: str, period: str) -> dict[str, int]:
    start, end = period_bounds(period)
    rows = await db.query_raw(
        """
        SELECT
          (SELECT COUNT(*) FROM "ExecutionLog" WHERE "tenantId" = $1 AND "createdAt" >= $2::timestamp
              AND "createdAt" < $3::timestamp
              AND error IS NULL) AS answered,
          (SELECT COUNT(*) FROM "Appointment" WHERE "tenantId" = $1 AND "createdAt" >= $2::timestamp
              AND "createdAt" < $3::timestamp)
              AS appointments,
          (SELECT COUNT(*) FROM "Appointment" WHERE "tenantId" = $1 AND "createdAt" >= $2::timestamp
              AND "createdAt" < $3::timestamp
              AND source = 'AI') AS appointments_ai,
          (SELECT COUNT(*) FROM "Patient" WHERE "tenantId" = $1 AND "createdAt" >= $2::timestamp
              AND "createdAt" < $3::timestamp)
              AS new_people,
          (SELECT COUNT(*) FROM "Notification" WHERE "tenantId" = $1 AND type = 'HUMAN_HANDOFF'
              AND "createdAt" >= $2::timestamp
              AND "createdAt" < $3::timestamp) AS handoffs,
          (SELECT COUNT(*) FROM "UpsellDispatch" WHERE "tenantId" = $1 AND "createdAt" >= $2::timestamp
              AND "createdAt" < $3::timestamp)
              AS invites,
          (SELECT COUNT(DISTINCT d."patientId") FROM "UpsellDispatch" d
              JOIN "Appointment" a ON a."patientId" = d."patientId" AND a."createdAt" > d."createdAt"
                                   AND a.status <> 'CANCELED'
              WHERE d."tenantId" = $1 AND d."createdAt" >= $2::timestamp AND d."createdAt" < $3::timestamp) AS recovered
        """,
        tenant_id,
        start.replace(tzinfo=None),
        end.replace(tzinfo=None),
    )
    r = rows[0] if rows else {}
    keys = ("answered", "appointments", "appointments_ai", "new_people", "handoffs", "invites", "recovered")
    return {k: int(r.get(k) or 0) for k in keys}


def render_report(settings: Settings, tenant, period: str, data: dict[str, int]) -> tuple[str, str]:
    niche = niche_for(getattr(tenant, "niche", None))
    people = niche.people.lower()
    label = period_label(period)
    panel = f"{settings.frontend_url.rstrip('/')}/app/{tenant.id}"
    lines = [
        f"Olá! Aqui está o resumo de {label} da assistente de {tenant.name}.",
        "",
        f"- Mensagens respondidas pela assistente: {data['answered']}",
        f"- {niche.appointment.capitalize()}s registrados: {data['appointments']}"
        + (
            f" ({data['appointments_ai']} pela própria assistente, sem ninguém da equipe digitar)"
            if data["appointments_ai"]
            else ""
        ),
        f"- Novos {people}: {data['new_people']}",
        f"- Pedidos para falar com a equipe: {data['handoffs']}",
    ]
    if data["invites"]:
        lines.append(f"- Convites de retorno enviados: {data['invites']} · voltaram: {data['recovered']}")
    lines += [
        "",
        f"Painel completo: {panel}",
        f"Dúvidas ou quer ajustar algo? Responda este e-mail ou fale com {settings.sales_contact_name}.",
        "",
        "Secretar.ia",
    ]
    return f"Resumo de {label} - {tenant.name}", "\n".join(lines)


async def owner_emails(tenant_id: str) -> list[str]:
    rows = await db.membership.find_many(where={"tenantId": tenant_id, "role": "OWNER"}, include={"user": True})
    return sorted({m.user.email for m in rows if m.user and m.user.email})


async def send_report(settings: Settings, tenant, period: str, *, force: bool = False) -> dict[str, Any]:
    """Envia (ou reenvia, com force) o relatório de um período e carimba lastReportPeriod."""
    data = await monthly_report_data(tenant.id, period)
    subject, text = render_report(settings, tenant, period, data)
    emails = await owner_emails(tenant.id)
    for to in emails:
        await enqueue(SEND_EMAIL, {"to": to, "subject": subject, "text": text})
    if force or (tenant.lastReportPeriod or "") < period:
        await db.tenant.update(where={"id": tenant.id}, data={"lastReportPeriod": period})
    return {"period": period, "emails": emails, "data": data, "subject": subject, "text": text}


async def send_monthly_reports(settings: Settings, now: datetime | None = None) -> dict[str, int]:
    period = previous_period(now)
    start, _ = period_bounds(period)
    tenants = await db.tenant.find_many(where={"status": "ACTIVE"})
    sent = skipped = 0
    for tenant in tenants:
        if (tenant.lastReportPeriod or "") >= period:
            skipped += 1
            continue
        if tenant.createdAt >= period_bounds(period)[1]:
            # conta criada depois do mês fechado: nada a relatar, só carimba para não reavaliar todo dia
            await db.tenant.update(where={"id": tenant.id}, data={"lastReportPeriod": period})
            skipped += 1
            continue
        try:
            await send_report(settings, tenant, period)
            sent += 1
        except Exception as exc:  # noqa: BLE001 - um tenant com problema não pode travar os demais
            log.warning("monthly_report_failed", tenant_id=tenant.id, error=str(exc)[:200])
    result = {"period": period, "sent": sent, "skipped": skipped, "since": start.isoformat()}
    log.info("monthly_reports_done", **result)
    return result
