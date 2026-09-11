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


async def test_login_is_rate_limited_per_ip_and_email(client, clean_db):
    reg = await register_user(client)
    bad = {"email": reg["email"], "password": "senha-errada-123"}
    statuses = [(await client.post("/api/auth/login", json=bad)).status_code for _ in range(10)]
    assert set(statuses) == {401}
    blocked = await client.post("/api/auth/login", json=bad)
    assert blocked.status_code == 429 and blocked.json()["error"]["code"] == "rate_limited"
    # Outro e-mail a partir do mesmo IP continua liberado (chave = ip + e-mail).
    other = await client.post("/api/auth/login", json={"email": "outra@example.com", "password": "senha-errada-123"})
    assert other.status_code == 401
