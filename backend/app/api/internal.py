"""Endpoints internos (cron externo e health)."""

from __future__ import annotations

import hmac
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse

from app.config import Settings
from app.db import db
from app.deps import get_settings_dep
from app.errors import UnauthorizedError
from app.jobs.scheduler import run_calendar_pulls, run_daily_maintenance
from app.services.marketing import run_upsell_campaign

router = APIRouter(tags=["internal"])
cron_router = APIRouter(prefix="/internal/cron", tags=["internal"])


async def require_cron_secret(
    authorization: str | None = Header(default=None), settings: Settings = Depends(get_settings_dep)
) -> None:
    expected = f"Bearer {settings.cron_secret}" if settings.cron_secret else None
    if not expected or not authorization or not hmac.compare_digest(authorization, expected):
        raise UnauthorizedError("Credencial de cron inválida.", code="invalid_cron_secret")


@router.get("/health")
async def health():
    """Liveness: o processo responde. Não consulta o banco, para uma oscilação do Postgres não reiniciar os pods."""
    return {"status": "ok", "time": datetime.now(UTC).isoformat()}


@router.get("/ready")
async def ready():
    """Readiness: pronto para receber tráfego (banco acessível). Use no balanceador, não no restart do container."""
    checks = {"database": "ok"}
    status_code = 200
    try:
        await db.query_raw("SELECT 1")
    except Exception:  # noqa: BLE001
        checks["database"] = "error"
        status_code = 503
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ok" if status_code == 200 else "degraded",
            "checks": checks,
            "time": datetime.now(UTC).isoformat(),
        },
    )


@cron_router.post("/reminders", dependencies=[Depends(require_cron_secret)])
async def cron_reminders():
    from app.services.engagement import send_reminders

    return {"sent": await send_reminders()}


@cron_router.post("/monthly-reports", dependencies=[Depends(require_cron_secret)])
async def cron_monthly_reports(settings: Settings = Depends(get_settings_dep)):
    from app.services.reports import send_monthly_reports

    return await send_monthly_reports(settings)


@cron_router.post("/upsell", dependencies=[Depends(require_cron_secret)])
async def cron_upsell():
    return await run_upsell_campaign()


@cron_router.post("/daily", dependencies=[Depends(require_cron_secret)])
async def cron_daily():
    return await run_daily_maintenance()


@cron_router.post("/pull-calendar", dependencies=[Depends(require_cron_secret)])
async def cron_pull_calendar():
    """Enfileira a leitura do Google Calendar de todas as clínicas conectadas (o scheduler interno já faz isso)."""
    return {"queued": await run_calendar_pulls()}
