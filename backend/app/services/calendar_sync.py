"""Sincronização da agenda da clínica com o Google Calendar do tenant.

Escrita (Secretar.ia → Google): OWNER/MANAGER conecta (OAuth) → refresh token cifrado em
`CalendarConnection` → cada criação, remarcação, confirmação ou cancelamento de agendamento enfileira
`sync-calendar` → o job cria/atualiza/apaga o evento e guarda `externalEventId` no agendamento.

Leitura (Google → Secretar.ia): o job `pull-calendar` (a cada PULL_INTERVAL_MINUTES por conexão, e logo
após conectar/ressincronizar) lê `events.list` com `syncToken` incremental e espelha em `ExternalBusy` os
compromissos criados direto no Google; eles bloqueiam horários na disponibilidade da IA e aparecem no
calendário. Eventos da própria Secretar.ia, cancelados, "livres" (transparent) ou recusados pelo dono da
agenda não bloqueiam. Token expirado (410) ou leitura completa periódica refaz a janela e remove o que sumiu.

Push (opcional): com PUBLIC_API_URL em https, cada leitura garante um canal `events.watch` apontando para
`/api/integrations/google/notify`; a notificação do Google só enfileira o mesmo `pull-calendar` (deduplicado),
então a latência cai de minutos para segundos sem mudar o modelo. O canal é renovado antes de expirar.

Um refresh token inválido desliga a sincronização e avisa a clínica na inbox (nunca falha em silêncio).
"""

from __future__ import annotations

import hmac
import secrets
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import jwt

from app.config import Settings
from app.db import db
from app.errors import AppError, ConflictError
from app.integrations.google_calendar import (
    GoogleAuthExpired,
    GoogleOAuthError,
    GoogleSyncTokenInvalid,
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
PULL_CALENDAR = "pull-calendar"
BACKFILL_LIMIT = 200
EVENT_STATUSES = {"PENDING", "CONFIRMED", "COMPLETED", "NO_SHOW"}  # CANCELED remove o evento
PULL_INTERVAL_MINUTES = 10
PULL_WINDOW_PAST_HOURS = 24
PULL_WINDOW_DAYS = 60
FULL_PULL_EVERY_HOURS = 24  # a janela de tempo fica presa ao syncToken; refazer a leitura completa periodicamente
WATCH_TTL_SECONDS = 7 * 24 * 3600  # o Google limita canais de eventos a ~1 semana
WATCH_RENEW_BEFORE = timedelta(hours=12)


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
            "lastPullAt": None,
            "pushActive": False,
        }
    return {
        "connected": True,
        "accountEmail": conn.accountEmail,
        "calendarId": conn.calendarId,
        "syncEnabled": conn.syncEnabled,
        "lastSyncAt": conn.lastSyncAt.isoformat() if conn.lastSyncAt else None,
        "lastError": conn.lastError,
        "lastPullAt": conn.lastPullAt.isoformat() if conn.lastPullAt else None,
        "pushActive": bool(conn.channelId and conn.channelExpiresAt and conn.channelExpiresAt > datetime.now(UTC)),
    }


async def status(settings: Settings, tenant_id: str) -> dict[str, Any]:
    conn = await db.calendarconnection.find_unique(where={"tenantId": tenant_id})
    external = await db.externalbusy.count(where={"tenantId": tenant_id}) if conn else 0
    return {**connection_view(conn), "available": google_enabled(settings), "externalEvents": external}


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


async def complete_connect(
    settings: Settings, *, code: str | None, state: str | None, expected_user_id: str, expected_tenant_id: str
) -> str:
    """Troca o código por tokens e grava a conexão. Retorna o tenant_id. Lança AppError em falhas.

    Chamado pelo frontend AUTENTICADO após o redirect do Google: o `state` precisa ter sido gerado por este
    usuário para esta clínica. Isso impede que alguém induza a vítima a conectar a agenda dela à clínica errada."""
    payload = parse_state(settings, state)
    if payload is None:
        raise AppError("Estado da autorização inválido ou expirado. Tente conectar novamente.", code="invalid_state")
    tenant_id, user_id = payload["tid"], payload["sub"]
    if user_id != expected_user_id or tenant_id != expected_tenant_id:
        raise AppError(
            "Esta autorização foi iniciada por outra pessoa ou para outra clínica.",
            code="invalid_state",
            status_code=403,
        )
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
        if existing.accountEmail and tokens.email and existing.accountEmail != tokens.email:
            # Outra conta Google: token de sincronização, canal push e compromissos espelhados eram da anterior.
            data.update(
                {
                    "syncToken": None,
                    "channelId": None,
                    "channelResourceId": None,
                    "channelToken": None,
                    "channelExpiresAt": None,
                }
            )
            await db.externalbusy.delete_many(where={"tenantId": tenant_id})
            await db.appointment.update_many(where={"tenantId": tenant_id}, data={"externalEventId": None})
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
    await enqueue(PULL_CALENDAR, {"tenantId": tenant_id})
    return tenant_id


