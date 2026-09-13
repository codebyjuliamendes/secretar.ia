"""Push do Google Calendar (events.watch): canal criado/renovado pela leitura, webhook enfileira o pull."""

from datetime import UTC, datetime, timedelta

from app.config import get_settings
from app.integrations import google_calendar
from app.security.crypto import encrypt_secret
from app.services import calendar_sync
from tests.conftest import auth_headers, register_user
from tests.integration.test_google_calendar_pull import MEETING, _drain_jobs, _reset_provider


async def _connected_tenant(client, clean_db):
    reg = await register_user(client)
    tid, h = reg["tenantId"], auth_headers(reg)
    await clean_db.calendarconnection.create(
        data={"tenantId": tid, "refreshTokenEnc": encrypt_secret(get_settings(), "console-refresh")}
    )
    return tid, h


def test_push_availability_rules():
    settings = get_settings()
    assert calendar_sync.push_available(settings)  # test/dev: provider console aceita http://localhost
    assert calendar_sync.notify_address(settings).endswith("/api/integrations/google/notify")
    prod = settings.model_copy(update={"app_env": "production", "public_api_url": "http://api.exemplo"})
    assert not calendar_sync.push_available(prod)
    prod_https = settings.model_copy(update={"app_env": "production", "public_api_url": "https://api.exemplo/"})
    assert calendar_sync.push_available(prod_https)
    assert not calendar_sync.push_available(settings.model_copy(update={"google_push_enabled": False}))


async def test_pull_creates_channel_and_notification_enqueues_pull(client, clean_db):
    provider = _reset_provider()
    provider.channels.clear()
    provider.stopped_channels.clear()
    provider.external_events[MEETING["id"]] = MEETING
    tid, h = await _connected_tenant(client, clean_db)

    result = await calendar_sync.pull_external_events(get_settings(), tenant_id=tid)
    assert result["push"] == "created"
    conn = await clean_db.calendarconnection.find_unique(where={"tenantId": tid})
    assert conn.channelId in provider.channels and conn.channelToken and conn.channelResourceId
    assert provider.channels[conn.channelId]["address"].endswith("/api/integrations/google/notify")
    assert provider.channels[conn.channelId]["token"] == conn.channelToken
    assert conn.channelExpiresAt > datetime.now(UTC) + timedelta(days=6)
    st = (await client.get(f"/api/clinic/{tid}/integrations/google", headers=h)).json()
    assert st["pushActive"] is True

    # Canal ainda válido: a próxima leitura não recria.
    assert (await calendar_sync.pull_external_events(get_settings(), tenant_id=tid))["push"] == "active"

    headers = {"X-Goog-Channel-ID": conn.channelId, "X-Goog-Channel-Token": conn.channelToken}
    # Handshake de criação: nada enfileirado.
    sync = await client.post("/api/integrations/google/notify", headers={**headers, "X-Goog-Resource-State": "sync"})
    assert sync.status_code == 204 and await clean_db.job.count(where={"name": "pull-calendar"}) == 0
    # Mudança real: enfileira uma leitura; a segunda notificação não duplica.
    for _ in range(2):
        res = await client.post(
            "/api/integrations/google/notify", headers={**headers, "X-Goog-Resource-State": "exists"}
        )
        assert res.status_code == 204
    assert await clean_db.job.count(where={"name": "pull-calendar"}) == 1
    # Token errado é recusado; canal desconhecido é ignorado (2xx para o Google não retentar).
    bad = await client.post(
        "/api/integrations/google/notify",
        headers={
            "X-Goog-Channel-ID": conn.channelId,
            "X-Goog-Channel-Token": "errado",
            "X-Goog-Resource-State": "exists",
        },
    )
    assert bad.status_code == 403
    unknown = await client.post(
        "/api/integrations/google/notify",
        headers={"X-Goog-Channel-ID": "nao-existe", "X-Goog-Channel-Token": "x", "X-Goog-Resource-State": "exists"},
    )
    assert unknown.status_code == 204
    assert (await client.post("/api/integrations/google/notify")).status_code == 204

    # A leitura enfileirada roda e espelha o evento.
    assert await _drain_jobs("pull-calendar") == 1
    assert await clean_db.externalbusy.count(where={"tenantId": tid}) == 1


async def test_channel_is_renewed_before_expiring_and_stopped_on_disconnect(client, clean_db):
    provider = _reset_provider()
    provider.channels.clear()
    provider.stopped_channels.clear()
    tid, h = await _connected_tenant(client, clean_db)
    assert (await calendar_sync.pull_external_events(get_settings(), tenant_id=tid))["push"] == "created"
    first = await clean_db.calendarconnection.find_unique(where={"tenantId": tid})

    await clean_db.calendarconnection.update(
        where={"id": first.id}, data={"channelExpiresAt": datetime.now(UTC) + timedelta(hours=1)}
    )
    assert (await calendar_sync.pull_external_events(get_settings(), tenant_id=tid))["push"] == "renewed"
    second = await clean_db.calendarconnection.find_unique(where={"tenantId": tid})
    assert second.channelId != first.channelId and second.channelToken != first.channelToken
    assert first.channelId in provider.stopped_channels and second.channelId in provider.channels
    # O canal antigo não autentica mais.
    stale = await client.post(
        "/api/integrations/google/notify",
        headers={
            "X-Goog-Channel-ID": first.channelId,
            "X-Goog-Channel-Token": first.channelToken,
            "X-Goog-Resource-State": "exists",
        },
    )
    assert stale.status_code == 204 and await clean_db.job.count(where={"name": "pull-calendar"}) == 0

    off = await client.post(f"/api/clinic/{tid}/integrations/google/disconnect", headers=h)
    assert off.status_code == 200 and off.json()["pushActive"] is False
    assert second.channelId in provider.stopped_channels and not provider.channels


async def test_push_disabled_by_setting_keeps_polling_working(client, clean_db, monkeypatch):
    provider = _reset_provider()
    provider.channels.clear()
    tid, _ = await _connected_tenant(client, clean_db)
    settings = get_settings().model_copy(update={"google_push_enabled": False})
    result = await calendar_sync.pull_external_events(settings, tenant_id=tid)
    assert result["status"] == "ok" and result["push"] == "unavailable" and not provider.channels
    assert google_calendar._console.lists >= 1
