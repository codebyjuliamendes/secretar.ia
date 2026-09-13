"""Eventos do Stripe aplicados fora de ordem, status incompletos e idempotência atômica."""

from app.services import billing
from tests.conftest import register_user


def _event(eid: str, etype: str, obj: dict) -> dict:
    return {"id": eid, "type": etype, "data": {"object": obj}}


async def test_stale_subscription_events_do_not_override_current_subscription(client, clean_db):
    reg = await register_user(client)
    tid = reg["tenantId"]
    # Assinatura A ativa e depois cancelada; assinatura B contratada em seguida.
    r = await billing.process_event(
        _event(
            "evt1",
            "checkout.session.completed",
            {
                "object": "checkout.session",
                "subscription": "sub_A",
                "customer": "cus_1",
                "client_reference_id": tid,
                "payment_status": "paid",
                "metadata": {"plan": "BASIC"},
            },
        )
    )
    assert r["handled"] and r["status"] == "ACTIVE"
    r = await billing.process_event(
        _event(
            "evt2",
            "checkout.session.completed",
            {
                "object": "checkout.session",
                "subscription": "sub_B",
                "customer": "cus_1",
                "client_reference_id": tid,
                "payment_status": "paid",
                "metadata": {"plan": "PRO"},
            },
        )
    )
    t = await clean_db.tenant.find_unique(where={"id": tid})
    assert t.subscriptionId == "sub_B" and str(t.plan) == "PRO"
    # O cancelamento da assinatura ANTIGA chega depois: não pode cancelar a clínica nem trocar o subscriptionId.
    r = await billing.process_event(
        _event("evt3", "customer.subscription.deleted", {"object": "subscription", "id": "sub_A", "customer": "cus_1"})
    )
    assert r == {"received": True, "handled": False, "reason": "stale_subscription"}
    t = await clean_db.tenant.find_unique(where={"id": tid})
    assert str(t.status) == "ACTIVE" and t.subscriptionId == "sub_B" and str(t.plan) == "PRO"
    # Reenvio do mesmo evento é duplicado, inclusive o descartado.
    again = await billing.process_event(
        _event("evt3", "customer.subscription.deleted", {"object": "subscription", "id": "sub_A"})
    )
    assert again["reason"] == "duplicate"
    # Cancelamento da assinatura corrente vale.
    r = await billing.process_event(
        _event("evt4", "customer.subscription.deleted", {"object": "subscription", "id": "sub_B", "customer": "cus_1"})
    )
    assert r["handled"] and r["status"] == "CANCELED"
    assert str((await clean_db.tenant.find_unique(where={"id": tid})).plan) == "PRO"  # plano não muda ao cancelar


async def test_incomplete_and_unpaid_do_not_activate(client, clean_db):
    reg = await register_user(client)
    tid = reg["tenantId"]
    await clean_db.tenant.update(where={"id": tid}, data={"status": "SUSPENDED"})
    # Checkout com boleto/Pix pendente: assinatura registrada, status não muda.
    r = await billing.process_event(
        _event(
            "e1",
            "checkout.session.completed",
            {
                "object": "checkout.session",
                "subscription": "sub_X",
                "customer": "cus_9",
                "client_reference_id": tid,
                "payment_status": "unpaid",
                "metadata": {"plan": "PRO"},
            },
        )
    )
    t = await clean_db.tenant.find_unique(where={"id": tid})
    assert r["handled"] and str(t.status) == "SUSPENDED" and t.subscriptionId == "sub_X" and str(t.plan) == "PRO"
    # Cartão recusado: subscription.created com status incomplete não ativa; incomplete_expired cancela.
    r = await billing.process_event(
        _event("e2", "customer.subscription.updated", {"object": "subscription", "id": "sub_X", "status": "incomplete"})
    )
    assert r["reason"] == "no_change"
    assert str((await clean_db.tenant.find_unique(where={"id": tid})).status) == "SUSPENDED"
    r = await billing.process_event(
        _event("e3", "customer.subscription.updated", {"object": "subscription", "id": "sub_X", "status": "active"})
    )
    assert r["status"] == "ACTIVE"
    r = await billing.process_event(
        _event("e4", "customer.subscription.updated", {"object": "subscription", "id": "sub_X", "status": "past_due"})
    )
    assert r["status"] == "PAST_DUE"
    r = await billing.process_event(
        _event(
            "e5",
            "customer.subscription.updated",
            {"object": "subscription", "id": "sub_X", "status": "incomplete_expired"},
        )
    )
    assert r["status"] == "CANCELED"
    other = await billing.process_event(_event("e6", "charge.succeeded", {"object": "charge"}))
    assert other["reason"] == "ignored_event_type"
    assert await clean_db.webhookevent.count() == 5
