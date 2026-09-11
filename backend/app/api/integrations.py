"""Callbacks públicos de integrações OAuth (sem sessão: o vínculo com o tenant vem do `state` assinado)."""

from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Query
from fastapi.responses import RedirectResponse

from app.config import Settings
from app.deps import get_settings_dep
from app.errors import AppError
from app.logging import get_logger
from app.services import calendar_sync

router = APIRouter(prefix="/integrations", tags=["integrations"])
log = get_logger("integrations")


@router.get("/google/callback", include_in_schema=False)
async def google_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    settings: Settings = Depends(get_settings_dep),
):
    frontend = settings.frontend_url.rstrip("/")
    payload = calendar_sync.parse_state(settings, state)
    tenant_path = f"{frontend}/app/{payload['tid']}/settings" if payload else f"{frontend}/app"
    if error:
        return RedirectResponse(f"{tenant_path}?{urlencode({'google': 'error', 'reason': 'denied'})}", status_code=303)
    try:
        await calendar_sync.complete_connect(settings, code=code, state=state)
    except AppError as exc:
        log.warning("google_callback_failed", code=exc.code)
        return RedirectResponse(f"{tenant_path}?{urlencode({'google': 'error', 'reason': exc.code})}", status_code=303)
    return RedirectResponse(f"{tenant_path}?google=connected", status_code=303)
