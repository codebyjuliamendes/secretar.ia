"""Tarefas executadas pela fila."""

from __future__ import annotations

from typing import Any

from app.config import get_settings
from app.db import db
from app.errors import IntegrationUnavailableError
from app.integrations.email import EmailTransientError, build_email_sender
from app.integrations.whatsapp import WhatsAppRateLimited, WhatsAppTransientError, build_whatsapp_provider
from app.jobs.queue import PermanentJobError, register_task
from app.logging import get_logger

log = get_logger("jobs.tasks")

SEND_WHATSAPP = "send-whatsapp"
SEND_EMAIL = "send-email"
UPSELL_CAMPAIGN = "upsell-campaign"
SYNC_CALENDAR = "sync-calendar"
PULL_CALENDAR = "pull-calendar"
MONTHLY_REPORTS = "monthly-reports"


@register_task(SEND_WHATSAPP)
async def send_whatsapp(payload: dict[str, Any]) -> None:
    tenant_id, phone, text = payload.get("tenantId"), payload.get("phone"), payload.get("text")
    if not (tenant_id and phone and text):
        raise PermanentJobError("payload incompleto para send-whatsapp")
    tenant = await db.tenant.find_unique(where={"id": tenant_id})
    if tenant is None:
        raise PermanentJobError("tenant inexistente")
    settings = get_settings()
    instance = tenant.whatsappInstance or (tenant.id if not settings.is_production_like else None)
    if not instance:
        raise PermanentJobError("tenant sem instância de WhatsApp conectada")
    try:
        provider = build_whatsapp_provider(settings)
        await provider.send_text(instance, phone, text)
    except IntegrationUnavailableError as exc:
        raise PermanentJobError(exc.message) from exc
    except (WhatsAppRateLimited, WhatsAppTransientError):
        raise  # retentável com backoff


@register_task(SEND_EMAIL)
async def send_email(payload: dict[str, Any]) -> None:
    to, subject, text = payload.get("to"), payload.get("subject"), payload.get("text")
    if not (to and subject and text):
        raise PermanentJobError("payload incompleto para send-email")
    try:
        sender = build_email_sender(get_settings())
        await sender.send(to, subject, text, payload.get("html"))
    except IntegrationUnavailableError as exc:
        raise PermanentJobError(exc.message) from exc
    except EmailTransientError:
        raise


@register_task(UPSELL_CAMPAIGN)
async def upsell_campaign(payload: dict[str, Any]) -> None:
    from app.services.marketing import run_upsell_campaign

    tenant_id = payload.get("tenantId")
    result = await run_upsell_campaign(tenant_id=tenant_id)
    log.info("upsell_campaign_done", **result)


@register_task(MONTHLY_REPORTS)
async def monthly_reports(payload: dict[str, Any]) -> None:
    from app.services.reports import send_monthly_reports

    result = await send_monthly_reports(get_settings())
    log.info("monthly_reports_task_done", **result)


@register_task(SYNC_CALENDAR)
async def sync_calendar(payload: dict[str, Any]) -> None:
    from app.services.calendar_sync import sync_appointment

    tenant_id, appointment_id = payload.get("tenantId"), payload.get("appointmentId")
    if not (tenant_id and appointment_id):
        raise PermanentJobError("payload incompleto para sync-calendar")
    result = await sync_appointment(get_settings(), tenant_id=tenant_id, appointment_id=appointment_id)
    log.info("sync_calendar_done", appointment_id=appointment_id, result=result)


@register_task(PULL_CALENDAR)
async def pull_calendar(payload: dict[str, Any]) -> None:
    from app.services.calendar_sync import pull_external_events

    tenant_id = payload.get("tenantId")
    if not tenant_id:
        raise PermanentJobError("payload incompleto para pull-calendar")
    result = await pull_external_events(get_settings(), tenant_id=tenant_id)
    log.info("pull_calendar_done", **result)
