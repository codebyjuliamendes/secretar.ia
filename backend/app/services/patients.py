"""CRM de pacientes."""

from __future__ import annotations

from typing import Any

from app.db import db
from app.domain.phones import normalize_phone
from app.domain.plans import limits_for, within_limit
from app.errors import AppError, ConflictError, NotFoundError, QuotaExceededError
from app.services import audit
from generated_prisma.errors import UniqueViolationError


def patient_view(p, *, appointment_count: int | None = None, last_appointment=None) -> dict:
    view = {
        "id": p.id,
        "name": p.name,
        "phone": p.phone,
        "notes": p.notes,
        "createdAt": p.createdAt.isoformat(),
    }
    if appointment_count is not None:
        view["appointmentCount"] = appointment_count
    if last_appointment is not None:
        view["lastAppointmentAt"] = last_appointment
    return view


async def list_patients(tenant_id: str, *, search: str | None, limit: int, offset: int) -> dict:
    where: dict[str, Any] = {"tenantId": tenant_id}
    if search:
        where["OR"] = [{"name": {"contains": search, "mode": "insensitive"}}, {"phone": {"contains": search}}]
    total = await db.patient.count(where=where)
    rows = await db.query_raw(
        """
        SELECT p.id, p.name, p.phone, p.notes, p."createdAt",
               COUNT(a.id) AS "appointmentCount", MAX(a.date) AS "lastAppointmentAt"
        FROM "Patient" p
        LEFT JOIN "Appointment" a ON a."patientId" = p.id
        WHERE p."tenantId" = $1
          AND ($2::text IS NULL OR p.name ILIKE '%' || $2 || '%' OR p.phone LIKE '%' || $2 || '%')
        GROUP BY p.id
        ORDER BY p."createdAt" DESC
        LIMIT $3 OFFSET $4
        """,
        tenant_id,
        search,
        limit,
        offset,
    )
    items = [
        {
            "id": r["id"],
            "name": r["name"],
            "phone": r["phone"],
            "notes": r["notes"],
            "createdAt": _iso(r["createdAt"]),
            "appointmentCount": int(r["appointmentCount"] or 0),
            "lastAppointmentAt": _iso(r["lastAppointmentAt"]),
        }
        for r in rows
    ]
    return {"items": items, "total": total, "limit": limit, "offset": offset}


def _iso(v):
    if v is None:
        return None
    return v.isoformat() if hasattr(v, "isoformat") else str(v)


async def get_patient(tenant_id: str, patient_id: str) -> dict:
    p = await db.patient.find_first(where={"id": patient_id, "tenantId": tenant_id})
    if p is None:
        raise NotFoundError("Paciente não encontrado.")
    appts = await db.appointment.find_many(
        where={"patientId": p.id, "tenantId": tenant_id}, order={"date": "desc"}, take=20
    )
    msgs = await db.message.find_many(
        where={"tenantId": tenant_id, "phone": p.phone}, order={"createdAt": "desc"}, take=30
    )
    return {
        **patient_view(p, appointment_count=len(appts)),
        "appointments": [
            {"id": a.id, "service": a.service, "date": a.date.isoformat(), "status": str(a.status)} for a in appts
        ],
        "conversation": [
            {"role": str(m.role), "content": m.content, "createdAt": m.createdAt.isoformat()} for m in reversed(msgs)
        ],
    }


async def create_patient(
    tenant_id: str,
    *,
    phone: str,
    name: str | None,
    notes: str | None,
    plan: str,
    actor_user_id: str,
    ip: str | None,
) -> dict:
    try:
        phone_n = normalize_phone(phone)
    except ValueError as exc:
        raise AppError("Telefone inválido.", code="invalid_phone") from exc
    count = await db.patient.count(where={"tenantId": tenant_id})
    if not within_limit(count, limits_for(plan).max_patients):
        raise QuotaExceededError("Limite de pacientes do plano atingido.", code="patient_limit")
    try:
        p = await db.patient.create(
            data={
                "tenantId": tenant_id,
                "phone": phone_n,
                "name": (name or "").strip() or None,
                "notes": notes,
            }
        )
    except UniqueViolationError as exc:
        raise ConflictError("Já existe um paciente com este telefone.", code="patient_exists") from exc
    await audit.record(
        action="patient.created",
        resource_type="patient",
        resource_id=p.id,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        ip=ip,
    )
    return patient_view(p, appointment_count=0)


async def update_patient(
    tenant_id: str, patient_id: str, *, data: dict[str, Any], actor_user_id: str, ip: str | None
) -> dict:
    p = await db.patient.find_first(where={"id": patient_id, "tenantId": tenant_id})
    if p is None:
        raise NotFoundError("Paciente não encontrado.")
    payload = {k: v for k, v in data.items() if v is not None}
    if not payload:
        raise AppError("Nada para atualizar.", code="empty_update")
    updated = await db.patient.update(where={"id": p.id}, data=payload)
    await audit.record(
        action="patient.updated",
        resource_type="patient",
        resource_id=p.id,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        metadata={"fields": sorted(payload)},
        ip=ip,
    )
    return patient_view(updated)


async def delete_patient(tenant_id: str, patient_id: str, *, actor_user_id: str, ip: str | None) -> None:
    p = await db.patient.find_first(where={"id": patient_id, "tenantId": tenant_id})
    if p is None:
        raise NotFoundError("Paciente não encontrado.")
    await db.patient.delete(where={"id": p.id})
    await audit.record(
        action="patient.deleted",
        resource_type="patient",
        resource_id=p.id,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        metadata={"phone": p.phone},
        ip=ip,
    )
