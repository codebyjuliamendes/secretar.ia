"""Operação pela Júlia: boas-vindas, cobrança fora do Stripe (pago até) e relatório mensal."""

from datetime import UTC, datetime, timedelta

from app.config import get_settings
from app.services import manual_billing, reports
from tests.conftest import auth_headers, register_user
from tests.integration.test_rbac_and_admin import login


async def _admin(client, clean_db):
    admin_user = await register_user(client, active=False)
    await clean_db.user.update(where={"email": admin_user["email"]}, data={"platformRole": "SUPER_ADMIN"})
    return auth_headers(await login(client, admin_user["email"], admin_user["password"]))


async def test_welcome_email_goes_to_owners_and_marks_the_checklist(client, clean_db):
    reg = await register_user(client, clinic="Barba Fina", active=False)
    tid = reg["tenantId"]
    ah = await _admin(client, clean_db)
    await client.patch(f"/api/admin/tenants/{tid}", headers=ah, json={"niche": "barbearia", "plan": "BASIC"})

    listed = (await client.get("/api/admin/tenants", headers=ah, params={"search": "Barba Fina"})).json()["items"][0]
    assert listed["checklist"] == {"plan": True, "whatsapp": False, "services": False, "welcome": False}

    r = await client.post(f"/api/admin/tenants/{tid}/welcome", headers=ah)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["emails"] == [reg["email"]] and body["whatsappLink"].startswith("https://wa.me/")
    assert "Importar de foto ou PDF" in body["text"] and "clientes" in body["text"]
    mails = [
        j for j in await clean_db.job.find_many(where={"name": "send-email"}) if "Bem-vindo" in j.payload["subject"]
    ]
    assert len(mails) == 1 and mails[0].payload["to"] == reg["email"] and "Barba Fina" in mails[0].payload["subject"]

    listed = (await client.get("/api/admin/tenants", headers=ah, params={"search": "Barba Fina"})).json()["items"][0]
    assert listed["checklist"]["welcome"] is True and listed["welcomeSentAt"]


async def test_manual_payment_activates_and_overdue_sweep_pauses(client, clean_db):
    reg = await register_user(client, clinic="Pix Ltda", active=False)
    tid, h = reg["tenantId"], auth_headers(reg)
    ah = await _admin(client, clean_db)
    settings = get_settings()

    # Registrar um Pix pago até daqui a 30 dias ativa a conta pendente.
    until = (datetime.now(UTC) + timedelta(days=30)).isoformat()
    r = await client.patch(
        f"/api/admin/tenants/{tid}", headers=ah, json={"paidUntil": until, "paymentMethod": "PIX", "billingNote": "750"}
    )
    assert r.status_code == 200 and r.json()["status"] == "ACTIVE"
    billing = (await client.get(f"/api/clinic/{tid}/billing", headers=h)).json()
    assert billing["paidUntil"] and billing["paymentMethod"] == "PIX"
    listed = (await client.get("/api/admin/tenants", headers=ah, params={"search": "Pix Ltda"})).json()["items"][0]
    assert listed["paymentMethod"] == "PIX" and listed["billingNote"] == "750" and listed["hasSubscription"] is False

    # Vencida há 1 dia: ainda na carência. Há 5 dias: pausa, avisa o cliente e a equipe.
    assert await manual_billing.sweep_overdue(settings, datetime.now(UTC)) == 0
    past = datetime.now(UTC) - timedelta(days=5)
    await clean_db.tenant.update(where={"id": tid}, data={"paidUntil": past})
    assert await manual_billing.sweep_overdue(settings) == 1
    assert await manual_billing.sweep_overdue(settings) == 0  # idempotente
    tenant = await clean_db.tenant.find_unique(where={"id": tid})
    assert str(tenant.status) == "PAST_DUE"
    notes = await clean_db.notification.find_many(where={"tenantId": tid, "type": "BILLING"})
    assert any(n.title == "Pagamento pendente" for n in notes)

    # Novo pagamento reativa; limpar a data (null) também é aceito.
    r = await client.patch(f"/api/admin/tenants/{tid}", headers=ah, json={"paidUntil": until})
    assert r.json()["status"] == "ACTIVE"
    r = await client.patch(f"/api/admin/tenants/{tid}", headers=ah, json={"paidUntil": None})
    assert r.status_code == 200 and (await clean_db.tenant.find_unique(where={"id": tid})).paidUntil is None
    # Assinatura no Stripe nunca é varrida por aqui.
    await clean_db.tenant.update(where={"id": tid}, data={"paidUntil": past, "subscriptionId": "sub_x"})
    assert await manual_billing.sweep_overdue(settings) == 0


