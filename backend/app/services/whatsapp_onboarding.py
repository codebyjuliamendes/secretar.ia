"""Onboarding self-service do WhatsApp da clínica (instância na Evolution API + QR Code)."""

from __future__ import annotations

import re

from app.config import Settings
from app.db import db
from app.errors import IntegrationUnavailableError
from app.integrations.whatsapp import WhatsAppRateLimited, WhatsAppTransientError, build_whatsapp_provider
from app.services import audit


def instance_name_for(tenant) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", tenant.name.lower()).strip("-")[:24] or "clinica"
    return f"{slug}-{tenant.id[-8:]}"


def _webhook_url(settings: Settings) -> str:
    return f"{settings.public_api_url.rstrip('/')}/api/webhooks/evolution/{settings.evolution_webhook_token}"


async def start_connection(settings: Settings, tenant, *, actor_user_id: str, ip: str | None) -> dict:
    provider = build_whatsapp_provider(settings)
    instance = tenant.whatsappInstance or instance_name_for(tenant)
    try:
        if tenant.whatsappInstance:
            try:
                info = await provider.connection_state(instance)
            except IntegrationUnavailableError:
                # Instância apagada na Evolution mas ainda registrada aqui: recria com o mesmo nome.
                info = await provider.create_instance(instance, _webhook_url(settings))
        else:
            try:
                info = await provider.create_instance(instance, _webhook_url(settings))
            except IntegrationUnavailableError:
                # Nome já existe na Evolution (tentativa anterior gravou lá e não aqui): reaproveita.
                info = await provider.connection_state(instance)
    except (WhatsAppRateLimited, WhatsAppTransientError) as exc:
        raise IntegrationUnavailableError("WhatsApp indisponível no momento. Tente novamente em instantes.") from exc
    await db.tenant.update(
        where={"id": tenant.id}, data={"whatsappInstance": instance, "whatsappConnected": info.connected}
    )
    await audit.record(
        action="whatsapp.connect_started",
        resource_type="tenant",
        resource_id=tenant.id,
        tenant_id=tenant.id,
        actor_user_id=actor_user_id,
        ip=ip,
    )
    return {
        "instance": instance,
        "connected": info.connected,
        "state": info.state,
        "qrCode": info.qr_code_base64,
    }


async def connection_status(settings: Settings, tenant) -> dict:
    if not tenant.whatsappInstance:
        return {"instance": None, "connected": False, "state": "not_configured", "qrCode": None}
    provider = build_whatsapp_provider(settings)
    try:
        info = await provider.connection_state(tenant.whatsappInstance)
    except (WhatsAppRateLimited, WhatsAppTransientError) as exc:
        raise IntegrationUnavailableError("WhatsApp indisponível no momento.") from exc
    if info.connected != tenant.whatsappConnected:
        await db.tenant.update(where={"id": tenant.id}, data={"whatsappConnected": info.connected})
    return {
        "instance": tenant.whatsappInstance,
        "connected": info.connected,
        "state": info.state,
        "qrCode": info.qr_code_base64,
    }


async def disconnect(settings: Settings, tenant, *, actor_user_id: str, ip: str | None) -> dict:
    if tenant.whatsappInstance:
        provider = build_whatsapp_provider(settings)
        try:
            await provider.logout_instance(tenant.whatsappInstance)
        except (WhatsAppRateLimited, WhatsAppTransientError) as exc:
            raise IntegrationUnavailableError("WhatsApp indisponível no momento.") from exc
    await db.tenant.update(where={"id": tenant.id}, data={"whatsappConnected": False})
    await audit.record(
        action="whatsapp.disconnected",
        resource_type="tenant",
        resource_id=tenant.id,
        tenant_id=tenant.id,
        actor_user_id=actor_user_id,
        ip=ip,
    )
    return {"instance": tenant.whatsappInstance, "connected": False, "state": "close", "qrCode": None}


async def mark_connection_update(instance: str, state: str) -> None:
    tenant = await db.tenant.find_unique(where={"whatsappInstance": instance})
    if tenant is None:
        return
    connected = state == "open"
    if connected != tenant.whatsappConnected:
        await db.tenant.update(where={"id": tenant.id}, data={"whatsappConnected": connected})
