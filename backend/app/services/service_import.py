"""Importar o catálogo de serviços a partir de uma foto, print ou PDF da tabela de preços.

O cliente manda o que já tem (cardápio de serviços, tabela impressa, print do Instagram) e o Gemini extrai
nome, preço e duração. Nada é gravado sem o cliente ver: devolvemos uma prévia; a confirmação cria os serviços.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.config import Settings
from app.errors import AppError
from app.integrations.gemini import AIProviderError, GeminiClient, parse_json_output
from app.services import knowledge_sources
from app.services import media as media_service

MAX_IMPORT_BYTES = 10 * 1024 * 1024
IMAGE_MIMES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}
MAX_ITEMS = 80

EXTRACT_PROMPT = (
    "Você recebe uma tabela de serviços e preços de um pequeno negócio (imagem ou texto). Extraia cada serviço "
    "como um objeto JSON com: name (string curta, sem preço), priceCents (inteiro em centavos, ou null se não "
    "houver preço), durationMin (inteiro em minutos se estiver escrito, senão null), description (string curta "
    "ou null). Ignore títulos, categorias e textos que não sejam serviços. Responda SOMENTE um JSON no formato "
    '{"items": [...]}. Não invente valores.'
)


@dataclass
class ImportedService:
    name: str
    priceCents: int | None
    durationMin: int | None
    description: str | None


def client_for(settings: Settings) -> GeminiClient | None:
    return media_service.client_for(settings)


def _clean_items(raw: Any) -> list[dict]:
    items = raw.get("items") if isinstance(raw, dict) else raw
    out: list[dict] = []
    seen: set[str] = set()
    for it in items or []:
        if not isinstance(it, dict):
            continue
        name = str(it.get("name") or "").strip()[:120]
        if len(name) < 2 or name.lower() in seen:
            continue
        seen.add(name.lower())
        price = it.get("priceCents")
        duration = it.get("durationMin")
        out.append(
            {
                "name": name,
                "priceCents": int(price) if isinstance(price, (int, float)) and 0 <= price <= 100_000_000 else None,
                "durationMin": int(duration) if isinstance(duration, (int, float)) and 5 <= duration <= 600 else None,
                "description": (str(it.get("description")).strip()[:1000] or None) if it.get("description") else None,
            }
        )
        if len(out) >= MAX_ITEMS:
            break
    return out


async def extract_services(settings: Settings, data: bytes, mime_type: str, filename: str) -> list[dict]:
    """Foto/print → Gemini multimodal; PDF → texto (com OCR se for digitalizado) → Gemini em modo JSON."""
    client = client_for(settings)
    if client is None:
        raise AppError(
            "A leitura automática não está disponível neste ambiente.", code="ai_unavailable", status_code=503
        )
    ctype = (mime_type or "").split(";")[0].strip().lower()
    lower = filename.lower()
    try:
        if ctype == knowledge_sources.PDF_MIME or lower.endswith(".pdf"):
            pdf = await knowledge_sources.extract_pdf_text(settings, data)
            result = await client.generate_json(
                EXTRACT_PROMPT,
                [{"role": "user", "content": pdf.text[:40_000]}],
                {"type": "object", "properties": {"items": {"type": "array"}}},
            )
        elif ctype in IMAGE_MIMES or lower.endswith((".jpg", ".jpeg", ".png", ".webp")):
            if len(data) > media_service.MAX_IMAGE_BYTES:
                raise AppError("Imagem acima de 8 MB.", code="file_too_large", status_code=413)
            result = await client.describe_media(EXTRACT_PROMPT, data, ctype or "image/jpeg", max_output_tokens=4096)
        else:
            raise AppError("Envie uma foto (JPG, PNG, WebP) ou um PDF.", code="unsupported_file")
    except AIProviderError as exc:
        raise AppError(
            "Não consegui ler o arquivo agora. Tente de novo em instantes.", code="ai_failed", status_code=502
        ) from exc
    items = _clean_items(parse_json_output(result.text))
    if not items:
        raise AppError(
            "Não encontrei serviços com preço nesse arquivo. Tente uma foto mais nítida.", code="no_services_found"
        )
    return items


async def confirm_import(tenant_id: str, items: list[dict], *, actor_user_id: str, ip: str | None) -> dict:
    """Cria os serviços confirmados; nomes já existentes são pulados (não sobrescrevemos o que o cliente ajustou)."""
    from app.errors import ConflictError
    from app.services import scheduling

    created, skipped = [], []
    for i, it in enumerate(items):
        payload = {
            "name": it["name"],
            "durationMin": it.get("durationMin") or 60,
            "priceCents": it.get("priceCents"),
            "description": it.get("description"),
            "active": True,
            "sortOrder": i,
        }
        try:
            created.append(await scheduling.create_service(tenant_id, payload, actor_user_id=actor_user_id, ip=ip))
        except ConflictError:
            skipped.append(it["name"])
    return {"created": created, "skipped": skipped}


async def read_upload(file) -> bytes:
    data = await file.read(MAX_IMPORT_BYTES + 1)
    if len(data) > MAX_IMPORT_BYTES:
        raise AppError("Arquivo acima de 10 MB.", code="file_too_large", status_code=413)
    if not data:
        raise AppError("Arquivo vazio.", code="empty_file")
    return data
