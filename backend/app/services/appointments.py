"""Agenda da clínica: listagem paginada, criação manual e transições de status."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from app.db import db
from app.domain.phones import normalize_phone
from app.domain.plans import limits_for, within_limit
from app.errors import AppError, ConflictError, NotFoundError, QuotaExceededError
from app.services import audit, calendar_sync, scheduling

VALID_TRANSITIONS: dict[str, set[str]] = {
    "PENDING": {"CONFIRMED", "CANCELED"},
    "CONFIRMED": {"COMPLETED", "CANCELED", "NO_SHOW"},
    "COMPLETED": set(),
    "CANCELED": set(),
    "NO_SHOW": set(),
}


def appointment_view(a) -> dict:
    return {
        "id": a.id,
        "service": a.service,
        "serviceId": a.serviceId,
        "date": a.date.isoformat(),
        "durationMin": a.durationMin,
        "end": (a.endAt or a.date + timedelta(minutes=a.durationMin or 60)).isoformat(),
        "status": str(a.status),
        "priceCents": a.priceCents,
        "notes": a.notes,
        "source": a.source,
        "externalEventId": a.externalEventId,
        "createdAt": a.createdAt.isoformat(),
        "patient": {"id": a.patient.id, "name": a.patient.name, "phone": a.patient.phone} if a.patient else None,
    }


async def list_appointments(
    tenant_id: str,
    *,
    status: str | None,
    date_from: datetime | None,
    date_to: datetime | None,
    search: str | None,
    limit: int,
    offset: int,
) -> dict:
    where: dict[str, Any] = {"tenantId": tenant_id}
    if status:
        where["status"] = status
    if date_from or date_to:
        where["date"] = {}
        if date_from:
            where["date"]["gte"] = date_from
        if date_to:
            where["date"]["lte"] = date_to
    if search:
        where["OR"] = [
            {"service": {"contains": search, "mode": "insensitive"}},
            {"patient": {"is": {"name": {"contains": search, "mode": "insensitive"}}}},
            {"patient": {"is": {"phone": {"contains": search}}}},
        ]
    total = await db.appointment.count(where=where)
    rows = await db.appointment.find_many(
        where=where, include={"patient": True}, order={"date": "desc"}, take=limit, skip=offset
    )
    return {"items": [appointment_view(a) for a in rows], "total": total, "limit": limit, "offset": offset}


async def create_manual(
    tenant,
    *,
    phone: str,
    patient_name: str | None,
    service: str,
    service_id: str | None,
    date: datetime,
    duration_min: int | None,
    price_cents: int | None,
    notes: str | None,
    force: bool,
    actor_user_id: str,
    ip: str | None,
    plan: str,
) -> dict:
    tenant_id = tenant.id
    svc = None
    if service_id:
        svc = await db.service.find_first(where={"id": service_id, "tenantId": tenant_id})
        if svc is None:
            raise NotFoundError("Serviço não encontrado.")
    duration = duration_min or (svc.durationMin if svc else None) or scheduling.DEFAULT_DURATION_MIN
    if price_cents is None and svc is not None:
        price_cents = svc.priceCents
    service_name = (svc.name if svc else service).strip()[:120]
    if not force:
        available, reason = await scheduling.check_availability(tenant, date, duration)
        if not available and reason != "past":
            detail = "conflito com outro agendamento." if reason == "conflict" else "fora do horário de atendimento."
            raise ConflictError(f"Horário indisponível: {detail}", code="slot_unavailable", details={"reason": reason})
    try:
        phone_n = normalize_phone(phone)
    except ValueError as exc:
        raise AppError("Telefone inválido.", code="invalid_phone") from exc
    patient = await db.patient.find_unique(where={"tenantId_phone": {"tenantId": tenant_id, "phone": phone_n}})
    if patient is None:
        count = await db.patient.count(where={"tenantId": tenant_id})
        if not within_limit(count, limits_for(plan).max_patients):
            raise QuotaExceededError("Limite de pacientes do plano atingido.", code="patient_limit")
        patient = await db.patient.create(
            data={"tenantId": tenant_id, "phone": phone_n, "name": (patient_name or "").strip() or None}
        )
    elif patient_name and not patient.name:
        await db.patient.update(where={"id": patient.id}, data={"name": patient_name.strip()})
    async with db.tx() as tx:
        await scheduling.lock_tenant_agenda(tx, tenant_id)
        if not force:
            # Reverifica sob a trava: outro clique/mensagem pode ter ocupado o horário entre a checagem e aqui.
            available, reason = await scheduling.check_availability(tenant, date, duration)
            if not available and reason != "past":
                raise ConflictError(
                    "Horário indisponível: acabou de ser ocupado.", code="slot_unavailable", details={"reason": reason}
                )
        appt = await tx.appointment.create(
            data={
                "tenantId": tenant_id,
                "patientId": patient.id,
                "service": service_name,
                "serviceId": svc.id if svc else None,
                "date": date,
                "durationMin": duration,
                "endAt": date + timedelta(minutes=duration),
                "status": "CONFIRMED",
                "priceCents": price_cents,
                "notes": notes,
                "source": "MANUAL",
            },
            include={"patient": True},
        )
    await audit.record(
        action="appointment.created",
        resource_type="appointment",
        resource_id=appt.id,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        ip=ip,
    )
    await calendar_sync.schedule_sync(tenant_id, appt.id)
    return appointment_view(appt)


async def change_status(
    tenant_id: str, appointment_id: str, *, new_status: str, actor_user_id: str, ip: str | None
) -> dict:
    appt = await db.appointment.find_first(
        where={"id": appointment_id, "tenantId": tenant_id}, include={"patient": True}
    )
    if appt is None:
        raise NotFoundError("Agendamento não encontrado.")
    current = str(appt.status)
    if new_status not in VALID_TRANSITIONS.get(current, set()):
        raise ConflictError(f"Transição {current} → {new_status} não é permitida.", code="invalid_transition")
    updated = await db.appointment.update(where={"id": appt.id}, data={"status": new_status}, include={"patient": True})
    await audit.record(
        action="appointment.status_changed",
        resource_type="appointment",
        resource_id=appt.id,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        metadata={"from": current, "to": new_status},
        ip=ip,
    )
    await calendar_sync.schedule_sync(tenant_id, appt.id)
    return appointment_view(updated)


async def update_details(
    tenant, appointment_id: str, *, data: dict[str, Any], force: bool, actor_user_id: str, ip: str | None
) -> dict:
    tenant_id = tenant.id
    appt = await db.appointment.find_first(where={"id": appointment_id, "tenantId": tenant_id})
    if appt is None:
        raise NotFoundError("Agendamento não encontrado.")
    payload = {k: v for k, v in data.items() if v is not None}
    if not payload:
        raise AppError("Nada para atualizar.", code="empty_update")
    new_date = payload.get("date", appt.date)
    new_duration = payload.get("durationMin", appt.durationMin or scheduling.DEFAULT_DURATION_MIN)
    reschedule = "date" in payload or "durationMin" in payload
    if reschedule:
        payload["endAt"] = new_date + timedelta(minutes=new_duration)
    async with db.tx() as tx:
        if reschedule:
            # Mesma trava da criação: duas remarcações/criações simultâneas não ocupam o mesmo horário.
            await scheduling.lock_tenant_agenda(tx, tenant_id)
            if not force and str(appt.status) in scheduling.BLOCKING_STATUSES:
                available, reason = await scheduling.check_availability(
                    tenant, new_date, new_duration, exclude_id=appt.id
                )
                if not available and reason != "past":
                    raise ConflictError(
                        "Horário indisponível para remarcação.", code="slot_unavailable", details={"reason": reason}
                    )
        updated = await tx.appointment.update(where={"id": appt.id}, data=payload, include={"patient": True})
    await audit.record(
        action="appointment.updated",
        resource_type="appointment",
        resource_id=appt.id,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        metadata={"fields": sorted(payload)},
        ip=ip,
    )
    await calendar_sync.schedule_sync(tenant_id, appt.id)
    return appointment_view(updated)
