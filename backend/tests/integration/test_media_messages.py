import base64
import json

import pytest

from app.integrations.gemini import AIProviderError, AIResult
from app.security.signatures import sign_hub
from app.services import media as media_service
from tests.conftest import auth_headers, register_user

FAKE_AUDIO = base64.b64encode(b"OggS" + b"\x00" * 64).decode()


def signed(payload: dict, secret: str = "test-whatsapp-secret"):
    body = json.dumps(payload).encode()
    return body, {"X-Hub-Signature-256": sign_hub(body, secret), "Content-Type": "application/json"}


class FakeGemini:
    def __init__(self, text: str | None = None, fail: bool = False):
        self.text = text
        self.fail = fail
        self.calls: list[tuple[str, str, int]] = []

    async def describe_media(self, prompt, data, mime_type, *, max_output_tokens=None):
        self.calls.append((prompt[:20], mime_type, len(data)))
        if self.fail:
            raise AIProviderError("Gemini respondeu 503")
        return AIResult(text=self.text or "", input_tokens=120, output_tokens=15, model="fake-gemini")


async def test_audio_without_ai_gets_clear_fallback_reply(client, clean_db):
    reg = await register_user(client)
    tid = reg["tenantId"]
    await clean_db.tenant.update(where={"id": tid}, data={"status": "ACTIVE"})
    body, headers = signed(
        {
            "messageId": "aud-1",
            "phone": "5581999990000",
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
    jobs = await clean_db.job.find_many(where={"name": "send-whatsapp"})
    assert len(jobs) == 1 and jobs[0].payload["text"] == data["reply"]
    logs = await clean_db.executionlog.find_many(where={"tenantId": tid})
    assert logs and logs[0].error == "media_unreadable"

    # Sem texto e sem mídia o payload é inválido.
    body2, headers2 = signed({"messageId": "aud-2", "phone": "5581999990000", "text": "", "tenantId": tid})
    assert (await client.post("/api/webhooks/whatsapp", content=body2, headers=headers2)).status_code == 422


async def test_audio_transcription_feeds_the_conversation(client, clean_db, monkeypatch: pytest.MonkeyPatch):
    fake = FakeGemini(text="Oi, quero agendar uma limpeza de pele")
    monkeypatch.setattr(media_service, "client_for", lambda settings: fake)
    reg = await register_user(client)
    tid = reg["tenantId"]
    await clean_db.tenant.update(where={"id": tid}, data={"status": "ACTIVE"})
    body, headers = signed(
        {
            "messageId": "aud-3",
            "phone": "5581999990001",
            "text": "",
            "tenantId": tid,
            "pushName": "Carla",
            "mediaKind": "audio",
            "mediaBase64": FAKE_AUDIO,
            "mediaMimeType": "audio/ogg; codecs=opus",
        }
    )
    res = await client.post("/api/webhooks/whatsapp", content=body, headers=headers)
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "processed" and res.json()["intent"] == "AGENDAR"
    assert fake.calls == [("Transcreva fielmente", "audio/ogg; codecs=opus", 68)]
    msgs = await clean_db.message.find_many(where={"tenantId": tid}, order={"createdAt": "asc"})
    assert msgs[0].content == "[Áudio do paciente, transcrito] Oi, quero agendar uma limpeza de pele"
    log = await clean_db.executionlog.find_first(where={"tenantId": tid})
    assert log.inputTokens == 120 and log.outputTokens == 15  # tokens da transcrição contabilizados
    detail = await client.get(f"/api/clinic/{tid}/patients", headers=auth_headers(reg))
    assert detail.json()["items"][0]["name"] == "Carla"


async def test_image_with_caption_and_provider_failure(client, clean_db, monkeypatch: pytest.MonkeyPatch):
    reg = await register_user(client)
    tid = reg["tenantId"]
    await clean_db.tenant.update(where={"id": tid}, data={"status": "ACTIVE"})
    png = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32).decode()

    fake = FakeGemini(text="Comprovante de pagamento de R$ 250,00 datado de 10/09.")
    monkeypatch.setattr(media_service, "client_for", lambda settings: fake)
    body, headers = signed(
        {
            "messageId": "img-1",
            "phone": "5581999990002",
            "text": "segue o comprovante",
            "tenantId": tid,
            "mediaKind": "image",
            "mediaBase64": png,
            "mediaMimeType": "image/png",
        }
    )
    res = await client.post("/api/webhooks/whatsapp", content=body, headers=headers)
    assert res.status_code == 200 and res.json()["status"] == "processed"
    msg = await clean_db.message.find_first(where={"tenantId": tid, "role": "USER"})
    assert msg.content.startswith("[Imagem enviada pelo paciente. Descrição: Comprovante")
    assert msg.content.endswith("Legenda: segue o comprovante")

    # Provedor falha: resposta honesta pedindo texto, sem erro 500.
    monkeypatch.setattr(media_service, "client_for", lambda settings: FakeGemini(fail=True))
    body, headers = signed({**json.loads(body), "messageId": "img-2"})
    res = await client.post("/api/webhooks/whatsapp", content=body, headers=headers)
    assert res.status_code == 200 and res.json()["degraded"] is True
    assert "sua imagem" in res.json()["reply"]


async def test_evolution_media_without_download_access_replies_gracefully(client, clean_db):
    reg = await register_user(client)
    tid = reg["tenantId"]
    await clean_db.tenant.update(where={"id": tid}, data={"status": "ACTIVE", "whatsappInstance": "inst-media"})
    evo = {
        "event": "messages.upsert",
        "instance": "inst-media",
        "data": {
            "key": {"remoteJid": "5581988880001@s.whatsapp.net", "fromMe": False, "id": "evo-aud-1"},
            "pushName": "Duda",
            "message": {"audioMessage": {"mimetype": "audio/ogg; codecs=opus"}},
        },
    }
    res = await client.post("/api/webhooks/evolution/test-evolution-token", json=evo)
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "processed"  # provider console não baixa mídia → resposta pedindo texto
    job = await clean_db.job.find_first(where={"name": "send-whatsapp"})
    assert "seu áudio" in job.payload["text"]
