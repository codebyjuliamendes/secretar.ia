"""Página pública de agendamento (/agendar/{slug}): serviço → horário livre → nome e WhatsApp.

Mesma agenda, mesmas regras e a mesma trava da assistente; o pedido nasce PENDENTE (source WEB) e a equipe
confirma. Quem agenda recebe a confirmação pelo WhatsApp do negócio quando ele está conectado.
"""

from __future__ import annotations

import re
import secrets
import unicodedata
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.db import db
from app.domain.niches import niche_view
from app.domain.phones import normalize_phone
from app.domain.plans import limits_for, within_limit
from app.errors import AppError, ConflictError, NotFoundError
from app.jobs.queue import enqueue
from app.jobs.tasks import SEND_WHATSAPP
from app.logging import get_logger
from app.services import engagement, notifications, scheduling
from app.services.tenants import is_tenant_operational
from generated_prisma.errors import UniqueViolationError

log = get_logger("public_booking")

MAX_DAYS = 21


def slugify(name: str) -> str:
    base = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()
    base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    return base[:50] or "negocio"


def new_referral_code() -> str:
    return secrets.token_hex(3).upper()  # 6 caracteres, fácil de ditar


async def ensure_public_codes(tenant) -> None:
    """Garante slug e código de indicação (contas antigas ou criadas por caminhos sem esses campos)."""
    data: dict[str, Any] = {}
    if not tenant.slug:
        data["slug"] = f"{slugify(tenant.name)}-{tenant.id[-4:]}"
    if not tenant.referralCode:
        data["referralCode"] = new_referral_code()
    if not data:
        return
    for _ in range(3):
        try:
            await db.tenant.update(where={"id": tenant.id}, data=data)
            return
        except UniqueViolationError:
            data["referralCode"] = new_referral_code()
            data["slug"] = f"{slugify(tenant.name)}-{secrets.token_hex(2)}"


async def _tenant_by_slug(slug: str):
    tenant = await db.tenant.find_unique(where={"slug": slug})
    if tenant is None or not tenant.publicBooking:
        raise NotFoundError("Página de agendamento não encontrada.")
    operational, _ = is_tenant_operational(tenant)
    if not operational:
        raise NotFoundError("Página de agendamento indisponível no momento.")
    return tenant


async def booking_info(slug: str) -> dict:
    tenant = await _tenant_by_slug(slug)
    services = await scheduling.list_services(tenant.id, only_active=True)
    professionals = await db.professional.find_many(
        where={"tenantId": tenant.id, "active": True}, order=[{"sortOrder": "asc"}, {"name": "asc"}]
    )
    rules = await scheduling.get_rules(tenant.id)
    return {
        "name": tenant.name,
        "slug": tenant.slug,
        "timezone": tenant.timezone,
        "niche": niche_view(tenant.niche),
        "hours": scheduling.rules_to_text(rules) if rules else None,
        "services": services,
        "professionals": [{"id": p.id, "name": p.name} for p in professionals],
        "deposit": engagement.deposit_text(tenant),
    }


async def booking_slots(slug: str, *, service_id: str | None, days: int, professional_id: str | None) -> dict:
    tenant = await _tenant_by_slug(slug)
    tz = ZoneInfo(tenant.timezone or "America/Sao_Paulo")
    duration = scheduling.DEFAULT_DURATION_MIN
    if service_id:
        svc = await db.service.find_first(where={"id": service_id, "tenantId": tenant.id, "active": True})
        if svc is None:
            raise NotFoundError("Serviço não encontrado.")
        duration = svc.durationMin
    slots = await scheduling.free_slots(
        tenant, days=min(days, MAX_DAYS), duration_min=duration, limit=400, professional_id=professional_id
    )
    by_day: dict[str, list[dict]] = {}
    for s in slots:
        local = s.start.astimezone(tz)
        by_day.setdefault(local.strftime("%Y-%m-%d"), []).append(
            {"start": s.start.isoformat(), "label": local.strftime("%H:%M")}
        )
    return {
        "durationMin": duration,
        "days": [
            {"date": d, "weekday": scheduling.WEEKDAY_NAMES[datetime.fromisoformat(d).weekday()], "slots": v}
            for d, v in by_day.items()
        ],
    }


