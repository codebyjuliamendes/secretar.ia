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
from app.jobs.scheduler import run_daily_maintenance
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


@cron_router.post("/upsell", dependencies=[Depends(require_cron_secret)])
async def cron_upsell():
    return await run_upsell_campaign()


@cron_router.post("/daily", dependencies=[Depends(require_cron_secret)])
async def cron_daily():
    return await run_daily_maintenance()
