"""Cliente Google Gemini (REST via httpx, sem SDK) com timeout e saída estruturada em JSON."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass

import httpx

from app.logging import get_logger

log = get_logger("integrations.gemini")

_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class AIProviderError(Exception):
    pass


@dataclass
class AIResult:
    text: str
    input_tokens: int | None
    output_tokens: int | None
    model: str


class GeminiClient:
    def __init__(self, api_key: str, model: str, timeout: float, max_output_tokens: int):
        self._key = api_key
        self.model = model
        self._timeout = timeout
        self._max_tokens = max_output_tokens

    async def generate_json(self, system_prompt: str, messages: list[dict], schema: dict) -> AIResult:
        """messages: [{"role": "user"|"assistant", "content": str}] em ordem cronológica."""
        contents = [
            {"role": "user" if m["role"] == "user" else "model", "parts": [{"text": m["content"]}]} for m in messages
        ]
        body = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": contents,
            "generationConfig": {
                "temperature": 0.4,
                "maxOutputTokens": self._max_tokens,
                "responseMimeType": "application/json",
                "responseSchema": schema,
            },
            "safetySettings": [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_ONLY_HIGH"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_ONLY_HIGH"},
            ],
        }
        return await self._generate(body)

    async def describe_media(
        self, prompt: str, data: bytes, mime_type: str, *, max_output_tokens: int | None = None
    ) -> AIResult:
        """Entrada multimodal (áudio/imagem inline) → texto livre. Usado para transcrição e descrição."""
        body = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": prompt},
                        {
                            "inlineData": {
                                "mimeType": mime_type.split(";")[0].strip(),
                                "data": base64.b64encode(data).decode(),
                            }
                        },
                    ],
                }
            ],
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": max_output_tokens or self._max_tokens},
        }
        return await self._generate(body)

    async def embed(self, texts: list[str], *, model: str, task_type: str, dims: int) -> list[list[float]]:
        """Embeddings em lote (batchEmbedContents). Mantém a ordem de `texts`."""
        if not texts:
            return []
        body = {
            "requests": [
                {
                    "model": f"models/{model}",
                    "content": {"parts": [{"text": t}]},
                    "taskType": task_type,
                    "outputDimensionality": dims,
                }
                for t in texts
            ]
        }
        url = f"{_BASE}/{model}:batchEmbedContents"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(url, params={"key": self._key}, json=body)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise AIProviderError(f"Gemini indisponível: {exc.__class__.__name__}") from exc
        if resp.status_code != 200:
            raise AIProviderError(f"Gemini embeddings respondeu {resp.status_code}")
        try:
            vectors = [e["values"] for e in resp.json()["embeddings"]]
        except (KeyError, TypeError, ValueError) as exc:
            raise AIProviderError("Resposta inválida do Gemini (embeddings)") from exc
        if len(vectors) != len(texts):
            raise AIProviderError("Gemini devolveu número inesperado de embeddings")
        return vectors

    async def _generate(self, body: dict) -> AIResult:
        url = f"{_BASE}/{self.model}:generateContent"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(url, params={"key": self._key}, json=body)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise AIProviderError(f"Gemini indisponível: {exc.__class__.__name__}") from exc
        if resp.status_code != 200:
            raise AIProviderError(f"Gemini respondeu {resp.status_code}")
        try:
            data = resp.json()
        except ValueError as exc:
            raise AIProviderError("Resposta do Gemini não é JSON") from exc
        try:
            parts = data["candidates"][0]["content"]["parts"]
            text = "".join(str(p.get("text", "")) for p in parts if isinstance(p, dict))
            if not text:
                raise KeyError("text")
        except (KeyError, IndexError, TypeError) as exc:
            reason = (data.get("promptFeedback") or {}).get("blockReason")
            raise AIProviderError(f"Resposta inválida do Gemini (blockReason={reason})") from exc
        usage = data.get("usageMetadata") or {}
        return AIResult(
            text=text,
            input_tokens=usage.get("promptTokenCount"),
            output_tokens=usage.get("candidatesTokenCount"),
            model=self.model,
        )


def parse_json_output(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AIProviderError("Saída do modelo não é JSON válido") from exc
    if not isinstance(parsed, dict):
        raise AIProviderError("Saída do modelo não é um objeto JSON")
    return parsed
