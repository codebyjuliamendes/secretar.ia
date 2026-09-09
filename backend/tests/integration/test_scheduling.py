from datetime import UTC, datetime, timedelta

from app.domain.intents import Intent
from app.services.ai import AIDecision, AIService
from tests.conftest import auth_headers, register_user

# 2030-01-07 é segunda-feira. Tenant novo recebe seg-sex 09:00-18:00 (America/Sao_Paulo = UTC-3).
MON_10H_LOCAL = "2030-01-07T13:00:00Z"  # 10:00 local
MON_10H30_LOCAL = "2030-01-07T13:30:00Z"
SAT_10H_LOCAL = "2030-01-12T13:00:00Z"


async def test_default_rules_services_and_calendar(client, clean_db):
    reg = await register_user(client)
    tid, h = reg["tenantId"], auth_headers(reg)
    rules = (await client.get(f"/api/clinic/{tid}/availability/rules", headers=h)).json()
    assert len(rules["rules"]) == 5 and rules["rules"][0] == {"weekday": 0, "start": "09:00", "end": "18:00"}

    svc = await client.post(
        f"/api/clinic/{tid}/services",
        headers=h,
        json={"name": "Toxina botulínica", "durationMin": 45, "priceCents": 99000},
    )
    assert svc.status_code == 201
    dup = await client.post(f"/api/clinic/{tid}/services", headers=h, json={"name": "toxina botulínica"})
    assert dup.status_code in (201, 409)  # unicidade é case-sensitive no banco; ambos aceitáveis
    settings = (await client.get(f"/api/clinic/{tid}/settings", headers=h)).json()
    assert "Toxina botulínica (45 min, R$ 990,00)" in settings["prices"]

    avail = (
        await client.get(f"/api/clinic/{tid}/availability?from=2030-01-07T00:00:00Z&days=1&duration=45", headers=h)
    ).json()
    starts = [s["start"] for s in avail["slots"]]
    assert MON_10H_LOCAL.replace("Z", "+00:00") in starts and len(starts) > 10

    created = await client.post(
        f"/api/clinic/{tid}/appointments",
        headers=h,
        json={"phone": "5581999990000", "service": "Do catálogo", "serviceId": svc.json()["id"], "date": MON_10H_LOCAL},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["service"] == "Toxina botulínica" and body["durationMin"] == 45 and body["priceCents"] == 99000

    conflict = await client.post(
        f"/api/clinic/{tid}/appointments",
        headers=h,
        json={"phone": "5581999990001", "service": "Peeling", "date": MON_10H30_LOCAL},
    )
    assert conflict.status_code == 409 and conflict.json()["error"]["code"] == "slot_unavailable"
    assert conflict.json()["error"]["details"]["reason"] == "conflict"
    outside = await client.post(
        f"/api/clinic/{tid}/appointments",
        headers=h,
        json={"phone": "5581999990001", "service": "Peeling", "date": SAT_10H_LOCAL},
    )
    assert outside.status_code == 409 and outside.json()["error"]["details"]["reason"] == "outside_hours"
    forced = await client.post(
        f"/api/clinic/{tid}/appointments",
        headers=h,
        json={"phone": "5581999990001", "service": "Encaixe", "date": MON_10H30_LOCAL, "force": True},
    )
    assert forced.status_code == 201

    cal = (
        await client.get(f"/api/clinic/{tid}/calendar?from=2030-01-06T00:00:00Z&to=2030-01-13T00:00:00Z", headers=h)
    ).json()
    assert len(cal["appointments"]) == 2 and cal["appointments"][0]["end"].startswith("2030-01-07T13:45")

    avail2 = (
        await client.get(f"/api/clinic/{tid}/availability?from=2030-01-07T00:00:00Z&days=1&duration=30", headers=h)
    ).json()
    assert all(not s["start"].startswith("2030-01-07T13:") for s in avail2["slots"])  # 10:00-11:00 local ocupado

    bad_range = await client.get(
        f"/api/clinic/{tid}/calendar?from=2030-01-06T00:00:00Z&to=2030-06-01T00:00:00Z", headers=h
    )
    assert bad_range.status_code == 400


async def test_rules_update_validation_and_rbac(client, clean_db):
    reg = await register_user(client)
    tid, h = reg["tenantId"], auth_headers(reg)
    bad = await client.put(
        f"/api/clinic/{tid}/availability/rules",
        headers=h,
        json={"rules": [{"weekday": 0, "start": "10:00", "end": "09:00"}]},
    )
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "invalid_window"
    overlap = await client.put(
        f"/api/clinic/{tid}/availability/rules",
        headers=h,
        json={
            "rules": [
                {"weekday": 2, "start": "09:00", "end": "12:00"},
                {"weekday": 2, "start": "11:00", "end": "13:00"},
            ]
        },
    )
    assert overlap.status_code == 400 and overlap.json()["error"]["code"] == "overlapping_windows"
    ok = await client.put(
        f"/api/clinic/{tid}/availability/rules",
        headers=h,
        json={"rules": [{"weekday": 5, "start": "08:00", "end": "12:00"}], "slotMinutes": 15},
    )
    assert ok.status_code == 200 and ok.json()["slotMinutes"] == 15 and len(ok.json()["rules"]) == 1
    settings = (await client.get(f"/api/clinic/{tid}/settings", headers=h)).json()
    assert settings["businessHours"] == "sábado 08:00-12:00" and settings["slotMinutes"] == 15
    # segunda deixou de ser dia de atendimento
    outside = await client.post(
        f"/api/clinic/{tid}/appointments",
        headers=h,
        json={"phone": "5581999990001", "service": "Peeling", "date": MON_10H_LOCAL},
    )
    assert outside.status_code == 409

    other = await register_user(client)
    assert (await client.get(f"/api/clinic/{tid}/availability/rules", headers=auth_headers(other))).status_code == 404
    assert (await client.get(f"/api/clinic/{tid}/services", headers=auth_headers(other))).status_code == 404


async def test_ai_scheduling_respects_availability(client, clean_db, monkeypatch):
    """Simula a decisão do modelo: horário livre cria PENDENTE; ocupado responde com alternativas."""
    import json

    from app.security.signatures import sign_hub

    reg = await register_user(client)
    tid, h = reg["tenantId"], auth_headers(reg)
    await clean_db.tenant.update(where={"id": tid}, data={"status": "ACTIVE"})
    await client.post(
        f"/api/clinic/{tid}/services", headers=h, json={"name": "Peeling", "durationMin": 30, "priceCents": 25000}
    )
    target = datetime(2030, 1, 7, 13, 0, tzinfo=UTC)

    async def fake_decide(self, tenant, **kwargs):
        return AIDecision(
            intent=Intent.SCHEDULE,
            reply="Perfeito, vou registrar seu pedido.",
            needs_human=False,
            appointment_service="peeling",
            appointment_datetime=target,
            model="fake",
        )

    monkeypatch.setattr(AIService, "decide", fake_decide)

    def send(msg_id, phone):
        body = json.dumps(
            {"messageId": msg_id, "phone": phone, "text": "quero marcar peeling segunda 10h", "tenantId": tid}
        ).encode()
        return client.post(
            "/api/webhooks/whatsapp",
            content=body,
            headers={"X-Hub-Signature-256": sign_hub(body, "test-whatsapp-secret"), "Content-Type": "application/json"},
        )

    r1 = await send("s1", "5581999990010")
    assert r1.status_code == 200 and r1.json()["reply"] == "Perfeito, vou registrar seu pedido."
    appts = (await client.get(f"/api/clinic/{tid}/appointments", headers=h)).json()["items"]
    assert len(appts) == 1 and appts[0]["status"] == "PENDING" and appts[0]["service"] == "Peeling"
    assert appts[0]["durationMin"] == 30 and appts[0]["priceCents"] == 25000 and appts[0]["source"] == "AI"

    r2 = await send("s2", "5581999990011")  # mesmo horário, outro paciente
    assert "não está disponível" in r2.json()["reply"] and "Posso oferecer" in r2.json()["reply"]
    appts = (await client.get(f"/api/clinic/{tid}/appointments", headers=h)).json()["items"]
    assert len(appts) == 1  # nada criado


async def test_reschedule_checks_conflicts(client, clean_db):
    reg = await register_user(client)
    tid, h = reg["tenantId"], auth_headers(reg)
    ra = await client.post(
        f"/api/clinic/{tid}/appointments",
        headers=h,
        json={"phone": "5581999990000", "service": "Serviço A", "date": MON_10H_LOCAL, "durationMin": 60},
    )
    assert ra.status_code == 201, ra.text
    a = ra.json()
    rb = await client.post(
        f"/api/clinic/{tid}/appointments",
        headers=h,
        json={"phone": "5581999990001", "service": "Serviço B", "date": "2030-01-07T15:00:00Z", "durationMin": 60},
    )
    assert rb.status_code == 201, rb.text
    b = rb.json()
    clash = await client.patch(f"/api/clinic/{tid}/appointments/{b['id']}", headers=h, json={"date": MON_10H30_LOCAL})
    assert clash.status_code == 409
    moved = await client.patch(
        f"/api/clinic/{tid}/appointments/{b['id']}", headers=h, json={"date": "2030-01-07T16:00:00Z"}
    )
    assert moved.status_code == 200 and moved.json()["end"].startswith("2030-01-07T17:00")
    same = await client.patch(f"/api/clinic/{tid}/appointments/{a['id']}", headers=h, json={"durationMin": 90})
    assert same.status_code == 200  # estende sem colidir consigo mesmo
    assert (datetime.fromisoformat(same.json()["end"]) - datetime.fromisoformat(same.json()["date"])) == timedelta(
        minutes=90
    )
