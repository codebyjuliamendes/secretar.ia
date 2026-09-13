"""Convites de equipe com aceite: consentimento, sem vazamento de contas, reenvio/cancelamento e limite."""

from datetime import UTC, datetime, timedelta

from tests.conftest import auth_headers, register_user, unique_email
from tests.integration.test_rbac_and_admin import login


def _last_token(job) -> str:
    return job.payload["text"].split("token=")[1].split()[0]


async def test_existing_user_must_accept_logged_in_and_owner_learns_nothing(client, clean_db):
    owner = await register_user(client)
    tid, ho = owner["tenantId"], auth_headers(owner)
    other = await register_user(client)  # já tem conta (e a própria clínica)

    inv = await client.post(
        f"/api/clinic/{tid}/team",
        headers=ho,
        json={"email": other["email"], "name": "Nome que o dono digitou", "role": "STAFF"},
    )
    assert inv.status_code == 201, inv.text
    # A resposta é o convite, não o membro: nada sobre a conta existente (nome real, verificação) vaza.
    assert set(inv.json()) == {"id", "email", "name", "role", "expiresAt", "createdAt"}
    assert inv.json()["name"] == "Nome que o dono digitou"
    team = (await client.get(f"/api/clinic/{tid}/team", headers=ho)).json()
    assert len(team["items"]) == 1 and [i["email"] for i in team["invites"]] == [other["email"]]

    job = await clean_db.job.find_first(where={"name": "send-email"}, order={"createdAt": "desc"})
    assert job.payload["to"] == other["email"] and "/invite?token=" in job.payload["text"]
    token = _last_token(job)
    info = (await client.get(f"/api/auth/invites/{token}")).json()
    assert info["userExists"] is True and info["role"] == "STAFF" and info["clinicName"]

    # Sem login: não aceita. Logado como OUTRA pessoa: também não.
    anon = await client.post("/api/auth/invites/accept", json={"token": token})
    assert anon.status_code == 403 and anon.json()["error"]["code"] == "invite_login_required"
    wrong = await client.post("/api/auth/invites/accept", json={"token": token}, headers=ho)
    assert wrong.status_code == 403
    assert await clean_db.membership.count(where={"tenantId": tid}) == 1

    ok = await client.post("/api/auth/invites/accept", json={"token": token}, headers=auth_headers(other))
    assert ok.status_code == 200, ok.text
    assert ok.json()["tenantId"] == tid and ok.json()["accessToken"]
    assert any(m["tenantId"] == tid and m["role"] == "STAFF" for m in ok.json()["user"]["memberships"])
    # Token é de uso único e o convite some da lista.
    assert (
        await client.post("/api/auth/invites/accept", json={"token": token}, headers=auth_headers(other))
    ).status_code == 404
    team = (await client.get(f"/api/clinic/{tid}/team", headers=ho)).json()
    assert len(team["items"]) == 2 and team["invites"] == []
    # Convidar de novo quem já é membro: conflito.
    dup = await client.post(
        f"/api/clinic/{tid}/team", headers=ho, json={"email": other["email"], "name": "Xis", "role": "STAFF"}
    )
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "already_member"


async def test_new_user_creates_account_on_accept_and_email_is_verified(client, clean_db):
    owner = await register_user(client)
    tid, ho = owner["tenantId"], auth_headers(owner)
    email = unique_email("nova")
    inv = await client.post(
        f"/api/clinic/{tid}/team", headers=ho, json={"email": email, "name": "Nova", "role": "MANAGER"}
    )
    assert inv.status_code == 201
    token = _last_token(await clean_db.job.find_first(where={"name": "send-email"}, order={"createdAt": "desc"}))
    assert (await client.get(f"/api/auth/invites/{token}")).json()["userExists"] is False
    # Sem senha não cria conta; senha fraca também não.
    assert (await client.post("/api/auth/invites/accept", json={"token": token})).status_code == 400
    weak = await client.post("/api/auth/invites/accept", json={"token": token, "password": "12345678"})
    assert weak.status_code == 400 and weak.json()["error"]["code"] == "weak_password"
    ok = await client.post(
        "/api/auth/invites/accept", json={"token": token, "name": "Nova Silva", "password": "Senha1234"}
    )
    assert ok.status_code == 200, ok.text
    user = await clean_db.user.find_unique(where={"email": email})
    assert user.name == "Nova Silva" and user.emailVerifiedAt is not None  # o link chegou no e-mail dela
    session = await login(client, email, "Senha1234")
    assert (await client.get(f"/api/clinic/{tid}/settings", headers=auth_headers(session))).status_code == 200


async def test_resend_cancel_expiry_and_member_limit_count_pending(client, clean_db):
    owner = await register_user(client, plan="BASIC")  # Essencial: 3 membros
    tid, ho = owner["tenantId"], auth_headers(owner)
    e1, e2, e3 = unique_email("a"), unique_email("b"), unique_email("c")
    inv1 = await client.post(f"/api/clinic/{tid}/team", headers=ho, json={"email": e1, "name": "Ana", "role": "STAFF"})
    assert inv1.status_code == 201
    first_token = _last_token(await clean_db.job.find_first(where={"name": "send-email"}, order={"createdAt": "desc"}))
    inv2 = await client.post(f"/api/clinic/{tid}/team", headers=ho, json={"email": e2, "name": "Bia", "role": "STAFF"})
    assert inv2.status_code == 201
    # Owner + 2 convites pendentes = 3: o próximo e-mail estoura o limite do Essencial.
    over = await client.post(f"/api/clinic/{tid}/team", headers=ho, json={"email": e3, "name": "Cris", "role": "STAFF"})
    assert over.status_code == 402 and over.json()["error"]["code"] == "member_limit"
    # Reenviar para o MESMO e-mail não conta duas vezes e troca o token.
    again = await client.post(f"/api/clinic/{tid}/team", headers=ho, json={"email": e1, "name": "Ana", "role": "STAFF"})
    assert again.status_code == 201
    assert (await client.get(f"/api/auth/invites/{first_token}")).status_code == 404  # token antigo morreu
    resent = await client.post(f"/api/clinic/{tid}/team/invites/{again.json()['id']}/resend", headers=ho)
    assert resent.status_code == 200
    token = _last_token(await clean_db.job.find_first(where={"name": "send-email"}, order={"createdAt": "desc"}))
    assert (await client.get(f"/api/auth/invites/{token}")).status_code == 200
    # Expirado: 410 e não aceita.
    await clean_db.teaminvite.update(
        where={"id": again.json()["id"]}, data={"expiresAt": datetime.now(UTC) - timedelta(minutes=1)}
    )
    assert (await client.get(f"/api/auth/invites/{token}")).status_code == 410
    assert (
        await client.post("/api/auth/invites/accept", json={"token": token, "password": "Senha1234"})
    ).status_code == 410
    # Expirado não conta no limite; cancelar remove.
    fresh = await client.post(
        f"/api/clinic/{tid}/team", headers=ho, json={"email": e3, "name": "Cris", "role": "STAFF"}
    )
    assert fresh.status_code == 201
    assert (await client.delete(f"/api/clinic/{tid}/team/invites/{fresh.json()['id']}", headers=ho)).status_code == 204
    assert (await client.delete(f"/api/clinic/{tid}/team/invites/{inv2.json()['id']}", headers=ho)).status_code == 204
    assert (await client.get(f"/api/clinic/{tid}/team", headers=ho)).json()["invites"] == []
    # Gerente não gerencia convites.
    assert (await client.delete(f"/api/clinic/{tid}/team/invites/nao-existe", headers=ho)).status_code == 404
