"""Processamento de eventos do gateway de pagamento (Stripe) com idempotência por event id."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.config import Settings
from app.db import db
from app.domain.plans import Plan, plan_public_view
from app.errors import AppError, ConflictError
from app.integrations.stripe import build_stripe_client
from app.logging import get_logger
from app.services import audit, notifications
from app.services.usage import usage_summary
from generated_prisma.errors import UniqueViolationError

log = get_logger("billing")

# price_id / lookup_key -> plano. Configurável por metadata["plan"] no Stripe também.
PLAN_BY_METADATA = {p.value: p for p in Plan}


def _extract(payload: dict[str, Any]) -> dict[str, Any]:
    obj = (payload.get("data") or {}).get("object") or {}
    obj_type = obj.get("object")
    # invoice e checkout.session apontam para a assinatura em `subscription`; subscription usa o próprio id.
    subscription_id = obj.get("subscription") if obj_type in ("invoice", "checkout.session") else obj.get("id")
    customer_id = obj.get("customer")
    metadata = obj.get("metadata") or {}
    tenant_id = metadata.get("tenantId") or (obj.get("client_reference_id") if obj_type == "checkout.session" else None)
    plan = PLAN_BY_METADATA.get(str(metadata.get("plan", "")).upper())
    if plan is None:
        for item in (obj.get("items") or {}).get("data") or []:
            price_meta = (item.get("price") or {}).get("metadata") or {}
            if (p := PLAN_BY_METADATA.get(str(price_meta.get("plan", "")).upper())) is not None:
                plan = p
                break
    return {
        "event_id": payload.get("id"),
        "type": payload.get("type"),
        "subscription_id": subscription_id,
        "customer_id": customer_id,
        "tenant_id": tenant_id,
        "plan": plan,
    }


async def _find_tenant(info: dict[str, Any]):
    if info["tenant_id"]:
        t = await db.tenant.find_unique(where={"id": info["tenant_id"]})
        if t:
            return t
    if info["subscription_id"]:
        t = await db.tenant.find_unique(where={"subscriptionId": info["subscription_id"]})
        if t:
            return t
    if info["customer_id"]:
        return await db.tenant.find_first(where={"customerId": info["customer_id"]})
    return None


async def process_event(payload: dict[str, Any]) -> dict[str, Any]:
    info = _extract(payload)
    event_id = info["event_id"]
    if not event_id or not info["type"]:
        return {"received": True, "handled": False, "reason": "missing_event_id_or_type"}

    # Idempotência por event id do provedor.
    try:
        await db.webhookevent.create(data={"id": f"stripe:{event_id}", "provider": "stripe"})
    except UniqueViolationError:
        return {"received": True, "handled": False, "reason": "duplicate"}

    tenant = await _find_tenant(info)
    if tenant is None:
        log.warning("billing_tenant_not_found", event_type=info["type"], subscription_id=info["subscription_id"])
        return {"received": True, "handled": False, "reason": "tenant_not_found"}

    etype = info["type"]
    data: dict[str, Any] = {}
    if info["subscription_id"] and tenant.subscriptionId != info["subscription_id"]:
        data["subscriptionId"] = info["subscription_id"]
    if info["customer_id"] and tenant.customerId != info["customer_id"]:
        data["customerId"] = info["customer_id"]

    if etype in (
        "checkout.session.completed",
        "customer.subscription.created",
        "invoice.payment_succeeded",
        "invoice.paid",
        "customer.subscription.updated",
    ):
        obj_status = ((payload.get("data") or {}).get("object") or {}).get("status")
        if etype == "customer.subscription.updated" and obj_status in ("past_due", "unpaid"):
            data["status"] = "PAST_DUE"
        elif etype == "customer.subscription.updated" and obj_status == "canceled":
            data["status"] = "CANCELED"
        else:
            data["status"] = "ACTIVE"
            data["trialEndsAt"] = None
        if info["plan"]:
            data["plan"] = info["plan"].value
    elif etype == "invoice.payment_failed":
        data["status"] = "PAST_DUE"
    elif etype == "customer.subscription.deleted":
        data["status"] = "CANCELED"
    else:
        return {"received": True, "handled": False, "reason": "ignored_event_type"}

    updated = await db.tenant.update(where={"id": tenant.id}, data=data)
    await audit.record(
        action=f"billing.{etype}",
        resource_type="tenant",
        resource_id=tenant.id,
        tenant_id=tenant.id,
        metadata={"eventId": event_id, "changes": {k: str(v) for k, v in data.items()}},
    )
    if data.get("status") == "PAST_DUE":
        await notifications.notify(
            tenant.id,
            type_="BILLING",
            title="Pagamento pendente",
            body="Não conseguimos processar o pagamento da assinatura. O atendimento "
            "automático ficará pausado até a regularização.",
            dedupe_minutes=60,
        )
    elif data.get("status") == "ACTIVE" and str(tenant.status) != "ACTIVE":
        await notifications.notify(
            tenant.id,
            type_="BILLING",
            title="Assinatura ativa",
            body=f"Sua assinatura está ativa no plano {updated.plan}. Bom atendimento!",
            dedupe_minutes=60,
        )
    log.info("billing_event_applied", event_type=etype, tenant_id=tenant.id, changes=list(data))
    return {
        "received": True,
        "handled": True,
        "tenantId": tenant.id,
        "status": str(updated.status),
        "processedAt": datetime.now(UTC).isoformat(),
    }


# ------------------------------ Checkout e portal ------------------------------

PURCHASABLE_PLANS = (Plan.BASIC, Plan.PRO)


def price_id_for(settings: Settings, plan: Plan) -> str:
    return {Plan.BASIC: settings.stripe_price_basic, Plan.PRO: settings.stripe_price_pro}.get(plan, "")


def checkout_enabled(settings: Settings) -> bool:
    """Em produção exige chave do Stripe; em dev/test o provider console permite exercitar o fluxo."""
    return bool(settings.stripe_secret_key) or not settings.is_production_like


def purchasable_plans(settings: Settings) -> list[str]:
    if not checkout_enabled(settings):
        return []
    if not settings.stripe_secret_key:
        return [p.value for p in PURCHASABLE_PLANS]
    return [p.value for p in PURCHASABLE_PLANS if price_id_for(settings, p)]


async def billing_overview(settings: Settings, tenant) -> dict[str, Any]:
    return {
        "status": str(tenant.status),
        "plan": str(tenant.plan),
        "trialEndsAt": tenant.trialEndsAt.isoformat() if tenant.trialEndsAt else None,
        "subscriptionId": tenant.subscriptionId,
        "hasCustomer": bool(tenant.customerId),
        "checkoutEnabled": checkout_enabled(settings),
        "purchasablePlans": purchasable_plans(settings),
        "usage": await usage_summary(tenant.id, str(tenant.plan)),
        "plans": [plan_public_view(p) for p in Plan],
    }


def _billing_url(settings: Settings, tenant_id: str, **query: str) -> str:
    qs = "&".join(f"{k}={v}" for k, v in query.items())
    return f"{settings.frontend_url.rstrip('/')}/app/{tenant_id}/billing" + (f"?{qs}" if qs else "")


async def create_checkout(
    settings: Settings, tenant, *, plan: str, user_email: str | None, actor_user_id: str, ip: str | None
) -> dict[str, str]:
    try:
        target = Plan(plan)
    except ValueError as exc:
        raise AppError("Plano inválido.", code="invalid_plan") from exc
    if target not in PURCHASABLE_PLANS or target.value not in purchasable_plans(settings):
        raise AppError("Este plano não está disponível para contratação online.", code="plan_not_purchasable")
    if tenant.subscriptionId and str(tenant.status) in ("ACTIVE", "PAST_DUE"):
        # Já existe assinatura: mudanças de plano e pagamento pendente são feitos no portal do gateway.
        raise ConflictError(
            "Sua clínica já tem uma assinatura. Use 'Gerenciar assinatura' para mudar de plano.",
            code="use_billing_portal",
        )
    client = build_stripe_client(settings)
    url = await client.create_checkout_session(
        price_id=price_id_for(settings, target),
        tenant_id=tenant.id,
        plan=target.value,
        customer_id=tenant.customerId,
        customer_email=user_email,
        success_url=_billing_url(settings, tenant.id, checkout="success"),
        cancel_url=_billing_url(settings, tenant.id, checkout="cancel"),
    )
    await audit.record(
        action="billing.checkout_started",
        resource_type="tenant",
        resource_id=tenant.id,
        tenant_id=tenant.id,
        actor_user_id=actor_user_id,
        metadata={"plan": target.value},
        ip=ip,
    )
    return {"url": url}


async def create_portal(settings: Settings, tenant, *, actor_user_id: str, ip: str | None) -> dict[str, str]:
    if not tenant.customerId:
        raise ConflictError("Sua clínica ainda não tem assinatura no gateway de pagamento.", code="no_customer")
    client = build_stripe_client(settings)
    url = await client.create_portal_session(
        customer_id=tenant.customerId, return_url=_billing_url(settings, tenant.id)
    )
    await audit.record(
        action="billing.portal_opened",
        resource_type="tenant",
        resource_id=tenant.id,
        tenant_id=tenant.id,
        actor_user_id=actor_user_id,
        ip=ip,
    )
    return {"url": url}
