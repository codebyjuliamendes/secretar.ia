"""Teste obrigatório: usuário do Tenant A jamais acessa dados do Tenant B."""

import pytest

from tests.conftest import auth_headers, register_user

READ_PATHS = [
    "",
    "/dashboard",
    "/settings",
    "/appointments",
    "/patients",
    "/notifications",
    "/team",
    "/audit",
    "/billing",
    "/whatsapp/status",
]


@pytest.fixture
async def two_tenants(client):
    a = await register_user(client, clinic="Clínica A")
    b = await register_user(client, clinic="Clínica B")
    # Dados no tenant B
    pat = await client.post(
        f"/api/clinic/{b['tenantId']}/patients",
        headers=auth_headers(b),
        json={"phone": "5581911112222", "name": "Paciente B"},
    )
    assert pat.status_code == 201
    appt = await client.post(
        f"/api/clinic/{b['tenantId']}/appointments",
        headers=auth_headers(b),
        json={"phone": "5581911112222", "service": "Botox", "date": "2030-01-10T14:00:00Z"},
    )
    assert appt.status_code == 201
    return a, b, pat.json()["id"], appt.json()["id"]


async def test_cross_tenant_reads_are_denied(client, two_tenants):
    a, b, patient_b, appt_b = two_tenants
    for path in READ_PATHS:
        res = await client.get(f"/api/clinic/{b['tenantId']}{path}", headers=auth_headers(a))
        assert res.status_code == 404, f"{path} -> {res.status_code}: {res.text}"
        assert "Paciente B" not in res.text
    res = await client.get(f"/api/clinic/{b['tenantId']}/patients/{patient_b}", headers=auth_headers(a))
    assert res.status_code == 404


async def test_cross_tenant_writes_are_denied(client, two_tenants):
    a, b, patient_b, appt_b = two_tenants
    hb = auth_headers(a)
    assert (
        await client.patch(
            f"/api/clinic/{b['tenantId']}/settings",
            headers=hb,
            json={"prompt": "Prompt malicioso injetado por outro tenant"},
        )
    ).status_code == 404
    assert (
        await client.post(
            f"/api/clinic/{b['tenantId']}/appointments/{appt_b}/status",
            headers=hb,
            json={"status": "CANCELED"},
        )
    ).status_code == 404
    assert (await client.delete(f"/api/clinic/{b['tenantId']}/patients/{patient_b}", headers=hb)).status_code == 404
    assert (
        await client.post(
            f"/api/clinic/{b['tenantId']}/team",
            headers=hb,
            json={"email": "intruso@example.com", "name": "Intruso", "role": "OWNER"},
        )
    ).status_code == 404
    # Nada mudou no tenant B
    settings_b = await client.get(f"/api/clinic/{b['tenantId']}/settings", headers=auth_headers(b))
    assert "malicioso" not in settings_b.json()["prompt"]
    appt = await client.get(f"/api/clinic/{b['tenantId']}/appointments", headers=auth_headers(b))
    assert appt.json()["items"][0]["status"] == "CONFIRMED"


async def test_idor_by_resource_id_across_tenants(client, two_tenants):
    """Mesmo passando o próprio tenant na URL, IDs de recursos de outro tenant não são encontrados."""
    a, b, patient_b, appt_b = two_tenants
    ha = auth_headers(a)
    assert (await client.get(f"/api/clinic/{a['tenantId']}/patients/{patient_b}", headers=ha)).status_code == 404
    assert (
        await client.patch(f"/api/clinic/{a['tenantId']}/patients/{patient_b}", headers=ha, json={"name": "Hackeado"})
    ).status_code == 404
    assert (
        await client.post(
            f"/api/clinic/{a['tenantId']}/appointments/{appt_b}/status",
            headers=ha,
            json={"status": "CANCELED"},
        )
    ).status_code == 404
    assert (
        await client.patch(
            f"/api/clinic/{a['tenantId']}/appointments/{appt_b}", headers=ha, json={"service": "Alterado"}
        )
    ).status_code == 404
    check = await client.get(f"/api/clinic/{b['tenantId']}/patients/{patient_b}", headers=auth_headers(b))
    assert check.json()["name"] == "Paciente B"


async def test_super_admin_is_not_implicit_member(client, clean_db, two_tenants):
    a, b, *_ = two_tenants
    await clean_db.user.update(where={"email": a["email"]}, data={"platformRole": "SUPER_ADMIN"})
    login = await client.post("/api/auth/login", json={"email": a["email"], "password": a["password"]})
    admin = login.json()
    assert (await client.get("/api/admin/tenants", headers=auth_headers(admin))).status_code == 200
    # Admin da plataforma não lê dados operacionais de uma clínica sem membership explícita.
    assert (await client.get(f"/api/clinic/{b['tenantId']}/patients", headers=auth_headers(admin))).status_code == 404


async def test_tenant_summary_and_own_access(client, two_tenants):
    a, b, *_ = two_tenants
    own = await client.get(f"/api/clinic/{a['tenantId']}", headers=auth_headers(a))
    assert own.status_code == 200 and own.json()["role"] == "OWNER"
    dash = await client.get(f"/api/clinic/{a['tenantId']}/dashboard", headers=auth_headers(a))
    assert dash.status_code == 200 and dash.json()["kpis"]["patientsTotal"] == 0
