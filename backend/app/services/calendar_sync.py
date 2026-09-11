"""Sincronização da agenda da clínica com o Google Calendar do tenant.

Fluxo: OWNER/MANAGER conecta (OAuth) → refresh token cifrado em `CalendarConnection` → cada criação,
remarcação, confirmação ou cancelamento de agendamento enfileira `sync-calendar` → o job cria/atualiza/apaga
o evento e guarda `externalEventId` no agendamento. Um refresh token inválido desliga a sincronização e
avisa a clínica na inbox (nunca falha em silêncio).
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import jwt

from app.config import Settings
from app.db import db
from app.errors import AppError, ConflictError
from app.integrations.google_calendar import (
    GoogleAuthExpired,
    GoogleOAuthError,
    build_google_calendar_provider,
    google_enabled,
)
from app.jobs.queue import PermanentJobError, enqueue
from app.logging import get_logger
from app.security.crypto import decrypt_secret, encrypt_secret
from app.services import audit, notifications

log = get_logger("calendar_sync")

STATE_TTL_MINUTES = 15
SYNC_CALENDAR = "sync-calendar"
BACKFILL_LIMIT = 200
EVENT_STATUSES = {"PENDING", "CONFIRMED", "COMPLETED", "NO_SHOW"}  # CANCELED remove o evento


# ------------------------------- OAuth (connect) -------------------------------


def redirect_uri(settings: Settings) -> str:
    return f"{settings.public_api_url.rstrip('/')}/api/integrations/google/callback"


def make_state(settings: Settings, *, tenant_id: str, user_id: str) -> str:
    now = datetime.now(UTC)
    payload = {
        "type": "gcal_state",
        "tid": tenant_id,
        "sub": user_id,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=STATE_TTL_MINUTES)).timestamp()),
        "jti": secrets.token_hex(8),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def parse_state(settings: Settings, state: str | None) -> dict | None:
    if not state:
        return None
    try:
        payload = jwt.decode(state, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    if payload.get("type") != "gcal_state" or not payload.get("tid") or not payload.get("sub"):
        return None
    return payload


def connection_view(conn) -> dict[str, Any]:
    if conn is None:
        return {
            "connected": False,
            "accountEmail": None,
            "calendarId": None,
            "syncEnabled": False,
            "lastSyncAt": None,
            "lastError": None,
        }
    return {
        "connected": True,
        "accountEmail": conn.accountEmail,
        "calendarId": conn.calendarId,
        "syncEnabled": conn.syncEnabled,
        "lastSyncAt": conn.lastSyncAt.isoformat() if conn.lastSyncAt else None,
        "lastError": conn.lastError,
    }


async def status(settings: Settings, tenant_id: str) -> dict[str, Any]:
    conn = await db.calendarconnection.find_unique(where={"tenantId": tenant_id})
    return {**connection_view(conn), "available": google_enabled(settings)}


async def start_connect(settings: Settings, tenant, *, actor_user_id: str, ip: str | None) -> dict[str, str]:
    provider = build_google_calendar_provider(settings)
    state = make_state(settings, tenant_id=tenant.id, user_id=actor_user_id)
    await audit.record(
        action="calendar.connect_started",
        resource_type="tenant",
        resource_id=tenant.id,
        tenant_id=tenant.id,
        actor_user_id=actor_user_id,
        ip=ip,
    )
    return {"url": provider.auth_url(state=state, redirect_uri=redirect_uri(settings))}


async def complete_connect(settings: Settings, *, code: str | None, state: str | None) -> str:
    """Troca o código por tokens e grava a conexão. Retorna o tenant_id. Lança AppError em falhas."""
    payload = parse_state(settings, state)
    if payload is None:
        raise AppError("Estado da autorização inválido ou expirado. Tente conectar novamente.", code="invalid_state")
    tenant_id, user_id = payload["tid"], payload["sub"]
    if not code:
        raise AppError("Autorização não concedida.", code="oauth_denied")
    # O usuário do state precisa continuar membro com permissão (o link pode ter sido forjado/compartilhado).
    membership = await db.membership.find_unique(where={"userId_tenantId": {"userId": user_id, "tenantId": tenant_id}})
    if membership is None or str(membership.role) not in ("OWNER", "MANAGER"):
        raise AppError("Sem permissão para conectar a agenda desta clínica.", code="forbidden", status_code=403)
    provider = build_google_calendar_provider(settings)
    try:
        tokens = await provider.exchange_code(code=code, redirect_uri=redirect_uri(settings))
    except GoogleOAuthError as exc:
        raise AppError("O Google recusou a autorização. Tente novamente.", code="oauth_failed") from exc
    existing = await db.calendarconnection.find_unique(where={"tenantId": tenant_id})
    refresh_enc = encrypt_secret(settings, tokens.refresh_token) if tokens.refresh_token else None
    if refresh_enc is None and existing is None:
        raise AppError(
            "O Google não devolveu credencial de acesso contínuo. Remova o acesso da Secretar.ia na sua conta "
            "Google e conecte novamente.",
            code="missing_refresh_token",
        )
    data = {
        "provider": "google",
        "accountEmail": tokens.email,
        "accessTokenEnc": encrypt_secret(settings, tokens.access_token),
        "accessTokenExpiresAt": datetime.now(UTC) + timedelta(seconds=max(60, tokens.expires_in - 60)),
        "syncEnabled": True,
        "lastError": None,
    }
    if refresh_enc:
        data["refreshTokenEnc"] = refresh_enc
    if existing:
        await db.calendarconnection.update(where={"id": existing.id}, data=data)
    else:
        await db.calendarconnection.create(data={"tenantId": tenant_id, **data})
    await audit.record(
        action="calendar.connected",
        resource_type="tenant",
        resource_id=tenant_id,
        tenant_id=tenant_id,
        actor_user_id=user_id,
        metadata={"accountEmail": tokens.email},
    )
    await notifications.notify(
        tenant_id,
        type_="SYSTEM",
        title="Google Calendar conectado",
        body=f"Agendamentos passam a aparecer na agenda {tokens.email or 'Google'} da clínica.",
        dedupe_minutes=5,
    )
    await backfill(tenant_id)
    return tenant_id


async def disconnect(settings: Settings, tenant, *, actor_user_id: str, ip: str | None) -> dict[str, Any]:
    conn = await db.calendarconnection.find_unique(where={"tenantId": tenant.id})
    if conn is None:
        return connection_view(None)
    try:
        provider = build_google_calendar_provider(settings)
        await provider.revoke(decrypt_secret(settings, conn.refreshTokenEnc))
    except Exception as exc:  # noqa: BLE001 - revogação é cortesia; a conexão local é removida de qualquer forma
        log.warning("google_revoke_skipped", error=str(exc)[:200])
    await db.calendarconnection.delete(where={"id": conn.id})
    await db.appointment.update_many(where={"tenantId": tenant.id}, data={"externalEventId": None})
    await audit.record(
        action="calendar.disconnected",
        resource_type="tenant",
        resource_id=tenant.id,
        tenant_id=tenant.id,
        actor_user_id=actor_user_id,
        ip=ip,
    )
    return connection_view(None)


# --------------------------------- Sincronização ---------------------------------


async def schedule_sync(tenant_id: str, appointment_id: str) -> bool:
    """Enfileira a sincronização se a clínica tiver Google Calendar ativo. Barato: uma leitura por chamada."""
    conn = await db.calendarconnection.find_unique(where={"tenantId": tenant_id})
    if conn is None or not conn.syncEnabled:
        return False
    await enqueue(SYNC_CALENDAR, {"tenantId": tenant_id, "appointmentId": appointment_id})
    return True


async def backfill(tenant_id: str) -> int:
    """Enfileira os agendamentos futuros ainda sem evento (após conectar ou reconectar)."""
    rows = await db.appointment.find_many(
        where={
            "tenantId": tenant_id,
            "status": {"in": ["PENDING", "CONFIRMED"]},
            "date": {"gte": datetime.now(UTC) - timedelta(hours=1)},
        },
        order={"date": "asc"},
        take=BACKFILL_LIMIT,
    )
    for a in rows:
        await enqueue(SYNC_CALENDAR, {"tenantId": tenant_id, "appointmentId": a.id})
    return len(rows)


def build_event(appointment, patient, tenant) -> dict[str, Any]:
    tz = tenant.timezone or "America/Sao_Paulo"
    start = appointment.date.astimezone(ZoneInfo(tz))
    end = (appointment.endAt or appointment.date + timedelta(minutes=appointment.durationMin or 60)).astimezone(
        ZoneInfo(tz)
    )
    name = (patient.name if patient else None) or (patient.phone if patient else "paciente")
    status = str(appointment.status)
    prefix = {"PENDING": "[Pendente] ", "NO_SHOW": "[Faltou] ", "COMPLETED": "[Realizado] "}.get(status, "")
    lines = [f"Paciente: {name}"]
    if patient and patient.phone:
        lines.append(f"WhatsApp: +{patient.phone}")
    lines.append(f"Status: {status}")
    if appointment.notes:
        lines.append(f"Observações: {appointment.notes}")
    lines.append("Criado pela Secretar.ia")
    return {
        "summary": f"{prefix}{appointment.service} – {name}",
        "description": "\n".join(lines),
        "start": {"dateTime": start.isoformat(), "timeZone": tz},
        "end": {"dateTime": end.isoformat(), "timeZone": tz},
        "status": "tentative" if status == "PENDING" else "confirmed",
        "transparency": "opaque",
        "extendedProperties": {"private": {"secretariaAppointmentId": appointment.id, "secretariaTenantId": tenant.id}},
        "reminders": {"useDefault": True},
    }


async def _access_token(settings: Settings, provider, conn) -> str:
    now = datetime.now(UTC)
    if conn.accessTokenEnc and conn.accessTokenExpiresAt and conn.accessTokenExpiresAt > now + timedelta(seconds=30):
        try:
            return decrypt_secret(settings, conn.accessTokenEnc)
        except ValueError:
            pass
    return await _refresh_access_token(settings, provider, conn)


async def _refresh_access_token(settings: Settings, provider, conn) -> str:
    tokens = await provider.refresh(decrypt_secret(settings, conn.refreshTokenEnc))
    await db.calendarconnection.update(
        where={"id": conn.id},
        data={
            "accessTokenEnc": encrypt_secret(settings, tokens.access_token),
            "accessTokenExpiresAt": datetime.now(UTC) + timedelta(seconds=max(60, tokens.expires_in - 60)),
        },
    )
    return tokens.access_token


async def _disable_connection(conn, reason: str) -> None:
    await db.calendarconnection.update(where={"id": conn.id}, data={"syncEnabled": False, "lastError": reason[:300]})
    await notifications.notify(
        conn.tenantId,
        type_="SYSTEM",
        title="Google Calendar desconectado",
        body="O Google recusou a credencial da clínica. Reconecte a agenda em Configurações para retomar a "
        "sincronização dos agendamentos.",
        dedupe_minutes=60,
    )


async def sync_appointment(settings: Settings, *, tenant_id: str, appointment_id: str) -> str:
    """Executado pela fila. Retorna created|updated|deleted|skipped."""
    conn = await db.calendarconnection.find_unique(where={"tenantId": tenant_id})
    if conn is None or not conn.syncEnabled:
        return "skipped"
    appt = await db.appointment.find_first(
        where={"id": appointment_id, "tenantId": tenant_id}, include={"patient": True, "tenant": True}
    )
    if appt is None:
        return "skipped"
    provider = build_google_calendar_provider(settings)
    try:
        token = await _access_token(settings, provider, conn)
        try:
            result = await _apply(provider, token, conn, appt)
        except GoogleAuthExpired:
            token = await _refresh_access_token(settings, provider, conn)
            result = await _apply(provider, token, conn, appt)
    except GoogleOAuthError as exc:
        await _disable_connection(conn, f"oauth: {exc}")
        raise PermanentJobError(f"Google recusou a credencial ({exc}); sincronização desligada") from exc
    except ValueError as exc:  # segredo cifrado ilegível (chave trocada)
        await _disable_connection(conn, "credencial ilegível (chave de criptografia alterada)")
        raise PermanentJobError(str(exc)) from exc
    await db.calendarconnection.update(where={"id": conn.id}, data={"lastSyncAt": datetime.now(UTC), "lastError": None})
    log.info("calendar_synced", appointment_id=appointment_id, result=result)
    return result


async def _apply(provider, token: str, conn, appt) -> str:
    if str(appt.status) == "CANCELED":
        if not appt.externalEventId:
            return "skipped"
        await provider.delete_event(access_token=token, calendar_id=conn.calendarId, event_id=appt.externalEventId)
        await db.appointment.update(where={"id": appt.id}, data={"externalEventId": None})
        return "deleted"
    if str(appt.status) not in EVENT_STATUSES:
        return "skipped"
    body = build_event(appt, appt.patient, appt.tenant)
    event_id = await provider.upsert_event(
        access_token=token, calendar_id=conn.calendarId, event_id=appt.externalEventId, body=body
    )
    if event_id != appt.externalEventId:
        await db.appointment.update(where={"id": appt.id}, data={"externalEventId": event_id})
        return "created"
    return "updated"


async def resync(settings: Settings, tenant, *, actor_user_id: str, ip: str | None) -> dict[str, int]:
    conn = await db.calendarconnection.find_unique(where={"tenantId": tenant.id})
    if conn is None:
        raise ConflictError("Google Calendar não está conectado.", code="calendar_not_connected")
    if not conn.syncEnabled:
        raise ConflictError("Reconecte o Google Calendar para retomar a sincronização.", code="calendar_disabled")
    queued = await backfill(tenant.id)
    await audit.record(
        action="calendar.resync_requested",
        resource_type="tenant",
        resource_id=tenant.id,
        tenant_id=tenant.id,
        actor_user_id=actor_user_id,
        metadata={"queued": queued},
        ip=ip,
    )
    return {"queued": queued}