async def disconnect(settings: Settings, tenant, *, actor_user_id: str, ip: str | None) -> dict[str, Any]:
    conn = await db.calendarconnection.find_unique(where={"tenantId": tenant.id})
    if conn is None:
        return connection_view(None)
    try:
        provider = build_google_calendar_provider(settings)
        if conn.channelId and conn.channelResourceId:
            token = await _access_token(settings, provider, conn)
            await provider.stop_channel(
                access_token=token, channel_id=conn.channelId, resource_id=conn.channelResourceId
            )
        await provider.revoke(decrypt_secret(settings, conn.refreshTokenEnc))
    except Exception as exc:  # noqa: BLE001 - revogação/parada é cortesia; a conexão local é removida de qualquer forma
        log.warning("google_revoke_skipped", error=str(exc)[:200])
    await db.calendarconnection.delete(where={"id": conn.id})
    await db.externalbusy.delete_many(where={"tenantId": tenant.id})
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
    # Ressincronizar também relê o Google do zero (janela completa), para corrigir qualquer divergência.
    await db.calendarconnection.update(where={"id": conn.id}, data={"syncToken": None})
    await enqueue(PULL_CALENDAR, {"tenantId": tenant.id})
    await audit.record(
        action="calendar.resync_requested",
        resource_type="tenant",
        resource_id=tenant.id,
        tenant_id=tenant.id,
        actor_user_id=actor_user_id,
        metadata={"queued": queued},
        ip=ip,
    )
    return {"queued": queued, "pullQueued": True}


# ---------------------------- Leitura (Google → Secretar.ia) ----------------------------


def _is_ours(item: dict, our_ids: set[str]) -> bool:
    private = (item.get("extendedProperties") or {}).get("private") or {}
    return bool(private.get("secretariaAppointmentId")) or item.get("id") in our_ids


NON_BLOCKING_EVENT_TYPES = {"workingLocation", "birthday"}  # "Escritório/Casa" e aniversários não são compromissos


def blocks_time(item: dict) -> bool:
    """Evento cancelado, marcado como "livre", recusado pelo dono da agenda ou de tipo informativo não ocupa
    horário."""
    if item.get("status") == "cancelled" or item.get("transparency") == "transparent":
        return False
    if item.get("eventType") in NON_BLOCKING_EVENT_TYPES:
        return False
    for attendee in item.get("attendees") or []:
        if attendee.get("self") and attendee.get("responseStatus") == "declined":
            return False
    return True


def event_window(item: dict, tz: str) -> tuple[datetime, datetime, bool] | None:
    """(início UTC, fim UTC, dia inteiro) de um evento do Google; None se não tiver datas utilizáveis."""
    start, end = item.get("start") or {}, item.get("end") or {}
    zone = ZoneInfo(tz)
    if start.get("dateTime") and end.get("dateTime"):
        s = datetime.fromisoformat(start["dateTime"])
        e = datetime.fromisoformat(end["dateTime"])
        if s.tzinfo is None:
            s = s.replace(tzinfo=ZoneInfo(start.get("timeZone") or tz))
        if e.tzinfo is None:
            e = e.replace(tzinfo=ZoneInfo(end.get("timeZone") or tz))
        return s.astimezone(UTC), e.astimezone(UTC), False
    if start.get("date") and end.get("date"):
        sd, ed = date.fromisoformat(start["date"]), date.fromisoformat(end["date"])
        s = datetime(sd.year, sd.month, sd.day, tzinfo=zone).astimezone(UTC)
        e = datetime(ed.year, ed.month, ed.day, tzinfo=zone).astimezone(UTC)
        return s, e, True
    return None


