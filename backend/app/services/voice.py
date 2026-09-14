"""Responder áudio com áudio (experimental): texto da resposta → voz (Gemini TTS) → WhatsApp.

Best-effort por desenho: qualquer falha (TTS fora, provedor sem suporte, áudio vazio) cai para a resposta em
texto, que é o que o cliente já recebe hoje. Nunca deixamos a pessoa sem resposta por causa da voz.
"""

from __future__ import annotations

import base64
import io
import wave

from app.config import Settings
from app.integrations.gemini import AIProviderError, GeminiClient
from app.logging import get_logger

log = get_logger("voice")

MAX_TTS_CHARS = 900  # respostas longas viram texto: áudio de 2 minutos ninguém ouve


def tts_client(settings: Settings) -> GeminiClient | None:
    """Fábrica isolada (testes injetam um cliente falso)."""
    if not settings.gemini_api_key:
        return None
    return GeminiClient(settings.gemini_api_key, settings.gemini_tts_model, settings.tts_timeout_seconds, 512)


def pcm_to_wav(pcm: bytes, *, rate: int = 24_000, channels: int = 1, sample_width: int = 2) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(sample_width)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


async def synthesize(settings: Settings, text: str) -> tuple[str, str] | None:
    """Retorna (base64 do áudio, mime) ou None quando não dá para falar essa resposta."""
    clean = " ".join((text or "").split())
    if not clean or len(clean) > MAX_TTS_CHARS:
        return None
    client = tts_client(settings)
    if client is None:
        return None
    try:
        pcm, mime = await client.synthesize_speech(clean, voice=settings.tts_voice)
    except AIProviderError as exc:
        log.warning("tts_failed", error=str(exc)[:200])
        return None
    if not pcm:
        return None
    if "wav" in mime or "wave" in mime:
        return base64.b64encode(pcm).decode(), "audio/wav"
    rate = 24_000
    for part in mime.split(";"):
        if part.strip().startswith("rate="):
            try:
                rate = int(part.split("=", 1)[1])
            except ValueError:
                pass
    return base64.b64encode(pcm_to_wav(pcm, rate=rate)).decode(), "audio/wav"
