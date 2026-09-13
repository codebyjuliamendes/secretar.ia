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


# Eventos que podem TROCAR a assinatura corrente do tenant. Os demais só se aplicam à assinatura atual:
# o Stripe não garante ordem, e um `customer.subscription.deleted` da assinatura antiga não pode cancelar a nova.
SUBSCRIPTION_SWITCH_EVENTS = ("checkout.session.completed", "customer.subscription.created")
# status da assinatura no Stripe → status do tenant (None = não mexer)
SUBSCRIPTION_STATUS_MAP = {
    "active": "ACTIVE",
    "trialing": "ACTIVE",
    "past_due": "PAST_DUE",
    "unpaid": "PAST_DUE",
    "canceled": "CANCELED",
    "incomplete_expired": "CANCELED",
    "incomplete": None,  # cartão recusado no checkout: nada muda até pagar
    "paused": None,
}


def _decide(etype: str, obj: dict[str, Any]) -> str | None:
    # Novo status do tenant para o evento, ou None para não alterar o status.
    if etype == "checkout.session.completed":
        # Boleto/Pix pendente chega com payment_status=unpaid: a assinatura nasce, mas só ativa ao pagar.
        return "ACTIVE" if obj.get("payment_status") in (None, "paid", "no_payment_required") else None
    if etype in ("invoice.payment_succeeded", "invoice.paid"):
        return "ACTIVE"
    if etype == "invoice.payment_failed":
        return "PAST_DUE"
    if etype == "customer.subscription.deleted":
        return "CANCELED"
    if etype in ("customer.subscription.created", "customer.subscription.updated"):
        return SUBSCRIPTION_STATUS_MAP.get(str(obj.get("status") or ""), "ACTIVE")
    return None


HANDLED_EVENTS = (
    "checkout.session.completed",
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
    "invoice.payment_succeeded",
    "invoice.paid",
    "invoice.payment_failed",
)


async def process_event(payload: dict[str, Any]) -> dict[str, Any]:
    info = _extract(payload)
    event_id, etype = info["event_id"], info["type"]
    if not event_id or not etype:
        return {"received": True, "handled": False, "reason": "missing_event_id_or_type"}
    if etype not in HANDLED_EVENTS:
        return {"received": True, "handled": False, "reason": "ignored_event_type"}
    if await db.webhookevent.find_unique(where={"id": f"stripe:{event_id}"}):
        return {"received": True, "handled": False, "reason": "duplicate"}

    tenant = await _find_tenant(info)
    if tenant is None:
        log.warning("billing_tenant_not_found", event_type=etype, subscription_id=info["subscription_id"])
        return {"received": True, "handled": False, "reason": "tenant_not_found"}

    obj = (payload.get("data") or {}).get("object") or {}
    sub_id = info["subscription_id"]
    if sub_id and tenant.subscriptionId and tenant.subscriptionId != sub_id and etype not in SUBSCRIPTION_SWITCH_EVENTS:
        log.info("billing_stale_subscription_event", event_type=etype, subscription_id=sub_id)
        await _mark_processed(event_id)
        return {"received": True, "handled": False, "reason": "stale_subscription"}

    data: dict[str, Any] = {}
    if sub_id and tenant.subscriptionId != sub_id:
        data["subscriptionId"] = sub_id
    if info["customer_id"] and tenant.customerId != info["customer_id"]:
        data["customerId"] = info["customer_id"]
    new_status = _decide(etype, obj)
    if new_status:
        data["status"] = new_status
    if info["plan"] and etype not in ("invoice.payment_failed", "customer.subscription.deleted"):
        data["plan"] = info["plan"].value

    if not data:
        await _mark_processed(event_id)
        return {"received": True, "handled": False, "reason": "no_change"}

    # Idempotência gravada na MESMA transação da mudança: se a atualização falhar, o Stripe reenvia e o
    # evento é reaplicado em vez de ficar marcado como processado sem efeito.
    try:
        async with db.tx() as tx:
            await tx.webhookevent.create(data={"id": f"stripe:{event_id}", "provider": "stripe"})
            updated = await tx.tenant.update(where={"id": tenant.id}, data=data)
    except UniqueViolationError as exc:
        if "WebhookEvent" in str(exc) or "PRIMARY" in str(exc).upper():
            return {"received": True, "handled": False, "reason": "duplicate"}
        # subscriptionId já pertence a outro tenant: evento inconsistente, não vale retentar.
        log.error("billing_subscription_conflict", event_type=etype, subscription_id=sub_id)
        await _mark_processed(event_id)
        return {"received": True, "handled": False, "reason": "subscription_conflict"}
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


async def _mark_processed(event_id: str) -> None:
    try:
        await db.webhookevent.create(data={"id": f"stripe:{event_id}", "provider": "stripe"})
    except UniqueViolationError:
        pass


# ------------------------------ Checkout e portal ------------------------------

PURCHASABLE_PLANS = (Plan.BASIC, Plan.PRO, Plan.PREMIUM)


def price_id_for(settings: Settings, plan: Plan) -> str:
    return {
        Plan.BASIC: settings.stripe_price_basic,
        Plan.PRO: settings.stripe_price_pro,
        Plan.PREMIUM: settings.stripe_price_premium,
    }.get(plan, "")


def sales_contact(settings: Settings) -> dict[str, str]:
    """Quem o cliente procura para Enterprise ou condições fora do checkout."""
    digits = "".join(ch for ch in settings.sales_whatsapp if ch.isdigit())
    return {"whatsapp": digits, "name": settings.sales_contact_name}


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
        "subscriptionId": tenant.subscriptionId,
        "hasCustomer": bool(tenant.customerId),
        "checkoutEnabled": checkout_enabled(settings),
        "purchasablePlans": purchasable_plans(settings),
        "usage": await usage_summary(tenant),
        "plans": [plan_public_view(p) for p in Plan],
        "sales": sales_contact(settings),
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
