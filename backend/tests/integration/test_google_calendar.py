from urllib.parse import parse_qs, urlparse

from app.config import get_settings
from app.integrations import google_calendar
from app.jobs.queue import claim_next_job, run_job
from app.security.crypto import decrypt_secret, encrypt_secret
from app.services import calendar_sync
from tests.conftest import auth_headers, register_user


def test_crypto_roundtrip_and_tamper():
    settings = get_settings()
    token = encrypt_secret(settings, "refresh-123")
    assert token != "refresh-123" and decrypt_secret(settings, token) == "refresh-123"
    try:
        decrypt_secret(settings, token[:-4] + "AAAA")
    except ValueError:
        pass
    else:
        raise AssertionError("token adulterado deveria falhar")


def test_state_token_roundtrip_and_rejects_foreign_tokens():
    settings = get_settings()
    state = calendar_sync.make_state(settings, tenant_id="t1", user_id="u1")
    payload = calendar_sync.parse_state(settings, state)
    assert payload["tid"] == "t1" and payload["sub"] == "u1"
    assert calendar_sync.parse_state(settings, None) is None
    assert calendar_sync.parse_state(settings, state + "x") is None
    from app.security.tokens import create_access_token

    access = create_access_token(user_id="u1", platform_role="USER", secret=settings.jwt_secret, minutes=5)
    assert calendar_sync.parse_state(settings, access) is None  # tipo diferente não serve como state


async def _drain_jobs(name: str) -> int:
    ran = 0
    while (job := await claim_next_job()) is not None:
        if job["name"] == name:
            ran += 1
        await run_job(job)
    return ran


async def test_connect_callback_sync_and_disconnect(client, clean_db):
    provider = google_calendar._console
    provider.events.clear()
    reg = await register_user(client)
    tid, h = reg["tenantId"], auth_headers(reg)

    st = (await client.get(f"/api/clinic/{tid}/integrations/google", headers=h)).json()
    assert st == {
        "connected": False,
        "accountEmail": None,
        "calendarId": None,
        "syncEnabled": False,
        "lastSyncAt": None,
        "lastError": None,
        "lastPullAt": None,
        "available": True,
        "externalEvents": 0,
    }
    assert (await client.post(f"/api/clinic/{tid}/integrations/google/sync", headers=h)).status_code == 409

    # Agendamento criado ANTES da conexão: entra no backfill ao conectar.
    early = await client.post(
        f"/api/clinic/{tid}/appointments",
        headers=h,
        json={"phone": "5581999990000", "patientName": "Ana", "service": "Botox", "date": "2031-01-10T14:00:00Z"},
    )
    assert early.status_code == 201
    assert await clean_db.job.count(where={"name": "sync-calendar"}) == 0  # sem conexão, nada enfileirado

    start = await client.post(f"/api/clinic/{tid}/integrations/google/connect", headers=h)
    assert start.status_code == 200
    url = urlparse(start.json()["url"])
    qs = parse_qs(url.query)
    assert url.path == "/api/integrations/google/callback" and qs["code"] == ["console"]

    # State adulterado/erro do Google → redirect com erro, nada gravado.
    bad = await client.get("/api/integrations/google/callback", params={"code": "console", "state": "lixo"})
    assert bad.status_code == 303 and "google=error" in bad.headers["location"]
    denied = await client.get(
        "/api/integrations/google/callback", params={"error": "access_denied", "state": qs["state"][0]}
    )
    assert denied.status_code == 303 and "reason=denied" in denied.headers["location"]
    assert await clean_db.calendarconnection.count() == 0

    ok = await client.get("/api/integrations/google/callback", params={"code": "console", "state": qs["state"][0]})
    assert ok.status_code == 303 and ok.headers["location"].endswith(f"/app/{tid}/settings?google=connected")
    conn = await clean_db.calendarconnection.find_unique(where={"tenantId": tid})
    assert conn and conn.accountEmail == "agenda@console.local" and conn.refreshTokenEnc != "console-refresh"
    assert decrypt_secret(get_settings(), conn.refreshTokenEnc) == "console-refresh"

    # Backfill enfileirou o agendamento antigo; executar cria o evento.
    assert await _drain_jobs("sync-calendar") == 1
    appt = await clean_db.appointment.find_unique(where={"id": early.json()["id"]})
    assert appt.externalEventId and appt.externalEventId in provider.events
    event = provider.events[appt.externalEventId]
    assert event["summary"] == "Botox – Ana" and event["status"] == "confirmed"
    assert event["start"]["timeZone"] == "America/Sao_Paulo" and event["start"]["dateTime"].startswith(
        "2031-01-10T11:00"
    )

    # Remarcar → mesmo evento atualizado; cancelar → evento removido.
    upd = await client.patch(
        f"/api/clinic/{tid}/appointments/{appt.id}", headers=h, json={"date": "2031-01-13T15:00:00Z"}
    )
    assert upd.status_code == 200
    await _drain_jobs("sync-calendar")
    assert provider.events[appt.externalEventId]["start"]["dateTime"].startswith("2031-01-13T12:00")
    cancel = await client.post(
        f"/api/clinic/{tid}/appointments/{appt.id}/status", headers=h, json={"status": "CANCELED"}
    )
    assert cancel.status_code == 200
    await _drain_jobs("sync-calendar")
    assert appt.externalEventId not in provider.events
    assert (await clean_db.appointment.find_unique(where={"id": appt.id})).externalEventId is None

    st = (await client.get(f"/api/clinic/{tid}/integrations/google", headers=h)).json()
    assert st["connected"] is True and st["syncEnabled"] is True and st["lastSyncAt"]

    off = await client.post(f"/api/clinic/{tid}/integrations/google/disconnect", headers=h)
    assert off.status_code == 200 and off.json()["connected"] is False
    assert await clean_db.calendarconnection.count() == 0 and "console-refresh" in provider.revoked


