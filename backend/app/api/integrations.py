"""Callbacks públicos de integrações OAuth (sem sessão: o vínculo com o tenant vem do `state` assinado)."""

from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Header, Query, Response
from fastapi.responses import RedirectResponse

from app.config import Settings
from app.deps import get_settings_dep
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
    if payload is None or not code:
        return RedirectResponse(
            f"{tenant_path}?{urlencode({'google': 'error', 'reason': 'invalid_state'})}", status_code=303
        )
    # A conclusão acontece pelo frontend autenticado (POST /clinic/{id}/integrations/google/complete): só quem
    # iniciou a autorização, logado, consegue vincular a agenda a esta clínica.
    return RedirectResponse(
        f"{tenant_path}?{urlencode({'google': 'pending', 'code': code, 'state': state})}", status_code=303
    )


@router.post("/google/notify", include_in_schema=False, status_code=204)
async def google_notify(
    x_goog_channel_id: str | None = Header(default=None),
    x_goog_channel_token: str | None = Header(default=None),
    x_goog_resource_state: str | None = Header(default=None),
):
    """Push do Google Calendar (events.watch): valida o token do canal e enfileira a leitura incremental.
    O corpo é vazio por contrato do Google; o que importa está nos cabeçalhos."""
    result = await calendar_sync.handle_push_notification(
        channel_id=x_goog_channel_id, token=x_goog_channel_token, state=x_goog_resource_state
    )
    log.info("google_push_received", result=result, state=x_goog_resource_state)
    return Response(status_code=204)
