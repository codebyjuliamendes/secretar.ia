"""Campanha de retenção (upsell): reengaja pacientes cujo procedimento periódico venceu.

Idempotência: um disparo por agendamento (UpsellDispatch.appointmentId único).
Respeita: plano do tenant, flag upsellEnabled, status operacional e janela de dias configurada.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.db import db
from app.domain.plans import limits_for
from app.jobs.queue import enqueue
from app.jobs.tasks import SEND_WHATSAPP
from app.logging import get_logger
from app.services.tenants import is_tenant_operational
from generated_prisma.errors import UniqueViolationError

log = get_logger("marketing")

DEFAULT_UPSELL_MESSAGE = (
    "Olá {nome}! Aqui é da {clinica}. Já faz um tempinho desde seu último procedimento ({servico}). "
    "Que tal garantir seu horário de retorno para manter os resultados? Responda por aqui e a gente agenda."
)
WINDOW_DAYS = 7  # tolerância para não perder pacientes se a rotina falhar por alguns dias


def render_message(template: str | None, *, nome: str, clinica: str, servico: str) -> str:
    tpl = template or DEFAULT_UPSELL_MESSAGE
    return (
        tpl.replace("{nome}", nome)
        .replace("{clinica}", clinica)
        .replace("{servico}", servico)
        .replace("{name}", nome)
        .replace("{clinic}", clinica)
        .replace("{service}", servico)
    )


async def run_upsell_campaign(*, tenant_id: str | None = None, dry_run: bool = False) -> dict:
    where = {"upsellEnabled": True}
    if tenant_id:
        where["id"] = tenant_id
    tenants = await db.tenant.find_many(where=where)
    sent = skipped = 0
    for tenant in tenants:
        operational, _ = is_tenant_operational(tenant)
        if not operational or not limits_for(str(tenant.plan)).upsell_campaigns:
            skipped += 1
            continue
        now = datetime.now(UTC)
        upper = now - timedelta(days=tenant.upsellDays)
        lower = upper - timedelta(days=WINDOW_DAYS)
        candidates = await db.appointment.find_many(
            where={
                "tenantId": tenant.id,
                "status": "COMPLETED",
                "date": {"gte": lower, "lte": upper},
                "upsellDispatches": {"none": {}},
            },
            include={"patient": True},
            take=500,
        )
        for appt in candidates:
            if appt.patient is None:
                continue
            # Não reengaja quem já tem retorno marcado.
            future = await db.appointment.count(
                where={
                    "tenantId": tenant.id,
                    "patientId": appt.patientId,
                    "date": {"gt": now},
                    "status": {"in": ["PENDING", "CONFIRMED"]},
                }
            )
            if future:
                skipped += 1
                continue
            if dry_run:
                sent += 1
                continue
            try:
                await db.upselldispatch.create(
                    data={"tenantId": tenant.id, "patientId": appt.patientId, "appointmentId": appt.id}
                )
            except UniqueViolationError:
                continue
            text = render_message(
                tenant.upsellMessage,
                nome=appt.patient.name or "tudo bem?",
                clinica=tenant.name,
                servico=appt.service,
            )
            await enqueue(SEND_WHATSAPP, {"tenantId": tenant.id, "phone": appt.patient.phone, "text": text})
            sent += 1
    result = {"tenantsEvaluated": len(tenants), "messagesQueued": sent, "skipped": skipped, "dryRun": dry_run}
    log.info("upsell_campaign_run", **result)
    return result
