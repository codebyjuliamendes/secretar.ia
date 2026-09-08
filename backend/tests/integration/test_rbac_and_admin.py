from tests.conftest import auth_headers, register_user, unique_email


async def login(client, email, password):
    res = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200, res.text
    return res.json()


async def test_staff_cannot_change_settings_or_team(client, clean_db):
    owner = await register_user(client)
    tid = owner["tenantId"]
    staff_email = unique_email("staff")
    inv = await client.post(
        f"/api/clinic/{tid}/team",
        headers=auth_headers(owner),
        json={"email": staff_email, "name": "Recepção", "role": "STAFF"},
    )
    assert inv.status_code == 201
    # Convite cria usuário com senha temporária e envia link de definição de senha.
    job = await clean_db.job.find_first(where={"name": "send-email"}, order={"createdAt": "desc"})
    token = job.payload["text"].split("token=")[1].split("&")[0]
    assert (
        await client.post("/api/auth/reset-password", json={"token": token, "password": "Staff1234"})
    ).status_code == 200
    staff = await login(client, staff_email, "Staff1234")
    hs = auth_headers(staff)

    assert (await client.get(f"/api/clinic/{tid}/appointments", headers=hs)).status_code == 200
    assert (await client.get(f"/api/clinic/{tid}/settings", headers=hs)).status_code == 200
    denied = await client.patch(f"/api/clinic/{tid}/settings", headers=hs, json={"prompt": "Novo prompt qualquer"})
    assert denied.status_code == 403 and denied.json()["error"]["code"] == "permission_denied"
    assert (await client.get(f"/api/clinic/{tid}/team", headers=hs)).status_code == 403
    assert (await client.get(f"/api/clinic/{tid}/audit", headers=hs)).status_code == 403
    assert (await client.post(f"/api/clinic/{tid}/whatsapp/connect", headers=hs)).status_code == 403


async def test_manager_cannot_promote_to_owner_and_last_owner_protected(client, clean_db):
    owner = await register_user(client)
    tid = owner["tenantId"]
    mgr_email = unique_email("mgr")
    inv = await client.post(
        f"/api/clinic/{tid}/team",
        headers=auth_headers(owner),
        json={"email": mgr_email, "name": "Gerente", "role": "MANAGER"},
    )
    assert inv.status_code == 201
    # MANAGER não gerencia equipe (TEAM_MANAGE é só OWNER)
    job = await clean_db.job.find_first(where={"name": "send-email"}, order={"createdAt": "desc"})
    token = job.payload["text"].split("token=")[1].split("&")[0]
    await client.post("/api/auth/reset-password", json={"token": token, "password": "Gerente123"})
    mgr = await login(client, mgr_email, "Gerente123")
    assert (
        await client.post(
            f"/api/clinic/{tid}/team",
            headers=auth_headers(mgr),
            json={"email": unique_email(), "name": "X", "role": "STAFF"},
        )
    ).status_code == 403

    team = (await client.get(f"/api/clinic/{tid}/team", headers=auth_headers(owner))).json()["items"]
    owner_membership = next(m for m in team if m["role"] == "OWNER")
    last = await client.patch(
        f"/api/clinic/{tid}/team/{owner_membership['id']}",
        headers=auth_headers(owner),
        json={"role": "STAFF"},
    )
    assert last.status_code == 409 and last.json()["error"]["code"] == "last_owner"
    assert (
        await client.delete(f"/api/clinic/{tid}/team/{owner_membership['id']}", headers=auth_headers(owner))
    ).status_code == 409


async def test_removed_member_loses_access_immediately(client, clean_db):
    owner = await register_user(client)
    tid = owner["tenantId"]
    email = unique_email("tmp")
    inv = await client.post(
        f"/api/clinic/{tid}/team",
        headers=auth_headers(owner),
        json={"email": email, "name": "Temp", "role": "STAFF"},
    )
    job = await clean_db.job.find_first(where={"name": "send-email"}, order={"createdAt": "desc"})
    token = job.payload["text"].split("token=")[1].split("&")[0]
    await client.post("/api/auth/reset-password", json={"token": token, "password": "Temp12345"})
    tmp = await login(client, email, "Temp12345")
    assert (await client.get(f"/api/clinic/{tid}/patients", headers=auth_headers(tmp))).status_code == 200
    assert (
        await client.delete(f"/api/clinic/{tid}/team/{inv.json()['id']}", headers=auth_headers(owner))
    ).status_code == 204
    assert (await client.get(f"/api/clinic/{tid}/patients", headers=auth_headers(tmp))).status_code == 404
    assert (await client.post("/api/auth/refresh", json={"refreshToken": tmp["refreshToken"]})).status_code == 401


async def test_admin_routes_require_super_admin_role_in_db(client, clean_db):
    user = await register_user(client)
    assert (await client.get("/api/admin/overview", headers=auth_headers(user))).status_code == 403
    await clean_db.user.update(where={"email": user["email"]}, data={"platformRole": "SUPER_ADMIN"})
    admin = await login(client, user["email"], user["password"])
    ov = await client.get("/api/admin/overview", headers=auth_headers(admin))
    assert ov.status_code == 200 and ov.json()["tenants"]["total"] == 1
    lst = await client.get("/api/admin/tenants?search=Cl", headers=auth_headers(admin))
    assert lst.status_code == 200 and lst.json()["total"] == 1
    created = await client.post(
        "/api/admin/tenants",
        headers=auth_headers(admin),
        json={
            "name": "Nova Clínica",
            "whatsapp": "+55 81 97777-6666",
            "prompt": "Você é a secretária virtual da clínica.",
            "plan": "PRO",
            "status": "ACTIVE",
        },
    )
    assert created.status_code == 201 and created.json()["whatsapp"] == "5581977776666"
    dup = await client.post(
        "/api/admin/tenants",
        headers=auth_headers(admin),
        json={
            "name": "Dup",
            "whatsapp": "5581977776666",
            "prompt": "Você é a secretária virtual da clínica.",
        },
    )
    assert dup.status_code == 409
    upd = await client.patch(
        f"/api/admin/tenants/{created.json()['id']}",
        headers=auth_headers(admin),
        json={"status": "SUSPENDED"},
    )
    assert upd.status_code == 200 and upd.json()["status"] == "SUSPENDED"
    # Rebaixamento no banco invalida privilégio mesmo com token ainda válido.
    await clean_db.user.update(where={"email": user["email"]}, data={"platformRole": "USER"})
    assert (await client.get("/api/admin/overview", headers=auth_headers(admin))).status_code == 403
