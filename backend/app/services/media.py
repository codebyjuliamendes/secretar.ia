"""Mídia recebida do paciente (áudio e imagem) convertida em texto para o pipeline da conversa.

Usa o Gemini multimodal (mesmo provedor da IA de atendimento): áudio → transcrição literal;
imagem → descrição objetiva, sem diagnóstico. Sem chave de IA, devolve None e a conversa responde com
uma mensagem clara pedindo texto (nunca finge ter entendido).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config import Settings
from app.integrations.gemini import AIProviderError, GeminiClient
from app.logging import get_logger

log = get_logger("media")

MAX_AUDIO_BYTES = 16 * 1024 * 1024
MAX_IMAGE_BYTES = 8 * 1024 * 1024
SUPPORTED_KINDS = ("audio", "image")

AUDIO_PROMPT = (
    "Transcreva fielmente o áudio a seguir, em português do Brasil, sem comentários, sem resumir e sem "
    "adicionar informações. Se o áudio estiver inaudível ou vazio, responda exatamente: [inaudível]."
)
IMAGE_PROMPT = (
    "Descreva objetivamente esta imagem enviada por um paciente a uma clínica, em até 3 frases curtas em "
    "português do Brasil. Diga o tipo de conteúdo (ex.: foto de documento, comprovante de pagamento, exame, "
    "print de conversa, foto de uma região do corpo, produto) e transcreva textos legíveis relevantes "
    "(datas, valores, nomes de procedimentos). Nunca faça diagnóstico nem avaliação clínica."
)


@dataclass
class MediaInput:
    kind: str  # audio | image
    data: bytes
    mime_type: str
    caption: str | None = None


@dataclass
class MediaText:
    text: str  # texto que entra na conversa como mensagem do paciente
    summary: str  # transcrição/descrição pura
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None


def client_for(settings: Settings) -> GeminiClient | None:
    """Fábrica isolada para testes poderem injetar um cliente falso."""
    if not settings.gemini_api_key:
        return None
    return GeminiClient(
        settings.gemini_api_key, settings.gemini_model, settings.ai_timeout_seconds, settings.ai_max_output_tokens
    )


def size_ok(media: MediaInput) -> bool:
    limit = MAX_AUDIO_BYTES if media.kind == "audio" else MAX_IMAGE_BYTES
    return 0 < len(media.data) <= limit


def unsupported_reply(kind: str, *, too_large: bool = False) -> str:
    noun = "seu áudio" if kind == "audio" else "sua imagem"
    if too_large:
        return f"Recebi {noun}, mas o arquivo é grande demais para eu processar. Pode me enviar por texto?"
    return f"Recebi {noun}, mas no momento só consigo ler mensagens de texto por aqui. Pode me escrever?"


def compose_text(kind: str, summary: str, caption: str | None) -> str:
    if kind == "audio":
        return f"[Áudio do paciente, transcrito] {summary}"
    text = f"[Imagem enviada pelo paciente. Descrição: {summary}]"
    if caption:
        text += f" Legenda: {caption}"
    return text


async def media_to_text(settings: Settings, media: MediaInput) -> MediaText | None:
    """Converte a mídia em texto. None = não foi possível (IA ausente, tamanho, falha do provedor)."""
    if media.kind not in SUPPORTED_KINDS or not size_ok(media):
        return None
    client = client_for(settings)
    if client is None:
        return None
    prompt = AUDIO_PROMPT if media.kind == "audio" else IMAGE_PROMPT
    try:
        result = await client.describe_media(prompt, media.data, media.mime_type, max_output_tokens=1024)
    except AIProviderError as exc:
        log.warning("media_provider_failed", kind=media.kind, error=str(exc)[:200])
        return None
    summary = " ".join(result.text.split()).strip()
    if not summary:
        return None
    return MediaText(
        text=compose_text(media.kind, summary, media.caption),
        summary=summary,
        model=result.model,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
    )
