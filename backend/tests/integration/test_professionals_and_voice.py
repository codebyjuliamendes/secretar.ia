"""Profissionais (agendas paralelas e "quero com a Paula"), voz e grupo de unidades."""

import base64
import json
from datetime import UTC, datetime

from app.domain.intents import Intent
from app.integrations.gemini import AIProviderError
from app.security.signatures import sign_hub
from app.services import professionals, voice
from app.services.ai import AIDecision, AIService
from tests.conftest import auth_headers, register_user
from tests.integration.test_rbac_and_admin import login

TARGET = datetime(2030, 1, 7, 13, 0, tzinfo=UTC)  # segunda-feira, 10h em São Paulo


def _send(client, tid, text, mid, phone="5581999990901"):
    body = json.dumps({"messageId": mid, "phone": phone, "text": text, "tenantId": tid}).encode()
    return client.post(
        "/api/webhooks/whatsapp",
        content=body,
        headers={"X-Hub-Signature-256": sign_hub(body, "test-whatsapp-secret"), "Content-Type": "application/json"},
    )


async def test_professionals_crud_and_parallel_agendas(client, clean_db):
    reg = await register_user(client)
    tid, h = reg["tenantId"], auth_headers(reg)
    await client.post(f"/api/clinic/{tid}/services", headers=h, json={"name": "Corte", "durationMin": 60})

    paula = (await client.post(f"/api/clinic/{tid}/professionals", headers=h, json={"name": "Paula"})).json()
    rui = (await client.post(f"/api/clinic/{tid}/professionals", headers=h, json={"name": "Rui"})).json()
    assert paula["active"] is True
    dup = await client.post(f"/api/clinic/{tid}/professionals", headers=h, json={"name": "Paula"})
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "professional_exists"

    # Com dois profissionais, o mesmo horário aceita dois atendimentos e recusa o terceiro.
    first = await client.post(
        f"/api/clinic/{tid}/appointments",
        headers=h,
        json={"phone": "5581999990911", "service": "Corte", "date": TARGET.isoformat(), "professionalId": paula["id"]},
    )
    assert first.status_code == 201, first.text
    assert first.json()["professionalName"] == "Paula"
    second = await client.post(
        f"/api/clinic/{tid}/appointments",
        headers=h,
        json={"phone": "5581999990912", "service": "Corte", "date": TARGET.isoformat(), "professionalId": rui["id"]},
    )
    assert second.status_code == 201, second.text
    third = await client.post(
        f"/api/clinic/{tid}/appointments",
        headers=h,
        json={"phone": "5581999990913", "service": "Corte", "date": TARGET.isoformat()},
    )
    assert third.status_code == 409 and third.json()["error"]["code"] == "slot_unavailable"
    # Paula já está ocupada nesse horário, mesmo que a agenda geral ainda tivesse vaga.
    quarta = await client.post(
        f"/api/clinic/{tid}/appointments",
        headers=h,
        json={"phone": "5581999990914", "service": "Corte", "date": TARGET.isoformat(), "professionalId": paula["id"]},
    )
    assert quarta.status_code == 409

    # Desativar e remover; o agendamento continua na agenda sem profissional.
    await client.patch(f"/api/clinic/{tid}/professionals/{rui['id']}", headers=h, json={"active": False})
    items = (await client.get(f"/api/clinic/{tid}/professionals", headers=h, params={"active": True})).json()["items"]
    assert [p["name"] for p in items] == ["Paula"]
    assert (await client.delete(f"/api/clinic/{tid}/professionals/{paula['id']}", headers=h)).status_code == 204
    appts = (await client.get(f"/api/clinic/{tid}/appointments", headers=h)).json()["items"]
    # Remover a Paula não apaga o agendamento dela: só solta o vínculo. O Rui, apenas desativado, continua ligado.
    assert len(appts) == 2 and sorted(str(a["professionalName"]) for a in appts) == ["None", "Rui"]
    missing = await client.post(
        f"/api/clinic/{tid}/appointments",
        headers=h,
        json={"phone": "5581999990915", "service": "Corte", "date": TARGET.isoformat(), "professionalId": "nope"},
    )
    assert missing.status_code == 404


def test_match_professional_ignores_accents_and_partials():
    items = [{"id": "1", "name": "Paula Souza"}, {"id": "2", "name": "Antônio"}]
    assert professionals.match_professional(items, "paula")["id"] == "1"
    assert professionals.match_professional(items, "Antonio")["id"] == "2"
    assert professionals.match_professional(items, "PAULA SOUZA")["id"] == "1"
    assert professionals.match_professional(items, "Carla") is None
    assert professionals.match_professional(items, None) is None
    assert professionals.professionals_text(items) == "Paula Souza, Antônio"


