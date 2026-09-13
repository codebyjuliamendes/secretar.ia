"""Leitura do Google Calendar (Google → Secretar.ia): eventos externos bloqueiam horários da IA."""

from datetime import UTC, datetime

from app.config import get_settings
from app.integrations import google_calendar
from app.jobs.queue import claim_next_job, run_job
from app.security.crypto import encrypt_secret
from app.services import calendar_sync
from tests.conftest import auth_headers, register_user

# Segunda-feira 13/01/2031: 14:00Z–15:00Z = 11:00–12:00 em America/Sao_Paulo (dentro de seg–sex 09–18).
MEETING = {
    "id": "g-reuniao",
    "status": "confirmed",
    "summary": "Reunião com fornecedor",
    "start": {"dateTime": "2031-01-13T14:00:00Z"},
    "end": {"dateTime": "2031-01-13T15:00:00Z"},
}
CONGRESS = {  # dia inteiro na terça 14/01
    "id": "g-congresso",
    "status": "confirmed",
    "summary": "Congresso",
    "start": {"date": "2031-01-14"},
    "end": {"date": "2031-01-15"},
}
IGNORED = [
    {**MEETING, "id": "g-cancelado", "status": "cancelled"},
    {**MEETING, "id": "g-livre", "transparency": "transparent"},
    {**MEETING, "id": "g-recusado", "attendees": [{"email": "dona@x", "self": True, "responseStatus": "declined"}]},
    {**MEETING, "id": "g-nosso", "extendedProperties": {"private": {"secretariaAppointmentId": "appt-1"}}},
    {**MEETING, "id": "g-sem-data", "start": {}, "end": {}},
]


def _reset_provider():
    provider = google_calendar._console
    provider.events.clear()
    provider.external_events.clear()
    provider.revoked.clear()
    provider.sync_token_valid = True
    provider.lists = 0
    return provider


async def _connected_tenant(client, clean_db):
    reg = await register_user(client)
    tid, h = reg["tenantId"], auth_headers(reg)
    await clean_db.calendarconnection.create(
        data={
            "tenantId": tid,
            "refreshTokenEnc": encrypt_secret(get_settings(), "console-refresh"),
            "accountEmail": "agenda@console.local",
        }
    )
    return tid, h


async def _drain_jobs(name: str) -> int:
    ran = 0
    while (job := await claim_next_job()) is not None:
        if job["name"] == name:
            ran += 1
        await run_job(job)
    return ran


def test_event_window_and_blocking_rules():
    s, e, all_day = calendar_sync.event_window(MEETING, "America/Sao_Paulo")
    assert (s, e, all_day) == (datetime(2031, 1, 13, 14, tzinfo=UTC), datetime(2031, 1, 13, 15, tzinfo=UTC), False)
    s, e, all_day = calendar_sync.event_window(CONGRESS, "America/Sao_Paulo")
    assert all_day and s == datetime(2031, 1, 14, 3, tzinfo=UTC) and e == datetime(2031, 1, 15, 3, tzinfo=UTC)
    local = {**MEETING, "start": {"dateTime": "2031-01-13T11:00:00", "timeZone": "America/Sao_Paulo"}}
    assert calendar_sync.event_window(local, "UTC")[0] == datetime(2031, 1, 13, 14, tzinfo=UTC)
    assert calendar_sync.event_window(IGNORED[-1], "UTC") is None
    assert calendar_sync.blocks_time(MEETING)
    assert not any(calendar_sync.blocks_time(x) for x in IGNORED[:3])


async def test_pull_mirrors_external_events_and_blocks_availability(client, clean_db):
    provider = _reset_provider()
    for ev in [MEETING, CONGRESS, *IGNORED]:
        provider.external_events[ev["id"]] = ev
    tid, h = await _connected_tenant(client, clean_db)

    result = await calendar_sync.pull_external_events(get_settings(), tenant_id=tid)
    assert result["status"] == "ok" and result["full"] is True and result["upserted"] == 2
    rows = await clean_db.externalbusy.find_many(where={"tenantId": tid}, order={"startAt": "asc"})
    assert [r.externalId for r in rows] == ["g-reuniao", "g-congresso"]
    assert rows[1].allDay is True and rows[0].summary == "Reunião com fornecedor"
    conn = await clean_db.calendarconnection.find_unique(where={"tenantId": tid})
    assert conn.syncToken and conn.syncToken.startswith("console-sync-") and conn.lastPullAt and conn.lastFullPullAt

    # Disponibilidade da IA: nada sobrepondo 14:00Z–15:00Z na segunda; terça inteira ocupada.
    slots = (
        await client.get(f"/api/clinic/{tid}/availability?from=2031-01-13T00:00:00Z&days=1&duration=60", headers=h)
    ).json()["slots"]
    starts = {s["start"] for s in slots}
    assert "2031-01-13T13:00:00+00:00" in starts and "2031-01-13T15:00:00+00:00" in starts
    assert not any("2031-01-13T14:00" in s or "2031-01-13T14:30" in s or "2031-01-13T13:30" in s for s in starts)
    tuesday = (
        await client.get(f"/api/clinic/{tid}/availability?from=2031-01-14T00:00:00Z&days=1&duration=30", headers=h)
    ).json()["slots"]
    assert tuesday == []

    # Agendamento manual em cima do compromisso do Google: conflito, salvo se a equipe forçar.
    body = {"phone": "5581999990000", "patientName": "Ana", "service": "Botox", "date": "2031-01-13T14:30:00Z"}
    conflict = await client.post(f"/api/clinic/{tid}/appointments", headers=h, json=body)
    assert conflict.status_code == 409 and conflict.json()["error"]["details"] == {"reason": "conflict"}
    forced = await client.post(f"/api/clinic/{tid}/appointments", headers=h, json={**body, "force": True})
    assert forced.status_code == 201

    cal = (
        await client.get(
            f"/api/clinic/{tid}/calendar",
            headers=h,
            params={"from": "2031-01-12T00:00:00Z", "to": "2031-01-19T00:00:00Z"},
        )
    ).json()
    assert [x["summary"] for x in cal["external"]] == ["Reunião com fornecedor", "Congresso"]
    assert cal["external"][1]["allDay"] is True and len(cal["appointments"]) == 1

    st = (await client.get(f"/api/clinic/{tid}/integrations/google", headers=h)).json()
    assert st["externalEvents"] == 2 and st["lastPullAt"] is not None

    # Isolamento: outra clínica não herda os bloqueios.
    other = await register_user(client)
    other_slots = (
        await client.get(
            f"/api/clinic/{other['tenantId']}/availability?from=2031-01-14T00:00:00Z&days=1&duration=30",
            headers=auth_headers(other),
        )
    ).json()["slots"]
    assert other_slots