async def _list_all(
    provider, token: str, conn, *, sync_token: str | None, now: datetime
) -> tuple[list[dict], str | None]:
    items: list[dict] = []
    page_token = None
    next_sync = None
    while True:
        if sync_token:
            page = await provider.list_events(
                access_token=token, calendar_id=conn.calendarId, sync_token=sync_token, page_token=page_token
            )
        else:
            page = await provider.list_events(
                access_token=token,
                calendar_id=conn.calendarId,
                time_min=now - timedelta(hours=PULL_WINDOW_PAST_HOURS),
                time_max=now + timedelta(days=PULL_WINDOW_DAYS),
                page_token=page_token,
            )
        items.extend(page.items)
        next_sync = page.next_sync_token or next_sync
        page_token = page.next_page_token
        if not page_token:
            return items, next_sync


async def _pull(provider, token: str, conn, tenant, now: datetime) -> dict[str, Any]:
    our_ids = {
        a.externalEventId
        for a in await db.appointment.find_many(
            where={
                "tenantId": conn.tenantId,
                "externalEventId": {"not": None},
                "date": {"gte": now - timedelta(days=2)},  # os antigos já saíram da janela de leitura
            }
        )
    }
    stale = conn.lastFullPullAt is None or now - conn.lastFullPullAt > timedelta(hours=FULL_PULL_EVERY_HOURS)
    full = conn.syncToken is None or stale
    try:
        items, next_sync = await _list_all(provider, token, conn, sync_token=None if full else conn.syncToken, now=now)
    except GoogleSyncTokenInvalid:
        full = True
        items, next_sync = await _list_all(provider, token, conn, sync_token=None, now=now)
    tz = tenant.timezone or "America/Sao_Paulo"
    upserted = removed = 0
    seen: set[str] = set()
    for item in items:
        eid = item.get("id")
        if not eid or _is_ours(item, our_ids):
            continue
        window = event_window(item, tz)
        if window is None or not blocks_time(item) or window[1] <= window[0]:
            removed += await db.externalbusy.delete_many(where={"tenantId": conn.tenantId, "externalId": eid})
            continue
        start, end, all_day = window
        seen.add(eid)
        data = {"summary": (item.get("summary") or "")[:200] or None, "startAt": start, "endAt": end, "allDay": all_day}
        await db.externalbusy.upsert(
            where={"tenantId_externalId": {"tenantId": conn.tenantId, "externalId": eid}},
            data={"create": {"tenantId": conn.tenantId, "externalId": eid, **data}, "update": data},
        )
        upserted += 1
    if full:
        # Leitura completa da janela: o que não veio deixou de existir (ou saiu da janela).
        where: dict[str, Any] = {"tenantId": conn.tenantId}
        if seen:
            where["externalId"] = {"not_in": sorted(seen)}
        removed += await db.externalbusy.delete_many(where=where)
    update: dict[str, Any] = {"syncToken": next_sync, "lastPullAt": now, "lastError": None}
    if full:
        update["lastFullPullAt"] = now
    await db.calendarconnection.update(where={"id": conn.id}, data=update)
    return {"status": "ok", "full": full, "upserted": upserted, "removed": removed, "events": len(items)}


async def pull_external_events(settings: Settings, *, tenant_id: str) -> dict[str, Any]:
    """Executado pela fila: espelha em ExternalBusy os compromissos do Google que não são nossos."""
    conn = await db.calendarconnection.find_unique(where={"tenantId": tenant_id})
    if conn is None or not conn.syncEnabled:
        return {"status": "skipped"}
    tenant = await db.tenant.find_unique(where={"id": tenant_id})
    if tenant is None:
        return {"status": "skipped"}
    provider = build_google_calendar_provider(settings)
    now = datetime.now(UTC)
    try:
        token = await _access_token(settings, provider, conn)
        try:
            result = await _pull(provider, token, conn, tenant, now)
        except GoogleAuthExpired:
            token = await _refresh_access_token(settings, provider, conn)
            result = await _pull(provider, token, conn, tenant, now)
    except GoogleOAuthError as exc:
        await _disable_connection(conn, f"oauth: {exc}")
        raise PermanentJobError(f"Google recusou a credencial ({exc}); sincronização desligada") from exc
    except ValueError as exc:
        await _disable_connection(conn, "credencial ilegível (chave de criptografia alterada)")
        raise PermanentJobError(str(exc)) from exc
    result["push"] = await ensure_watch(settings, provider, token, conn, now)
    log.info("calendar_pulled", **result)
    return result


