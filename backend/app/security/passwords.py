"""Hash de senha com bcrypt (custo 12) e política mínima de senha."""

from __future__ import annotations

import asyncio

import bcrypt

MIN_PASSWORD_LENGTH = 8


def validate_password_policy(password: str) -> str | None:
    """Retorna mensagem de erro ou None se a senha for aceitável."""
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"A senha deve ter pelo menos {MIN_PASSWORD_LENGTH} caracteres."
    if len(password) > 128:
        return "A senha deve ter no máximo 128 caracteres."
    if password.isdigit() or password.isalpha():
        return "A senha deve combinar letras e números."
    return None


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


async def hash_password_async(password: str) -> str:
    return await asyncio.to_thread(hash_password, password)


async def verify_password_async(password: str, password_hash: str) -> bool:
    return await asyncio.to_thread(verify_password, password, password_hash)
