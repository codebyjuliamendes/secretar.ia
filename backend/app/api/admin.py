"""Administração da plataforma (SUPER_ADMIN)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import BaseModel, Field

from app.db import db
from app.deps import CurrentUser, client_ip, require_super_admin
from app.domain.phones import normalize_phone
from app.errors import AppError
from app.jobs.queue import registered_tasks
from app.services import tenants as tenant_service

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_super_admin)])

PlanLiteral = Literal["FREE", "BASIC", "PRO", "ENTERPRISE"]
StatusLiteral = Literal["TRIAL", "ACTIVE", "PAST_DUE", "CANCELED", "SUSPENDED"]


class TenantCreateIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    whatsapp: str = Field(min_length=8, max_length=32)
    prompt: str = Field(min_length=10, max_length=4000)
    prices: str | None = Field(default=None, max_length=4000)
    businessHours: str | None = Field(default=None, max_length=300)
    plan: PlanLiteral = "FREE"
    status: StatusLiteral = "TRIAL"
    trialEndsAt: datetime | None = None


class TenantUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    plan: PlanLiteral | None = None
    status: StatusLiteral | None = None
    trialEndsAt: datetime | None = None


@router.get("/overview")
async def overview():
    return await tenant_service.admin_overview()


@router.get("/tenants")
async def list_tenants(
    search: str | None = Query(default=None, max_length=120),
    status_: StatusLiteral | None = Query(default=None, alias="status"),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    return await tenant_service.admin_list_tenants(search=search, status=status_, limit=limit, offset=offset)


@router.post("/tenants", status_code=status.HTTP_201_CREATED)
async def create_tenant(data: TenantCreateIn, request: Request, user: CurrentUser = Depends(require_super_admin)):
    try:
        whatsapp = normalize_phone(data.whatsapp)
    except ValueError as exc:
        raise AppError("Número de WhatsApp inválido.", code="invalid_phone") from exc
    payload = data.model_dump()
    payload["whatsapp"] = whatsapp
    return await tenant_service.admin_create_tenant(payload, actor_user_id=user.id, ip=client_ip(request))


@router.patch("/tenants/{tenant_id}")
async def update_tenant(
    tenant_id: str, data: TenantUpdateIn, request: Request, user: CurrentUser = Depends(require_super_admin)
):
    return await tenant_service.admin_update_tenant(
        tenant_id, data.model_dump(exclude_unset=True), actor_user_id=user.id, ip=client_ip(request)
    )


@router.get("/jobs")
async def list_jobs(
    status_: Literal["PENDING", "RUNNING", "COMPLETED", "FAILED"] | None = Query(None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
):
    where = {"status": status_} if status_ else {}
    rows = await db.job.find_many(where=where, order={"updatedAt": "desc"}, take=limit)
    return {
        "tasks": registered_tasks(),
        "items": [
            {
                "id": j.id,
                "name": j.name,
                "status": str(j.status),
                "retries": j.retries,
                "maxRetries": j.maxRetries,
                "runAt": j.runAt.isoformat(),
                "error": j.error,
                "updatedAt": j.updatedAt.isoformat(),
            }
            for j in rows
        ],
    }


@router.post("/jobs/{job_id}/retry")
async def retry_job(job_id: str):
    job = await db.job.find_unique(where={"id": job_id})
    if job is None:
        raise AppError("Job não encontrado.", code="not_found", status_code=404)
    updated = await db.job.update(
        where={"id": job_id},
        data={"status": "PENDING", "retries": 0, "runAt": datetime.now(tz=None), "error": None},
    )
    return {"id": updated.id, "status": str(updated.status)}
