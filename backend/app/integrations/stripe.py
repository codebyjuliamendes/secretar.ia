"""Cliente Stripe (REST via httpx, sem SDK): Checkout Sessions e Customer Portal.

Sem STRIPE_SECRET_KEY em desenvolvimento/test, usa o provider `console`, que devolve uma URL local
sinalizada com `checkout=console` (nada é cobrado). Em produção, ausência de chave é erro explícito.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

import httpx

from app.config import Settings
from app.errors import IntegrationUnavailableError
from app.logging import get_logger

log = get_logger("integrations.stripe")

_BASE = "https://api.stripe.com/v1"


def flatten_form(data: dict[str, Any], prefix: str = "") -> list[tuple[str, str]]:
    """Converte dict aninhado no formato de formulário do Stripe: a[b][c]=v, listas como a[0][b]=v."""
    out: list[tuple[str, str]] = []
    for key, value in data.items():
        name = f"{prefix}[{key}]" if prefix else str(key)
        if value is None:
            continue
        if isinstance(value, dict):
            out.extend(flatten_form(value, name))
        elif isinstance(value, list | tuple):
            for i, item in enumerate(value):
                if isinstance(item, dict):
                    out.extend(flatten_form(item, f"{name}[{i}]"))
                else:
                    out.append((f"{name}[{i}]", str(item)))
        elif isinstance(value, bool):
            out.append((name, "true" if value else "false"))
        else:
            out.append((name, str(value)))
    return out


class StripeClient:
    async def create_checkout_session(
        self,
        *,
        price_id: str,
        tenant_id: str,
        plan: str,
        customer_id: str | None,
        customer_email: str | None,
        success_url: str,
        cancel_url: str,
    ) -> str: ...

    async def create_portal_session(self, *, customer_id: str, return_url: str) -> str: ...


class ConsoleStripeClient(StripeClient):
    """Desenvolvimento: não chama o Stripe; devolve URL local marcada como `console`."""

    async def create_checkout_session(
        self, *, price_id, tenant_id, plan, customer_id, customer_email, success_url, cancel_url
    ):
        log.info("stripe_console_checkout", tenant_id=tenant_id, plan=plan, price_id=price_id or None)
        return success_url.replace("checkout=success", "checkout=console")

    async def create_portal_session(self, *, customer_id, return_url):
        log.info("stripe_console_portal", customer_id=customer_id)
        sep = "&" if "?" in return_url else "?"
        return f"{return_url}{sep}portal=console"


class HttpStripeClient(StripeClient):
    def __init__(self, secret_key: str, timeout: float = 15.0):
        self._headers = {
            "Authorization": f"Bearer {secret_key}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Stripe-Version": "2024-06-20",
        }
        self._timeout = timeout

    async def _post(self, path: str, data: dict[str, Any], idempotency_key: str | None = None) -> dict:
        headers = dict(self._headers)
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(f"{_BASE}{path}", headers=headers, content=urlencode(flatten_form(data)))
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise IntegrationUnavailableError(
                "Gateway de pagamento indisponível. Tente novamente em instantes.", code="stripe_unavailable"
            ) from exc
        if resp.status_code >= 400:
            try:
                err = (resp.json() or {}).get("error") or {}
            except ValueError:
                err = {}
            log.error("stripe_error", status=resp.status_code, code=err.get("code"), type=err.get("type"))
            raise IntegrationUnavailableError(
                "O gateway de pagamento recusou a operação. Nossa equipe foi avisada.", code="stripe_error"
            )
        return resp.json()

    async def create_checkout_session(
        self, *, price_id, tenant_id, plan, customer_id, customer_email, success_url, cancel_url
    ):
        payload: dict[str, Any] = {
            "mode": "subscription",
            "line_items": [{"price": price_id, "quantity": 1}],
            "success_url": success_url,
            "cancel_url": cancel_url,
            "client_reference_id": tenant_id,
            "locale": "pt-BR",
            "allow_promotion_codes": True,
            "metadata": {"tenantId": tenant_id, "plan": plan},
            "subscription_data": {"metadata": {"tenantId": tenant_id, "plan": plan}},
        }
        if customer_id:
            payload["customer"] = customer_id
        elif customer_email:
            payload["customer_email"] = customer_email
        data = await self._post("/checkout/sessions", payload)
        url = data.get("url")
        if not url:
            raise IntegrationUnavailableError("Resposta inválida do gateway de pagamento.", code="stripe_error")
        return str(url)

    async def create_portal_session(self, *, customer_id, return_url):
        data = await self._post("/billing_portal/sessions", {"customer": customer_id, "return_url": return_url})
        url = data.get("url")
        if not url:
            raise IntegrationUnavailableError("Resposta inválida do gateway de pagamento.", code="stripe_error")
        return str(url)


def build_stripe_client(settings: Settings) -> StripeClient:
    if settings.stripe_secret_key:
        return HttpStripeClient(settings.stripe_secret_key)
    if settings.is_production_like:
        raise IntegrationUnavailableError(
            "Pagamentos online não configurados (STRIPE_SECRET_KEY).", code="stripe_not_configured"
        )
    return ConsoleStripeClient()
