"""Pipeline de uma mensagem recebida no WhatsApp: idempotência → elegibilidade → IA → ações → resposta."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from app.config import Settings
from app.db import db
from app.domain.intents import Intent
from app.domain.niches import fill, niche_for
from app.domain.plans import feature_enabled, limits_for, within_limit
from app.jobs.queue import enqueue
from app.jobs.tasks import SEND_WHATSAPP
from app.logging import get_logger, tenant_id_var
from app.services import calendar_sync, knowledge, notifications, quota_alerts, scheduling
from app.services import media as media_service
from app.services.ai import AIDecision, AIService
from app.services.tenants import is_tenant_operational
from app.services.usage import AI_MESSAGES, ai_quota_available, increment
from generated_prisma.errors import UniqueViolationError

log = get_logger("conversation")

HISTORY_LIMIT = 10
OPT_OUT_PHRASES = (
    "nao quero receber",
    "nao quero mais receber",
    "parar de receber",
    "pare de mandar",
    "para de mandar",
    "nao me mande",
    "nao me manda",
    "sair da lista",
    "descadastrar",
    "remover meu numero",
    "nao quero mais mensagens",
)
OPT_OUT_REPLY = (
    "Entendido! Você não vai mais receber nossos lembretes de retorno por aqui. Se precisar de algo, é só chamar."
)


def wants_opt_out(text: str) -> bool:
    from app.domain.intents import normalize

    t = normalize(text)
    return any(p in t for p in OPT_OUT_PHRASES)


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
        where={"tenantId": tenant_id, "phone": phone},
        order=[{"createdAt": "desc"}, {"id": "desc"}],
        take=HISTORY_LIMIT,
    )
    return [{"role": "user" if str(m.role) == "USER" else "assistant", "content": m.content} for m in reversed(rows)]


def _local(dt: datetime, tz: ZoneInfo) -> str:
    return dt.astimezone(tz).strftime("%d/%m/%Y às %H:%M")


async def _upcoming(tenant_id: str, patient_id: str, tz: ZoneInfo) -> list[dict]:
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
    # Datas no fuso da clínica: é assim que o prompt as descreve e que o paciente as entende.
    return [
        {"id": a.id, "service": a.service, "date": a.date.astimezone(tz).isoformat(), "status": str(a.status)}
        for a in rows
    ]


async def _save_exchange(tenant_id: str, phone: str, user_text: str, reply: str) -> None:
    # Gravação sequencial (não create_many): garante ordem estável user → assistant no histórico.
    await db.message.create(data={"tenantId": tenant_id, "phone": phone, "role": "USER", "content": user_text[:4000]})
    await db.message.create(data={"tenantId": tenant_id, "phone": phone, "role": "ASSISTANT", "content": reply[:4000]})


async def _get_or_create_patient(tenant, phone: str, push_name: str | None):
    """Retorna (paciente, criado). Tolera duas primeiras mensagens simultâneas do mesmo número."""
    patient = await db.patient.find_unique(where={"tenantId_phone": {"tenantId": tenant.id, "phone": phone}})
    if patient is not None:
        return patient, False
    try:
        return (
            await db.patient.create(
                data={"tenantId": tenant.id, "phone": phone, "name": (push_name or "").strip()[:120] or None}
            ),
            True,
        )
    except UniqueViolationError:
        return await db.patient.find_unique(where={"tenantId_phone": {"tenantId": tenant.id, "phone": phone}}), False


async def _apply_actions(
    tenant, patient, decision: AIDecision, phone: str, text: str, upcoming: list[dict], services: list[dict]
) -> None:
    name = patient.name or phone
    tz = ZoneInfo(tenant.timezone or "America/Sao_Paulo")
    if decision.intent == Intent.SCHEDULE and decision.appointment_datetime and not decision.appointment_service:
        # Data sem procedimento: nada é criado, e a resposta não pode sugerir que ficou agendado.
        decision.reply = (
            f"Anotei o horário de {_local(decision.appointment_datetime, tz)}. Para eu registrar, me diga qual "
            "procedimento você quer agendar."
        )
        decision.appointment_datetime = None
        return
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
        async with db.tx() as tx:
            await scheduling.lock_tenant_agenda(tx, tenant.id)
            # Sob a trava: outra mensagem pode ter ocupado o slot entre a checagem acima e aqui.
            available, reason = await scheduling.check_availability(tenant, decision.appointment_datetime, duration)
            if not available:
                decision.reply = "Esse horário acabou de ser ocupado. Pode me dizer outro horário de sua preferência?"
                decision.extra["availability"] = reason
                return
            appt = await tx.appointment.create(
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
            body=f"{appt.service} em {_local(appt.date, tz)} (aguardando confirmação).",
            phone=phone,
        )
        await calendar_sync.schedule_sync(tenant.id, appt.id)
    elif decision.intent == Intent.CANCEL and upcoming:
        target = upcoming[0]
        when = _local(datetime.fromisoformat(target["date"]), tz)
        if decision.degraded or len(upcoming) > 1:
            # Sem IA (só regras) ou com mais de um agendamento futuro não dá para saber qual, nem se é mesmo
            # cancelamento: a equipe confirma antes de desmarcar.
            await notifications.notify(
                tenant.id,
                type_="APPOINTMENT_CANCELED",
                title=f"Pedido de cancelamento para confirmar: {name}",
                body=f'O paciente pediu para cancelar ("{text[:200]}"). Próximo agendamento: {target["service"]} em '
                f"{when}. Nada foi desmarcado ainda; confirme com o paciente.",
                phone=phone,
                dedupe_minutes=30,
            )
            return
        await db.appointment.update(where={"id": target["id"]}, data={"status": "CANCELED"})
        await calendar_sync.schedule_sync(tenant.id, target["id"])
        await notifications.notify(
            tenant.id,
            type_="APPOINTMENT_CANCELED",
            title=f"Cancelamento solicitado: {name}",
            body=f"{target['service']} em {when} foi cancelado pelo paciente via WhatsApp.",
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
        try:
            return await _process(
                settings,
                tenant=tenant,
                phone=phone,
                text=text,
                push_name=push_name,
                source=source,
                media=media,
                started=started,
            )
        except Exception:
            # Falha inesperada: solta a reivindicação para o reenvio do provedor ser processado de novo,
            # em vez de virar "duplicate_ignored" e deixar o paciente sem resposta para sempre.
            await db.processedmessage.delete_many(where={"tenantId": tenant.id, "messageId": message_id})
            raise
    finally:
        tenant_id_var.reset(token)


async def _process(
    settings: Settings,
    *,
    tenant,
    phone: str,
    text: str,
    push_name: str | None,
    source: str,
    media: media_service.MediaInput | None,
    started: float,
) -> InboundResult:

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
        # Estourar a cota não corta o atendimento (decisão de produto): só corta se o admin ligou hardLimit.
        if tenant.hardLimit:
            log.warning("inbound_quota_exceeded", used=used, limit=limit)
            return InboundResult(status="blocked", reason="quota_exceeded")
        log.info("inbound_over_quota", used=used, limit=limit)

    patient_limit = limits_for(str(tenant.plan)).max_patients
    first_contact = False
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
        patient, first_contact = await _get_or_create_patient(tenant, phone, push_name)
    elif push_name and not patient.name:
        patient = await db.patient.update(where={"id": patient.id}, data={"name": push_name.strip()[:120]})

    media_text: media_service.MediaText | None = None
    media_failed = False
    media_error = "media_unreadable"
    if media is not None and not feature_enabled(tenant, "media"):
        # Recurso de plano: não gastamos o provedor, avisamos a clínica e pedimos texto ao paciente.
        media_failed = True
        media_error = "media_not_in_plan"
        noun = "um áudio" if media.kind == "audio" else "uma imagem"
        await notifications.notify(
            tenant.id,
            type_="BILLING",
            title="Áudio e imagem não incluídos no plano",
            body=f"Um paciente enviou {noun}, mas o plano {tenant.plan} não inclui leitura de mídia pela "
            "assistente; ela pediu que ele escrevesse. Faça upgrade em Plano & uso para habilitar.",
            phone=phone,
            dedupe_minutes=24 * 60,
        )
    elif media is not None:
        media_text = await media_service.media_to_text(settings, media)
        if media_text is None:
            media_failed = True
        else:
            text = media_text.text
    if media_failed:
        # Registra a tentativa e responde com clareza; não consome a IA de atendimento.
        too_large = media_error == "media_unreadable" and media_service.too_large(media)
        reply = media_service.unsupported_reply(media.kind, too_large=too_large)
        await _save_exchange(tenant.id, phone, f"[{media.kind}] {text}".strip(), reply)
        await db.executionlog.create(
            data={
                "tenantId": tenant.id,
                "agent": "secretaria",
                "intent": Intent.INFO.value,
                "model": "rules",
                "input": f"[{media.kind}] {text}"[:4000],
                "output": reply,
                "error": media_error,
                "runTimeMs": int((time.perf_counter() - started) * 1000),
            }
        )
        # Não consome a quota de IA: nenhuma IA foi usada nesta resposta.
        await enqueue(SEND_WHATSAPP, {"tenantId": tenant.id, "phone": phone, "text": reply})
        log.info("inbound_media_unreadable", kind=media.kind, source=source, error=media_error)
        return InboundResult(status="processed", intent=Intent.INFO.value, reply=reply, degraded=True)

    if wants_opt_out(text):
        # LGPD: pedido explícito para não receber campanhas vale na hora, sem passar pela IA.
        await db.patient.update(where={"id": patient.id}, data={"marketingOptOut": True})
        await _save_exchange(tenant.id, phone, text, OPT_OUT_REPLY)
        await enqueue(SEND_WHATSAPP, {"tenantId": tenant.id, "phone": phone, "text": OPT_OUT_REPLY})
        await notifications.notify(
            tenant.id,
            type_="SYSTEM",
            title=f"Paciente pediu para não receber campanhas: {patient.name or phone}",
            body="A campanha de retorno não vai mais enviar mensagens para este número.",
            phone=phone,
            dedupe_minutes=24 * 60,
        )
        log.info("inbound_marketing_opt_out", source=source)
        return InboundResult(status="processed", intent=Intent.INFO.value, reply=OPT_OUT_REPLY, degraded=False)

    tz = ZoneInfo(tenant.timezone or "America/Sao_Paulo")
    history = await _history(tenant.id, phone)
    upcoming = await _upcoming(tenant.id, patient.id, tz)
    services = await scheduling.list_services(tenant.id, only_active=True)
    rules = await scheduling.get_rules(tenant.id)
    # Sugestões espalhadas em vários dias (2 por dia), não seis horários seguidos da mesma manhã.
    slots = scheduling.spread_slots(await scheduling.free_slots(tenant, days=7, limit=80), tz, per_day=2, limit=6)
    snippets = await knowledge.retrieve(settings, tenant.id, text) if feature_enabled(tenant, "knowledge") else []
    decision = await AIService(settings).decide(
        tenant,
        history=history,
        text=text,
        upcoming=upcoming,
        services_text=scheduling.services_to_text(services) if services else None,
        hours_text=scheduling.rules_to_text(rules) if rules else None,
        free_slots_text=", ".join(s.label(tz) for s in slots) if slots else None,
        knowledge_text=knowledge.snippets_to_text(snippets),
        knowledge_snippet=snippets[0].content[:350].strip() if snippets else None,
    )
    if snippets:
        decision.extra["knowledge"] = [s.title for s in snippets]

    await _apply_actions(tenant, patient, decision, phone, text, upcoming, services)

    await _save_exchange(tenant.id, phone, text, decision.reply)
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
    if not decision.degraded:
        # A quota do plano conta mensagens ATENDIDAS PELA IA; respostas por regras (IA indisponível) não.
        used_now = await increment(tenant.id, AI_MESSAGES)
        await quota_alerts.after_ai_message(settings, tenant, used_now)
    reply = decision.reply
    if first_contact and tenant.introEnabled:
        # Primeiro contato: a assistente diz que é assistente e que a equipe acompanha (sem "robô escondido").
        reply = fill(niche_for(tenant.niche).intro, tenant.name) + "\n\n" + reply
    await enqueue(SEND_WHATSAPP, {"tenantId": tenant.id, "phone": phone, "text": reply})
    log.info("inbound_processed", intent=decision.intent.value, degraded=decision.degraded, source=source)
    return InboundResult(status="processed", intent=decision.intent.value, reply=reply, degraded=decision.degraded)