async def test_monthly_report_counts_the_previous_month_and_sends_once(client, clean_db):
    reg = await register_user(client, clinic="Relatório SA")
    tid, h = reg["tenantId"], auth_headers(reg)
    ah = await _admin(client, clean_db)
    settings_start = reports.period_bounds(reports.previous_period())[0]
    await clean_db.tenant.update(
        where={"id": tid}, data={"niche": "salao", "createdAt": settings_start}
    )  # existia no mês
    settings = get_settings()
    period = reports.previous_period()
    start, _ = reports.period_bounds(period)
    inside = start + timedelta(days=3)

    patient = await clean_db.patient.create(data={"tenantId": tid, "phone": "5581999990501", "name": "Ana"})
    await clean_db.patient.update(where={"id": patient.id}, data={"createdAt": inside})
    appt = await clean_db.appointment.create(
        data={"tenantId": tid, "patientId": patient.id, "service": "Corte", "date": inside, "source": "AI"}
    )
    await clean_db.appointment.update(where={"id": appt.id}, data={"createdAt": inside})
    for i in range(3):
        log = await clean_db.executionlog.create(
            data={"tenantId": tid, "agent": "secretaria", "input": f"m{i}", "output": "ok", "runTimeMs": 10}
        )
        await clean_db.executionlog.update(where={"id": log.id}, data={"createdAt": inside})
    await clean_db.notification.create(
        data={"tenantId": tid, "type": "HUMAN_HANDOFF", "title": "x", "body": "y", "createdAt": inside}
    )
    disp = await clean_db.upselldispatch.create(
        data={"tenantId": tid, "patientId": patient.id, "appointmentId": appt.id}
    )
    await clean_db.upselldispatch.update(where={"id": disp.id}, data={"createdAt": inside})
    back = await clean_db.appointment.create(
        data={
            "tenantId": tid,
            "patientId": patient.id,
            "service": "Corte",
            "date": inside + timedelta(days=10),
            "source": "MANUAL",
        }
    )
    await clean_db.appointment.update(where={"id": back.id}, data={"createdAt": inside + timedelta(days=9)})

    data = await reports.monthly_report_data(tid, period)
    assert data == {
        "answered": 3,
        "appointments": 2,
        "appointments_ai": 1,
        "new_people": 1,
        "handoffs": 1,
        "invites": 1,
        "recovered": 1,
    }
    result = await reports.send_monthly_reports(settings)
    assert result["period"] == period and result["sent"] >= 1
    mails = [
        j for j in await clean_db.job.find_many(where={"name": "send-email"}) if "Resumo de" in j.payload["subject"]
    ]
    mine = [m for m in mails if m.payload["to"] == reg["email"]]
    assert len(mine) == 1
    text = mine[0].payload["text"]
    assert "Relatório SA" in text and "Atendimentos registrados: 2" in text and "voltaram: 1" in text
    assert "Novos clientes: 1" in text  # vocabulário do nicho (salão)
    # Segunda rodada no mesmo mês não reenvia; o admin pode forçar.
    again = await reports.send_monthly_reports(settings)
    assert again["sent"] == 0
    r = await client.post(f"/api/admin/tenants/{tid}/report", headers=ah)
    assert r.status_code == 200 and r.json()["period"] == period and r.json()["emails"] == [reg["email"]]
    assert (await clean_db.tenant.find_unique(where={"id": tid})).lastReportPeriod == period
    assert (await client.get(f"/api/clinic/{tid}", headers=h)).status_code == 200


async def test_export_csv_and_annual_cycle(client, clean_db):
    reg = await register_user(client, clinic="Export SA")
    tid, h = reg["tenantId"], auth_headers(reg)
    await client.post(f"/api/clinic/{tid}/patients", headers=h, json={"phone": "5581999990601", "name": "Bia; Souza"})
    r = await client.get(f"/api/clinic/{tid}/export/patients.csv", headers=h)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    body = r.text
    assert body.startswith("﻿") and "Nome;Telefone" in body and '"Bia; Souza"' in body and "+5581999990601" in body
    r = await client.get(f"/api/clinic/{tid}/export/appointments.csv", headers=h)
    assert r.status_code == 200 and "Data e hora;Serviço" in r.text

    ah = await _admin(client, clean_db)
    r = await client.patch(f"/api/admin/tenants/{tid}", headers=ah, json={"billingCycle": "ANNUAL"})
    assert r.status_code == 200
    billing = (await client.get(f"/api/clinic/{tid}/billing", headers=h)).json()
    assert billing["billingCycle"] == "ANNUAL"
    pro = next(p for p in billing["plans"] if p["plan"] == "PRO")
    assert pro["priceCentsYear"] == pro["priceCentsMonth"] * 11
    listed = (await client.get("/api/admin/tenants", headers=ah, params={"search": "Export SA"})).json()["items"][0]
    assert listed["billingCycle"] == "ANNUAL"
    bad = await client.patch(f"/api/admin/tenants/{tid}", headers=ah, json={"billingCycle": "WEEKLY"})
    assert bad.status_code == 422
    public = (await client.get("/api/public/config")).json()
    assert "demo" in public["sales"]
