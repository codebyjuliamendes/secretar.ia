"""Webhooks externos. Cada um tem autenticação própria e é idempotente."""

from __future__ import annotations

import hmac
import json

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, Field, ValidationError

from app.config import Settings
from app.db import db
from app.deps import get_settings_dep
from app.domain.phones import normalize_phone
from app.errors import AppError, NotFoundError, UnauthorizedError
from app.integrations.whatsapp import parse_evolution_message
from app.logging import get_logger
from app.security.signatures import verify_hub_signature, verify_stripe_signature
from app.services import billing as billing_service
from app.services import conversation
from app.services import whatsapp_onboarding as wa_service

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
log = get_logger("webhooks")


class NormalizedWhatsAppIn(BaseModel):
    """Payload normalizado (integradores próprios). Autenticado por HMAC do corpo bruto."""

    messageId: str = Field(min_length=1, max_length=128)
    phone: str = Field(min_length=8, max_length=32)
    text: str = Field(min_length=1, max_length=4000)
    tenantId: str = Field(min_length=1, max_length=64)
    pushName: str | None = Field(default=None, max_length=120)


@router.post("/whatsapp")
async def whatsapp_normalized(
    request: Request,
    settings: Settings = Depends(get_settings_dep),
    x_hub_signature_256: str | None = Header(default=None, alias="X-Hub-Signature-256"),
):
    body = await request.body()
    if not settings.whatsapp_app_secret:
        raise UnauthorizedError("Webhook não configurado (WHATSAPP_APP_SECRET ausente).", code="webhook_disabled")
    if not verify_hub_signature(body, x_hub_signature_256, settings.whatsapp_app_secret):
        raise UnauthorizedError("Assinatura do webhook inválida.", code="invalid_signature")
    try:
        data = NormalizedWhatsAppIn.model_validate(json.loads(body or b"{}"))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise AppError("Payload inválido.", code="validation_error", status_code=422) from exc
    tenant = await db.tenant.find_unique(where={"id": data.tenantId})
    if tenant is None:
        raise NotFoundError("Clínica não encontrada.")
    try:
        phone = normalize_phone(data.phone)
    except ValueError as exc:
        raise AppError("Telefone inválido.", code="invalid_phone") from exc
    result = await conversation.handle_inbound(
        settings,
        tenant=tenant,
        phone=phone,
        text=data.text,
        message_id=data.messageId,
        push_name=data.pushName,
        source="normalized",
    )
    return {
        "status": result.status,
        "intent": result.intent,
        "reply": result.reply,
        "reason": result.reason,
        "degraded": result.degraded,
    }


@router.post("/evolution/{token}")
async def whatsapp_evolution(token: str, request: Request, settings: Settings = Depends(get_settings_dep)):
    """Webhook nativo da Evolution API. Autenticado pelo token secreto na URL; tenant resolvido pela instância."""
    if not settings.evolution_webhook_token or not hmac.compare_digest(token, settings.evolution_webhook_token):
        raise UnauthorizedError("Token do webhook inválido.", code="invalid_webhook_token")
    try:
        payload = await request.json()
    except ValueError as exc:
        raise AppError("Payload inválido.", code="validation_error", status_code=422) from exc
    if not isinstance(payload, dict):
        raise AppError("Payload inválido.", code="validation_error", status_code=422)

    event = str(payload.get("event") or "").lower().replace("_", ".")
    instance = str(payload.get("instance") or "")
    if event == "connection.update":
        state = str(((payload.get("data") or {}).get("state")) or "")
        await wa_service.mark_connection_update(instance, state)
        return {"status": "connection_updated", "state": state}

    parsed = parse_evolution_message(payload)
    if parsed is None:
        return {"status": "ignored"}
    tenant = await db.tenant.find_unique(where={"whatsappInstance": instance}) if instance else None
    if tenant is None:
        log.warning("evolution_unknown_instance", instance=instance)
        return {"status": "ignored", "reason": "unknown_instance"}
    if parsed.get("unsupported"):
        return {"status": "unsupported_message_type"}
    try:
        phone = normalize_phone(parsed["remote_jid"])
    except ValueError:
        return {"status": "ignored", "reason": "invalid_phone"}
    result = await conversation.handle_inbound(
        settings,
        tenant=tenant,
        phone=phone,
        text=parsed["text"],
        message_id=parsed["message_id"] or f"{instance}:{phone}",
        push_name=parsed.get("push_name"),
        source="evolution",
    )
    return {"status": result.status, "intent": result.intent, "reason": result.reason}


@router.post("/billing")
async def billing_webhook(
    request: Request,
    settings: Settings = Depends(get_settings_dep),
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
):
    body = await request.body()
    if not settings.stripe_webhook_secret:
        raise UnauthorizedError("Webhook de billing não configurado.", code="webhook_disabled")
    if not verify_stripe_signature(body, stripe_signature, settings.stripe_webhook_secret):
        raise UnauthorizedError("Assinatura do webhook inválida.", code="invalid_signature")
    try:
        payload = json.loads(body or b"{}")
    except json.JSONDecodeError as exc:
        raise AppError("Payload inválido.", code="validation_error", status_code=422) from exc
    if not isinstance(payload, dict):
        raise AppError("Payload inválido.", code="validation_error", status_code=422)
    return await billing_service.process_event(payload)
