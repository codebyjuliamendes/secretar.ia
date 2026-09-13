"""LGPD: pedido de exclusão pelo titular, encerramento pedido pelo dono e exclusão definitiva pela equipe."""

import json

from app.config import get_settings
from app.security.signatures import sign_hub
from tests.conftest import auth_headers, register_user, unique_email
from tests.integration.test_rbac_and_admin import login


def signed(payload: dict, secret: str = "test-whatsapp-secret"):
    body = json.dumps(payload).encode()
    return body, {"X-Hub-Signature-256": sign_hub(body, secret), "Content-Type": "application/json"}


async def _admin(client, clean_db):
    admin_user = await register_user(client, active=False)
    await clean_db.user.update(where={"email": admin_user["email"]}, data={"platformRole": "SUPER_ADMIN"})
    return auth_headers(await login(client, admin_user["email"], admin_user["password"]))


async def test_contact_asking_for_deletion_is_recorded_and_business_is_warned(client, clean_db):
    reg = await register_user(client)
    tid, h = reg["tenantId"], auth_headers(reg)
    body, headers = signed(
        {"messageId": "d1", "phone": "5581999991001", "text": "quero que apague meus dados", "tenantId": tid}
    )
    r = await client.post("/api/webhooks/whatsapp", content=body, headers=headers)
    assert r.status_code == 200, r.text
    assert "pedido de exclusão de dados" in r.json()["reply"].lower()

    patient = await clean_db.patient.find_first(where={"tenantId": tid, "phone": "5581999991001"})
    assert patient.marketingOptOut is True  # campanhas param na hora, sem esperar a equipe
    notes = await clean_db.notification.find_many(where={"tenantId": tid, "type": "SYSTEM"})
    assert any("LGPD" in n.title for n in notes)
    assert "15 dias" in next(n for n in notes if "LGPD" in n.title).body
    jobs = await clean_db.job.find_many(where={"name": "send-whatsapp"})
    assert len(jobs) == 1 and "exclusão" in jobs[0].payload["text"]

    # A equipe atende o pedido com o botão que já existe em Contatos.
    assert (await client.delete(f"/api/clinic/{tid}/patients/{patient.id}", headers=h)).status_code == 204
    assert await clean_db.patient.count(where={"tenantId": tid}) == 0

    # Conversa normal não dispara o fluxo.
    body, headers = signed({"messageId": "d2", "phone": "5581999991002", "text": "bom dia", "tenantId": tid})
    r = await client.post("/api/webhooks/whatsapp", content=body, headers=headers)
    assert "exclusão de dados" not in r.json()["reply"]


async def test_owner_requests_closure_and_platform_deletes_for_good(client, clean_db, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(type(settings), "alerts_to", property(lambda self: "julia@example.com"))
    reg = await register_user(client, clinic="Vai Fechar")
    tid, h = reg["tenantId"], auth_headers(reg)
    await client.post(f"/api/clinic/{tid}/patients", headers=h, json={"phone": "5581999991011", "name": "Ana"})
    ah = await _admin(client, clean_db)

    r = await client.post(f"/api/clinic/{tid}/account/deletion-request", headers=h, json={"reason": "fechei a loja"})
    assert r.status_code == 200 and r.json()["requestedAt"]
    mails = [
        j for j in await clean_db.job.find_many(where={"name": "send-email"}) if "encerramento" in j.payload["subject"]
    ]
    assert (
        len(mails) == 1
        and mails[0].payload["to"] == "julia@example.com"
        and "fechei a loja" in mails[0].payload["text"]
    )
    listed = (await client.get("/api/admin/tenants", headers=ah, params={"search": "Vai Fechar"})).json()["items"][0]
    assert listed["deletionRequestedAt"]

    # Confirmação errada não apaga nada.
    bad = await client.post(f"/api/admin/tenants/{tid}/delete", headers=ah, json={"confirm": "vai fechar"})
    assert bad.status_code == 409 and bad.json()["error"]["code"] == "confirm_mismatch"
    assert await clean_db.tenant.count(where={"id": tid}) == 1

    ok = await client.post(f"/api/admin/tenants/{tid}/delete", headers=ah, json={"confirm": "Vai Fechar"})
    assert ok.status_code == 200 and ok.json()["deleted"] is True and ok.json()["usersRemoved"] == 1
    assert await clean_db.tenant.count(where={"id": tid}) == 0
    assert await clean_db.patient.count(where={"tenantId": tid}) == 0
    assert await clean_db.user.find_unique(where={"email": reg["email"]}) is None
    audit = await clean_db.auditlog.find_many(where={"action": "admin.tenant_deleted"})
    assert audit and audit[0].metadata["name"] == "Vai Fechar"


async def test_deletion_request_requires_owner_and_public_config_exposes_legal(client, clean_db):
    owner = await register_user(client, clinic="Com Equipe")
    tid = owner["tenantId"]
    staff_email = unique_email("staff-lgpd")
    inv = await client.post(
        f"/api/clinic/{tid}/team",
        headers=auth_headers(owner),
        json={"email": staff_email, "name": "Recepção", "role": "STAFF"},
    )
    assert inv.status_code == 201, inv.text
    job = await clean_db.job.find_first(where={"name": "send-email"}, order={"createdAt": "desc"})
    token = job.payload["text"].split("token=")[1].split()[0]
    assert (
        await client.post("/api/auth/invites/accept", json={"token": token, "password": "Staff1234"})
    ).status_code == 200
    hs = auth_headers(await login(client, staff_email, "Staff1234"))
    denied = await client.post(f"/api/clinic/{tid}/account/deletion-request", headers=hs, json={})
    assert denied.status_code == 403 and denied.json()["error"]["code"] == "permission_denied"
    assert (await clean_db.tenant.find_unique(where={"id": tid})).deletionRequestedAt is None

    body = (await client.get("/api/public/config")).json()
    assert set(body["legal"]) == {"entity", "doc", "privacyEmail"}
