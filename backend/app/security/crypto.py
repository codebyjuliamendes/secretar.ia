"""Criptografia simétrica (Fernet) para segredos de terceiros guardados no banco (ex.: refresh tokens OAuth).

Chave: `TOKEN_ENCRYPTION_KEY` (Fernet, base64 urlsafe de 32 bytes). Em development/test, sem chave,
deriva-se uma do JWT_SECRET para facilitar o setup; em produção a chave é obrigatória.
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.config import Settings
from app.errors import IntegrationUnavailableError


def generate_key() -> str:
    return Fernet.generate_key().decode()


def _fernet(settings: Settings) -> Fernet:
    if settings.token_encryption_key:
        try:
            return Fernet(settings.token_encryption_key.encode())
        except (ValueError, TypeError) as exc:
            raise IntegrationUnavailableError(
                "TOKEN_ENCRYPTION_KEY inválida (use `python -m app.cli gen-key`).", code="bad_encryption_key"
            ) from exc
    if settings.is_production_like:
        raise IntegrationUnavailableError(
            "TOKEN_ENCRYPTION_KEY é obrigatória em produção para guardar credenciais de integrações.",
            code="encryption_key_missing",
        )
    derived = base64.urlsafe_b64encode(hashlib.sha256(settings.jwt_secret.encode("utf-8")).digest())
    return Fernet(derived)


def encrypt_secret(settings: Settings, plaintext: str) -> str:
    return _fernet(settings).encrypt(plaintext.encode("utf-8")).decode()


def decrypt_secret(settings: Settings, token: str) -> str:
    try:
        return _fernet(settings).decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Segredo cifrado inválido ou chave alterada.") from exc
