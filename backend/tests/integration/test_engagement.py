"""Lembrete de véspera com SIM/NÃO, lista de espera, sinal por Pix e perguntas sem resposta."""

import json
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from app.config import get_settings
from app.security.signatures import sign_hub
from app.services import engagement
from tests.conftest import auth_headers, register_user


def signed(payload: dict, secret: str = "test-whatsapp-secret"):
    body = json.dumps(payload).encode()
    return body, {"X-Hub-Signature-256": sign_hub(body, secret), "Content-Type": "application/json"}


async def _inbound(client, tid, phone, text, mid):
    body, headers = signed({"messageId": mid, "phone": phone, "text": text, "tenantId": tid})
    r = await client.post("/api/webhooks/whatsapp", content=body, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


SP = ZoneInfo("America/Sao_Paulo")


def _tomorrow_10h() -> datetime:
    """Dentro da janela do lembrete (2h a 36h)."""
    d = datetime.now(UTC) + timedelta(hours=26)
    return d.replace(minute=0, second=0, microsecond=0)


def _same_local_day(ref: datetime, hour: int) -> datetime:
    """Outro horário no MESMO dia local de `ref` (a lista de espera agrupa por dia local, não por UTC)."""
    local = ref.astimezone(SP).replace(hour=hour, minute=0, second=0, microsecond=0)
    return local.astimezone(UTC)


async def test_reminder_then_yes_confirms_and_no_cancels_and_offers_waitlist(client, clean_db):
    reg = await register_user(client)
    tid, h = reg["tenantId"], auth_headers(reg)
    tenant = await clean_db.tenant.update(where={"id": tid}, data={"whatsappConnected": True})
    ana = await clean_db.patient.create(data={"tenantId": tid, "phone": "5581999990701", "name": "Ana"})
    bia = await clean_db.patient.create(data={"tenantId": tid, "phone": "5581999990702", "name": "Bia"})
    when = _tomorrow_10h()
    appt = await clean_db.appointment.create(
        data={
            "tenantId": tid,
            "patientId": ana.id,
            "service": "Corte",
            "date": when,
            "endAt": when + timedelta(hours=1),
        }
    )
    # Bia pediu esse dia e não conseguiu: entra na lista de espera.
    await engagement.waitlist_add(tenant, bia, _same_local_day(when, 12), "Corte")
    await engagement.waitlist_add(tenant, bia, _same_local_day(when, 15), "Corte")  # mesmo dia local: não duplica
    assert await clean_db.waitlistentry.count(where={"tenantId": tid}) == 1

    assert await engagement.send_reminders() == 1
    assert await engagement.send_reminders() == 0  # nunca repete
    jobs = await clean_db.job.find_many(where={"name": "send-whatsapp"})
    assert (
        len(jobs) == 1 and "Responda SIM para confirmar" in jobs[0].payload["text"] and "Ana" in jobs[0].payload["text"]
    )
    assert (await clean_db.appointment.find_unique(where={"id": appt.id})).reminderSentAt is not None

    # "sim" confirma sem IA
    res = await _inbound(client, tid, "5581999990701", "Sim", "r1")
    assert res["intent"] == "CONFIRMAR" and res["reply"].startswith("Confirmado")
    assert str((await clean_db.appointment.find_unique(where={"id": appt.id})).status) == "CONFIRMED"

    # "não" cancela, oferece alternativas e avisa a Bia (lista de espera)
    res = await _inbound(client, tid, "5581999990701", "não", "r2")
    assert res["intent"] == "CANCELAR" and res["reply"].startswith("Cancelei Corte")
    assert str((await clean_db.appointment.find_unique(where={"id": appt.id})).status) == "CANCELED"
    jobs = await clean_db.job.find_many(where={"name": "send-whatsapp"}, order={"createdAt": "asc"})
    offered = [j for j in jobs if j.payload["phone"] == "5581999990702"]
    assert (
        len(offered) == 1 and "Abriu um horário" in offered[0].payload["text"] and "Bia" in offered[0].payload["text"]
    )
    assert (await clean_db.waitlistentry.find_first(where={"tenantId": tid})).notifiedAt is not None
    notes = await clean_db.notification.find_many(where={"tenantId": tid, "type": "APPOINTMENT_CANCELED"})
    assert any(n.title.startswith("Cancelou pelo lembrete") for n in notes)

    # Sem lembrete pendente, "sim" volta a ser conversa normal (regras/IA).
    res = await _inbound(client, tid, "5581999990701", "sim", "r3")
    assert res["intent"] not in ("CONFIRMAR", "CANCELAR")

    # Cliente pode desligar o lembrete.
    await client.patch(f"/api/clinic/{tid}/settings", headers=h, json={"reminderEnabled": False})
    await clean_db.appointment.create(
        data={
            "tenantId": tid,
            "patientId": bia.id,
            "service": "Corte",
            "date": when,
            "endAt": when + timedelta(hours=1),
        }
    )
    assert await engagement.send_reminders() == 0


async def test_team_cancel_offers_freed_slot_to_waitlist(client, clean_db):
    reg = await register_user(client)
    tid, h = reg["tenantId"], auth_headers(reg)
    tenant = await clean_db.tenant.find_unique(where={"id": tid})
    ana = await clean_db.patient.create(data={"tenantId": tid, "phone": "5581999990711", "name": "Ana"})
    caio = await clean_db.patient.create(data={"tenantId": tid, "phone": "5581999990712", "name": "Caio"})
    when = _tomorrow_10h()
    appt = await clean_db.appointment.create(
        data={
            "tenantId": tid,
            "patientId": ana.id,
            "service": "Escova",
            "date": when,
            "endAt": when + timedelta(hours=1),
        }
    )
    await engagement.waitlist_add(tenant, caio, when, None)
    r = await client.post(f"/api/clinic/{tid}/appointments/{appt.id}/status", headers=h, json={"status": "CANCELED"})
    assert r.status_code == 200
    jobs = await clean_db.job.find_many(where={"name": "send-whatsapp"})
    assert len(jobs) == 1 and jobs[0].payload["phone"] == "5581999990712" and "Escova" in jobs[0].payload["text"]


async def test_deposit_settings_and_text(client, clean_db):
    reg = await register_user(client)
    tid, h = reg["tenantId"], auth_headers(reg)
    bad = await client.patch(
        f"/api/clinic/{tid}/settings", headers=h, json={"depositEnabled": True, "depositCents": 5000}
    )
    assert bad.status_code == 409 and bad.json()["error"]["code"] == "pix_key_required"
    ok = await client.patch(
        f"/api/clinic/{tid}/settings",
        headers=h,
        json={"depositEnabled": True, "depositCents": 5000, "pixKey": "11999998888", "slug": "barba-fina-teste"},
    )
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert (
        body["depositEnabled"]
        and body["pixKey"] == "11999998888"
        and body["bookingUrl"].endswith("/agendar/barba-fina-teste")
    )
    assert body["referralCode"] is None or len(body["referralCode"]) == 6
    tenant = await clean_db.tenant.find_unique(where={"id": tid})
    text = engagement.deposit_text(tenant)
    assert text and "R$ 50,00" in text and "11999998888" in text
    # slug repetido em outra conta
    other = await register_user(client)
    dup = await client.patch(
        f"/api/clinic/{other['tenantId']}/settings", headers=auth_headers(other), json={"slug": "barba-fina-teste"}
    )
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "slug_taken"
    bad_slug = await client.patch(f"/api/clinic/{tid}/settings", headers=h, json={"slug": "Barba Fina"})
    assert bad_slug.status_code == 422


async def test_unanswered_questions_are_recorded_grouped_resolved_and_digested(client, clean_db, monkeypatch):
    reg = await register_user(client)
    tid, h = reg["tenantId"], auth_headers(reg)
    settings = get_settings()
    monkeypatch.setattr(type(settings), "alerts_to", property(lambda self: "julia@example.com"))
    # Sem IA configurada, uma pergunta fora de preço/horário cai na resposta "não sei": fica registrada.
    for i, phone in enumerate(["5581999990721", "5581999990722", "5581999990723"]):
        res = await _inbound(client, tid, phone, "Vocês têm estacionamento no prédio?", f"q{i}")
        assert "avisei nossa equipe" in res["reply"]
    await _inbound(client, tid, "5581999990721", "Vocês têm estacionamento no prédio?", "q9")
    items = (await client.get(f"/api/clinic/{tid}/questions", headers=h)).json()["items"]
    assert len(items) == 1 and items[0]["people"] == 3 and items[0]["count"] == 4 and len(items[0]["ids"]) == 4
    assert "estacionamento" in items[0]["question"]

    # Resumo semanal: aviso no painel + e-mail aos responsáveis; não repete na mesma semana.
    assert await engagement.questions_digest(settings) == 1
    assert await engagement.questions_digest(settings) == 0
    notes = await clean_db.notification.find_many(where={"tenantId": tid, "type": "SYSTEM"})
    assert any("não soube responder" in n.title for n in notes)
    mails = [
        j for j in await clean_db.job.find_many(where={"name": "send-email"}) if "não soube" in j.payload["subject"]
    ]
    assert len(mails) == 1 and mails[0].payload["to"] == reg["email"]

    r = await client.post(f"/api/clinic/{tid}/questions/resolve", headers=h, json={"ids": items[0]["ids"]})
    assert r.status_code == 200 and r.json()["resolved"] == 4
    assert (await client.get(f"/api/clinic/{tid}/questions", headers=h)).json()["items"] == []
