"""Workspace da clínica. Todas as rotas exigem membership no tenant da URL e permissão por papel."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile, status
from pydantic import AwareDatetime, BaseModel, Field

from app.config import Settings
from app.deps import TenantContext, client_ip, get_settings_dep, require_permission, tenant_context
from app.domain.plans import feature_enabled
from app.domain.roles import Permission
from app.services import appointments as appt_service
from app.services import audit, calendar_sync, knowledge, knowledge_sources, scheduling
from app.services import billing as billing_service
from app.services import dashboard as dashboard_service
from app.services import notifications as notif_service
from app.services import patients as patient_service
from app.services import team as team_service
from app.services import tenants as tenant_service
from app.services import whatsapp_onboarding as wa_service
from app.services.marketing import run_upsell_campaign

router = APIRouter(prefix="/clinic/{tenant_id}", tags=["clinic"])

AppointmentStatusLiteral = Literal["PENDING", "CONFIRMED", "COMPLETED", "CANCELED", "NO_SHOW"]
RoleLiteral = Literal["OWNER", "MANAGER", "STAFF"]


# ------------------------------- Dashboard -------------------------------


@router.get("/dashboard")
async def dashboard(
    days: int = Query(default=30, ge=7, le=365),
    ctx: TenantContext = Depends(require_permission(Permission.DASHBOARD_VIEW)),
):
    return await dashboard_service.clinic_dashboard(ctx.tenant, days=days)


@router.get("")
async def tenant_summary(ctx: TenantContext = Depends(tenant_context)):
    return {
        **tenant_service.tenant_public(ctx.tenant),
        "role": ctx.role.value,
        "unreadNotifications": await notif_service.unread_count(ctx.tenant_id),
    }


# ------------------------------- Settings --------------------------------


class SettingsUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    prompt: str | None = Field(default=None, max_length=4000)  # instruções extras; vazio = só a persona padrão
    tone: Literal["acolhedor", "objetivo", "formal"] | None = None
    prices: str | None = Field(default=None, max_length=4000)
    businessHours: str | None = Field(default=None, max_length=300)
    timezone: str | None = Field(default=None, max_length=64)
    upsellEnabled: bool | None = None
    upsellMessage: str | None = Field(default=None, max_length=1000)
    upsellDays: int | None = Field(default=None, ge=7, le=730)
    # `features` (Json do tenant) não é editável pela clínica: recursos vêm do plano (ADR-013).


@router.get("/settings")
async def get_settings(ctx: TenantContext = Depends(require_permission(Permission.SETTINGS_VIEW))):
    return tenant_service.tenant_settings_view(ctx.tenant)


@router.patch("/settings")
async def update_settings(
    data: SettingsUpdateIn,
    request: Request,
    ctx: TenantContext = Depends(require_permission(Permission.SETTINGS_MANAGE)),
):
    if data.timezone:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            ZoneInfo(data.timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            from app.errors import AppError

            raise AppError("Fuso horário inválido.", code="invalid_timezone") from exc
    return await tenant_service.update_settings(
        ctx.tenant_id, data.model_dump(exclude_unset=True), actor_user_id=ctx.user.id, ip=client_ip(request)
    )


@router.get("/billing")
async def billing(
    ctx: TenantContext = Depends(require_permission(Permission.BILLING_VIEW)),
    settings: Settings = Depends(get_settings_dep),
):
    return await billing_service.billing_overview(settings, ctx.tenant)


class CheckoutIn(BaseModel):
    plan: Literal["BASIC", "PRO", "PREMIUM"]


@router.post("/billing/checkout")
async def billing_checkout(
    data: CheckoutIn,
    request: Request,
    ctx: TenantContext = Depends(require_permission(Permission.BILLING_MANAGE)),
    settings: Settings = Depends(get_settings_dep),
):
    """Cria uma sessão de checkout no gateway; o plano só muda quando o webhook confirmar o pagamento."""
    from app.db import db

    user = await db.user.find_unique(where={"id": ctx.user.id})
    return await billing_service.create_checkout(
        settings,
        ctx.tenant,
        plan=data.plan,
        user_email=user.email if user else None,
        actor_user_id=ctx.user.id,
        ip=client_ip(request),
    )


@router.post("/billing/portal")
async def billing_portal(
    request: Request,
    ctx: TenantContext = Depends(require_permission(Permission.BILLING_MANAGE)),
    settings: Settings = Depends(get_settings_dep),
):
    return await billing_service.create_portal(settings, ctx.tenant, actor_user_id=ctx.user.id, ip=client_ip(request))


# ------------------------------- WhatsApp --------------------------------


@router.get("/whatsapp/status")
async def whatsapp_status(
    ctx: TenantContext = Depends(require_permission(Permission.SETTINGS_VIEW)),
    settings: Settings = Depends(get_settings_dep),
):
    return await wa_service.connection_status(settings, ctx.tenant)


@router.post("/whatsapp/connect")
async def whatsapp_connect(
    request: Request,
    ctx: TenantContext = Depends(require_permission(Permission.INTEGRATIONS_MANAGE)),
    settings: Settings = Depends(get_settings_dep),
):
    return await wa_service.start_connection(settings, ctx.tenant, actor_user_id=ctx.user.id, ip=client_ip(request))


@router.post("/whatsapp/disconnect")
async def whatsapp_disconnect(
    request: Request,
    ctx: TenantContext = Depends(require_permission(Permission.INTEGRATIONS_MANAGE)),
    settings: Settings = Depends(get_settings_dep),
):
    return await wa_service.disconnect(settings, ctx.tenant, actor_user_id=ctx.user.id, ip=client_ip(request))


# --------------------------- Base de conhecimento ------------------------


class KnowledgeDocumentIn(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    content: str = Field(min_length=20, max_length=30_000)


@router.get("/knowledge")
async def list_knowledge(ctx: TenantContext = Depends(require_permission(Permission.SETTINGS_VIEW))):
    return {"items": await knowledge.list_documents(ctx.tenant_id)}


@router.get("/knowledge/{document_id}")
async def get_knowledge(document_id: str, ctx: TenantContext = Depends(require_permission(Permission.SETTINGS_VIEW))):
    return await knowledge.get_document(ctx.tenant_id, document_id)


@router.post("/knowledge", status_code=status.HTTP_201_CREATED)
async def add_knowledge(
    data: KnowledgeDocumentIn,
    request: Request,
    ctx: TenantContext = Depends(require_permission(Permission.SETTINGS_MANAGE)),
    settings: Settings = Depends(get_settings_dep),
):
    return await knowledge.add_document(
        settings,
        ctx.tenant,
        title=data.title,
        content=data.content,
        actor_user_id=ctx.user.id,
        ip=client_ip(request),
    )


@router.post("/knowledge/upload", status_code=status.HTTP_201_CREATED)
async def upload_knowledge(
    request: Request,
    file: UploadFile = File(...),
    title: str | None = Form(default=None, max_length=120),
    ctx: TenantContext = Depends(require_permission(Permission.SETTINGS_MANAGE)),
    settings: Settings = Depends(get_settings_dep),
):
    """PDF (texto extraído) ou .txt/.md. Conteúdo longo vira várias partes; a cota é verificada antes."""
    from app.errors import AppError

    await knowledge_sources.assert_document_slot(ctx.tenant)
    data = await file.read(knowledge_sources.MAX_UPLOAD_BYTES + 1)
    if len(data) > knowledge_sources.MAX_UPLOAD_BYTES:
        raise AppError("Arquivo acima de 10 MB.", code="file_too_large", status_code=413)
    name = (file.filename or "documento").strip()
    ctype = (file.content_type or "").split(";")[0].strip().lower()
    ocr_pages = 0
    if ctype == knowledge_sources.PDF_MIME or name.lower().endswith(".pdf"):
        pdf = await knowledge_sources.extract_pdf_text(settings, data)
        text, source, ocr_pages = pdf.text, "pdf", pdf.ocr_pages
    elif ctype in knowledge_sources.TEXT_MIMES or name.lower().endswith((".txt", ".md")):
        text, source = data.decode("utf-8", errors="replace"), "file"
    else:
        raise AppError("Envie um PDF ou um arquivo de texto (.txt ou .md).", code="unsupported_file")
    items = await knowledge_sources.import_text(
        settings,
        ctx.tenant,
        title=(title or "").strip() or knowledge_sources.title_from_filename(name),
        text=text,
        source=source,
        source_ref=name[:200],
        actor_user_id=ctx.user.id,
        ip=client_ip(request),
    )
    return {"items": items, "ocrPages": ocr_pages}


class KnowledgeUrlIn(BaseModel):
    url: str = Field(min_length=8, max_length=2000)
    title: str | None = Field(default=None, min_length=2, max_length=120)


@router.post("/knowledge/import-url", status_code=status.HTTP_201_CREATED)
async def import_knowledge_url(
    data: KnowledgeUrlIn,
    request: Request,
    ctx: TenantContext = Depends(require_permission(Permission.SETTINGS_MANAGE)),
    settings: Settings = Depends(get_settings_dep),
):
    """Página HTML, PDF ou texto público. Hosts internos são recusados (SSRF)."""
    await knowledge_sources.assert_document_slot(ctx.tenant)
    fetched = await knowledge_sources.fetch_url(settings, data.url)
    items = await knowledge_sources.import_text(
        settings,
        ctx.tenant,
        title=data.title or fetched.title or knowledge_sources.title_from_url(fetched.final_url),
        text=fetched.text,
        source="url",
        source_ref=fetched.final_url[:500],
        actor_user_id=ctx.user.id,
        ip=client_ip(request),
    )
    return {"items": items, "sourceUrl": fetched.final_url, "kind": fetched.kind, "ocrPages": fetched.ocr_pages}


@router.delete("/knowledge/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_knowledge(
    document_id: str, request: Request, ctx: TenantContext = Depends(require_permission(Permission.SETTINGS_MANAGE))
):
    await knowledge.delete_document(ctx.tenant_id, document_id, actor_user_id=ctx.user.id, ip=client_ip(request))
    return None


@router.post("/knowledge/reindex")
async def reindex_knowledge(
    request: Request,
    ctx: TenantContext = Depends(require_permission(Permission.SETTINGS_MANAGE)),
    settings: Settings = Depends(get_settings_dep),
):
    return await knowledge.reindex(settings, ctx.tenant, actor_user_id=ctx.user.id, ip=client_ip(request))


@router.post("/knowledge/search")
async def search_knowledge(
    q: str = Query(min_length=2, max_length=500),
    ctx: TenantContext = Depends(require_permission(Permission.SETTINGS_VIEW)),
    settings: Settings = Depends(get_settings_dep),
):
    """Teste manual da recuperação: o que a IA veria para esta pergunta (nada, se o plano não incluir RAG)."""
    if not feature_enabled(ctx.tenant, "knowledge"):
        return {"items": [], "locked": True}
    snippets = await knowledge.retrieve(settings, ctx.tenant_id, q)
    return {"items": [{"title": s.title, "content": s.content, "score": round(s.score, 4)} for s in snippets]}


# ----------------------------- Google Calendar ---------------------------


@router.get("/integrations/google")
async def google_calendar_status(
    ctx: TenantContext = Depends(require_permission(Permission.SETTINGS_VIEW)),
    settings: Settings = Depends(get_settings_dep),
):
    return await calendar_sync.status(settings, ctx.tenant_id)


@router.post("/integrations/google/connect")
async def google_calendar_connect(
    request: Request,
    ctx: TenantContext = Depends(require_permission(Permission.INTEGRATIONS_MANAGE)),
    settings: Settings = Depends(get_settings_dep),
):
    """Devolve a URL de autorização do Google; o retorno cai em /api/integrations/google/callback."""
    return await calendar_sync.start_connect(settings, ctx.tenant, actor_user_id=ctx.user.id, ip=client_ip(request))


class GoogleCompleteIn(BaseModel):
    code: str = Field(min_length=1, max_length=2048)
    state: str = Field(min_length=10, max_length=4096)


@router.post("/integrations/google/complete")
async def google_calendar_complete(
    data: GoogleCompleteIn,
    ctx: TenantContext = Depends(require_permission(Permission.INTEGRATIONS_MANAGE)),
    settings: Settings = Depends(get_settings_dep),
):
    """Conclui o OAuth iniciado em /connect: o state precisa ser deste usuário e desta clínica."""
    await calendar_sync.complete_connect(
        settings, code=data.code, state=data.state, expected_user_id=ctx.user.id, expected_tenant_id=ctx.tenant_id
    )
    return await calendar_sync.status(settings, ctx.tenant_id)


@router.post("/integrations/google/disconnect")
async def google_calendar_disconnect(
    request: Request,
    ctx: TenantContext = Depends(require_permission(Permission.INTEGRATIONS_MANAGE)),
    settings: Settings = Depends(get_settings_dep),
):
    return await calendar_sync.disconnect(settings, ctx.tenant, actor_user_id=ctx.user.id, ip=client_ip(request))


@router.post("/integrations/google/sync")
async def google_calendar_resync(
    request: Request,
    ctx: TenantContext = Depends(require_permission(Permission.INTEGRATIONS_MANAGE)),
    settings: Settings = Depends(get_settings_dep),
):
    return await calendar_sync.resync(settings, ctx.tenant, actor_user_id=ctx.user.id, ip=client_ip(request))


# ------------------------------ Appointments -----------------------------


class AppointmentCreateIn(BaseModel):
    phone: str = Field(min_length=8, max_length=32)
    patientName: str | None = Field(default=None, max_length=120)
    service: str = Field(min_length=2, max_length=120)
    serviceId: str | None = Field(default=None, max_length=64)
    date: AwareDatetime
    durationMin: int | None = Field(default=None, ge=5, le=600)
    priceCents: int | None = Field(default=None, ge=0, le=100_000_000)
    notes: str | None = Field(default=None, max_length=2000)
    force: bool = False  # encaixe consciente fora do horário ou sobreposto


class AppointmentStatusIn(BaseModel):
    status: AppointmentStatusLiteral


class AppointmentUpdateIn(BaseModel):
    service: str | None = Field(default=None, min_length=2, max_length=120)
    date: AwareDatetime | None = None
    durationMin: int | None = Field(default=None, ge=5, le=600)
    priceCents: int | None = Field(default=None, ge=0, le=100_000_000)
    notes: str | None = Field(default=None, max_length=2000)
    force: bool = False


@router.get("/appointments")
async def list_appointments(
    status_: AppointmentStatusLiteral | None = Query(default=None, alias="status"),
    date_from: AwareDatetime | None = Query(default=None, alias="from"),
    date_to: AwareDatetime | None = Query(default=None, alias="to"),
    search: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    ctx: TenantContext = Depends(require_permission(Permission.APPOINTMENTS_VIEW)),
):
    return await appt_service.list_appointments(
        ctx.tenant_id,
        status=status_,
        date_from=date_from,
        date_to=date_to,
        search=search,
        limit=limit,
        offset=offset,
    )


@router.post("/appointments", status_code=status.HTTP_201_CREATED)
async def create_appointment(
    data: AppointmentCreateIn,
    request: Request,
    ctx: TenantContext = Depends(require_permission(Permission.APPOINTMENTS_MANAGE)),
):
    return await appt_service.create_manual(
        ctx.tenant,
        phone=data.phone,
        patient_name=data.patientName,
        service=data.service,
        service_id=data.serviceId,
        date=data.date,
        duration_min=data.durationMin,
        price_cents=data.priceCents,
        notes=data.notes,
        force=data.force,
        actor_user_id=ctx.user.id,
        ip=client_ip(request),
        plan=str(ctx.tenant.plan),
    )


@router.patch("/appointments/{appointment_id}")
async def update_appointment(
    appointment_id: str,
    data: AppointmentUpdateIn,
    request: Request,
    ctx: TenantContext = Depends(require_permission(Permission.APPOINTMENTS_MANAGE)),
):
    return await appt_service.update_details(
        ctx.tenant,
        appointment_id,
        data=data.model_dump(exclude_unset=True, exclude={"force"}),
        force=data.force,
        actor_user_id=ctx.user.id,
        ip=client_ip(request),
    )


@router.post("/appointments/{appointment_id}/status")
async def change_appointment_status(
    appointment_id: str,
    data: AppointmentStatusIn,
    request: Request,
    ctx: TenantContext = Depends(require_permission(Permission.APPOINTMENTS_MANAGE)),
):
    return await appt_service.change_status(
        ctx.tenant_id,
        appointment_id,
        new_status=data.status,
        actor_user_id=ctx.user.id,
        ip=client_ip(request),
    )


# ------------------- Scheduling: calendar, availability, services -------------------


class RuleIn(BaseModel):
    weekday: int = Field(ge=0, le=6)
    start: str = Field(pattern=r"^\d{2}:\d{2}$")
    end: str = Field(pattern=r"^\d{2}:\d{2}$")


class RulesIn(BaseModel):
    rules: list[RuleIn] = Field(max_length=21)
    slotMinutes: int | None = Field(default=None, ge=5, le=240)


class ServiceIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    durationMin: int = Field(default=60, ge=5, le=600)
    priceCents: int | None = Field(default=None, ge=0, le=100_000_000)
    description: str | None = Field(default=None, max_length=1000)
    active: bool = True
    sortOrder: int = Field(default=0, ge=0, le=1000)


class ServiceUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    durationMin: int | None = Field(default=None, ge=5, le=600)
    priceCents: int | None = Field(default=None, ge=0, le=100_000_000)
    description: str | None = Field(default=None, max_length=1000)
    active: bool | None = None
    sortOrder: int | None = Field(default=None, ge=0, le=1000)


@router.get("/calendar")
async def calendar_view(
    start: AwareDatetime = Query(alias="from"),
    end: AwareDatetime = Query(alias="to"),
    ctx: TenantContext = Depends(require_permission(Permission.APPOINTMENTS_VIEW)),
):
    return await scheduling.calendar(ctx.tenant, start=start, end=end)


@router.get("/availability")
async def availability(
    start: AwareDatetime | None = Query(default=None, alias="from"),
    days: int = Query(default=7, ge=1, le=31),
    duration: int = Query(default=60, ge=5, le=600),
    ctx: TenantContext = Depends(require_permission(Permission.APPOINTMENTS_VIEW)),
):
    slots = await scheduling.free_slots(ctx.tenant, start_from=start, days=days, duration_min=duration, limit=200)
    return {"slots": [{"start": s.start.isoformat(), "end": s.end.isoformat()} for s in slots]}


@router.get("/availability/rules")
async def get_rules(ctx: TenantContext = Depends(require_permission(Permission.SETTINGS_VIEW))):
    return {
        "rules": scheduling.rules_view(await scheduling.get_rules(ctx.tenant_id)),
        "slotMinutes": ctx.tenant.slotMinutes,
    }


@router.put("/availability/rules")
async def put_rules(
    data: RulesIn,
    request: Request,
    ctx: TenantContext = Depends(require_permission(Permission.SETTINGS_MANAGE)),
):
    rules = await scheduling.set_rules(
        ctx.tenant_id, [r.model_dump() for r in data.rules], actor_user_id=ctx.user.id, ip=client_ip(request)
    )
    slot = ctx.tenant.slotMinutes
    if data.slotMinutes:
        await tenant_service.update_settings(
            ctx.tenant_id, {"slotMinutes": data.slotMinutes}, actor_user_id=ctx.user.id, ip=client_ip(request)
        )
        slot = data.slotMinutes
    return {"rules": rules, "slotMinutes": slot}


@router.get("/services")
async def list_services(
    active: bool = Query(default=False),
    ctx: TenantContext = Depends(require_permission(Permission.SETTINGS_VIEW)),
):
    return {"items": await scheduling.list_services(ctx.tenant_id, only_active=active)}


@router.post("/services", status_code=status.HTTP_201_CREATED)
async def create_service(
    data: ServiceIn, request: Request, ctx: TenantContext = Depends(require_permission(Permission.SETTINGS_MANAGE))
):
    return await scheduling.create_service(
        ctx.tenant_id, data.model_dump(), actor_user_id=ctx.user.id, ip=client_ip(request)
    )


@router.patch("/services/{service_id}")
async def update_service(
    service_id: str,
    data: ServiceUpdateIn,
    request: Request,
    ctx: TenantContext = Depends(require_permission(Permission.SETTINGS_MANAGE)),
):
    return await scheduling.update_service(
        ctx.tenant_id, service_id, data.model_dump(exclude_unset=True), actor_user_id=ctx.user.id, ip=client_ip(request)
    )


@router.delete("/services/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_service(
    service_id: str, request: Request, ctx: TenantContext = Depends(require_permission(Permission.SETTINGS_MANAGE))
):
    await scheduling.delete_service(ctx.tenant_id, service_id, actor_user_id=ctx.user.id, ip=client_ip(request))
    return None


# -------------------------------- Patients -------------------------------


class PatientCreateIn(BaseModel):
    phone: str = Field(min_length=8, max_length=32)
    name: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=2000)


class PatientUpdateIn(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=2000)
    marketingOptOut: bool | None = None


@router.get("/patients")
async def list_patients(
    search: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    ctx: TenantContext = Depends(require_permission(Permission.PATIENTS_VIEW)),
):
    return await patient_service.list_patients(ctx.tenant_id, search=search, limit=limit, offset=offset)


@router.post("/patients", status_code=status.HTTP_201_CREATED)
async def create_patient(
    data: PatientCreateIn,
    request: Request,
    ctx: TenantContext = Depends(require_permission(Permission.PATIENTS_MANAGE)),
):
    return await patient_service.create_patient(
        ctx.tenant_id,
        phone=data.phone,
        name=data.name,
        notes=data.notes,
        plan=str(ctx.tenant.plan),
        actor_user_id=ctx.user.id,
        ip=client_ip(request),
    )


@router.get("/patients/{patient_id}")
async def get_patient(patient_id: str, ctx: TenantContext = Depends(require_permission(Permission.PATIENTS_VIEW))):
    return await patient_service.get_patient(ctx.tenant_id, patient_id)


@router.patch("/patients/{patient_id}")
async def update_patient(
    patient_id: str,
    data: PatientUpdateIn,
    request: Request,
    ctx: TenantContext = Depends(require_permission(Permission.PATIENTS_MANAGE)),
):
    return await patient_service.update_patient(
        ctx.tenant_id,
        patient_id,
        data=data.model_dump(exclude_unset=True),
        actor_user_id=ctx.user.id,
        ip=client_ip(request),
    )


@router.delete("/patients/{patient_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_patient(
    patient_id: str,
    request: Request,
    ctx: TenantContext = Depends(require_permission(Permission.PATIENTS_MANAGE)),
):
    await patient_service.delete_patient(ctx.tenant_id, patient_id, actor_user_id=ctx.user.id, ip=client_ip(request))
    return None


# ----------------------------- Notifications -----------------------------


@router.get("/notifications")
async def list_notifications(
    unread: bool = Query(default=False),
    limit: int = Query(default=30, ge=1, le=100),
    cursor: str | None = Query(default=None),
    ctx: TenantContext = Depends(require_permission(Permission.INBOX_VIEW)),
):
    items = await notif_service.list_notifications(ctx.tenant_id, unread_only=unread, limit=limit, cursor=cursor)
    return {
        "items": items,
        "unreadCount": await notif_service.unread_count(ctx.tenant_id),
        "nextCursor": items[-1]["id"] if len(items) == limit else None,
    }


@router.post("/notifications/read")
async def mark_notifications_read(
    notification_id: str | None = Query(default=None, alias="id"),
    ctx: TenantContext = Depends(require_permission(Permission.INBOX_MANAGE)),
):
    return {"updated": await notif_service.mark_read(ctx.tenant_id, notification_id)}


# ---------------------------------- Team ---------------------------------


class InviteIn(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    name: str = Field(min_length=2, max_length=120)
    role: RoleLiteral = "STAFF"


class RoleIn(BaseModel):
    role: RoleLiteral


@router.get("/team")
async def list_team(ctx: TenantContext = Depends(require_permission(Permission.TEAM_VIEW))):
    return {
        "items": await team_service.list_members(ctx.tenant_id),
        "invites": await team_service.list_invites(ctx.tenant_id),
    }


@router.post("/team/invites/{invite_id}/resend")
async def resend_team_invite(
    invite_id: str,
    request: Request,
    ctx: TenantContext = Depends(require_permission(Permission.TEAM_MANAGE)),
    settings: Settings = Depends(get_settings_dep),
):
    return await team_service.resend_invite(
        settings, ctx.tenant, invite_id, actor_user_id=ctx.user.id, ip=client_ip(request)
    )


@router.delete("/team/invites/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_team_invite(
    invite_id: str, request: Request, ctx: TenantContext = Depends(require_permission(Permission.TEAM_MANAGE))
):
    await team_service.cancel_invite(ctx.tenant_id, invite_id, actor_user_id=ctx.user.id, ip=client_ip(request))
    return None


@router.post("/team", status_code=status.HTTP_201_CREATED)
async def invite(
    data: InviteIn,
    request: Request,
    ctx: TenantContext = Depends(require_permission(Permission.TEAM_MANAGE)),
    settings: Settings = Depends(get_settings_dep),
):
    return await team_service.invite_member(
        settings,
        ctx.tenant,
        email=data.email,
        name=data.name,
        role=data.role,
        actor_role=ctx.role.value,
        actor_user_id=ctx.user.id,
        ip=client_ip(request),
    )


@router.patch("/team/{membership_id}")
async def change_role(
    membership_id: str,
    data: RoleIn,
    request: Request,
    ctx: TenantContext = Depends(require_permission(Permission.TEAM_MANAGE)),
):
    return await team_service.change_role(
        ctx.tenant_id,
        membership_id,
        role=data.role,
        actor_role=ctx.role.value,
        actor_user_id=ctx.user.id,
        ip=client_ip(request),
    )


@router.delete("/team/{membership_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    membership_id: str,
    request: Request,
    ctx: TenantContext = Depends(require_permission(Permission.TEAM_MANAGE)),
):
    await team_service.remove_member(
        ctx.tenant_id,
        membership_id,
        actor_role=ctx.role.value,
        actor_user_id=ctx.user.id,
        ip=client_ip(request),
    )
    return None


# ---------------------------- Audit & Marketing --------------------------


@router.get("/audit")
async def audit_log(
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None),
    ctx: TenantContext = Depends(require_permission(Permission.AUDIT_VIEW)),
):
    items = await audit.list_for_tenant(ctx.tenant_id, limit=limit, cursor=cursor)
    return {"items": items, "nextCursor": items[-1]["id"] if len(items) == limit else None}


@router.post("/marketing/upsell/preview")
async def upsell_preview(ctx: TenantContext = Depends(require_permission(Permission.SETTINGS_MANAGE))):
    return await run_upsell_campaign(tenant_id=ctx.tenant_id, dry_run=True)