async def test_incremental_pull_removes_cancelled_and_expired_token_forces_full_resync(client, clean_db):
    provider = _reset_provider()
    provider.external_events.update({MEETING["id"]: MEETING, CONGRESS["id"]: CONGRESS})
    tid, h = await _connected_tenant(client, clean_db)
    assert (await calendar_sync.pull_external_events(get_settings(), tenant_id=tid))["upserted"] == 2

    # Cancelado no Google → sai do espelho na leitura incremental (com syncToken).
    provider.external_events[MEETING["id"]] = {**MEETING, "status": "cancelled"}
    result = await calendar_sync.pull_external_events(get_settings(), tenant_id=tid)
    assert result["full"] is False and result["removed"] == 1
    assert [r.externalId for r in await clean_db.externalbusy.find_many(where={"tenantId": tid})] == ["g-congresso"]

    # Evento sumiu sem aviso e o token expirou (410): leitura completa remove o que não veio.
    provider.external_events.clear()
    provider.sync_token_valid = False
    result = await calendar_sync.pull_external_events(get_settings(), tenant_id=tid)
    assert result["full"] is True and result["removed"] == 1
    assert await clean_db.externalbusy.count(where={"tenantId": tid}) == 0
    conn = await clean_db.calendarconnection.find_unique(where={"tenantId": tid})
    assert conn.syncToken and conn.lastError is None

    # Ressincronizar pela UI reenfileira a leitura completa; desconectar apaga o espelho.
    provider.external_events[CONGRESS["id"]] = CONGRESS
    res = await client.post(f"/api/clinic/{tid}/integrations/google/sync", headers=h)
    assert res.status_code == 200 and res.json()["pullQueued"] is True
    assert await _drain_jobs("pull-calendar") == 1
    assert await clean_db.externalbusy.count(where={"tenantId": tid}) == 1
    assert (await client.post(f"/api/clinic/{tid}/integrations/google/disconnect", headers=h)).status_code == 200
    assert await clean_db.externalbusy.count(where={"tenantId": tid}) == 0


async def test_schedule_pulls_dedupes_and_cron_endpoint(client, clean_db):
    _reset_provider()
    tid, _ = await _connected_tenant(client, clean_db)
    off, _ = await _connected_tenant(client, clean_db)
    await clean_db.calendarconnection.update(where={"tenantId": off}, data={"syncEnabled": False})

    assert await calendar_sync.schedule_pulls() == 1  # só a conexão ativa
    assert await calendar_sync.schedule_pulls() == 0  # já há um job pendente para ela
    assert (await client.post("/api/internal/cron/pull-calendar")).status_code == 401
    cron = await client.post("/api/internal/cron/pull-calendar", headers={"Authorization": "Bearer test-cron-secret"})
    assert cron.status_code == 200 and cron.json() == {"queued": 0}
    assert await _drain_jobs("pull-calendar") == 1
    conn = await clean_db.calendarconnection.find_unique(where={"tenantId": tid})
    assert conn.lastPullAt is not None
    assert await calendar_sync.schedule_pulls() == 1  # concluído: pode enfileirar de novo
    assert (await calendar_sync.pull_external_events(get_settings(), tenant_id=off))["status"] == "skipped"


async def test_connecting_via_callback_schedules_a_pull(client, clean_db):
    provider = _reset_provider()
    provider.external_events[MEETING["id"]] = MEETING
    reg = await register_user(client)
    tid, h = reg["tenantId"], auth_headers(reg)
    from urllib.parse import parse_qs, urlparse

    start = (await client.post(f"/api/clinic/{tid}/integrations/google/connect", headers=h)).json()["url"]
    state = parse_qs(urlparse(start).query)["state"][0]
    ok = await client.get("/api/integrations/google/callback", params={"code": "console", "state": state})
    assert ok.status_code == 303
    done = await client.post(
        f"/api/clinic/{tid}/integrations/google/complete", headers=h, json={"code": "console", "state": state}
    )
    assert done.status_code == 200
    assert await clean_db.job.count(where={"name": "pull-calendar"}) == 1
    await _drain_jobs("pull-calendar")
    assert await clean_db.externalbusy.count(where={"tenantId": tid}) == 1
