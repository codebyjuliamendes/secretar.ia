"""Agendador leve em processo (substitui dependência de cron externo).

Usa advisory lock do PostgreSQL para que apenas uma réplica dispare cada rotina (diária e leitura periódica
do Google Calendar). Os endpoints /api/internal/cron/* continuam disponíveis para orquestradores externos.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from app.db import db
from app.jobs.queue import enqueue
from app.jobs.tasks import MONTHLY_REPORTS, UPSELL_CAMPAIGN
from app.logging import get_logger
from app.security.ratelimit import purge_expired_buckets

log = get_logger("jobs.scheduler")

LOCK_KEY_DAILY = 7_401_001
LOCK_KEY_PULL = 7_401_002
DAILY_HOUR_UTC = 12  # 09:00 America/Sao_Paulo


async def _try_lock(key: int) -> bool:
    rows = await db.query_raw("SELECT pg_try_advisory_lock($1) AS locked", key)
    return bool(rows and rows[0].get("locked"))


async def _unlock(key: int) -> None:
    await db.query_raw("SELECT pg_advisory_unlock($1)", key)


async def daily_already_ran_today(now: datetime | None = None) -> bool:
    """O `Job` da campanha é o carimbo durável do dia: outra réplica (ou um restart) não repete a rotina."""
    now = now or datetime.now(UTC)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return await db.job.count(where={"name": UPSELL_CAMPAIGN, "createdAt": {"gte": start}}) > 0


async def run_daily_maintenance() -> dict:
    """Rotinas diárias: campanha de upsell e limpeza de dados técnicos antigos."""
    now = datetime.now(UTC)
    await enqueue(UPSELL_CAMPAIGN, {"tenantId": None})
    await enqueue(MONTHLY_REPORTS, {})  # só envia para quem ainda não recebeu o mês fechado
    from app.config import get_settings
    from app.services.manual_billing import sweep_overdue

    overdue = await sweep_overdue(get_settings(), now)
    removed_msgs = await db.processedmessage.delete_many(where={"processedAt": {"lt": now - timedelta(days=30)}})
    removed_tokens = await db.refreshtoken.delete_many(where={"expiresAt": {"lt": now - timedelta(days=1)}})
    removed_verif = await db.verificationtoken.delete_many(where={"expiresAt": {"lt": now - timedelta(days=1)}})
    removed_jobs = await db.job.delete_many(
        where={"status": {"in": ["COMPLETED"]}, "updatedAt": {"lt": now - timedelta(days=7)}}
    )
    removed_buckets = await purge_expired_buckets()
    from app.services.calendar_sync import purge_past_external_busy

    removed_external = await purge_past_external_busy(now)
    result = {
        "processedMessagesRemoved": removed_msgs,
        "rateLimitBucketsRemoved": removed_buckets,
        "externalBusyRemoved": removed_external,
        "refreshTokensRemoved": removed_tokens,
        "verificationTokensRemoved": removed_verif,
        "jobsRemoved": removed_jobs,
        "tenantsOverdue": overdue,
    }
    log.info("daily_maintenance_done", **result)
    return result


async def run_calendar_pulls() -> int:
    from app.services.calendar_sync import schedule_pulls

    return await schedule_pulls()


async def scheduler_loop(stop: asyncio.Event) -> None:
    from app.services.calendar_sync import PULL_INTERVAL_MINUTES

    last_run_day: str | None = None
    last_pull: datetime | None = None
    log.info("scheduler_started", daily_hour_utc=DAILY_HOUR_UTC, pull_interval_min=PULL_INTERVAL_MINUTES)
    while not stop.is_set():
        try:
            now = datetime.now(UTC)
            today = now.date().isoformat()
            if now.hour == DAILY_HOUR_UTC and last_run_day != today:
                if await _try_lock(LOCK_KEY_DAILY):
                    try:
                        if not await daily_already_ran_today(now):
                            await run_daily_maintenance()
                    finally:
                        await _unlock(LOCK_KEY_DAILY)
                last_run_day = today
            if last_pull is None or now - last_pull >= timedelta(minutes=PULL_INTERVAL_MINUTES):
                if await _try_lock(LOCK_KEY_PULL):
                    try:
                        queued = await run_calendar_pulls()
                        if queued:
                            log.info("calendar_pulls_scheduled", queued=queued)
                    finally:
                        await _unlock(LOCK_KEY_PULL)
                last_pull = now
        except Exception as exc:  # noqa: BLE001
            log.error("scheduler_error", error=str(exc), exc_info=exc)
        try:
            await asyncio.wait_for(stop.wait(), timeout=60)
        except TimeoutError:
            pass
    log.info("scheduler_stopped")