async def test_ai_books_with_the_requested_professional(client, clean_db, monkeypatch):
    reg = await register_user(client)
    tid, h = reg["tenantId"], auth_headers(reg)
    await client.post(f"/api/clinic/{tid}/services", headers=h, json={"name": "Corte", "durationMin": 60})
    paula = (await client.post(f"/api/clinic/{tid}/professionals", headers=h, json={"name": "Paula"})).json()
    await client.post(f"/api/clinic/{tid}/professionals", headers=h, json={"name": "Rui"})

    seen = {}

    async def fake_decide(self, tenant, **kwargs):
        seen.update(kwargs)
        return AIDecision(
            intent=Intent.SCHEDULE,
            reply="Perfeito, vou registrar seu pedido.",
            needs_human=False,
            appointment_service="corte",
            appointment_datetime=TARGET,
            appointment_professional="paula",
            model="fake",
        )

    monkeypatch.setattr(AIService, "decide", fake_decide)
    r = await _send(client, tid, "quero corte com a Paula segunda 10h", "p1")
    assert r.status_code == 200 and r.json()["status"] == "processed"
    assert seen["professionals_text"] == "Paula, Rui"  # o modelo recebe quem atende
    appts = (await client.get(f"/api/clinic/{tid}/appointments", headers=h)).json()["items"]
    assert len(appts) == 1 and appts[0]["professionalName"] == "Paula"
    notes = await clean_db.notification.find_many(where={"tenantId": tid, "type": "APPOINTMENT_REQUESTED"})
    assert "com Paula" in notes[0].body

    # Mesmo horário com a Paula de novo: indisponível, mesmo havendo o Rui livre.
    r2 = await _send(client, tid, "quero corte com a Paula segunda 10h", "p2", phone="5581999990902")
    assert "não está disponível" in r2.json()["reply"]
    assert await clean_db.appointment.count(where={"tenantId": tid}) == 1
    assert paula["name"] == "Paula"


class FakeTTS:
    def __init__(self, pcm: bytes = b"\x00\x01" * 100, mime: str = "audio/L16;rate=24000", fail: bool = False):
        self.pcm, self.mime, self.fail, self.calls = pcm, mime, fail, []

    async def synthesize_speech(self, text, *, voice="Kore"):
        self.calls.append((text, voice))
        if self.fail:
            raise AIProviderError("TTS fora do ar")
        return self.pcm, self.mime


async def test_voice_synthesis_wraps_pcm_and_falls_back(monkeypatch):
    from app.config import get_settings

    settings = get_settings()
    fake = FakeTTS()
    monkeypatch.setattr(voice, "tts_client", lambda s: fake)
    out = await voice.synthesize(settings, "Confirmado para amanhã às 10h.")
    assert out is not None
    audio_b64, mime = out
    raw = base64.b64decode(audio_b64)
    assert mime == "audio/wav" and raw[:4] == b"RIFF" and raw[8:12] == b"WAVE"
    assert fake.calls[0][1] == "Kore"

    assert await voice.synthesize(settings, "   ") is None  # nada a falar
    assert await voice.synthesize(settings, "a" * 1000) is None  # longo demais vira texto
    monkeypatch.setattr(voice, "tts_client", lambda s: FakeTTS(fail=True))
    assert await voice.synthesize(settings, "oi") is None  # falha do provedor cai para texto
    monkeypatch.setattr(voice, "tts_client", lambda s: None)
    assert await voice.synthesize(settings, "oi") is None  # sem chave configurada


