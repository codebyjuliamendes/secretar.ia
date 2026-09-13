from app.security.ratelimit import PostgresRateLimiter, purge_expired_buckets
from tests.conftest import register_user


async def test_postgres_rate_limiter_counts_per_scope_and_key(client, clean_db):
    rl = PostgresRateLimiter("test.scope", limit=2, window_seconds=60)
    assert await rl.allow("ip-a") is True
    assert await rl.allow("ip-a") is True
    assert await rl.allow("ip-a") is False  # terceira tentativa na mesma janela
    assert await rl.allow("ip-b") is True  # outra chave não é afetada
    other = PostgresRateLimiter("other.scope", limit=2, window_seconds=60)
    assert await other.allow("ip-a") is True  # outro escopo tem contador próprio
    await rl.reset("ip-a")
    assert await rl.allow("ip-a") is True

    # Buckets antigos são removidos pela manutenção; buckets recentes ficam.
    await clean_db.execute_raw(
        """UPDATE "RateLimitBucket" SET "windowStart" = NOW() - INTERVAL '2 days' WHERE scope = 'other.scope'"""
    )
    assert await purge_expired_buckets() == 1
    assert await clean_db.ratelimitbucket.count(where={"scope": "test.scope"}) >= 1


async def test_login_is_rate_limited_per_ip_and_email(client, clean_db, monkeypatch):
    # Janela fixa: congela o bucket para o teste não atravessar a virada do minuto.
    from datetime import UTC, datetime

    from app.security import ratelimit

    monkeypatch.setattr(ratelimit, "window_start", lambda now_ts, window_seconds: datetime(2030, 1, 1, tzinfo=UTC))
    reg = await register_user(client)
    bad = {"email": reg["email"], "password": "senha-errada-123"}
    statuses = [(await client.post("/api/auth/login", json=bad)).status_code for _ in range(10)]
    assert set(statuses) == {401}
    blocked = await client.post("/api/auth/login", json=bad)
    assert blocked.status_code == 429 and blocked.json()["error"]["code"] == "rate_limited"
    # Outro e-mail a partir do mesmo IP continua liberado (chave = ip + e-mail).
    other = await client.post("/api/auth/login", json={"email": "outra@example.com", "password": "senha-errada-123"})
    assert other.status_code == 401


async def test_login_has_a_per_account_ceiling_independent_of_ip(client, clean_db, monkeypatch):
    from datetime import UTC, datetime

    from app.security import ratelimit

    monkeypatch.setattr(ratelimit, "window_start", lambda now_ts, window_seconds: datetime(2030, 1, 1, tzinfo=UTC))
    reg = await register_user(client)
    bad = {"email": reg["email"], "password": "senha-errada-123"}
    # 30 tentativas de 30 IPs diferentes (X-Forwarded-For forjado): o limite por e-mail ainda fecha na 31ª.
    for i in range(30):
        res = await client.post(
            "/api/auth/login", json=bad, headers={"X-Forwarded-For": f"10.0.{i // 250}.{i % 250 + 1}"}
        )
        assert res.status_code == 401, (i, res.text)
    blocked = await client.post("/api/auth/login", json=bad, headers={"X-Forwarded-For": "10.9.9.9"})
    assert blocked.status_code == 429
    # A senha certa também é barrada até a janela virar (é o comportamento esperado de um teto por conta).
    ok_but_blocked = await client.post(
        "/api/auth/login",
        json={"email": reg["email"], "password": reg["password"]},
        headers={"X-Forwarded-For": "10.9.9.8"},
    )
    assert ok_but_blocked.status_code == 429
