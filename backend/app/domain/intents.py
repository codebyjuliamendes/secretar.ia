"""Classificador de intenção por regras.

Usado (a) como fallback quando o provedor de IA está indisponível ou não configurado e
(b) como sanity check do rótulo devolvido pelo LLM.
"""

from __future__ import annotations

import re
import unicodedata
from enum import StrEnum


class Intent(StrEnum):
    SCHEDULE = "AGENDAR"
    CANCEL = "CANCELAR"
    INFO = "INFO"
    HUMAN = "HUMANO"
    GREETING = "SAUDACAO"


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text).strip()


_HUMAN = ("atendente", "humano", "pessoa de verdade", "falar com alguem", "reclamacao", "urgente", "ajuda")
_CANCEL = ("cancelar", "desmarcar", "nao vou poder", "remarcar", "adiar")
_SCHEDULE = ("agendar", "marcar", "horario", "consulta", "quero fazer", "aplicacao", "sessao", "vaga")
_INFO = (
    "preco",
    "valor",
    "quanto custa",
    "funcionamento",
    "endereco",
    "horario de atendimento",
    "abre",
    "fecha",
)
_GREETING = ("oi", "ola", "bom dia", "boa tarde", "boa noite", "hey", "e ai")


def classify(text: str) -> Intent:
    t = normalize(text)
    if any(k in t for k in _HUMAN):
        return Intent.HUMAN
    if any(k in t for k in _CANCEL):
        return Intent.CANCEL
    if any(k in t for k in _INFO):
        return Intent.INFO
    if any(k in t for k in _SCHEDULE):
        return Intent.SCHEDULE
    bare = re.sub(r"[^\w\s]", "", t).strip()
    if bare in _GREETING or any(bare.startswith(g + " ") for g in _GREETING):
        return Intent.GREETING
    return Intent.INFO


def coerce_intent(value: str | None) -> Intent | None:
    if not value:
        return None
    v = normalize(value).upper().replace("Ç", "C")
    aliases = {
        "AGENDAR": Intent.SCHEDULE,
        "SCHEDULE": Intent.SCHEDULE,
        "CANCELAR": Intent.CANCEL,
        "CANCEL": Intent.CANCEL,
        "INFO": Intent.INFO,
        "INFORMACAO": Intent.INFO,
        "HUMANO": Intent.HUMAN,
        "HUMAN": Intent.HUMAN,
        "SAUDACAO": Intent.GREETING,
        "GREETING": Intent.GREETING,
    }
    return aliases.get(v)