async def test_voice_reply_only_for_audio_when_enabled(client, clean_db, monkeypatch):
    """Áudio do cliente + voz ligada + IA respondendo = tarefa de áudio; nos demais casos, texto."""
    from app.integrations.gemini import AIResult
    from app.services import media as media_service

    reg = await register_user(client, plan="PRO")
    tid, h = reg["tenantId"], auth_headers(reg)
    await client.patch(f"/api/clinic/{tid}/settings", headers=h, json={"voiceReplies": True})

    class FakeGemini:
        async def describe_media(self, prompt, data, mime_type, *, max_output_tokens=None):
            return AIResult(text="quanto custa o corte?", input_tokens=10, output_tokens=5, model="fake")

    monkeypatch.setattr(media_service, "client_for", lambda s: FakeGemini())

    async def fake_decide(self, tenant, **kwargs):
        return AIDecision(intent=Intent.INFO, reply="O corte custa R$ 50.", needs_human=False, model="fake")

    monkeypatch.setattr(AIService, "decide", fake_decide)

    audio = base64.b64encode(b"fake-ogg-bytes").decode()
    body = json.dumps(
        {
            "messageId": "v1",
            "phone": "5581999990921",
            "text": "",
            "tenantId": tid,
            "mediaKind": "audio",
            "mediaBase64": audio,
            "mediaMimeType": "audio/ogg",
        }
    ).encode()
    r = await client.post(
        "/api/webhooks/whatsapp",
        content=body,
        headers={"X-Hub-Signature-256": sign_hub(body, "test-whatsapp-secret"), "Content-Type": "application/json"},
    )
    assert r.status_code == 200 and r.json()["status"] == "processed"
    assert await clean_db.job.count(where={"name": "send-whatsapp-audio"}) == 1
    assert await clean_db.job.count(where={"name": "send-whatsapp"}) == 0

    # Mensagem de texto na mesma conta continua em texto.
    await _send(client, tid, "e a barba?", "v2", phone="5581999990921")
    assert await clean_db.job.count(where={"name": "send-whatsapp"}) == 1

    # Com a voz desligada, áudio também responde em texto.
    await client.patch(f"/api/clinic/{tid}/settings", headers=h, json={"voiceReplies": False})
    body = json.dumps(
        {
            "messageId": "v3",
            "phone": "5581999990922",
            "text": "",
            "tenantId": tid,
            "mediaKind": "audio",
            "mediaBase64": audio,
            "mediaMimeType": "audio/ogg",
        }
    ).encode()
    await client.post(
        "/api/webhooks/whatsapp",
        content=body,
        headers={"X-Hub-Signature-256": sign_hub(body, "test-whatsapp-secret"), "Content-Type": "application/json"},
    )
    assert await clean_db.job.count(where={"name": "send-whatsapp-audio"}) == 1
    assert await clean_db.job.count(where={"name": "send-whatsapp"}) == 2


async def test_audio_task_falls_back_to_text_when_provider_has_no_audio(client, clean_db, monkeypatch):
    from app.jobs.tasks import send_whatsapp_audio
    from app.services import voice as voice_service

    reg = await register_user(client)
    tid = reg["tenantId"]
    await clean_db.tenant.update(where={"id": tid}, data={"whatsappInstance": "inst-voz"})
    sent = []

    class Provider:
        async def send_audio(self, instance, phone, audio_base64, mime_type):
            from app.errors import IntegrationUnavailableError

            raise IntegrationUnavailableError("sem áudio", code="whatsapp_audio_unsupported")

        async def send_text(self, instance, phone, text):
            sent.append(text)
            return "id"

    monkeypatch.setattr("app.jobs.tasks.build_whatsapp_provider", lambda s: Provider())
    monkeypatch.setattr(voice_service, "tts_client", lambda s: FakeTTS())
    await send_whatsapp_audio({"tenantId": tid, "phone": "5581999990931", "text": "Confirmado!"})
    assert sent == ["Confirmado!"]


async def test_admin_groups_units_under_a_parent(client, clean_db):
    matriz = await register_user(client, clinic="Rede Matriz")
    unidade = await register_user(client, clinic="Rede Boa Viagem")
    admin_user = await register_user(client, active=False)
    await clean_db.user.update(where={"email": admin_user["email"]}, data={"platformRole": "SUPER_ADMIN"})
    ah = auth_headers(await login(client, admin_user["email"], admin_user["password"]))

    r = await client.patch(
        f"/api/admin/tenants/{unidade['tenantId']}", headers=ah, json={"parentTenantId": matriz["tenantId"]}
    )
    assert r.status_code == 200, r.text
    items = (await client.get("/api/admin/tenants", headers=ah, params={"search": "Boa Viagem"})).json()["items"]
    assert items[0]["groupName"] == "Rede Matriz" and items[0]["parentTenantId"] == matriz["tenantId"]

    itself = await client.patch(
        f"/api/admin/tenants/{unidade['tenantId']}", headers=ah, json={"parentTenantId": unidade["tenantId"]}
    )
    assert itself.status_code == 409 and itself.json()["error"]["code"] == "invalid_parent"
    ghost = await client.patch(
        f"/api/admin/tenants/{unidade['tenantId']}", headers=ah, json={"parentTenantId": "nao-existe"}
    )
    assert ghost.status_code == 409

    me = (await client.get("/api/auth/me", headers=auth_headers(unidade))).json()
    assert me["memberships"][0]["tenant"]["parentTenantId"] == matriz["tenantId"]
    clear = await client.patch(f"/api/admin/tenants/{unidade['tenantId']}", headers=ah, json={"parentTenantId": ""})
    assert clear.status_code == 200
    assert (await clean_db.tenant.find_unique(where={"id": unidade["tenantId"]})).parentTenantId is None
