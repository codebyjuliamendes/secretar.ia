"""Planos pagos (Essencial, Profissional, Premium, Enterprise), clínica pendente até o admin liberar, limites."""

import base64
import json

import pytest

from app.integrations.gemini import AIResult
from app.security.signatures import sign_hub
from app.services import media as media_service
from tests.conftest import auth_headers, register_user
from tests.integration.test_knowledge import DOC_PAGAMENTO
from tests.integration.test_rbac_and_admin import login

FAKE_AUDIO = base64.b64encode(b"OggS" + b"\x00" * 64).decode()


def signed(payload: dict, secret: str = "test-whatsapp-secret"):
    body = json.dumps(payload).encode()
    return body, {"X-Hub-Signature-256": sign_hub(body, secret), "Content-Type": "application/json"}


class FakeGemini:
    def __init__(self):
        self.calls = 0

    async def describe_media(self, prompt, data, mime_type, *, max_output_tokens=None):
        self.calls += 1
        return AIResult(text="Quero agendar um peeling", input_tokens=1, output_tokens=1, model="fake")


async def test_new_clinic_waits_for_admin_to_release_the_plan(client, clean_db):
    reg = await register_user(client, active=False)
    tid, h = reg["tenantId"], auth_headers(reg)
    summary = (await client.get(f"/api/clinic/{tid}", headers=h)).json()
    assert summary["status"] == "PENDING" and summary["plan"] == "BASIC"
    settings = (await client.get(f"/api/clinic/{tid}/settings", headers=h)).json()
    assert settings["prompt"] == "" and settings["tone"] == "acolhedor"  # nada a escrever: persona gerada

    # Pendente: pode configurar (inclusive a base de conhecimento), mas a IA não atende pacientes.
    doc = await client.post(
        f"/api/clinic/{tid}/knowledge", headers=h, json={"title": "Pagamento", "content": DOC_PAGAMENTO}
    )
    assert doc.status_code == 201
    body, headers = signed({"messageId": "pend-1", "phone": "5581999990000", "text": "oi", "tenantId": tid})
    res = await client.post("/api/webhooks/whatsapp", content=body, headers=headers)
    assert res.json() == {
        "status": "blocked",
        "intent": None,
        "reply": None,
        "reason": "tenant_pending",
        "degraded": False,
    }

    # Admin libera o plano: a clínica ativa sozinha e passa a atender.
    admin_user = await register_user(client, active=False)
    await clean_db.user.update(where={"email": admin_user["email"]}, data={"platformRole": "SUPER_ADMIN"})
    admin = await login(client, admin_user["email"], admin_user["password"])
    upd = await client.patch(f"/api/admin/tenants/{tid}", headers=auth_headers(admin), json={"plan": "PRO"})
    assert upd.status_code == 200 and upd.json()["status"] == "ACTIVE" and upd.json()["plan"] == "PRO"
    body, headers = signed({"messageId": "pend-2", "phone": "5581999990000", "text": "oi", "tenantId": tid})
    assert (await client.post("/api/webhooks/whatsapp", content=body, headers=headers)).json()["status"] == "processed"
    overview = (await client.get("/api/admin/overview", headers=auth_headers(admin))).json()
    assert overview["tenants"]["pending"] == 1  # a clínica do próprio admin continua pendente


async def test_plan_catalog_and_document_limits(client, clean_db):
    reg = await register_user(client, plan="BASIC")
    tid, h = reg["tenantId"], auth_headers(reg)
    billing = (await client.get(f"/api/clinic/{tid}/billing", headers=h)).json()
    plans = {p["plan"]: p for p in billing["plans"]}
    assert list(plans) == ["BASIC", "PRO", "PREMIUM", "ENTERPRISE"]
    assert plans["BASIC"]["label"] == "Essencial" and plans["BASIC"]["priceCentsMonth"] == 75_000
    assert plans["PRO"]["priceCentsMonth"] == 100_000 and plans["PREMIUM"]["priceCentsMonth"] == 150_000
    assert plans["ENTERPRISE"]["priceFrom"] is True and plans["ENTERPRISE"]["maxKnowledgeDocuments"] == -1
    assert all(p["mediaUnderstanding"] and p["knowledgeBase"] for p in plans.values())
    assert billing["usage"]["knowledgeDocuments"] == {"used": 0, "limit": 10}

    for i in range(10):
        r = await client.post(
            f"/api/clinic/{tid}/knowledge",
            headers=h,
            json={"title": f"Documento {i}", "content": f"Conteúdo número {i} da base de conhecimento da clínica."},
        )
        assert r.status_code == 201, r.text
    over = await client.post(
        f"/api/clinic/{tid}/knowledge", headers=h, json={"title": "Onze", "content": "Este documento excede o plano."}
    )
    assert over.status_code == 402 and over.json()["error"]["details"] == {"limit": 10}
    # Subiu para Profissional: 30 documentos.
    await clean_db.tenant.update(where={"id": tid}, data={"plan": "PRO"})
    assert (await client.get(f"/api/clinic/{tid}/billing", headers=h)).json()["usage"]["knowledgeDocuments"][
        "limit"
    ] == 30


