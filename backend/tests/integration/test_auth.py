from tests.conftest import auth_headers, register_user, unique_email, unique_phone


async def test_register_login_me_refresh_logout(client, clean_db):
    reg = await register_user(client)
    assert reg["user"]["memberships"][0]["role"] == "OWNER"
    assert reg["user"]["emailVerified"] is False

    me = await client.get("/api/auth/me", headers=auth_headers(reg))
    assert me.status_code == 200 and me.json()["email"] == reg["email"]

    bad = await client.post("/api/auth/login", json={"email": reg["email"], "password": "errada123"})
    assert bad.status_code == 401 and bad.json()["error"]["code"] == "invalid_credentials"

    login = await client.post("/api/auth/login", json={"email": reg["email"], "password": reg["password"]})
    assert login.status_code == 200
    tokens = login.json()

    refreshed = await client.post("/api/auth/refresh", json={"refreshToken": tokens["refreshToken"]})
    assert refreshed.status_code == 200
    new_tokens = refreshed.json()
    assert new_tokens["refreshToken"] != tokens["refreshToken"]

    # Rotação: o refresh antigo não pode ser reutilizado. Reuso IMEDIATO (duas abas renovando juntas) só falha
    # para quem chegou depois; a sessão renovada continua válida.
    reuse = await client.post("/api/auth/refresh", json={"refreshToken": tokens["refreshToken"]})
    assert reuse.status_code == 401
    still_ok = await client.post("/api/auth/refresh", json={"refreshToken": new_tokens["refreshToken"]})
    assert still_ok.status_code == 200
    new_tokens = still_ok.json()
    # Reuso TARDIO de um token rotacionado (fora da janela de 30 s) é tratado como roubo: revoga a família.
    from datetime import UTC, datetime, timedelta

    from app.security.tokens import hash_token

    await clean_db.refreshtoken.update_many(
        where={"tokenHash": hash_token(tokens["refreshToken"])},
        data={"revokedAt": datetime.now(UTC) - timedelta(minutes=5)},
    )
    late = await client.post("/api/auth/refresh", json={"refreshToken": tokens["refreshToken"]})
    assert late.status_code == 401
    after_reuse = await client.post("/api/auth/refresh", json={"refreshToken": new_tokens["refreshToken"]})
    assert after_reuse.status_code == 401

    login2 = await client.post("/api/auth/login", json={"email": reg["email"], "password": reg["password"]})
    rt = login2.json()["refreshToken"]
    out = await client.post("/api/auth/logout", json={"refreshToken": rt})
    assert out.status_code == 204
    assert (await client.post("/api/auth/refresh", json={"refreshToken": rt})).status_code == 401


async def test_register_validation_and_duplicates(client, clean_db):
    weak = await client.post(
        "/api/auth/register",
        json={
            "name": "A",
            "email": "x@example.com",
            "password": "12345678",
            "clinicName": "C",
            "whatsapp": "5581999998888",
        },
    )
    assert weak.status_code == 422  # name muito curto -> validação pydantic
    weak2 = await client.post(
        "/api/auth/register",
        json={
            "name": "Ana",
            "email": unique_email(),
            "password": "12345678",
            "clinicName": "Clinica",
            "whatsapp": unique_phone(),
        },
    )
    assert weak2.status_code == 400 and weak2.json()["error"]["code"] == "weak_password"

    first = await register_user(client)
    dup = await client.post(
        "/api/auth/register",
        json={
            "name": "Ana",
            "email": first["email"],
            "password": "Senha1234",
            "clinicName": "Outra",
            "whatsapp": unique_phone(),
        },
    )
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "email_taken"


async def test_protected_routes_require_token(client, clean_db):
    assert (await client.get("/api/auth/me")).status_code == 401
    assert (await client.get("/api/admin/tenants")).status_code == 401
    assert (await client.get("/api/clinic/qualquer/dashboard")).status_code == 401
    bad = await client.get("/api/auth/me", headers={"Authorization": "Bearer token-invalido"})
    assert bad.status_code == 401 and bad.json()["error"]["code"] == "invalid_token"


async def test_email_verification_and_password_reset_flow(client, clean_db):
    from app.security.tokens import hash_token

    reg = await register_user(client)
    # O token foi gerado e o e-mail enfileirado; recuperamos o link a partir do job (SMTP não configurado).
    job = await clean_db.job.find_first(where={"name": "send-email"}, order={"createdAt": "desc"})
    assert job is not None and reg["email"] in job.payload["to"]
    token = job.payload["text"].split("token=")[1].split()[0]
    row = await clean_db.verificationtoken.find_unique(where={"tokenHash": hash_token(token)})
    assert row is not None and row.type == "EMAIL_VERIFY"

    ok = await client.post("/api/auth/verify-email", json={"token": token})
    assert ok.status_code == 200
    again = await client.post("/api/auth/verify-email", json={"token": token})
    assert again.status_code == 400
    me = await client.get("/api/auth/me", headers=auth_headers(reg))
    assert me.json()["emailVerified"] is True

    forgot = await client.post("/api/auth/forgot-password", json={"email": reg["email"]})
    assert forgot.status_code == 202
    unknown = await client.post("/api/auth/forgot-password", json={"email": "naoexiste@example.com"})
    assert unknown.status_code == 202  # não revela existência
    job = await clean_db.job.find_first(where={"name": "send-email"}, order={"createdAt": "desc"})
    reset_token = job.payload["text"].split("token=")[1].split()[0]
    reset = await client.post("/api/auth/reset-password", json={"token": reset_token, "password": "NovaSenha99"})
    assert reset.status_code == 200
    assert (
        await client.post("/api/auth/login", json={"email": reg["email"], "password": reg["password"]})
    ).status_code == 401
    assert (
        await client.post("/api/auth/login", json={"email": reg["email"], "password": "NovaSenha99"})
    ).status_code == 200
    # Sessões antigas foram revogadas após o reset.
    assert (await client.post("/api/auth/refresh", json={"refreshToken": reg["refreshToken"]})).status_code == 401


async def test_change_password_requires_current(client, clean_db):
    reg = await register_user(client)
    wrong = await client.post(
        "/api/auth/change-password",
        headers=auth_headers(reg),
        json={"currentPassword": "errada999", "newPassword": "Outra1234"},
    )
    assert wrong.status_code == 400 and wrong.json()["error"]["code"] == "invalid_current_password"
    ok = await client.post(
        "/api/auth/change-password",
        headers=auth_headers(reg),
        json={"currentPassword": reg["password"], "newPassword": "Outra1234"},
    )
    assert ok.status_code == 200
    assert (
        await client.post("/api/auth/login", json={"email": reg["email"], "password": "Outra1234"})
    ).status_code == 200


async def test_error_envelope_never_leaks_internals(client, clean_db):
    res = await client.post("/api/auth/login", json={"email": "not-an-email", "password": "x"})
    assert res.status_code == 422
    body = res.json()["error"]
    assert body["code"] == "validation_error" and "request_id" in body
    assert "Traceback" not in res.text
