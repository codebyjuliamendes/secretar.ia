import json

from app.security.signatures import sign_stripe
from tests.conftest import auth_headers, register_user


def _stripe_headers(body: bytes) -> dict:
    return {"Stripe-Signature": sign_stripe(body, "whsec_test"), "Content-Type": "application/json"}


async def test_checkout_flow_console_provider_and_webhook_activation(client, clean_db):
    reg = await register_user(client)
    tid, h = reg["tenantId"], auth_headers(reg)

    overview = (await client.get(f"/api/clinic/{tid}/billing", headers=h)).json()
    assert overview["checkoutEnabled"] is True and overview["hasCustomer"] is False
    assert overview["purchasablePlans"] == ["BASIC", "PRO", "PREMIUM"]

    # Plano não contratável online.
    bad = await client.post(f"/api/clinic/{tid}/billing/checkout", headers=h, json={"plan": "FREE"})
    assert bad.status_code == 422  # rejeitado pelo schema (Literal)

    # Sem assinatura no gateway, o portal não existe.
    portal = await client.post(f"/api/clinic/{tid}/billing/portal", headers=h)
    assert portal.status_code == 409 and portal.json()["error"]["code"] == "no_customer"

    # Checkout (provider console em test): devolve URL de retorno marcada como console.
    res = await client.post(f"/api/clinic/{tid}/billing/checkout", headers=h, json={"plan": "PRO"})
    assert res.status_code == 200, res.text
    assert res.json()["url"].endswith(f"/app/{tid}/billing?checkout=console")
    audit = (await client.get(f"/api/clinic/{tid}/audit", headers=h)).json()
    assert any(a["action"] == "billing.checkout_started" for a in audit["items"])

    # Webhook checkout.session.completed: resolve o tenant por client_reference_id e ativa o plano.
    event = {
        "id": "evt_cs_1",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "object": "checkout.session",
                "id": "cs_test_1",
                "subscription": "sub_cs_1",
                "customer": "cus_cs_1",
                "client_reference_id": tid,
                "metadata": {"plan": "PRO"},
            }
        },
    }
    body = json.dumps(event).encode()
    hook = await client.post("/api/webhooks/billing", content=body, headers=_stripe_headers(body))
    assert hook.status_code == 200 and hook.json()["handled"] is True and hook.json()["status"] == "ACTIVE"
    t = await clean_db.tenant.find_unique(where={"id": tid})
    assert str(t.plan) == "PRO" and t.subscriptionId == "sub_cs_1" and t.customerId == "cus_cs_1"

    # Com assinatura ativa, novo checkout é recusado e o portal passa a funcionar.
    again = await client.post(f"/api/clinic/{tid}/billing/checkout", headers=h, json={"plan": "BASIC"})
    assert again.status_code == 409 and again.json()["error"]["code"] == "use_billing_portal"
    portal = await client.post(f"/api/clinic/{tid}/billing/portal", headers=h)
    assert portal.status_code == 200 and "portal=console" in portal.json()["url"]
    overview = (await client.get(f"/api/clinic/{tid}/billing", headers=h)).json()
    assert overview["hasCustomer"] is True and overview["plan"] == "PRO"


async def test_checkout_requires_billing_manage_permission(client, clean_db):
    owner = await register_user(client)
    tid = owner["tenantId"]
    staff_email = "staff-billing@example.com"
    invite = await client.post(
        f"/api/clinic/{tid}/team",
        headers=auth_headers(owner),
        json={"email": staff_email, "name": "Staff", "role": "MANAGER"},
    )
    assert invite.status_code == 201, invite.text
    # Gerente tem BILLING_VIEW mas não BILLING_MANAGE.
    job = await clean_db.job.find_first(where={"name": "send-email"}, order={"createdAt": "desc"})
    token = job.payload["text"].split("token=")[1].split()[0]
    assert (
        await client.post("/api/auth/invites/accept", json={"token": token, "password": "Senha1234"})
    ).status_code == 200
    login = await client.post("/api/auth/login", json={"email": staff_email, "password": "Senha1234"})
    assert login.status_code == 200, login.text
    h = {"Authorization": f"Bearer {login.json()['accessToken']}"}
    assert (await client.get(f"/api/clinic/{tid}/billing", headers=h)).status_code == 200
    denied = await client.post(f"/api/clinic/{tid}/billing/checkout", headers=h, json={"plan": "PRO"})
    assert denied.status_code == 403 and denied.json()["error"]["code"] == "permission_denied"