async def test_invalid_refresh_token_disables_sync_and_notifies(client, clean_db):
    provider = google_calendar._console
    reg = await register_user(client)
    tid, h = reg["tenantId"], auth_headers(reg)
    settings = get_settings()
    await clean_db.calendarconnection.create(
        data={
            "tenantId": tid,
            "refreshTokenEnc": encrypt_secret(settings, "revogado"),
            "accountEmail": "x@console.local",
        }
    )
    provider.revoked.append("revogado")
    created = await client.post(
        f"/api/clinic/{tid}/appointments",
        headers=h,
        json={"phone": "5581999990001", "service": "Peeling", "date": "2031-02-03T13:00:00Z"},
    )
    assert created.status_code == 201
    job = await clean_db.job.find_first(where={"name": "sync-calendar"})
    assert job is not None
    await _drain_jobs("sync-calendar")
    job = await clean_db.job.find_unique(where={"id": job.id})
    assert str(job.status) == "FAILED" and "permanente" in job.error
    conn = await clean_db.calendarconnection.find_unique(where={"tenantId": tid})
    assert conn.syncEnabled is False and "oauth" in conn.lastError
    inbox = (await client.get(f"/api/clinic/{tid}/notifications", headers=h)).json()
    assert any(n["title"] == "Google Calendar desconectado" for n in inbox["items"])
    # Novos agendamentos não geram jobs enquanto a conexão estiver desligada.
    before = await clean_db.job.count(where={"name": "sync-calendar"})
    await client.post(
        f"/api/clinic/{tid}/appointments",
        headers=h,
        json={"phone": "5581999990001", "service": "Peeling", "date": "2031-02-04T13:00:00Z"},
    )
    assert await clean_db.job.count(where={"name": "sync-calendar"}) == before


async def test_ai_created_appointment_is_synced(client, clean_db):
    import json

    from app.security.signatures import sign_hub

    provider = google_calendar._console
    provider.revoked.clear()
    provider.events.clear()
    reg = await register_user(client)
    tid = reg["tenantId"]
    await clean_db.tenant.update(where={"id": tid}, data={"status": "ACTIVE"})
    await clean_db.calendarconnection.create(
        data={"tenantId": tid, "refreshTokenEnc": encrypt_secret(get_settings(), "console-refresh")}
    )
    # Sem IA configurada a criação via conversa não acontece (regras não extraem data); simulamos a
    # cancelamento via WhatsApp de um agendamento já sincronizado.
    p = await clean_db.patient.create(data={"tenantId": tid, "phone": "5581977770009", "name": "Lia"})
    a = await clean_db.appointment.create(
        data={
            "tenantId": tid,
            "patientId": p.id,
            "service": "Limpeza",
            "date": __import__("datetime").datetime(2031, 3, 1, 13, tzinfo=__import__("datetime").UTC),
            "status": "CONFIRMED",
            "externalEventId": "console-evt-lia",
        }
    )
    provider.events["console-evt-lia"] = {"summary": "Limpeza – Lia"}
    payload = {"messageId": "c1", "phone": "5581977770009", "text": "quero cancelar minha consulta", "tenantId": tid}
    body = json.dumps(payload).encode()
    res = await client.post(
        "/api/webhooks/whatsapp",
        content=body,
        headers={"X-Hub-Signature-256": sign_hub(body, "test-whatsapp-secret"), "Content-Type": "application/json"},
    )
    assert res.status_code == 200 and res.json()["intent"] == "CANCELAR"
    await _drain_jobs("sync-calendar")
    assert "console-evt-lia" not in provider.events
    assert (await clean_db.appointment.find_unique(where={"id": a.id})).externalEventId is None
