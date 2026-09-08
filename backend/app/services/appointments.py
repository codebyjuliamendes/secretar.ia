"""Agenda da clínica: listagem paginada, criação manual e transições de status."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.db import db
from app.domain.phones import normalize_phone
from app.domain.plans import limits_for, within_limit
from app.errors import AppError, ConflictError, NotFoundError, QuotaExceededError
from app.services import audit

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
        "date": a.date.isoformat(),
        "status": str(a.status),
        "priceCents": a.priceCents,
        "notes": a.notes,
        "source": a.source,
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
    tenant_id: str,
    *,
    phone: str,
    patient_name: str | None,
    service: str,
    date: datetime,
    price_cents: int | None,
    notes: str | None,
    actor_user_id: str,
    ip: str | None,
    plan: str,
) -> dict:
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
    appt = await db.appointment.create(
        data={
            "tenantId": tenant_id,
            "patientId": patient.id,
            "service": service.strip()[:120],
            "date": date,
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
    return appointment_view(updated)


async def update_details(
    tenant_id: str, appointment_id: str, *, data: dict[str, Any], actor_user_id: str, ip: str | None
) -> dict:
    appt = await db.appointment.find_first(where={"id": appointment_id, "tenantId": tenant_id})
    if appt is None:
        raise NotFoundError("Agendamento não encontrado.")
    payload = {k: v for k, v in data.items() if v is not None}
    if not payload:
        raise AppError("Nada para atualizar.", code="empty_update")
    updated = await db.appointment.update(where={"id": appt.id}, data=payload, include={"patient": True})
    await audit.record(
        action="appointment.updated",
        resource_type="appointment",
        resource_id=appt.id,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        metadata={"fields": sorted(payload)},
        ip=ip,
    )
    return appointment_view(updated)
