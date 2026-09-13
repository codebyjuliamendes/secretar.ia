"""Recursos de plano: leitura de áudio/imagem e base de conhecimento (RAG).

Regra: FREE não inclui nenhum dos dois; BASIC/PRO/ENTERPRISE incluem (com limite de documentos por plano).
Não há trial: a clínica nasce ATIVA no FREE e o admin libera o plano pago. Tudo verificado no backend.
"""

import base64
import json

import pytest

from app.integrations.gemini import AIResult
from app.security.signatures import sign_hub
from app.services import media as media_service
from tests.conftest import auth_headers, register_user
from tests.integration.test_knowledge import DOC_PAGAMENTO

FAKE_AUDIO = base64.b64encode(b"OggS" + b"\x00" * 64).decode()


def signed(payload: dict, secret: str = "test-whatsapp-secret"):
    body = json.dumps(payload).encode()
    return body, {"X-Hub-Signature-256": sign_hub(body, secret), "Content-Type": "application/json"}


class FakeGemini:
    def __init__(self):
        self.calls = 0

    async def describe_media(self, prompt, data, mime_type, *, max_output_tokens=None):
        self.calls += 1
        return AIResult(text="não deveria ser chamado", input_tokens=1, output_tokens=1, model="fake")


async def test_new_clinic_is_active_free_and_plan_unlocks_features(client, clean_db):
    reg = await register_user(client)
    tid, h = reg["tenantId"], auth_headers(reg)

    summary = (await client.get(f"/api/clinic/{tid}", headers=h)).json()
    assert summary["status"] == "ACTIVE" and summary["plan"] == "FREE" and "trialEndsAt" not in summary
    settings = (await client.get(f"/api/clinic/{tid}/settings", headers=h)).json()
    assert settings["featureAccess"] == {
        "featurePlan": "FREE",
        "media": False,
        "knowledge": False,
        "maxKnowledgeDocuments": 0,
    }
    assert settings["planLimits"]["knowledgeBase"] is False
    billing = (await client.get(f"/api/clinic/{tid}/billing", headers=h)).json()
    assert billing["usage"]["knowledgeDocuments"] == {"used": 0, "limit": 0}
    # O admin libera o plano manualmente (aqui, direto no banco): recursos passam a valer.
    await clean_db.tenant.update(where={"id": tid}, data={"plan": "PRO"})
    settings = (await client.get(f"/api/clinic/{tid}/settings", headers=h)).json()
    assert settings["featureAccess"]["featurePlan"] == "PRO" and settings["featureAccess"]["knowledge"] is True
    billing = (await client.get(f"/api/clinic/{tid}/billing", headers=h)).json()
    assert billing["usage"]["knowledgeDocuments"] == {"used": 0, "limit": 50}
    plans = {p["plan"]: p for p in billing["plans"]}
    assert plans["FREE"]["mediaUnderstanding"] is False and plans["BASIC"]["maxKnowledgeDocuments"] == 10
    assert plans["ENTERPRISE"]["maxKnowledgeDocuments"] == -1

    doc = await client.post(
        f"/api/clinic/{tid}/knowledge", headers=h, json={"title": "Pagamento", "content": DOC_PAGAMENTO}
    )
    assert doc.status_code == 201
    # O campo livre `features` não é editável pela clínica nem sobrepõe o plano.
    patched = await client.patch(f"/api/clinic/{tid}/settings", headers=h, json={"features": {"knowledge": True}})
    assert patched.status_code == 200 and patched.json()["features"] == {}

    # Voltou ao FREE: documento continua listado, mas não pode ser alterado nem usado.
    await clean_db.tenant.update(where={"id": tid}, data={"plan": "FREE"})
    settings = (await client.get(f"/api/clinic/{tid}/settings", headers=h)).json()
    assert settings["featureAccess"]["knowledge"] is False
    assert len((await client.get(f"/api/clinic/{tid}/knowledge", headers=h)).json()["items"]) == 1
    locked = await client.post(
        f"/api/clinic/{tid}/knowledge", headers=h, json={"title": "Outro", "content": DOC_PAGAMENTO}
    )
    assert locked.status_code == 402 and locked.json()["error"]["code"] == "plan_feature_locked"
    assert (await client.post(f"/api/clinic/{tid}/knowledge/reindex", headers=h)).status_code == 402
    search = (await client.post(f"/api/clinic/{tid}/knowledge/search?q=cartão", headers=h)).json()
    assert search == {"items": [], "locked": True}
    billing = (await client.get(f"/api/clinic/{tid}/billing", headers=h)).json()
    assert billing["usage"]["knowledgeDocuments"] == {"used": 1, "limit": 0}

    # A IA não cita a base: a resposta por regras vira a padrão, sem o trecho.
    body, headers = signed({"messageId": "pf-1", "phone": "5581999990000", "text": "aceitam cartão?", "tenantId": tid})
    res = await client.post("/api/webhooks/whatsapp", content=body, headers=headers)
    assert res.status_code == 200 and "cartão de crédito em até 6" not in res.json()["reply"]

    # Voltou a pagar: a base volta a funcionar sem precisar recriar nada.
    await clean_db.tenant.update(where={"id": tid}, data={"plan": "BASIC"})
    body, headers = signed({"messageId": "pf-2", "phone": "5581999990000", "text": "aceitam cartão?", "tenantId": tid})
    res = await client.post("/api/webhooks/whatsapp", content=body, headers=headers)
    assert "cartão de crédito em até 6" in res.json()["reply"]
    assert (await client.delete(f"/api/clinic/{tid}/knowledge/{doc.json()['id']}", headers=h)).status_code == 204


