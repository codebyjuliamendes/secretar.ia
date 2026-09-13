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


# "ajuda" NÃO entra aqui: "pode me ajudar a agendar?" é um pedido de agendamento, não de humano.
_HUMAN = (
    "atendente",
    "humano",
    "humana",
    "pessoa de verdade",
    "uma pessoa",
    "falar com alguem",
    "falar com a ",
    "falar com o ",
    "falar com um",
    "alguem da clinica",
    "reclamacao",
    "urgente",
)
# Remarcar não é cancelar: vira pedido de horário (a IA/regras oferecem alternativas) e nada é desmarcado.
_RESCHEDULE = ("remarcar", "reagendar", "adiar", "mudar o horario", "trocar o horario", "outro horario", "outro dia")
_CANCEL = ("cancelar", "desmarcar", "nao vou poder", "nao vou conseguir")
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
_PRICE_OR_HOURS = ("preco", "valor", "quanto", "custa", "custo", "horario", "abre", "fecha", "funciona", "atende")
_GREETING = ("oi", "ola", "bom dia", "boa tarde", "boa noite", "hey", "e ai")


def classify(text: str) -> Intent:
    t = normalize(text)
    bare = re.sub(r"[^\w\s]", "", t).strip()
    if not bare:  # só emoji/figurinha de texto: cumprimenta e se apresenta
        return Intent.GREETING
    if any(k in t for k in _HUMAN):
        return Intent.HUMAN
    if any(k in t for k in _RESCHEDULE):
        return Intent.SCHEDULE
    if any(k in t for k in _CANCEL):
        return Intent.CANCEL
    if any(k in t for k in _INFO):
        return Intent.INFO
    if any(k in t for k in _SCHEDULE):
        return Intent.SCHEDULE
    if bare in _GREETING or any(bare.startswith(g + " ") for g in _GREETING):
        return Intent.GREETING
    return Intent.INFO


def asks_prices_or_hours(text: str) -> bool:
    """Dúvida que o fallback por regras consegue responder com catálogo/horários (sem inventar o resto)."""
    t = normalize(text)
    return any(k in t for k in _PRICE_OR_HOURS)


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