async def test_every_paid_plan_reads_media(client, clean_db, monkeypatch: pytest.MonkeyPatch):
    fake = FakeGemini()
    monkeypatch.setattr(media_service, "client_for", lambda settings: fake)
    reg = await register_user(client, plan="BASIC")
    tid = reg["tenantId"]
    body, headers = signed(
        {
            "messageId": "aud-basic",
            "phone": "5581999990001",
            "text": "",
            "tenantId": tid,
            "mediaKind": "audio",
            "mediaBase64": FAKE_AUDIO,
            "mediaMimeType": "audio/ogg",
        }
    )
    res = await client.post("/api/webhooks/whatsapp", content=body, headers=headers)
    assert res.status_code == 200 and fake.calls == 1
    logs = await clean_db.executionlog.find_many(where={"tenantId": tid})
    assert logs and logs[0].error != "media_not_in_plan"


async def test_tone_drives_the_generated_persona(client, clean_db):
    from datetime import UTC, datetime
    from types import SimpleNamespace

    from app.services.ai import build_system_prompt

    reg = await register_user(client)
    tid, h = reg["tenantId"], auth_headers(reg)
    upd = await client.patch(f"/api/clinic/{tid}/settings", headers=h, json={"tone": "formal", "prompt": ""})
    assert upd.status_code == 200 and upd.json()["tone"] == "formal"
    t = SimpleNamespace(name="Clínica X", tone="formal", prompt="", businessHours=None, prices=None, timezone="UTC")
    prompt = build_system_prompt(t, now_local=datetime.now(UTC), upcoming=[])
    assert "senhor/senhora" in prompt and "secretária virtual da clínica Clínica X" in prompt
    assert "Instruções adicionais" not in prompt
    t.prompt = "Não prometa desconto."
    assert "Não prometa desconto." in build_system_prompt(t, now_local=datetime.now(UTC), upcoming=[])
    bad = await client.patch(f"/api/clinic/{tid}/settings", headers=h, json={"tone": "sarcástico"})
    assert bad.status_code == 422


async def test_admin_picks_the_niche_and_the_assistant_adapts(client, clean_db):
    from datetime import UTC, datetime
    from types import SimpleNamespace

    from app.services.ai import build_system_prompt

    reg = await register_user(client, active=False)
    tid, h = reg["tenantId"], auth_headers(reg)
    assert (await client.get(f"/api/clinic/{tid}", headers=h)).json()["niche"]["people"] == "Pacientes"
    admin_user = await register_user(client, active=False)
    await clean_db.user.update(where={"email": admin_user["email"]}, data={"platformRole": "SUPER_ADMIN"})
    admin = await login(client, admin_user["email"], admin_user["password"])
    niches = (await client.get("/api/admin/niches", headers=auth_headers(admin))).json()["items"]
    assert {n["key"] for n in niches} >= {"clinica", "salao", "pet", "advocacia", "outro"}
    bad = await client.patch(f"/api/admin/tenants/{tid}", headers=auth_headers(admin), json={"niche": "padaria"})
    assert bad.status_code == 409
    ok = await client.patch(
        f"/api/admin/tenants/{tid}", headers=auth_headers(admin), json={"niche": "pet", "plan": "PRO"}
    )
    assert ok.status_code == 200 and ok.json()["niche"]["person"] == "tutor" and ok.json()["status"] == "ACTIVE"
    assert (await client.get(f"/api/clinic/{tid}", headers=h)).json()["niche"]["people"] == "Tutores"
    t = SimpleNamespace(
        name="Bicho Feliz", tone="acolhedor", prompt="", niche="pet", businessHours=None, prices=None, timezone="UTC"
    )
    prompt = build_system_prompt(t, now_local=datetime.now(UTC), upcoming=[])
    assert "clínica veterinária Bicho Feliz" in prompt and "tutores" in prompt and "sintomas do animal" in prompt
    assert "diagnóstico ou orientação médica" not in prompt
    law = SimpleNamespace(
        name="Silva & Souza",
        tone="formal",
        prompt="",
        niche="advocacia",
        businessHours=None,
        prices=None,
        timezone="UTC",
    )
    assert "orientação jurídica" in build_system_prompt(law, now_local=datetime.now(UTC), upcoming=[])


async def test_niche_suggests_the_tone_unless_the_customer_chose_one(client, clean_db):
    reg = await register_user(client, active=False)
    tid, h = reg["tenantId"], auth_headers(reg)
    admin_user = await register_user(client, active=False)
    await clean_db.user.update(where={"email": admin_user["email"]}, data={"platformRole": "SUPER_ADMIN"})
    ah = auth_headers(await login(client, admin_user["email"], admin_user["password"]))
    # cliente ainda no tom sugerido (acolhedor): advocacia vira formal
    r = await client.patch(f"/api/admin/tenants/{tid}", headers=ah, json={"niche": "advocacia"})
    assert r.status_code == 200 and r.json()["niche"]["tone"] == "formal"
    assert (await client.get(f"/api/clinic/{tid}/settings", headers=h)).json()["tone"] == "formal"
    # cliente escolhe o próprio tom: trocar o nicho de novo não mexe
    await client.patch(f"/api/clinic/{tid}/settings", headers=h, json={"tone": "objetivo"})
    r = await client.patch(f"/api/admin/tenants/{tid}", headers=ah, json={"niche": "psicologia"})
    assert r.status_code == 200
    assert (await client.get(f"/api/clinic/{tid}/settings", headers=h)).json()["tone"] == "objetivo"
