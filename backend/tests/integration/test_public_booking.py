"""Página pública de agendamento, indicação (indique e ganhe) e saúde da carteira no admin."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from tests.conftest import auth_headers, register_user
from tests.integration.test_rbac_and_admin import login


def _next_weekday_10h(tz: str = "America/Sao_Paulo") -> datetime:
    """Próximo dia útil às 10h locais (dentro das janelas padrão seg–sex 09–18)."""
    local = datetime.now(ZoneInfo(tz)).replace(hour=10, minute=0, second=0, microsecond=0) + timedelta(days=1)
    while local.weekday() >= 5:
        local += timedelta(days=1)
    return local.astimezone(UTC)


async def test_public_booking_flow_creates_pending_web_appointment(client, clean_db):
    reg = await register_user(client, clinic="Studio Luz")
    tid, h = reg["tenantId"], auth_headers(reg)
    settings = (await client.get(f"/api/clinic/{tid}/settings", headers=h)).json()
    assert settings["slug"] and settings["slug"].startswith("studio-luz-") and settings["bookingUrl"]
    slug = settings["slug"]
    await client.post(
        f"/api/clinic/{tid}/services", headers=h, json={"name": "Escova", "durationMin": 60, "priceCents": 6000}
    )
    await clean_db.tenant.update(where={"id": tid}, data={"whatsappConnected": True})

    info = await client.get(f"/api/public/booking/{slug}")
    assert info.status_code == 200, info.text
    body = info.json()
    assert body["name"] == "Studio Luz" and body["services"][0]["name"] == "Escova" and body["professionals"] == []
    service_id = body["services"][0]["id"]

    slots = await client.get(f"/api/public/booking/{slug}/slots", params={"serviceId": service_id, "days": 7})
    assert slots.status_code == 200 and slots.json()["durationMin"] == 60 and slots.json()["days"]
    start = _next_weekday_10h()
    all_starts = {s["start"] for d in slots.json()["days"] for s in d["slots"]}
    assert start.isoformat() in all_starts

    created = await client.post(
        f"/api/public/booking/{slug}",
        json={"name": "Duda", "phone": "(81) 99999-0801", "start": start.isoformat(), "serviceId": service_id},
    )
    assert created.status_code == 201, created.text
    done = created.json()
    assert done["service"] == "Escova" and done["whatsappConfirmation"] is True
    appts = (await client.get(f"/api/clinic/{tid}/appointments", headers=h)).json()["items"]
    assert len(appts) == 1 and appts[0]["status"] == "PENDING" and appts[0]["source"] == "WEB"
    assert appts[0]["patient"]["name"] == "Duda" and appts[0]["patient"]["phone"] == "5581999990801"
    jobs = await clean_db.job.find_many(where={"name": "send-whatsapp"})
    assert len(jobs) == 1 and "Recebemos seu pedido" in jobs[0].payload["text"]
    notes = await clean_db.notification.find_many(where={"tenantId": tid, "type": "APPOINTMENT_REQUESTED"})
    assert notes and "página de agendamento" in notes[0].title

    # Mesmo horário de novo: ocupado. Slug desligado: 404. Conta pendente: 404.
    again = await client.post(
        f"/api/public/booking/{slug}",
        json={"name": "Lia", "phone": "(81) 99999-0802", "start": start.isoformat(), "serviceId": service_id},
    )
    assert again.status_code == 409 and again.json()["error"]["code"] == "slot_conflict"
    await client.patch(f"/api/clinic/{tid}/settings", headers=h, json={"publicBooking": False})
    assert (await client.get(f"/api/public/booking/{slug}")).status_code == 404
    await client.patch(f"/api/clinic/{tid}/settings", headers=h, json={"publicBooking": True})
    await clean_db.tenant.update(where={"id": tid}, data={"status": "PENDING"})
    assert (await client.get(f"/api/public/booking/{slug}")).status_code == 404
    assert (await client.get("/api/public/booking/nao-existe")).status_code == 404


async def test_referral_code_links_accounts_and_shows_in_admin(client, clean_db):
    ref = await register_user(client, clinic="Quem Indica")
    tid, h = ref["tenantId"], auth_headers(ref)
    code = (await client.get(f"/api/clinic/{tid}/settings", headers=h)).json()["referralCode"]
    assert code and len(code) == 6

    bad = await client.post(
        "/api/auth/register",
        json={
            "name": "Novo",
            "email": "novo-ref-bad@example.com",
            "password": "Senha1234",
            "clinicName": "Indicado",
            "whatsapp": "(81) 98888-0001",
            "referralCode": "ZZZZZZ",
        },
    )
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "invalid_referral"
    ok = await client.post(
        "/api/auth/register",
        json={
            "name": "Novo",
            "email": "novo-ref@example.com",
            "password": "Senha1234",
            "clinicName": "Indicado",
            "whatsapp": "(81) 98888-0002",
            "referralCode": code.lower(),  # aceita minúsculas
        },
    )
    assert ok.status_code == 201, ok.text
    new_tid = ok.json()["user"]["memberships"][0]["tenantId"]
    assert (await clean_db.tenant.find_unique(where={"id": new_tid})).referredById == tid

    admin_user = await register_user(client, active=False)
    await clean_db.user.update(where={"email": admin_user["email"]}, data={"platformRole": "SUPER_ADMIN"})
    ah = auth_headers(await login(client, admin_user["email"], admin_user["password"]))
    items = (await client.get("/api/admin/tenants", headers=ah, params={"search": "Indicado"})).json()["items"]
    assert items[0]["referredByName"] == "Quem Indica" and items[0]["referralsCount"] == 0
    items = (await client.get("/api/admin/tenants", headers=ah, params={"search": "Quem Indica"})).json()["items"]
    assert items[0]["referralsCount"] == 1 and items[0]["referralCode"] == code


async def test_admin_health_lists_who_to_call(client, clean_db):
    old = datetime.now(UTC) - timedelta(days=10)
    a = await register_user(client, clinic="Sem Zap")  # ativa, sem WhatsApp, 10 dias
    await clean_db.tenant.update(where={"id": a["tenantId"]}, data={"createdAt": old})
    b = await register_user(client, clinic="Calada")  # ativa, conectada, sem mensagens em 7 dias
    await clean_db.tenant.update(where={"id": b["tenantId"]}, data={"createdAt": old, "whatsappConnected": True})
    c = await register_user(client, clinic="No Limite", plan="BASIC")
    from app.services.usage import AI_MESSAGES, current_period

    await clean_db.usagecounter.create(
        data={"tenantId": c["tenantId"], "period": current_period(), "metric": AI_MESSAGES, "count": 1300}
    )
    d = await register_user(client, clinic="Vencendo")
    await clean_db.tenant.update(
        where={"id": d["tenantId"]}, data={"paidUntil": datetime.now(UTC) + timedelta(days=2), "paymentMethod": "PIX"}
    )
    e = await register_user(client, clinic="Pendente", active=False)

    admin_user = await register_user(client, active=False)
    await clean_db.user.update(where={"email": admin_user["email"]}, data={"platformRole": "SUPER_ADMIN"})
    ah = auth_headers(await login(client, admin_user["email"], admin_user["password"]))
    r = await client.get("/api/admin/health", headers=ah)
    assert r.status_code == 200, r.text
    health = r.json()
    names = {k: [i["name"] for i in v] for k, v in health.items()}
    assert "Sem Zap" in names["noWhatsapp"] and "Calada" in names["silent"]
    assert "No Limite" in names["nearLimit"] and "Vencendo" in names["expiring"] and "Pendente" in names["pending"]
    limite = next(i for i in health["nearLimit"] if i["name"] == "No Limite")
    assert limite["used"] == 1300 and limite["limit"] == 1500 and limite["pct"] == 87
    assert e["tenantId"] not in {i["id"] for i in health["noWhatsapp"]}
