"""Cobrança fora do Stripe (Pix, boleto, transferência): a Júlia marca "pago até" no admin.

Regras: registrar um pagamento com data futura ativa a conta (PENDING/PAST_DUE → ACTIVE). Vencido há mais de
GRACE_DAYS, sem assinatura no Stripe, a rotina diária passa a conta para PAST_DUE, avisa o cliente no painel e
a equipe por e-mail. O Stripe continua funcionando para quem preferir cartão (subscriptionId presente).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.config import Settings
from app.db import db
from app.jobs.queue import enqueue
from app.jobs.tasks import SEND_EMAIL
from app.logging import get_logger
from app.services import audit, notifications

log = get_logger("manual_billing")

GRACE_DAYS = 3
PAYMENT_METHODS = ("", "PIX", "BOLETO", "STRIPE", "OUTRO")


def days_left(paid_until: datetime | None, now: datetime | None = None) -> int | None:
    if paid_until is None:
        return None
    now = now or datetime.now(UTC)
    return (paid_until - now).days


async def sweep_overdue(settings: Settings, now: datetime | None = None) -> int:
    """Contas ativas com "pago até" vencido além da carência viram PAST_DUE. Idempotente."""
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(days=GRACE_DAYS)
    overdue = await db.tenant.find_many(where={"status": "ACTIVE", "subscriptionId": None, "paidUntil": {"lt": cutoff}})
    for tenant in overdue:
        await db.tenant.update(where={"id": tenant.id}, data={"status": "PAST_DUE"})
        await notifications.notify(
            tenant.id,
            type_="BILLING",
            title="Pagamento pendente",
            body=(
                f"O período pago terminou em {tenant.paidUntil.strftime('%d/%m/%Y')}. A assistente fica pausada até "
                f"a confirmação do pagamento; fale com {settings.sales_contact_name} para regularizar."
            ),
            dedupe_minutes=7 * 24 * 60,
        )
        await audit.record(
            action="billing.overdue",
            resource_type="tenant",
            resource_id=tenant.id,
            tenant_id=tenant.id,
            metadata={"paidUntil": tenant.paidUntil.isoformat()},
        )
        if settings.alerts_to:
            await enqueue(
                SEND_EMAIL,
                {
                    "to": settings.alerts_to,
                    "subject": (
                        f"[Secretar.ia] {tenant.name} venceu em {tenant.paidUntil.strftime('%d/%m')} e foi pausada"
                    ),
                    "text": (
                        f"{tenant.name} estava paga até {tenant.paidUntil.strftime('%d/%m/%Y')} e passou os "
                        f"{GRACE_DAYS} dias de carência. Status agora: pagamento pendente (assistente pausada).\n"
                        f"Ao receber, registre o novo 'pago até' em {settings.frontend_url.rstrip('/')}/admin/tenants."
                    ),
                },
            )
        log.info("tenant_overdue", tenant_id=tenant.id)
    return len(overdue)
