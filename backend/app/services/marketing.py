"""Campanha de retenção (upsell): reengaja pacientes cujo procedimento periódico venceu.

Idempotência: um disparo por agendamento (UpsellDispatch.appointmentId único).
Respeita: plano do tenant, flag upsellEnabled, status operacional e janela de dias configurada.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.db import db
from app.domain.niches import niche_for
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


def default_message_for(tenant) -> str:
    """Texto pronto do nicho (o cliente não precisa escrever nada); a clínica genérica mantém o texto histórico."""
    return niche_for(getattr(tenant, "niche", None)).campaign or DEFAULT_UPSELL_MESSAGE


def render_message(template: str | None, *, nome: str, clinica: str, servico: str) -> str:
    tpl = template or DEFAULT_UPSELL_MESSAGE
    return (
        tpl.replace("{nome}", nome)
        .replace("{negocio}", clinica)
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
                "patient": {"is": {"marketingOptOut": False}},
            },
            include={"patient": True},
            order={"date": "desc"},
            take=500,
        )
        # Quem já voltou depois da janela (realizado, confirmado ou pendente) não recebe convite: uma consulta só.
        returned = await db.appointment.find_many(
            where={
                "tenantId": tenant.id,
                "patientId": {"in": sorted({a.patientId for a in candidates})},
                "date": {"gt": upper},
                "status": {"not": "CANCELED"},
            },
            distinct=["patientId"],
        )
        already_back = {a.patientId for a in returned}
        # Um convite por paciente por ciclo: quem já recebeu nos últimos `upsellDays` não recebe pelo 2º procedimento.
        recent = await db.upselldispatch.find_many(
            where={
                "tenantId": tenant.id,
                "patientId": {"in": sorted({a.patientId for a in candidates})},
                "createdAt": {"gte": now - timedelta(days=tenant.upsellDays)},
            },
            distinct=["patientId"],
        )
        messaged: set[str] = {d.patientId for d in recent}
        for appt in candidates:
            if appt.patient is None or appt.patientId in already_back or appt.patientId in messaged:
                skipped += 1
                continue
            messaged.add(appt.patientId)  # um convite por paciente por rodada, mesmo com vários procedimentos
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
                tenant.upsellMessage or default_message_for(tenant),
                nome=appt.patient.name or "tudo bem?",
                clinica=tenant.name,
                servico=appt.service,
            )
            await enqueue(SEND_WHATSAPP, {"tenantId": tenant.id, "phone": appt.patient.phone, "text": text})
            sent += 1
    result = {"tenantsEvaluated": len(tenants), "messagesQueued": sent, "skipped": skipped, "dryRun": dry_run}
    log.info("upsell_campaign_run", **result)
    return result
