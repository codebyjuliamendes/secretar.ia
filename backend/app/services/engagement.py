"""Engajamento pós-agendamento: lembrete de véspera com confirmação por resposta, lista de espera,
sinal por Pix e "perguntas sem resposta" (melhoria contínua da base de conhecimento).

Tudo aqui é por regras (sem IA), idempotente e respeita o vocabulário do nicho.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from app.config import Settings
from app.db import db
from app.domain.niches import niche_for
from app.jobs.queue import enqueue
from app.jobs.tasks import SEND_EMAIL, SEND_WHATSAPP
from app.logging import get_logger
from app.services import notifications
from app.services.tenants import is_tenant_operational

log = get_logger("engagement")

YES_WORDS = {"sim", "s", "confirmo", "confirmar", "confirmado", "ok", "pode ser", "isso", "claro", "certo", "yes"}
NO_WORDS = {"nao", "n", "cancela", "cancelar", "cancele", "desmarca", "desmarcar", "nao vou", "nao posso"}
REMINDER_WINDOW_HOURS = 36  # lembra quem tem compromisso entre agora e ~36h (véspera, uma vez)


def _norm(text: str) -> str:
    t = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9 ]+", " ", t).strip()


def _tz(tenant) -> ZoneInfo:
    return ZoneInfo(tenant.timezone or "America/Sao_Paulo")


def _when(dt: datetime, tz: ZoneInfo) -> str:
    local = dt.astimezone(tz)
    return f"{local.strftime('%d/%m')} às {local.strftime('%H:%M')}"


def _day_utc(dt: datetime, tz: ZoneInfo) -> datetime:
    """Meia-noite UTC do dia local: chave estável para agrupar pedidos por dia."""
    local = dt.astimezone(tz)
    return datetime(local.year, local.month, local.day, tzinfo=UTC)


# ------------------------------------------------------------------ lembrete de véspera


def reminder_text(tenant, appointment, patient_name: str | None) -> str:
    tz = _tz(tenant)
    hello = f"Olá, {patient_name}!" if patient_name else "Olá!"
    return (
        f"{hello} Lembrete de {tenant.name}: {appointment.service} em {_when(appointment.date, tz)}. "
        "Responda SIM para confirmar ou NÃO para cancelar."
    )


async def send_reminders(now: datetime | None = None) -> int:
    """Manda um lembrete por compromisso na véspera; marca reminderSentAt para nunca repetir."""
    now = now or datetime.now(UTC)
    rows = await db.appointment.find_many(
        where={
            "status": {"in": ["PENDING", "CONFIRMED"]},
            "reminderSentAt": None,
            "date": {"gt": now + timedelta(hours=2), "lt": now + timedelta(hours=REMINDER_WINDOW_HOURS)},
        },
        include={"patient": True, "tenant": True},
    )
    sent = 0
    for appt in rows:
        tenant = appt.tenant
        operational, _ = is_tenant_operational(tenant)
        if not tenant.reminderEnabled or not operational or not tenant.whatsappConnected:
            continue
        await db.appointment.update(where={"id": appt.id}, data={"reminderSentAt": now})
        await enqueue(
            SEND_WHATSAPP,
            {
                "tenantId": tenant.id,
                "phone": appt.patient.phone,
                "text": reminder_text(tenant, appt, appt.patient.name),
            },
        )
        sent += 1
    log.info("reminders_sent", count=sent)
    return sent


async def handle_reminder_reply(tenant, patient, text: str) -> tuple[str, str] | None:
    """Se a pessoa está respondendo a um lembrete (SIM/NÃO), resolve sem IA. Retorna (intent, reply) ou None."""
    norm = _norm(text)
    if not norm or len(norm) > 40:
        return None
    is_yes = norm in YES_WORDS
    is_no = norm in NO_WORDS or norm.startswith("nao ")
    if not (is_yes or is_no):
        return None
    appt = await db.appointment.find_first(
        where={
            "tenantId": tenant.id,
            "patientId": patient.id,
            "reminderSentAt": {"not": None},
            "status": {"in": ["PENDING", "CONFIRMED"]},
            "date": {"gt": datetime.now(UTC)},
        },
        order={"date": "asc"},
    )
    if appt is None:
        return None
    tz = _tz(tenant)
    name = patient.name or patient.phone
    if is_yes:
        if str(appt.status) != "CONFIRMED":
            await db.appointment.update(where={"id": appt.id}, data={"status": "CONFIRMED"})
            from app.services import calendar_sync

            await calendar_sync.schedule_sync(tenant.id, appt.id)
        reply = f"Confirmado: {appt.service} em {_when(appt.date, tz)}. Até lá!"
        return "CONFIRMAR", reply
    await db.appointment.update(where={"id": appt.id}, data={"status": "CANCELED"})
    from app.services import calendar_sync, scheduling

    await calendar_sync.schedule_sync(tenant.id, appt.id)
    await notifications.notify(
        tenant.id,
        type_="APPOINTMENT_CANCELED",
        title=f"Cancelou pelo lembrete: {name}",
        body=f"{appt.service} em {_when(appt.date, tz)} foi liberado; a lista de espera foi avisada.",
        phone=patient.phone,
    )
    await offer_freed_slot(tenant, appt)
    alternatives = await scheduling.free_slots(tenant, days=7, duration_min=appt.durationMin or 60, limit=40)
    options = scheduling.spread_slots(alternatives, tz, per_day=1, limit=3)
    alt = ", ".join(s.label(tz) for s in options)
    reply = f"Cancelei {appt.service} de {_when(appt.date, tz)}. " + (
        f"Quer remarcar? Tenho {alt}. É só me dizer qual." if alt else "Quando quiser remarcar, é só me chamar."
    )
    return "CANCELAR", reply


# ------------------------------------------------------------------ lista de espera


async def waitlist_add(tenant, patient, desired_dt: datetime, service: str | None) -> None:
    """Pedido de horário que não estava livre: guarda o dia para avisar quando abrir vaga (um por pessoa/dia)."""
    day = _day_utc(desired_dt, _tz(tenant))
    existing = await db.waitlistentry.find_first(
        where={"tenantId": tenant.id, "patientId": patient.id, "desiredDay": day, "notifiedAt": None}
    )
    if existing:
        return
    await db.waitlistentry.create(
        data={
            "tenantId": tenant.id,
            "patientId": patient.id,
            "desiredDay": day,
            "service": (service or "")[:120] or None,
        }
    )


async def offer_freed_slot(tenant, appointment, *, limit: int = 3) -> int:
    """Um horário abriu: avisa quem pediu aquele dia e não conseguiu (menos quem acabou de cancelar)."""
    tz = _tz(tenant)
    day = _day_utc(appointment.date, tz)
    entries = await db.waitlistentry.find_many(
        where={
            "tenantId": tenant.id,
            "desiredDay": day,
            "notifiedAt": None,
            "patientId": {"not": appointment.patientId},
        },
        include={"patient": True},
        order={"createdAt": "asc"},
        take=limit,
    )
    if not entries:
        return 0
    operational, _ = is_tenant_operational(tenant)
    if not operational:
        return 0
    now = datetime.now(UTC)
    niche = niche_for(getattr(tenant, "niche", None))
    for e in entries:
        hello = f"Olá, {e.patient.name}!" if e.patient.name else "Olá!"
        what = e.service or appointment.service or niche.appointment
        text = (
            f"{hello} Abriu um horário em {tenant.name}: {_when(appointment.date, tz)} para {what}. "
            "Quer? Responda por aqui e eu reservo."
        )
        await enqueue(SEND_WHATSAPP, {"tenantId": tenant.id, "phone": e.patient.phone, "text": text})
        await db.waitlistentry.update(where={"id": e.id}, data={"notifiedAt": now})
    log.info("waitlist_offered", count=len(entries))
    return len(entries)


# ------------------------------------------------------------------ sinal por Pix


def deposit_text(tenant) -> str | None:
    if not tenant.depositEnabled or not tenant.depositCents or not (tenant.pixKey or "").strip():
        return None
    value = f"R$ {tenant.depositCents / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return (
        f"Para garantir o horário, pedimos um sinal de {value} via Pix (chave: {tenant.pixKey.strip()}). "
        "Envie o comprovante por aqui e a equipe confirma."
    )


# ------------------------------------------------------------------ perguntas sem resposta


async def record_unanswered(tenant_id: str, phone: str, question: str) -> None:
    q = (question or "").strip()
    if len(q) < 6:
        return
    await db.unansweredquestion.create(data={"tenantId": tenant_id, "phone": phone, "question": q[:500]})


async def list_unanswered(tenant_id: str, *, days: int = 30, limit: int = 50) -> list[dict]:
    """Agrupa perguntas parecidas (texto normalizado) e conta quantas pessoas perguntaram."""
    since = datetime.now(UTC) - timedelta(days=days)
    rows = await db.unansweredquestion.find_many(
        where={"tenantId": tenant_id, "resolvedAt": None, "createdAt": {"gte": since}},
        order={"createdAt": "desc"},
        take=500,
    )
    groups: dict[str, dict] = {}
    for r in rows:
        key = " ".join(_norm(r.question).split()[:8])
        g = groups.setdefault(
            key, {"id": r.id, "question": r.question, "count": 0, "phones": set(), "lastAskedAt": r.createdAt}
        )
        g["count"] += 1
        g["phones"].add(r.phone)
        g["ids"] = g.get("ids", []) + [r.id]
    items = sorted(groups.values(), key=lambda g: (-len(g["phones"]), -g["count"]))[:limit]
    return [
        {
            "id": g["id"],
            "ids": g["ids"],
            "question": g["question"],
            "count": g["count"],
            "people": len(g["phones"]),
            "lastAskedAt": g["lastAskedAt"].isoformat(),
        }
        for g in items
    ]


async def resolve_unanswered(tenant_id: str, ids: list[str]) -> int:
    res = await db.unansweredquestion.update_many(
        where={"tenantId": tenant_id, "id": {"in": ids}, "resolvedAt": None}, data={"resolvedAt": datetime.now(UTC)}
    )
    return int(res)


async def questions_digest(settings: Settings, now: datetime | None = None) -> int:
    """Semanal: contas com 3+ perguntas sem resposta nos últimos 7 dias recebem aviso no painel e por e-mail."""
    now = now or datetime.now(UTC)
    since = now - timedelta(days=7)
    tenants = await db.tenant.find_many(
        where={"status": "ACTIVE", "OR": [{"lastQuestionsDigestAt": None}, {"lastQuestionsDigestAt": {"lt": since}}]}
    )
    sent = 0
    for tenant in tenants:
        items = await list_unanswered(tenant.id, days=7, limit=5)
        total = sum(i["count"] for i in items)
        if total < 3:
            continue
        top = "; ".join(f"“{i['question'][:80]}” ({i['people']})" for i in items[:3])
        title = f"{total} perguntas que a assistente não soube responder esta semana"
        body = f"As mais comuns: {top}. Adicione a resposta à base de conhecimento e ela passa a responder sozinha."
        await notifications.notify(tenant.id, type_="SYSTEM", title=title, body=body, dedupe_minutes=6 * 24 * 60)
        from app.services.reports import owner_emails

        link = f"{settings.frontend_url.rstrip('/')}/app/{tenant.id}/settings#perguntas"
        for to in await owner_emails(tenant.id):
            await enqueue(
                SEND_EMAIL,
                {
                    "to": to,
                    "subject": f"{title} - {tenant.name}",
                    "text": f"{body}\n\nVeja e resolva em: {link}\n\nSecretar.ia",
                },
            )
        await db.tenant.update(where={"id": tenant.id}, data={"lastQuestionsDigestAt": now})
        sent += 1
    log.info("questions_digest_done", tenants=sent)
    return sent
