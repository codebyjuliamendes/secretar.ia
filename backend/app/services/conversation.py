"""Pipeline de uma mensagem recebida no WhatsApp: idempotência → elegibilidade → IA → ações → resposta."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from app.config import Settings
from app.db import db
from app.domain.intents import Intent
from app.domain.plans import limits_for, within_limit
from app.jobs.queue import enqueue
from app.jobs.tasks import SEND_WHATSAPP
from app.logging import get_logger, tenant_id_var
from app.services import calendar_sync, notifications, scheduling
from app.services import media as media_service
from app.services.ai import AIDecision, AIService
from app.services.tenants import is_tenant_operational
from app.services.usage import AI_MESSAGES, ai_quota_available, increment
from generated_prisma.errors import UniqueViolationError

log = get_logger("conversation")

HISTORY_LIMIT = 10


@dataclass
class InboundResult:
    status: str  # processed | duplicate_ignored | blocked | unsupported
    intent: str | None = None
    reply: str | None = None
    reason: str | None = None
    degraded: bool = False


async def _claim_message(tenant_id: str, message_id: str) -> bool:
    try:
        await db.processedmessage.create(data={"tenantId": tenant_id, "messageId": message_id})
        return True
    except UniqueViolationError:
        return False


async def _history(tenant_id: str, phone: str) -> list[dict]:
    rows = await db.message.find_many(
        where={"tenantId": tenant_id, "phone": phone}, order={"createdAt": "desc"}, take=HISTORY_LIMIT
    )
    return [{"role": "user" if str(m.role) == "USER" else "assistant", "content": m.content} for m in reversed(rows)]


async def _upcoming(tenant_id: str, patient_id: str) -> list[dict]:
    rows = await db.appointment.find_many(
        where={
            "tenantId": tenant_id,
            "patientId": patient_id,
            "status": {"in": ["PENDING", "CONFIRMED"]},
            "date": {"gte": datetime.now(UTC)},
        },
        order={"date": "asc"},
        take=3,
    )
    return [{"id": a.id, "service": a.service, "date": a.date.isoformat(), "status": str(a.status)} for a in rows]


async def _apply_actions(
    tenant, patient, decision: AIDecision, phone: str, text: str, upcoming: list[dict], services: list[dict]
) -> None:
    name = patient.name or phone
    if decision.intent == Intent.SCHEDULE and decision.appointment_datetime and decision.appointment_service:
        svc = scheduling.match_service(services, decision.appointment_service)
        duration = (svc or {}).get("durationMin") or scheduling.DEFAULT_DURATION_MIN
        available, reason = await scheduling.check_availability(tenant, decision.appointment_datetime, duration)
        if not available:
            # Nunca criamos um horário indisponível: respondemos com alternativas reais.
            tz = ZoneInfo(tenant.timezone or "America/Sao_Paulo")
            alternatives = await scheduling.free_slots(
                tenant,
                start_from=max(datetime.now(UTC), decision.appointment_datetime - timedelta(hours=3)),
                days=7,
                duration_min=duration,
                limit=3,
            )
            alt_txt = ", ".join(s.label(tz) for s in alternatives)
            decision.reply = "Esse horário não está disponível. " + (
                f"Posso oferecer: {alt_txt}. Qual prefere?"
                if alt_txt
                else "Vou pedir para a equipe te retornar com opções."
            )
            decision.extra["availability"] = reason
            log.info("ai_slot_unavailable", reason=reason)
            return
        appt = await db.appointment.create(
            data={
                "tenantId": tenant.id,
                "patientId": patient.id,
                "serviceId": (svc or {}).get("id"),
                "service": ((svc or {}).get("name") or decision.appointment_service)[:120],
                "date": decision.appointment_datetime,
                "durationMin": duration,
                "endAt": decision.appointment_datetime + timedelta(minutes=duration),
                "priceCents": (svc or {}).get("priceCents"),
                "status": "PENDING",
                "source": "AI",
            }
        )
        await notifications.notify(
            tenant.id,
            type_="APPOINTMENT_REQUESTED",
            title=f"Novo pedido de agendamento: {name}",
            body=f"{appt.service} em {appt.date.astimezone(UTC).isoformat()} (aguardando confirmação).",
            phone=phone,
        )
        await calendar_sync.schedule_sync(tenant.id, appt.id)
    elif decision.intent == Intent.CANCEL and upcoming:
        target = upcoming[0]
        await db.appointment.update(where={"id": target["id"]}, data={"status": "CANCELED"})
        await calendar_sync.schedule_sync(tenant.id, target["id"])
        await notifications.notify(
            tenant.id,
            type_="APPOINTMENT_CANCELED",
            title=f"Cancelamento solicitado: {name}",
            body=f"{target['service']} em {target['date']} foi cancelado pelo paciente via WhatsApp.",
            phone=phone,
        )
    if decision.needs_human or decision.intent == Intent.HUMAN:
        await notifications.notify(
            tenant.id,
            type_="HUMAN_HANDOFF",
            title=f"Paciente pede atendimento humano: {name}",
            body=f'Última mensagem: "{text[:300]}"',
            phone=phone,
            dedupe_minutes=30,
        )


async def handle_inbound(
    settings: Settings,
    *,
    tenant,
    phone: str,
    text: str,
    message_id: str,
    push_name: str | None = None,
    source: str = "webhook",
    media: media_service.MediaInput | None = None,
) -> InboundResult:
    """`text` é a mensagem do paciente; com `media`, o texto é derivado (transcrição/descrição) e `text`
    vira a legenda. Sem IA para ler a mídia, respondemos pedindo texto em vez de fingir compreensão."""
    token = tenant_id_var.set(tenant.id)
    started = time.perf_counter()
    try:
        if not await _claim_message(tenant.id, message_id):
            log.info("inbound_duplicate", message_id=message_id)
            return InboundResult(status="duplicate_ignored")

        operational, reason = is_tenant_operational(tenant)
        if not operational:
            log.warning("inbound_blocked", reason=reason)
            await notifications.notify(
                tenant.id,
                type_="BILLING",
                title="Atendimento pausado",
                body="Uma mensagem de paciente não foi respondida porque a assinatura da clínica está inativa.",
                phone=phone,
                dedupe_minutes=24 * 60,
            )
            return InboundResult(status="blocked", reason=reason)

        ok, used, limit = await ai_quota_available(tenant.id, str(tenant.plan))
        if not ok:
            log.warning("inbound_quota_exceeded", used=used, limit=limit)
            await notifications.notify(
                tenant.id,
                type_="BILLING",
                title="Limite mensal de mensagens atingido",
                body=f"O plano {tenant.plan} permite {limit} mensagens/mês. Faça upgrade para continuar respondendo.",
                dedupe_minutes=24 * 60,
            )
            return InboundResult(status="blocked", reason="quota_exceeded")

        patient_limit = limits_for(str(tenant.plan)).max_patients
        patient = await db.patient.find_unique(where={"tenantId_phone": {"tenantId": tenant.id, "phone": phone}})
        if patient is None:
            count = await db.patient.count(where={"tenantId": tenant.id})
            if not within_limit(count, patient_limit):
                await notifications.notify(
                    tenant.id,
                    type_="BILLING",
                    title="Limite de pacientes do plano atingido",
                    body="Um novo paciente entrou em contato mas o limite do plano foi atingido.",
                    dedupe_minutes=24 * 60,
                )
                return InboundResult(status="blocked", reason="patient_limit")
            patient = await db.patient.create(
                data={"tenantId": tenant.id, "phone": phone, "name": (push_name or "").strip()[:120] or None}
            )
        elif push_name and not patient.name:
            patient = await db.patient.update(where={"id": patient.id}, data={"name": push_name.strip()[:120]})

        media_text: media_service.MediaText | None = None
        media_failed = False
        if media is not None:
            media_text = await media_service.media_to_text(settings, media)
            if media_text is None:
                media_failed = True
            else:
                text = media_text.text
        if media_failed:
            # Registra a tentativa e responde com clareza; não consome a IA de atendimento.
            too_large = not media_service.size_ok(media)
            reply = media_service.unsupported_reply(media.kind, too_large=too_large)
            await db.message.create_many(
                data=[
                    {
                        "tenantId": tenant.id,
                        "phone": phone,
                        "role": "USER",
                        "content": f"[{media.kind}] {text}".strip(),
                    },
                    {"tenantId": tenant.id, "phone": phone, "role": "ASSISTANT", "content": reply},
                ]
            )
            await db.executionlog.create(
                data={
                    "tenantId": tenant.id,
                    "agent": "secretaria",
                    "intent": Intent.INFO.value,
                    "model": "rules",
                    "input": f"[{media.kind}] {text}"[:4000],
                    "output": reply,
                    "error": "media_unreadable",
                    "runTimeMs": int((time.perf_counter() - started) * 1000),
                }
            )
            await increment(tenant.id, AI_MESSAGES)
            await enqueue(SEND_WHATSAPP, {"tenantId": tenant.id, "phone": phone, "text": reply})
            log.info("inbound_media_unreadable", kind=media.kind, source=source)
            return InboundResult(status="processed", intent=Intent.INFO.value, reply=reply, degraded=True)

        history = await _history(tenant.id, phone)
        upcoming = await _upcoming(tenant.id, patient.id)
        services = await scheduling.list_services(tenant.id, only_active=True)
        rules = await scheduling.get_rules(tenant.id)
        tz = ZoneInfo(tenant.timezone or "America/Sao_Paulo")
        slots = await scheduling.free_slots(tenant, days=7, limit=6)
        decision = await AIService(settings).decide(
            tenant,
            history=history,
            text=text,
            upcoming=upcoming,
            services_text=scheduling.services_to_text(services) if services else None,
            hours_text=scheduling.rules_to_text(rules) if rules else None,
            free_slots_text=", ".join(s.label(tz) for s in slots) if slots else None,
        )

        await _apply_actions(tenant, patient, decision, phone, text, upcoming, services)

        await db.message.create_many(
            data=[
                {"tenantId": tenant.id, "phone": phone, "role": "USER", "content": text[:4000]},
                {
                    "tenantId": tenant.id,
                    "phone": phone,
                    "role": "ASSISTANT",
                    "content": decision.reply[:4000],
                },
            ]
        )
        await db.executionlog.create(
            data={
                "tenantId": tenant.id,
                "agent": "secretaria",
                "intent": decision.intent.value,
                "model": decision.model,
                "input": text[:4000],
                "output": decision.reply[:4000],
                "error": decision.error,
                "inputTokens": (decision.input_tokens or 0) + (media_text.input_tokens or 0)
                if media_text
                else decision.input_tokens,
                "outputTokens": (decision.output_tokens or 0) + (media_text.output_tokens or 0)
                if media_text
                else decision.output_tokens,
                "runTimeMs": int((time.perf_counter() - started) * 1000),
            }
        )
        await increment(tenant.id, AI_MESSAGES)
        await enqueue(SEND_WHATSAPP, {"tenantId": tenant.id, "phone": phone, "text": decision.reply})
        log.info("inbound_processed", intent=decision.intent.value, degraded=decision.degraded, source=source)
        return InboundResult(
            status="processed", intent=decision.intent.value, reply=decision.reply, degraded=decision.degraded
        )
    finally:
        tenant_id_var.reset(token)
