from tests.conftest import auth_headers, register_user


async def test_appointments_lifecycle_and_validation(client, clean_db):
    reg = await register_user(client)
    tid, h = reg["tenantId"], auth_headers(reg)
    bad = await client.post(
        f"/api/clinic/{tid}/appointments",
        headers=h,
        json={"phone": "12", "service": "Botox", "date": "2030-01-10T14:00:00Z"},
    )
    assert bad.status_code == 422
    created = await client.post(
        f"/api/clinic/{tid}/appointments",
        headers=h,
        json={
            "phone": "5581999990000",
            "patientName": "Ana",
            "service": "Botox",
            "date": "2030-01-10T14:00:00Z",
            "priceCents": 99000,
        },
    )
    assert created.status_code == 201
    appt = created.json()
    assert appt["status"] == "CONFIRMED" and appt["patient"]["name"] == "Ana"

    invalid = await client.post(
        f"/api/clinic/{tid}/appointments/{appt['id']}/status", headers=h, json={"status": "PENDING"}
    )
    assert invalid.status_code == 409 and invalid.json()["error"]["code"] == "invalid_transition"
    done = await client.post(
        f"/api/clinic/{tid}/appointments/{appt['id']}/status", headers=h, json={"status": "COMPLETED"}
    )
    assert done.status_code == 200 and done.json()["status"] == "COMPLETED"

    lst = await client.get(f"/api/clinic/{tid}/appointments?status=COMPLETED&search=ana", headers=h)
    assert lst.json()["total"] == 1
    empty = await client.get(f"/api/clinic/{tid}/appointments?status=PENDING", headers=h)
    assert empty.json()["total"] == 0 and empty.json()["items"] == []

    audit = await client.get(f"/api/clinic/{tid}/audit", headers=h)
    actions = [a["action"] for a in audit.json()["items"]]
    assert "appointment.created" in actions and "appointment.status_changed" in actions
    assert all(a["actor"]["email"] == reg["email"] for a in audit.json()["items"] if a["actor"])


async def test_patients_crud_and_limits(client, clean_db):
    reg = await register_user(client)
    tid, h = reg["tenantId"], auth_headers(reg)
    p = await client.post(f"/api/clinic/{tid}/patients", headers=h, json={"phone": "(81) 98888-0000", "name": "Bia"})
    assert p.status_code == 201 and p.json()["phone"] == "5581988880000"
    dup = await client.post(f"/api/clinic/{tid}/patients", headers=h, json={"phone": "5581988880000"})
    assert dup.status_code == 409
    detail = await client.get(f"/api/clinic/{tid}/patients/{p.json()['id']}", headers=h)
    assert detail.status_code == 200 and detail.json()["appointments"] == [] and detail.json()["conversation"] == []
    upd = await client.patch(f"/api/clinic/{tid}/patients/{p.json()['id']}", headers=h, json={"notes": "VIP"})
    assert upd.json()["notes"] == "VIP"
    lst = await client.get(f"/api/clinic/{tid}/patients?search=bia", headers=h)
    assert lst.json()["total"] == 1 and lst.json()["items"][0]["appointmentCount"] == 0

    # Limite do plano Essencial (1.000 pacientes) é aplicado no backend.
    await clean_db.tenant.update(where={"id": tid}, data={"plan": "BASIC"})
    await clean_db.query_raw(
        """INSERT INTO "Patient" (id, "tenantId", phone, "updatedAt")
           SELECT 'p' || g, $1, '55819' || lpad(g::text, 8, '0'), NOW() FROM generate_series(1, 999) g""",
        tid,
    )
    over = await client.post(f"/api/clinic/{tid}/patients", headers=h, json={"phone": "5581900000001"})
    assert over.status_code == 402 and over.json()["error"]["code"] == "patient_limit"

    assert (await client.delete(f"/api/clinic/{tid}/patients/{p.json()['id']}", headers=h)).status_code == 204
    assert (await client.get(f"/api/clinic/{tid}/patients/{p.json()['id']}", headers=h)).status_code == 404


async def test_settings_update_and_dashboard_reflects_real_data(client, clean_db):
    reg = await register_user(client)
    tid, h = reg["tenantId"], auth_headers(reg)
    upd = await client.patch(
        f"/api/clinic/{tid}/settings",
        headers=h,
        json={
            "prompt": "Você é a secretária da clínica X, cordial e objetiva.",
            "prices": "Botox R$ 990",
            "businessHours": "09h às 18h",
            "timezone": "America/Recife",
        },
    )
    assert upd.status_code == 200 and upd.json()["timezone"] == "America/Recife"
    assert (
        await client.patch(f"/api/clinic/{tid}/settings", headers=h, json={"timezone": "Marte/Base"})
    ).status_code == 400

    await client.post(
        f"/api/clinic/{tid}/appointments",
        headers=h,
        json={
            "phone": "5581999990000",
            "service": "Botox",
            "date": "2030-01-10T14:00:00Z",
            "priceCents": 99000,
        },
    )
    dash = (await client.get(f"/api/clinic/{tid}/dashboard?days=30", headers=h)).json()
    assert dash["kpis"]["patientsTotal"] == 1 and dash["kpis"]["appointmentsCreated"] == 1
    assert dash["kpis"]["appointmentsUpcoming"] == 1 and dash["kpis"]["revenueCompletedCents"] == 0
    assert len(dash["series"]) >= 30 and dash["recentAppointments"][0]["service"] == "Botox"
    assert dash["usage"]["aiMessages"]["limit"] == 4000


async def test_whatsapp_onboarding_console_provider(client, clean_db):
    reg = await register_user(client)
    tid, h = reg["tenantId"], auth_headers(reg)
    st = await client.get(f"/api/clinic/{tid}/whatsapp/status", headers=h)
    assert st.json()["state"] == "not_configured"
    conn = await client.post(f"/api/clinic/{tid}/whatsapp/connect", headers=h)
    assert conn.status_code == 200 and conn.json()["instance"] and conn.json()["qrCode"]
    st2 = await client.get(f"/api/clinic/{tid}/whatsapp/status", headers=h)
    assert st2.json()["connected"] is True
    off = await client.post(f"/api/clinic/{tid}/whatsapp/disconnect", headers=h)
    assert off.json()["connected"] is False