# ------------------------------ Push (events.watch) ------------------------------


def notify_address(settings: Settings) -> str:
    return f"{settings.public_api_url.rstrip('/')}/api/integrations/google/notify"


def push_available(settings: Settings) -> bool:
    """O Google só entrega notificações em https com certificado válido; fora de produção o provider console
    aceita qualquer endereço, o que permite testar o fluxo inteiro."""
    if not settings.google_push_enabled:
        return False
    return settings.public_api_url.startswith("https://") or not settings.is_production_like


async def ensure_watch(settings: Settings, provider, token: str, conn, now: datetime) -> str:
    """Cria/renova o canal push da conexão. Retorna active|renewed|created|unavailable|failed."""
    if not push_available(settings):
        return "unavailable"
    if conn.channelId and conn.channelExpiresAt and conn.channelExpiresAt - now > WATCH_RENEW_BEFORE:
        return "active"
    channel_id = str(uuid.uuid4())
    secret = secrets.token_urlsafe(32)
    try:
        channel = await provider.watch(
            access_token=token,
            calendar_id=conn.calendarId,
            channel_id=channel_id,
            address=notify_address(settings),
            token=secret,
            ttl_seconds=WATCH_TTL_SECONDS,
        )
    except Exception as exc:  # noqa: BLE001 - push é otimização: a leitura periódica segue funcionando
        log.warning("google_watch_failed", error=str(exc)[:200])
        return "failed"
    # Grava o canal novo ANTES de parar o antigo: se o stop falhar, nada vaza nem se perde.
    await db.calendarconnection.update(
        where={"id": conn.id},
        data={
            "channelId": channel.channel_id,
            "channelResourceId": channel.resource_id,
            "channelToken": secret,
            "channelExpiresAt": channel.expires_at,
        },
    )
    if conn.channelId and conn.channelResourceId:
        try:
            await provider.stop_channel(
                access_token=token, channel_id=conn.channelId, resource_id=conn.channelResourceId
            )
        except Exception as exc:  # noqa: BLE001 - canal antigo expira sozinho em até 7 dias
            log.warning("google_stop_channel_failed", error=str(exc)[:200])
    return "renewed" if conn.channelId else "created"


async def enqueue_pull_if_idle(tenant_id: str) -> bool:
    pending = await db.query_raw(
        """
        SELECT 1 FROM "Job"
        WHERE name = $1 AND status IN ('PENDING', 'RUNNING') AND payload->>'tenantId' = $2
        LIMIT 1
        """,
        PULL_CALENDAR,
        tenant_id,
    )
    if pending:
        return False
    await enqueue(PULL_CALENDAR, {"tenantId": tenant_id})
    return True


async def handle_push_notification(*, channel_id: str | None, token: str | None, state: str | None) -> str:
    """Webhook do Google. Retorna ignored|sync|queued|duplicate; lança AppError 403 para token errado."""
    if not channel_id:
        return "ignored"
    conn = await db.calendarconnection.find_unique(where={"channelId": channel_id})
    if conn is None:
        log.info("google_push_unknown_channel", channel_id=channel_id[:36])
        return "ignored"  # canal antigo (já trocado/desconectado): responder 2xx evita retentativas do Google
    if not conn.channelToken or not token or not hmac.compare_digest(conn.channelToken, token):
        raise AppError("Token do canal inválido.", code="forbidden", status_code=403)
    if state == "sync":
        return "sync"  # handshake de criação do canal
    if not conn.syncEnabled:
        return "ignored"
    return "queued" if await enqueue_pull_if_idle(conn.tenantId) else "duplicate"


async def schedule_pulls() -> int:
    """Enfileira uma leitura por conexão ativa, sem duplicar se já houver uma pendente/rodando."""
    conns = await db.calendarconnection.find_many(where={"syncEnabled": True})
    queued = 0
    for conn in conns:
        queued += int(await enqueue_pull_if_idle(conn.tenantId))
    return queued


async def purge_past_external_busy(now: datetime | None = None) -> int:
    now = now or datetime.now(UTC)
    return await db.externalbusy.delete_many(where={"endAt": {"lt": now - timedelta(days=2)}})