async def test_free_plan_media_gets_text_fallback_without_calling_provider(
    client, clean_db, monkeypatch: pytest.MonkeyPatch
):
    fake = FakeGemini()
    monkeypatch.setattr(media_service, "client_for", lambda settings: fake)
    reg = await register_user(client)
    tid, h = reg["tenantId"], auth_headers(reg)
    await clean_db.tenant.update(where={"id": tid}, data={"status": "ACTIVE", "plan": "FREE"})
    body, headers = signed(
        {
            "messageId": "pf-aud-1",
            "phone": "5581999990001",
            "text": "",
            "tenantId": tid,
            "mediaKind": "audio",
            "mediaBase64": FAKE_AUDIO,
            "mediaMimeType": "audio/ogg",
        }
    )
    res = await client.post("/api/webhooks/whatsapp", content=body, headers=headers)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["status"] == "processed" and data["degraded"] is True
    assert "só consigo ler mensagens de texto" in data["reply"]
    assert fake.calls == 0  # o provedor não é acionado para um recurso fora do plano
    logs = await clean_db.executionlog.find_many(where={"tenantId": tid})
    assert logs and logs[0].error == "media_not_in_plan"
    inbox = (await client.get(f"/api/clinic/{tid}/notifications", headers=h)).json()
    titles = [n["title"] for n in inbox["items"]]
    assert "Áudio e imagem não incluídos no plano" in titles
    # Mesma clínica no PRO: a mídia passa a ser lida (o fake é chamado).
    await clean_db.tenant.update(where={"id": tid}, data={"plan": "PRO"})
    body, headers = signed(
        {
            "messageId": "pf-aud-2",
            "phone": "5581999990001",
            "text": "",
            "tenantId": tid,
            "mediaKind": "audio",
            "mediaBase64": FAKE_AUDIO,
            "mediaMimeType": "audio/ogg",
        }
    )
    assert (await client.post("/api/webhooks/whatsapp", content=body, headers=headers)).status_code == 200
    assert fake.calls == 1


async def test_basic_plan_document_limit(client, clean_db):
    reg = await register_user(client)
    tid, h = reg["tenantId"], auth_headers(reg)
    await clean_db.tenant.update(where={"id": tid}, data={"status": "ACTIVE", "plan": "BASIC"})
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
    assert over.status_code == 402 and over.json()["error"]["code"] == "knowledge_limit"
    assert over.json()["error"]["details"] == {"limit": 10}
    billing = (await client.get(f"/api/clinic/{tid}/billing", headers=h)).json()
    assert billing["usage"]["knowledgeDocuments"] == {"used": 10, "limit": 10}
