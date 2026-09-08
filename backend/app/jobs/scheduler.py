"""Agendador leve em processo (substitui dependência de cron externo).

Usa advisory lock do PostgreSQL para que apenas uma réplica dispare cada rotina diária.
O endpoint /api/internal/cron/* continua disponível para orquestradores externos.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from app.db import db
from app.jobs.queue import enqueue
from app.jobs.tasks import UPSELL_CAMPAIGN
from app.logging import get_logger

log = get_logger("jobs.scheduler")

LOCK_KEY_DAILY = 7_401_001
DAILY_HOUR_UTC = 12  # 09:00 America/Sao_Paulo


async def _try_lock(key: int) -> bool:
    rows = await db.query_raw("SELECT pg_try_advisory_lock($1) AS locked", key)
    return bool(rows and rows[0].get("locked"))


async def _unlock(key: int) -> None:
    await db.query_raw("SELECT pg_advisory_unlock($1)", key)


async def run_daily_maintenance() -> dict:
    """Rotinas diárias: campanha de upsell e limpeza de dados técnicos antigos."""
    now = datetime.now(UTC)
    await enqueue(UPSELL_CAMPAIGN, {"tenantId": None})
    removed_msgs = await db.processedmessage.delete_many(where={"processedAt": {"lt": now - timedelta(days=30)}})
    removed_tokens = await db.refreshtoken.delete_many(where={"expiresAt": {"lt": now - timedelta(days=1)}})
    removed_verif = await db.verificationtoken.delete_many(where={"expiresAt": {"lt": now - timedelta(days=1)}})
    removed_jobs = await db.job.delete_many(
        where={"status": {"in": ["COMPLETED"]}, "updatedAt": {"lt": now - timedelta(days=7)}}
    )
    result = {
        "processedMessagesRemoved": removed_msgs,
        "refreshTokensRemoved": removed_tokens,
        "verificationTokensRemoved": removed_verif,
        "jobsRemoved": removed_jobs,
    }
    log.info("daily_maintenance_done", **result)
    return result


async def scheduler_loop(stop: asyncio.Event) -> None:
    last_run_day: str | None = None
    log.info("scheduler_started", daily_hour_utc=DAILY_HOUR_UTC)
    while not stop.is_set():
        try:
            now = datetime.now(UTC)
            today = now.date().isoformat()
            if now.hour == DAILY_HOUR_UTC and last_run_day != today:
                if await _try_lock(LOCK_KEY_DAILY):
                    try:
                        await run_daily_maintenance()
                    finally:
                        await _unlock(LOCK_KEY_DAILY)
                last_run_day = today
        except Exception as exc:  # noqa: BLE001
            log.error("scheduler_error", error=str(exc), exc_info=exc)
        try:
            await asyncio.wait_for(stop.wait(), timeout=60)
        except TimeoutError:
            pass
    log.info("scheduler_stopped")
