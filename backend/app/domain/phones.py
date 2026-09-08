"""Normalização de telefones em formato E.164 sem '+' (padrão usado pela Evolution API)."""

from __future__ import annotations

import re


def normalize_phone(raw: str, default_country: str = "55") -> str:
    digits = re.sub(r"\D", "", raw or "")
    if "@" in (raw or ""):  # remoteJid: 5581999998888@s.whatsapp.net
        digits = re.sub(r"\D", "", raw.split("@", 1)[0])
    if not digits:
        raise ValueError("Telefone vazio")
    if len(digits) in (10, 11) and not digits.startswith(default_country):
        digits = default_country + digits
    if len(digits) < 10 or len(digits) > 15:
        raise ValueError("Telefone inválido")
    return digits
