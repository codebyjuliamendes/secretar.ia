"""Rate limiting por chave.

- `PostgresRateLimiter`: janela fixa persistida no Postgres (INSERT ... ON CONFLICT atômico). Consistente
  entre réplicas sem Redis (ADR-008). Se o banco falhar, o limiter *abre* (fail-open) e loga o erro:
  indisponibilidade do banco já derruba o login por si só, e nunca deve virar bloqueio silencioso.
- `SlidingWindowRateLimiter`: em memória, para processos únicos ou testes de lógica.
"""

from __future__ import annotations

import time
from collections import deque
from datetime import UTC, datetime

from app.db import db
from app.logging import get_logger

log = get_logger("security.ratelimit")


class SlidingWindowRateLimiter:
    def __init__(self, limit: int, window_seconds: int = 60):
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = {}

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        q = self._hits.setdefault(key, deque())
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.limit:
            return False
        q.append(now)
        if len(self._hits) > 10_000:  # evita crescimento indefinido
            for k in [k for k, v in self._hits.items() if not v or now - v[-1] > self.window]:
                self._hits.pop(k, None)
        return True

    def reset(self) -> None:
        self._hits.clear()


def window_start(now_ts: float, window_seconds: int) -> datetime:
    """Início do bucket (UTC) que contém `now_ts`."""
    start = (int(now_ts) // window_seconds) * window_seconds
    return datetime.fromtimestamp(start, UTC)


class PostgresRateLimiter:
    """Contador por (scope, key, janela) no Postgres. `allow` incrementa e compara com o limite."""

    def __init__(self, scope: str, limit: int, window_seconds: int = 60):
        self.scope = scope
        self.limit = limit
        self.window = window_seconds

    async def allow(self, key: str) -> bool:
        start = window_start(time.time(), self.window).replace(tzinfo=None).isoformat(sep=" ")
        try:
            rows = await db.query_raw(
                """
                INSERT INTO "RateLimitBucket" (scope, key, "windowStart", count)
                VALUES ($1, $2, $3::timestamp, 1)
                ON CONFLICT (scope, key, "windowStart") DO UPDATE SET count = "RateLimitBucket".count + 1
                RETURNING count
                """,
                self.scope,
                key[:200],
                start,
            )
        except Exception as exc:  # noqa: BLE001 - fail-open documentado acima
            log.error("ratelimit_store_unavailable", scope=self.scope, error=str(exc)[:200])
            return True
        return int(rows[0]["count"]) <= self.limit if rows else True

    async def reset(self, key: str | None = None) -> None:
        if key is None:
            await db.execute_raw('DELETE FROM "RateLimitBucket" WHERE scope = $1', self.scope)
        else:
            await db.execute_raw('DELETE FROM "RateLimitBucket" WHERE scope = $1 AND key = $2', self.scope, key)


async def purge_expired_buckets(older_than_seconds: int = 24 * 3600) -> int:
    return await db.execute_raw(
        """DELETE FROM "RateLimitBucket" WHERE "windowStart" < NOW() - ($1::int * INTERVAL '1 second')""",
        older_than_seconds,
    )