async def create_booking(
    slug: str,
    *,
    name: str,
    phone: str,
    start: datetime,
    service_id: str | None,
    professional_id: str | None,
    ip: str | None,
) -> dict:
    tenant = await _tenant_by_slug(slug)
    tz = ZoneInfo(tenant.timezone or "America/Sao_Paulo")
    try:
        phone_n = normalize_phone(phone)
    except ValueError as exc:
        raise AppError("Número de WhatsApp inválido.", code="invalid_phone") from exc
    svc = None
    if service_id:
        svc = await db.service.find_first(where={"id": service_id, "tenantId": tenant.id, "active": True})
        if svc is None:
            raise NotFoundError("Serviço não encontrado.")
    duration = svc.durationMin if svc else scheduling.DEFAULT_DURATION_MIN
    professional = None
    if professional_id:
        professional = await db.professional.find_first(
            where={"id": professional_id, "tenantId": tenant.id, "active": True}
        )
        if professional is None:
            raise NotFoundError("Profissional não encontrado.")

    patient = await db.patient.find_unique(where={"tenantId_phone": {"tenantId": tenant.id, "phone": phone_n}})
    if patient is None:
        count = await db.patient.count(where={"tenantId": tenant.id})
        if not within_limit(count, limits_for(str(tenant.plan)).max_patients):
            raise ConflictError("Agenda cheia no momento. Fale com a equipe pelo WhatsApp.", code="patient_limit")
        patient = await db.patient.create(data={"tenantId": tenant.id, "phone": phone_n, "name": name.strip()[:120]})
    elif not patient.name and name.strip():
        patient = await db.patient.update(where={"id": patient.id}, data={"name": name.strip()[:120]})

    async with db.tx() as tx:
        await scheduling.lock_tenant_agenda(tx, tenant.id)
        available, reason = await scheduling.check_availability(
            tenant, start, duration, professional_id=professional_id
        )
        if not available:
            raise ConflictError("Esse horário acabou de ser ocupado. Escolha outro.", code=f"slot_{reason}")
        appt = await tx.appointment.create(
            data={
                "tenantId": tenant.id,
                "patientId": patient.id,
                "serviceId": svc.id if svc else None,
                "service": (svc.name if svc else "Atendimento")[:120],
                "date": start,
                "durationMin": duration,
                "endAt": start + timedelta(minutes=duration),
                "priceCents": svc.priceCents if svc else None,
                "status": "PENDING",
                "source": "WEB",
                "professionalId": professional.id if professional else None,
            }
        )
    deposit = engagement.deposit_text(tenant)
    if deposit:
        await db.appointment.update(where={"id": appt.id}, data={"depositStatus": "REQUESTED"})
    when = start.astimezone(tz).strftime("%d/%m às %H:%M")
    await notifications.notify(
        tenant.id,
        type_="APPOINTMENT_REQUESTED",
        title=f"Pedido pela página de agendamento: {patient.name or phone_n}",
        body=f"{appt.service} em {when}"
        + (f" com {professional.name}" if professional else "")
        + " (aguardando confirmação).",
        phone=phone_n,
    )
    if tenant.whatsappConnected:
        text = (
            f"Olá, {patient.name or ''}! Recebemos seu pedido em {tenant.name}: {appt.service} em {when}. "
            "A equipe confirma por aqui em breve." + (f"\n\n{deposit}" if deposit else "")
        ).replace("Olá, !", "Olá!")
        await enqueue(SEND_WHATSAPP, {"tenantId": tenant.id, "phone": phone_n, "text": text})
    from app.services import calendar_sync

    await calendar_sync.schedule_sync(tenant.id, appt.id)
    log.info("public_booking_created", tenant_id=tenant.id, ip=ip)
    return {
        "id": appt.id,
        "service": appt.service,
        "start": start.isoformat(),
        "end": (start + timedelta(minutes=duration)).isoformat(),
        "when": when,
        "professional": professional.name if professional else None,
        "deposit": deposit,
        "whatsappConfirmation": bool(tenant.whatsappConnected),
    }
