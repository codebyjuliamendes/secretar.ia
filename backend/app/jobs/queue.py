"""Fila de tarefas persistida no PostgreSQL.

Garantias:
  - Claim atômico com `FOR UPDATE SKIP LOCKED`: vários workers/pods nunca pegam o mesmo job.
  - Backoff exponencial com jitter; falhas permanentes (PermanentJobError) não são retentadas.
  - Jobs presos em RUNNING (worker morreu) são devolvidos para PENDING após `queue_stuck_minutes`.
"""

from __future__ import annotations

import asyncio
import json
import random
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from app.config import get_settings
from app.db import db
from app.logging import get_logger, tenant_id_var
from generated_prisma import Json

log = get_logger("jobs.queue")

TaskFn = Callable[[dict[str, Any]], Awaitable[None]]
_registry: dict[str, TaskFn] = {}


class PermanentJobError(Exception):
    """Erro que não deve ser retentado (payload inválido, tenant inexistente, etc.)."""


def register_task(name: str) -> Callable[[TaskFn], TaskFn]:
    def decorator(fn: TaskFn) -> TaskFn:
        _registry[name] = fn
        return fn

    return decorator


def registered_tasks() -> list[str]:
    return sorted(_registry)


async def enqueue(name: str, payload: dict[str, Any], *, max_retries: int = 5, delay_seconds: int = 0) -> str:
    if name not in _registry:
        raise ValueError(f"Tarefa desconhecida: {name}")
    run_at = datetime.now(UTC) + timedelta(seconds=delay_seconds)
    job = await db.job.create(data={"name": name, "payload": Json(payload), "maxRetries": max_retries, "runAt": run_at})
    log.info("job_enqueued", job_id=job.id, job_name=name, run_at=run_at.isoformat())
    return job.id


async def claim_next_job() -> dict[str, Any] | None:
    rows = await db.query_raw(
        """
        UPDATE "Job" SET status = 'RUNNING'::"JobStatus", "lockedAt" = NOW(), "updatedAt" = NOW()
        WHERE id = (
            SELECT id FROM "Job"
            WHERE status = 'PENDING'::"JobStatus" AND "runAt" <= NOW()
            ORDER BY "runAt" ASC, "createdAt" ASC
            LIMIT 1
            FOR UPDATE SKIP LOCKED
        )
        RETURNING id, name, payload, retries, "maxRetries"
        """
    )
    if not rows:
        return None
    row = rows[0]
    payload = row.get("payload")
    if isinstance(payload, str):
        payload = json.loads(payload)
    row["payload"] = payload or {}
    return row


async def recover_stuck_jobs(stuck_minutes: int) -> int:
    return await db.execute_raw(
        """
        UPDATE "Job" SET status = 'PENDING'::"JobStatus", "lockedAt" = NULL,
               error = COALESCE(error, '') || ' [recuperado após worker inativo]', "updatedAt" = NOW()
        WHERE status = 'RUNNING'::"JobStatus" AND "lockedAt" < NOW() - ($1::int * INTERVAL '1 minute')
        """,
        stuck_minutes,
    )


def backoff_seconds(retries: int) -> float:
    base = min(2**retries, 300)
    return base + random.uniform(0, base * 0.25)


async def run_job(job: dict[str, Any]) -> None:
    job_id, name, payload = job["id"], job["name"], job["payload"]
    token = tenant_id_var.set(payload.get("tenantId")) if isinstance(payload, dict) else None
    try:
        fn = _registry.get(name)
        if fn is None:
            raise PermanentJobError(f"Nenhum executor registrado para '{name}'")
        await fn(payload)
        await db.job.update(where={"id": job_id}, data={"status": "COMPLETED", "error": None, "lockedAt": None})
        log.info("job_completed", job_id=job_id, job_name=name)
    except PermanentJobError as exc:
        await db.job.update(
            where={"id": job_id}, data={"status": "FAILED", "error": f"permanente: {exc}", "lockedAt": None}
        )
        log.error("job_failed_permanent", job_id=job_id, job_name=name, error=str(exc))
    except Exception as exc:  # noqa: BLE001 - qualquer outra falha é retentável
        retries = int(job["retries"]) + 1
        if retries >= int(job["maxRetries"]):
            await db.job.update(
                where={"id": job_id},
                data={"status": "FAILED", "retries": retries, "error": str(exc)[:1000], "lockedAt": None},
            )
            log.error("job_failed_final", job_id=job_id, job_name=name, retries=retries, error=str(exc))
        else:
            delay = backoff_seconds(retries)
            await db.job.update(
                where={"id": job_id},
                data={
                    "status": "PENDING",
                    "retries": retries,
                    "runAt": datetime.now(UTC) + timedelta(seconds=delay),
                    "error": str(exc)[:1000],
                    "lockedAt": None,
                },
            )
            log.warning("job_retry_scheduled", job_id=job_id, job_name=name, retries=retries, delay_s=round(delay))
    finally:
        if token is not None:
            tenant_id_var.reset(token)


async def worker_loop(stop: asyncio.Event) -> None:
    settings = get_settings()
    sem = asyncio.Semaphore(settings.queue_concurrency)
    log.info("queue_worker_started", concurrency=settings.queue_concurrency, tasks=registered_tasks())
    last_recovery = datetime.now(UTC)
    inflight: set[asyncio.Task] = set()

    async def guarded(job: dict[str, Any]) -> None:
        try:
            await run_job(job)
        finally:
            sem.release()

    while not stop.is_set():
        try:
            if datetime.now(UTC) - last_recovery > timedelta(minutes=1):
                recovered = await recover_stuck_jobs(settings.queue_stuck_minutes)
                if recovered:
                    log.warning("jobs_recovered", count=recovered)
                last_recovery = datetime.now(UTC)

            await sem.acquire()
            try:
                job = await claim_next_job()
            except BaseException:
                sem.release()  # falha no claim (ex.: banco fora) não pode consumir a concorrência para sempre
                raise
            if job is None:
                sem.release()
                try:
                    await asyncio.wait_for(stop.wait(), timeout=2.0)
                except TimeoutError:
                    pass
                continue
            task = asyncio.create_task(guarded(job))
            inflight.add(task)
            task.add_done_callback(inflight.discard)
        except asyncio.CancelledError:
            break
        except Exception as exc:  # noqa: BLE001
            log.error("queue_loop_error", error=str(exc), exc_info=exc)
            await asyncio.sleep(2)

    if inflight:
        await asyncio.gather(*inflight, return_exceptions=True)
    log.info("queue_worker_stopped")
