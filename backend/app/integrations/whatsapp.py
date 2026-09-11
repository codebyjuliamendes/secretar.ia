"""Camada de integração com WhatsApp via Evolution API.

Toda chamada externa passa por aqui: timeout, tratamento de indisponibilidade e rate limit.
Sem EVOLUTION_API_URL configurada em desenvolvimento, usa o provider `console` (apenas loga).
Em produção, ausência de configuração é erro explícito, nunca sucesso silencioso.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass

import httpx

from app.config import Settings
from app.errors import IntegrationUnavailableError
from app.logging import get_logger

log = get_logger("integrations.whatsapp")


class WhatsAppRateLimited(Exception):
    """Sinaliza rate limit do provedor; a fila fará retry com backoff."""


class WhatsAppTransientError(Exception):
    """Falha temporária (5xx, timeout); a fila fará retry."""


@dataclass
class ConnectionInfo:
    connected: bool
    state: str
    qr_code_base64: str | None = None


@dataclass
class MediaPayload:
    data: bytes
    mime_type: str


class WhatsAppProvider:
    async def send_text(self, instance: str, phone: str, text: str) -> str: ...

    async def create_instance(self, instance: str, webhook_url: str) -> ConnectionInfo: ...

    async def connection_state(self, instance: str) -> ConnectionInfo: ...

    async def logout_instance(self, instance: str) -> None: ...

    async def download_media(self, instance: str, message_key: dict) -> MediaPayload | None:
        """Baixa a mídia de uma mensagem. None quando o provider não tem acesso ao conteúdo."""
        return None


class ConsoleWhatsAppProvider(WhatsAppProvider):
    """Provider de desenvolvimento: registra a mensagem no log e devolve um id sintético."""

    async def send_text(self, instance: str, phone: str, text: str) -> str:
        log.info("whatsapp_console_send", instance=instance, phone=phone, text=text)
        return f"console-{instance}-{phone}"

    async def create_instance(self, instance: str, webhook_url: str) -> ConnectionInfo:
        # QR ilustrativo apenas em desenvolvimento (PNG 1x1). Em produção este provider não é usado.
        px = base64.b64encode(
            bytes.fromhex(
                "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d4944415478"
                "9c63f8ffff3f0300050001019a6d8b6e0000000049454e44ae426082"
            )
        ).decode()
        return ConnectionInfo(connected=False, state="connecting", qr_code_base64=px)

    async def connection_state(self, instance: str) -> ConnectionInfo:
        return ConnectionInfo(connected=True, state="open")

    async def logout_instance(self, instance: str) -> None:
        log.info("whatsapp_console_logout", instance=instance)


class EvolutionWhatsAppProvider(WhatsAppProvider):
    def __init__(self, base_url: str, api_key: str, timeout: float = 15.0):
        self._base = base_url.rstrip("/")
        self._headers = {"apikey": api_key, "Content-Type": "application/json"}
        self._timeout = timeout

    async def _request(self, method: str, path: str, json: dict | None = None) -> dict:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.request(method, f"{self._base}{path}", headers=self._headers, json=json)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise WhatsAppTransientError(f"Evolution API indisponível: {exc.__class__.__name__}") from exc
        if resp.status_code == 429:
            raise WhatsAppRateLimited("Evolution API rate limit")
        if resp.status_code >= 500:
            raise WhatsAppTransientError(f"Evolution API respondeu {resp.status_code}")
        if resp.status_code >= 400:
            raise IntegrationUnavailableError(
                f"Evolution API rejeitou a requisição ({resp.status_code}).", code="whatsapp_error"
            )
        try:
            return resp.json() if resp.content else {}
        except ValueError:
            return {}

    async def send_text(self, instance: str, phone: str, text: str) -> str:
        data = await self._request("POST", f"/message/sendText/{instance}", {"number": phone, "text": text})
        return str((data.get("key") or {}).get("id") or data.get("messageId") or "")

    async def create_instance(self, instance: str, webhook_url: str) -> ConnectionInfo:
        payload = {
            "instanceName": instance,
            "qrcode": True,
            "integration": "WHATSAPP-BAILEYS",
            "webhook": {
                "url": webhook_url,
                "byEvents": False,
                "base64": False,
                "events": ["MESSAGES_UPSERT", "CONNECTION_UPDATE"],
            },
        }
        data = await self._request("POST", "/instance/create", payload)
        qr = (data.get("qrcode") or {}).get("base64")
        if qr and qr.startswith("data:image"):
            qr = qr.split(",", 1)[1]
        return ConnectionInfo(connected=False, state="connecting", qr_code_base64=qr)

    async def connection_state(self, instance: str) -> ConnectionInfo:
        data = await self._request("GET", f"/instance/connectionState/{instance}")
        state = str((data.get("instance") or {}).get("state") or data.get("state") or "unknown")
        if state != "open":
            try:
                qr_data = await self._request("GET", f"/instance/connect/{instance}")
                qr = qr_data.get("base64")
                if qr and qr.startswith("data:image"):
                    qr = qr.split(",", 1)[1]
                return ConnectionInfo(connected=False, state=state, qr_code_base64=qr)
            except (IntegrationUnavailableError, WhatsAppTransientError):
                return ConnectionInfo(connected=False, state=state)
        return ConnectionInfo(connected=True, state=state)

    async def logout_instance(self, instance: str) -> None:
        await self._request("DELETE", f"/instance/logout/{instance}")

    async def download_media(self, instance: str, message_key: dict) -> MediaPayload | None:
        data = await self._request(
            "POST",
            f"/chat/getBase64FromMediaMessage/{instance}",
            {"message": {"key": message_key}, "convertToMp4": False},
        )
        b64 = data.get("base64")
        if not b64:
            return None
        if isinstance(b64, str) and b64.startswith("data:"):
            b64 = b64.split(",", 1)[1]
        try:
            raw = base64.b64decode(b64)
        except (ValueError, TypeError):
            return None
        return MediaPayload(data=raw, mime_type=str(data.get("mimetype") or "application/octet-stream"))


def build_whatsapp_provider(settings: Settings) -> WhatsAppProvider:
    if settings.evolution_api_url and settings.evolution_api_key:
        return EvolutionWhatsAppProvider(settings.evolution_api_url, settings.evolution_api_key)
    if settings.is_production_like:
        raise IntegrationUnavailableError(
            "Integração com WhatsApp não configurada (EVOLUTION_API_URL/EVOLUTION_API_KEY).",
            code="whatsapp_not_configured",
        )
    return ConsoleWhatsAppProvider()


def parse_evolution_message(payload: dict) -> dict | None:
    """Normaliza o evento MESSAGES_UPSERT da Evolution API. Retorna None para eventos ignoráveis."""
    event = str(payload.get("event") or "").lower().replace("_", ".")
    if event not in ("messages.upsert",):
        return None
    data = payload.get("data") or {}
    if isinstance(data, list):
        data = data[0] if data else {}
    key = data.get("key") or {}
    if key.get("fromMe"):
        return None
    remote_jid = str(key.get("remoteJid") or "")
    if not remote_jid or remote_jid.endswith("@g.us"):  # ignora grupos
        return None
    message = data.get("message") or {}
    text = message.get("conversation") or (message.get("extendedTextMessage") or {}).get("text") or ""
    base = {
        "message_id": str(key.get("id") or ""),
        "remote_jid": remote_jid,
        "push_name": data.get("pushName"),
        "instance": payload.get("instance"),
        "message_key": {k: key.get(k) for k in ("remoteJid", "fromMe", "id", "participant") if key.get(k) is not None},
    }
    if text:
        return {**base, "text": str(text)}
    for field, kind in (("audioMessage", "audio"), ("imageMessage", "image")):
        media = message.get(field)
        if isinstance(media, dict):
            caption = str(media.get("caption") or "").strip() or None
            return {
                **base,
                "text": caption or "",
                "media": {"kind": kind, "mimetype": str(media.get("mimetype") or ""), "caption": caption},
            }
    return {"unsupported": True, "message_id": base["message_id"], "remote_jid": remote_jid}
