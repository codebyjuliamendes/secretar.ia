"""Google Calendar por clínica: OAuth 2.0 (código + refresh) e eventos, via REST com httpx.

Sem GOOGLE_CLIENT_ID/SECRET em development/test usa o provider `console` (em memória, sem rede).
Em produção, ausência de credenciais é erro explícito.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode

import httpx

from app.config import Settings
from app.errors import IntegrationUnavailableError
from app.logging import get_logger

log = get_logger("integrations.google_calendar")

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
CALENDAR_URL = "https://www.googleapis.com/calendar/v3"
SCOPES = "openid email https://www.googleapis.com/auth/calendar.events"


class GoogleTransientError(Exception):
    """Timeout/5xx/429: a fila retenta com backoff."""


class GoogleAuthExpired(Exception):
    """Access token recusado (401): renovar e repetir uma vez."""


class GoogleOAuthError(Exception):
    """Falha permanente de credencial (invalid_grant, acesso revogado): exige reconectar."""


@dataclass
class OAuthTokens:
    access_token: str
    expires_in: int
    refresh_token: str | None = None
    email: str | None = None


class GoogleCalendarProvider:
    def auth_url(self, *, state: str, redirect_uri: str) -> str: ...

    async def exchange_code(self, *, code: str, redirect_uri: str) -> OAuthTokens: ...

    async def refresh(self, refresh_token: str) -> OAuthTokens: ...

    async def revoke(self, token: str) -> None: ...

    async def upsert_event(self, *, access_token: str, calendar_id: str, event_id: str | None, body: dict) -> str: ...

    async def delete_event(self, *, access_token: str, calendar_id: str, event_id: str) -> None: ...


@dataclass
class ConsoleGoogleCalendarProvider(GoogleCalendarProvider):
    """Desenvolvimento/testes: guarda eventos em memória e aceita qualquer código."""

    events: dict[str, dict] = field(default_factory=dict)
    revoked: list[str] = field(default_factory=list)
    refreshes: int = 0
    _seq: itertools.count = field(default_factory=lambda: itertools.count(1))

    def auth_url(self, *, state: str, redirect_uri: str) -> str:
        return f"{redirect_uri}?{urlencode({'state': state, 'code': 'console'})}"

    async def exchange_code(self, *, code: str, redirect_uri: str) -> OAuthTokens:
        if code != "console":
            raise GoogleOAuthError("código inválido (console)")
        return OAuthTokens(
            access_token="console-access",
            expires_in=3600,
            refresh_token="console-refresh",
            email="agenda@console.local",
        )

    async def refresh(self, refresh_token: str) -> OAuthTokens:
        self.refreshes += 1
        if refresh_token in self.revoked:
            raise GoogleOAuthError("invalid_grant")
        return OAuthTokens(access_token=f"console-access-{self.refreshes}", expires_in=3600)

    async def revoke(self, token: str) -> None:
        self.revoked.append(token)

    async def upsert_event(self, *, access_token, calendar_id, event_id, body):
        eid = event_id or f"console-evt-{next(self._seq)}"
        self.events[eid] = {**body, "calendarId": calendar_id}
        return eid

    async def delete_event(self, *, access_token, calendar_id, event_id):
        self.events.pop(event_id, None)


class HttpGoogleCalendarProvider(GoogleCalendarProvider):
    def __init__(self, client_id: str, client_secret: str, timeout: float = 15.0):
        self._id = client_id
        self._secret = client_secret
        self._timeout = timeout

    def auth_url(self, *, state: str, redirect_uri: str) -> str:
        params = {
            "client_id": self._id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": SCOPES,
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
            "state": state,
        }
        return f"{AUTH_URL}?{urlencode(params)}"

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                return await client.request(method, url, **kwargs)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise GoogleTransientError(f"Google indisponível: {exc.__class__.__name__}") from exc

    async def _token_request(self, data: dict[str, str]) -> OAuthTokens:
        form = {**data, "client_id": self._id, "client_secret": self._secret}
        resp = await self._request("POST", TOKEN_URL, data=form)
        if resp.status_code >= 500 or resp.status_code == 429:
            raise GoogleTransientError(f"Google token endpoint respondeu {resp.status_code}")
        payload = resp.json() if resp.content else {}
        if resp.status_code >= 400:
            err = str(payload.get("error") or "oauth_error")
            log.warning("google_oauth_error", error=err, description=str(payload.get("error_description") or "")[:200])
            raise GoogleOAuthError(err)
        return OAuthTokens(
            access_token=str(payload["access_token"]),
            expires_in=int(payload.get("expires_in") or 3600),
            refresh_token=payload.get("refresh_token"),
        )

    async def exchange_code(self, *, code: str, redirect_uri: str) -> OAuthTokens:
        tokens = await self._token_request(
            {"code": code, "grant_type": "authorization_code", "redirect_uri": redirect_uri}
        )
        info = await self._request("GET", USERINFO_URL, headers={"Authorization": f"Bearer {tokens.access_token}"})
        if info.status_code == 200:
            tokens.email = (info.json() or {}).get("email")
        return tokens

    async def refresh(self, refresh_token: str) -> OAuthTokens:
        return await self._token_request({"refresh_token": refresh_token, "grant_type": "refresh_token"})

    async def revoke(self, token: str) -> None:
        try:
            await self._request("POST", REVOKE_URL, data={"token": token})
        except GoogleTransientError:
            log.warning("google_revoke_failed")

    async def _calendar(self, method: str, access_token: str, path: str, json: dict | None = None) -> dict:
        resp = await self._request(
            method,
            f"{CALENDAR_URL}{path}",
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
            json=json,
        )
        if resp.status_code == 401:
            raise GoogleAuthExpired()
        if resp.status_code in (404, 410) and method == "DELETE":
            return {}
        if resp.status_code >= 500 or resp.status_code == 429:
            raise GoogleTransientError(f"Google Calendar respondeu {resp.status_code}")
        if resp.status_code == 403:
            raise GoogleOAuthError("insufficient_permissions")
        if resp.status_code >= 400:
            raise IntegrationUnavailableError(
                f"Google Calendar rejeitou a operação ({resp.status_code}).", code="google_calendar_error"
            )
        try:
            return resp.json() if resp.content else {}
        except ValueError:
            return {}

    async def upsert_event(self, *, access_token, calendar_id, event_id, body):
        if event_id:
            try:
                data = await self._calendar("PATCH", access_token, f"/calendars/{calendar_id}/events/{event_id}", body)
                return str(data.get("id") or event_id)
            except IntegrationUnavailableError:
                pass  # evento apagado manualmente no Google: recria abaixo
        data = await self._calendar("POST", access_token, f"/calendars/{calendar_id}/events", body)
        return str(data["id"])

    async def delete_event(self, *, access_token, calendar_id, event_id):
        await self._calendar("DELETE", access_token, f"/calendars/{calendar_id}/events/{event_id}")


_console = ConsoleGoogleCalendarProvider()


def build_google_calendar_provider(settings: Settings) -> GoogleCalendarProvider:
    if settings.google_client_id and settings.google_client_secret:
        return HttpGoogleCalendarProvider(settings.google_client_id, settings.google_client_secret)
    if settings.is_production_like:
        raise IntegrationUnavailableError(
            "Integração com Google Calendar não configurada (GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET).",
            code="google_not_configured",
        )
    return _console


def google_enabled(settings: Settings) -> bool:
    return bool(settings.google_client_id and settings.google_client_secret) or not settings.is_production_like
