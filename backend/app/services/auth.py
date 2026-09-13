"""Autenticação: cadastro, login, refresh rotativo, logout, verificação de e-mail e senha."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.config import Settings
from app.db import db
from app.domain.phones import normalize_phone
from app.errors import AppError, ConflictError, UnauthorizedError
from app.jobs.queue import enqueue
from app.jobs.tasks import SEND_EMAIL
from app.logging import get_logger
from app.security.passwords import (
    hash_password,
    hash_password_async,
    validate_password_policy,
    verify_password_async,
)
from app.security.tokens import create_access_token, generate_opaque_token, hash_token
from app.services import audit
from app.services.scheduling import DEFAULT_RULES
from generated_prisma.errors import UniqueViolationError

log = get_logger("auth")

VERIFY_TTL = timedelta(hours=24)
RESET_TTL = timedelta(hours=1)


def _issue_access(settings: Settings, user) -> str:
    return create_access_token(
        user_id=user.id,
        platform_role=str(user.platformRole),
        secret=settings.jwt_secret,
        minutes=settings.access_token_minutes,
    )


async def _issue_refresh(settings: Settings, user_id: str, *, user_agent: str | None, ip: str | None) -> str:
    raw = generate_opaque_token()
    await db.refreshtoken.create(
        data={
            "userId": user_id,
            "tokenHash": hash_token(raw),
            "expiresAt": datetime.now(UTC) + timedelta(days=settings.refresh_token_days),
            "userAgent": (user_agent or "")[:255] or None,
            "ip": ip,
        }
    )
    return raw


async def issue_tokens(settings: Settings, user, *, user_agent: str | None, ip: str | None) -> dict:
    return {
        "accessToken": _issue_access(settings, user),
        "refreshToken": await _issue_refresh(settings, user.id, user_agent=user_agent, ip=ip),
        "expiresIn": settings.access_token_minutes * 60,
    }


async def create_verification(user_id: str, type_: str, ttl: timedelta) -> str:
    raw = generate_opaque_token()
    await db.verificationtoken.update_many(
        where={"userId": user_id, "type": type_, "usedAt": None}, data={"usedAt": datetime.now(UTC)}
    )
    await db.verificationtoken.create(
        data={
            "userId": user_id,
            "type": type_,
            "tokenHash": hash_token(raw),
            "expiresAt": datetime.now(UTC) + ttl,
        }
    )
    return raw


async def send_verification_email(settings: Settings, user) -> None:
    raw = await create_verification(user.id, "EMAIL_VERIFY", VERIFY_TTL)
    link = f"{settings.frontend_url}/verify-email?token={raw}"
    await enqueue(
        SEND_EMAIL,
        {
            "to": user.email,
            "subject": "Confirme seu e-mail - Secretar.ia",
            "text": f"Olá {user.name},\n\nConfirme seu e-mail acessando: {link}\n\nO link expira em 24 horas.",
        },
    )


async def register(
    settings: Settings,
    *,
    name: str,
    email: str,
    password: str,
    clinic_name: str,
    whatsapp: str,
    user_agent: str | None,
    ip: str | None,
    referral_code: str | None = None,
) -> dict:
    if (err := validate_password_policy(password)) is not None:
        raise AppError(err, code="weak_password")
    try:
        phone = normalize_phone(whatsapp)
    except ValueError as exc:
        raise AppError("Número de WhatsApp inválido.", code="invalid_phone") from exc

    email = email.strip().lower()
    password_hash = await hash_password_async(password)
    referrer = None
    if referral_code and referral_code.strip():
        referrer = await db.tenant.find_unique(where={"referralCode": referral_code.strip().upper()})
        if referrer is None:
            raise AppError("Código de indicação não encontrado.", code="invalid_referral")
    try:
        async with db.tx() as tx:
            user = await tx.user.create(data={"email": email, "passwordHash": password_hash, "name": name.strip()})
            tenant = await tx.tenant.create(
                data={
                    "name": clinic_name.strip(),
                    "whatsapp": phone,
                    "prompt": "",  # a persona é gerada pelo tom; a clínica não precisa escrever nada
                    "status": "PENDING",  # a equipe Secretar.ia libera o plano
                    "plan": "BASIC",
                    "referredById": referrer.id if referrer else None,
                }
            )
            await tx.membership.create(data={"userId": user.id, "tenantId": tenant.id, "role": "OWNER"})
            await tx.availabilityrule.create_many(
                data=[
                    {"tenantId": tenant.id, "weekday": wd, "startMin": s_, "endMin": e_} for wd, s_, e_ in DEFAULT_RULES
                ]
            )
    except UniqueViolationError as exc:
        msg = str(exc)
        if "whatsapp" in msg:
            raise ConflictError("Este número de WhatsApp já está cadastrado.", code="whatsapp_taken") from exc
        raise ConflictError("Este e-mail já está cadastrado.", code="email_taken") from exc

    await audit.record(
        action="auth.register",
        resource_type="user",
        resource_id=user.id,
        tenant_id=tenant.id,
        actor_user_id=user.id,
        ip=ip,
    )
    from app.services.public_booking import ensure_public_codes

    await ensure_public_codes(tenant)  # slug do link público e código de indicação
    await send_verification_email(settings, user)
    tokens = await issue_tokens(settings, user, user_agent=user_agent, ip=ip)
    return {**tokens, "user": await me(user.id)}


async def login(settings: Settings, *, email: str, password: str, user_agent: str | None, ip: str | None) -> dict:
    user = await db.user.find_unique(where={"email": email.strip().lower()})
    # Sempre verifica um hash para manter tempo de resposta constante.
    ok = await verify_password_async(password, user.passwordHash if user else _DUMMY_HASH)
    if not user or not ok:
        raise UnauthorizedError("E-mail ou senha incorretos.", code="invalid_credentials")
    await db.user.update(where={"id": user.id}, data={"lastLoginAt": datetime.now(UTC)})
    await audit.record(action="auth.login", resource_type="user", resource_id=user.id, actor_user_id=user.id, ip=ip)
    tokens = await issue_tokens(settings, user, user_agent=user_agent, ip=ip)
    return {**tokens, "user": await me(user.id)}


REFRESH_REUSE_GRACE = timedelta(seconds=30)


async def refresh(settings: Settings, *, refresh_token: str, user_agent: str | None, ip: str | None) -> dict:
    row = await db.refreshtoken.find_unique(where={"tokenHash": hash_token(refresh_token)}, include={"user": True})
    now = datetime.now(UTC)
    if row is None or row.revokedAt is not None or row.expiresAt < now or row.user is None:
        if row is not None and row.revokedAt is not None:
            if now - row.revokedAt <= REFRESH_REUSE_GRACE:
                # Duas abas/requisições renovaram ao mesmo tempo com o mesmo token: não é roubo. Só esta falha;
                # a sessão renovada pela outra continua válida.
                log.info("refresh_token_concurrent_reuse", user_id=row.userId)
            else:
                # Reuso de token já rotacionado há tempo: possível roubo. Revoga toda a família do usuário.
                await db.refreshtoken.update_many(
                    where={"userId": row.userId, "revokedAt": None}, data={"revokedAt": now}
                )
                log.warning("refresh_token_reuse_detected", user_id=row.userId)
        raise UnauthorizedError("Sessão inválida ou expirada.", code="invalid_refresh")
    await db.refreshtoken.update(where={"id": row.id}, data={"revokedAt": now})
    tokens = await issue_tokens(settings, row.user, user_agent=user_agent, ip=ip)
    return {**tokens, "user": await me(row.user.id)}


async def logout(refresh_token: str | None, *, user_id: str | None = None, all_sessions: bool = False) -> None:
    now = datetime.now(UTC)
    if all_sessions and user_id:
        await db.refreshtoken.update_many(where={"userId": user_id, "revokedAt": None}, data={"revokedAt": now})
        return
    if refresh_token:
        await db.refreshtoken.update_many(
            where={"tokenHash": hash_token(refresh_token), "revokedAt": None}, data={"revokedAt": now}
        )


async def verify_email(token: str) -> None:
    row = await db.verificationtoken.find_unique(where={"tokenHash": hash_token(token)})
    now = datetime.now(UTC)
    if row is None or row.type != "EMAIL_VERIFY" or row.usedAt is not None or row.expiresAt < now:
        raise AppError("Link de verificação inválido ou expirado.", code="invalid_token")
    async with db.tx() as tx:
        await tx.verificationtoken.update(where={"id": row.id}, data={"usedAt": now})
        await tx.user.update(where={"id": row.userId}, data={"emailVerifiedAt": now})
    await audit.record(
        action="auth.email_verified", resource_type="user", resource_id=row.userId, actor_user_id=row.userId
    )


async def resend_verification(settings: Settings, user_id: str) -> None:
    user = await db.user.find_unique(where={"id": user_id})
    if user and user.emailVerifiedAt is None:
        await send_verification_email(settings, user)


async def forgot_password(settings: Settings, email: str) -> None:
    """Sempre responde sucesso para não revelar se o e-mail existe."""
    user = await db.user.find_unique(where={"email": email.strip().lower()})
    if user is None:
        return
    raw = await create_verification(user.id, "PASSWORD_RESET", RESET_TTL)
    link = f"{settings.frontend_url}/reset-password?token={raw}"
    await enqueue(
        SEND_EMAIL,
        {
            "to": user.email,
            "subject": "Redefinição de senha - Secretar.ia",
            "text": f"Olá {user.name},\n\nPara redefinir sua senha acesse: {link}\n\n"
            "Se você não solicitou, ignore este e-mail. O link expira em 1 hora.",
        },
    )


async def reset_password(token: str, new_password: str) -> None:
    if (err := validate_password_policy(new_password)) is not None:
        raise AppError(err, code="weak_password")
    row = await db.verificationtoken.find_unique(where={"tokenHash": hash_token(token)})
    now = datetime.now(UTC)
    if row is None or row.type != "PASSWORD_RESET" or row.usedAt is not None or row.expiresAt < now:
        raise AppError("Link de redefinição inválido ou expirado.", code="invalid_token")
    password_hash = await hash_password_async(new_password)
    async with db.tx() as tx:
        await tx.verificationtoken.update(where={"id": row.id}, data={"usedAt": now})
        await tx.user.update(where={"id": row.userId}, data={"passwordHash": password_hash})
        await tx.refreshtoken.update_many(where={"userId": row.userId, "revokedAt": None}, data={"revokedAt": now})
    await audit.record(
        action="auth.password_reset", resource_type="user", resource_id=row.userId, actor_user_id=row.userId
    )


async def change_password(user_id: str, *, current_password: str, new_password: str) -> None:
    if (err := validate_password_policy(new_password)) is not None:
        raise AppError(err, code="weak_password")
    user = await db.user.find_unique(where={"id": user_id})
    if user is None or not await verify_password_async(current_password, user.passwordHash):
        # 400, não 401: um 401 faria o BFF encerrar a sessão de quem só errou a senha atual.
        raise AppError("Senha atual incorreta.", code="invalid_current_password")
    password_hash = await hash_password_async(new_password)
    now = datetime.now(UTC)
    async with db.tx() as tx:
        await tx.user.update(where={"id": user_id}, data={"passwordHash": password_hash})
        await tx.refreshtoken.update_many(where={"userId": user_id, "revokedAt": None}, data={"revokedAt": now})
    await audit.record(action="auth.password_changed", resource_type="user", resource_id=user_id, actor_user_id=user_id)


async def me(user_id: str) -> dict:
    user = await db.user.find_unique(where={"id": user_id}, include={"memberships": {"include": {"tenant": True}}})
    if user is None:
        raise UnauthorizedError("Usuário não encontrado.")
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "platformRole": str(user.platformRole),
        "emailVerified": user.emailVerifiedAt is not None,
        "memberships": [
            {
                "tenantId": m.tenantId,
                "role": str(m.role),
                "tenant": {
                    "id": m.tenant.id,
                    "name": m.tenant.name,
                    "status": str(m.tenant.status),
                    "plan": str(m.tenant.plan),
                    "whatsappConnected": m.tenant.whatsappConnected,
                },
            }
            for m in (user.memberships or [])
            if m.tenant
        ],
    }


# Hash bcrypt de uma senha aleatória, usado para equalizar o tempo de resposta do login
# quando o e-mail não existe (evita enumeração de usuários por timing).
_DUMMY_HASH = hash_password(generate_opaque_token())
