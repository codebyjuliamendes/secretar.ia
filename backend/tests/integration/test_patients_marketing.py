"""Pacientes com agendamentos futuros, datas sem fuso, campanha de retorno (dedupe, retorno posterior, opt-out)."""

import json
from datetime import UTC, datetime, timedelta

from app.security.signatures import sign_hub
from app.services import calendar_sync, scheduling
from app.services.marketing import run_upsell_campaign
from tests.conftest import auth_headers, register_user


def signed(payload: dict):
    body = json.dumps(payload, ensure_ascii=False).encode()
    return body, {"X-Hub-Signature-256": sign_hub(body, "test-whatsapp-secret"), "Content-Type": "application/json"}


async def test_patient_with_upcoming_appointments_cannot_be_deleted(client, clean_db):
    reg = await register_user(client)
    tid, h = reg["tenantId"], auth_headers(reg)
    appt = await client.post(
        f"/api/clinic/{tid}/appointments",
        headers=h,
        json={"phone": "5581999990010", "patientName": "Carla", "service": "Botox", "date": "2031-05-05T14:00:00Z"},
    )
    assert appt.status_code == 201
    pid = appt.json()["patient"]["id"]
    blocked = await client.delete(f"/api/clinic/{tid}/patients/{pid}", headers=h)
    assert blocked.status_code == 409 and blocked.json()["error"]["code"] == "patient_has_upcoming"
    assert (
        await client.post(
            f"/api/clinic/{tid}/appointments/{appt.json()['id']}/status", headers=h, json={"status": "CANCELED"}
        )
    ).status_code == 200
    assert (await client.delete(f"/api/clinic/{tid}/patients/{pid}", headers=h)).status_code == 204
    # Detalhe conta TODOS os agendamentos, não só os 20 mais recentes.
    detail_count = (await client.get(f"/api/clinic/{tid}/patients", headers=h)).json()["total"]
    assert detail_count == 0


async def test_naive_datetimes_are_rejected_and_conflicts_win_over_past(client, clean_db):
    reg = await register_user(client)
    tid, h = reg["tenantId"], auth_headers(reg)
    naive = await client.post(
        f"/api/clinic/{tid}/appointments",
        headers=h,
        json={"phone": "5581999990011", "service": "Botox", "date": "2031-05-05T14:00:00"},
    )
    assert naive.status_code == 422
    assert (
        await client.get(f"/api/clinic/{tid}/calendar?from=2031-05-04T00:00:00&to=2031-05-11T00:00:00", headers=h)
    ).status_code == 422
    # Lançamento retroativo é permitido (force), mas sobreposição com outro retroativo é apontada antes de "past".
    past = (datetime.now(UTC) - timedelta(days=3)).replace(hour=14, minute=0, second=0, microsecond=0)  # 11h local
    while past.weekday() >= 5:
        past -= timedelta(days=1)
    first = await client.post(
        f"/api/clinic/{tid}/appointments",
        headers=h,
        json={"phone": "5581999990012", "service": "Peeling", "date": past.isoformat(), "force": True},
    )
    assert first.status_code == 201
    tenant = await clean_db.tenant.find_unique(where={"id": tid})
    available, reason = await scheduling.check_availability(tenant, past + timedelta(minutes=30), 60)
    assert available is False and reason == "conflict"
    available, reason = await scheduling.check_availability(tenant, past - timedelta(days=7), 60)
    assert reason == "past"


async def test_upsell_one_invite_per_patient_and_skips_returned_or_opted_out(client, clean_db):
    reg = await register_user(client)
    tid, h = reg["tenantId"], auth_headers(reg)
    await clean_db.tenant.update(
        where={"id": tid}, data={"status": "ACTIVE", "plan": "BASIC", "upsellEnabled": True, "upsellDays": 150}
    )
    now = datetime.now(UTC)
    done_at = now - timedelta(days=152)
    ana = await clean_db.patient.create(data={"tenantId": tid, "phone": "5581988880001", "name": "Ana"})
    bia = await clean_db.patient.create(data={"tenantId": tid, "phone": "5581988880002", "name": "Bia"})
    cris = await clean_db.patient.create(
        data={"tenantId": tid, "phone": "5581988880003", "name": "Cris", "marketingOptOut": True}
    )
    for p, svc, when, status in [
        (ana, "Botox", done_at, "COMPLETED"),
        (ana, "Peeling", done_at + timedelta(days=2), "COMPLETED"),  # Ana: 2 procedimentos na janela → 1 convite
        (bia, "Botox", done_at, "COMPLETED"),
        (bia, "Limpeza", now - timedelta(days=40), "COMPLETED"),  # Bia já voltou depois: não convidar
        (cris, "Botox", done_at, "COMPLETED"),  # Cris pediu para não receber
    ]:
        await clean_db.appointment.create(
            data={
                "tenantId": tid,
                "patientId": p.id,
                "service": svc,
                "date": when,
                "status": status,
                "source": "MANUAL",
            }
        )
    result = await run_upsell_campaign(tenant_id=tid)
    assert result["messagesQueued"] == 1
    jobs = await clean_db.job.find_many(where={"name": "send-whatsapp"})
    assert [j.payload["phone"] for j in jobs] == ["5581988880001"]
    # Rodar de novo não repete.
    assert (await run_upsell_campaign(tenant_id=tid))["messagesQueued"] == 0

    # Opt-out pela conversa: pedido explícito vale na hora e aparece no CRM.
    await clean_db.tenant.update(where={"id": tid}, data={"plan": "PRO"})
    body, headers = signed(
        {
            "messageId": "opt1",
            "phone": "5581988880001",
            "text": "não quero mais receber mensagens de vocês",
            "tenantId": tid,
        }
    )
    res = await client.post("/api/webhooks/whatsapp", content=body, headers=headers)
    assert res.status_code == 200 and "não vai mais receber" in res.json()["reply"]
    patient = (await client.get(f"/api/clinic/{tid}/patients/{ana.id}", headers=h)).json()
    assert patient["marketingOptOut"] is True
    # A equipe pode reverter pelo CRM.
    upd = await client.patch(f"/api/clinic/{tid}/patients/{ana.id}", headers=h, json={"marketingOptOut": False})
    assert upd.status_code == 200 and upd.json()["marketingOptOut"] is False


def test_google_informational_event_types_do_not_block():
    base = {"status": "confirmed", "start": {"date": "2031-01-14"}, "end": {"date": "2031-01-15"}}
    assert calendar_sync.blocks_time({**base, "eventType": "default"})
    assert not calendar_sync.blocks_time({**base, "eventType": "workingLocation"})
    assert not calendar_sync.blocks_time({**base, "eventType": "birthday"})
    assert calendar_sync.blocks_time({**base, "eventType": "outOfOffice"})  # folga/viagem bloqueia
