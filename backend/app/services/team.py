"""Equipe da clínica: convites (criação de usuário com senha temporária por e-mail), papéis e remoção."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime

from app.config import Settings
from app.db import db
from app.domain.plans import limits_for, within_limit
from app.domain.roles import TenantRole, can_assign_role
from app.errors import ConflictError, ForbiddenError, NotFoundError, QuotaExceededError
from app.jobs.queue import enqueue
from app.jobs.tasks import SEND_EMAIL
from app.security.passwords import hash_password_async
from app.services import audit
from app.services.auth import RESET_TTL, create_verification
from generated_prisma.errors import UniqueViolationError


def member_view(m) -> dict:
    return {
        "id": m.id,
        "role": str(m.role),
        "createdAt": m.createdAt.isoformat(),
        "user": {
            "id": m.user.id,
            "name": m.user.name,
            "email": m.user.email,
            "emailVerified": m.user.emailVerifiedAt is not None,
        }
        if m.user
        else None,
    }


async def list_members(tenant_id: str) -> list[dict]:
    rows = await db.membership.find_many(
        where={"tenantId": tenant_id}, include={"user": True}, order={"createdAt": "asc"}
    )
    return [member_view(m) for m in rows]


async def invite_member(
    settings: Settings,
    tenant,
    *,
    email: str,
    name: str,
    role: str,
    actor_role: str,
    actor_user_id: str,
    ip: str | None,
) -> dict:
    if not can_assign_role(actor_role, role):
        raise ForbiddenError("Você não pode atribuir este papel.")
    count = await db.membership.count(where={"tenantId": tenant.id})
    if not within_limit(count, limits_for(str(tenant.plan)).max_members):
        raise QuotaExceededError("Limite de membros do plano atingido.", code="member_limit")
    email = email.strip().lower()
    user = await db.user.find_unique(where={"email": email})
    created = False
    if user is None:
        temp_hash = await hash_password_async(secrets.token_urlsafe(24))
        user = await db.user.create(data={"email": email, "passwordHash": temp_hash, "name": name.strip()})
        created = True
    try:
        membership = await db.membership.create(
            data={"userId": user.id, "tenantId": tenant.id, "role": role}, include={"user": True}
        )
    except UniqueViolationError as exc:
        raise ConflictError("Esta pessoa já faz parte da equipe.", code="already_member") from exc

    if created:
        raw = await create_verification(user.id, "PASSWORD_RESET", RESET_TTL * 48)
        link = f"{settings.frontend_url}/reset-password?token={raw}&welcome=1"
        body = (
            f"Olá {user.name},\n\nVocê foi convidado(a) para a equipe da clínica {tenant.name} na Secretar.ia.\n"
            f"Defina sua senha em: {link}\n\nO link expira em 48 horas."
        )
    else:
        body = (
            f"Olá {user.name},\n\nVocê foi adicionado(a) à equipe da clínica {tenant.name} na Secretar.ia "
            f"com o papel {role}. Acesse: {settings.frontend_url}/login"
        )
    await enqueue(SEND_EMAIL, {"to": user.email, "subject": f"Convite para {tenant.name} - Secretar.ia", "text": body})
    await audit.record(
        action="team.member_invited",
        resource_type="membership",
        resource_id=membership.id,
        tenant_id=tenant.id,
        actor_user_id=actor_user_id,
        metadata={"role": role},
        ip=ip,
    )
    return member_view(membership)


async def change_role(
    tenant_id: str, membership_id: str, *, role: str, actor_role: str, actor_user_id: str, ip: str | None
) -> dict:
    m = await db.membership.find_first(where={"id": membership_id, "tenantId": tenant_id}, include={"user": True})
    if m is None:
        raise NotFoundError("Membro não encontrado.")
    if not can_assign_role(actor_role, role) or not can_assign_role(actor_role, str(m.role)):
        raise ForbiddenError("Você não pode alterar este papel.")
    if str(m.role) == TenantRole.OWNER and role != TenantRole.OWNER:
        owners = await db.membership.count(where={"tenantId": tenant_id, "role": "OWNER"})
        if owners <= 1:
            raise ConflictError("A clínica precisa de pelo menos um OWNER.", code="last_owner")
    updated = await db.membership.update(where={"id": m.id}, data={"role": role}, include={"user": True})
    await audit.record(
        action="team.role_changed",
        resource_type="membership",
        resource_id=m.id,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        metadata={"from": str(m.role), "to": role},
        ip=ip,
    )
    return member_view(updated)


async def remove_member(
    tenant_id: str, membership_id: str, *, actor_role: str, actor_user_id: str, ip: str | None
) -> None:
    m = await db.membership.find_first(where={"id": membership_id, "tenantId": tenant_id})
    if m is None:
        raise NotFoundError("Membro não encontrado.")
    if not can_assign_role(actor_role, str(m.role)):
        raise ForbiddenError("Você não pode remover este membro.")
    if str(m.role) == TenantRole.OWNER:
        owners = await db.membership.count(where={"tenantId": tenant_id, "role": "OWNER"})
        if owners <= 1:
            raise ConflictError("A clínica precisa de pelo menos um OWNER.", code="last_owner")
    await db.membership.delete(where={"id": m.id})
    # Encerra as sessões do usuário removido para que o acesso caia imediatamente.
    await db.refreshtoken.update_many(
        where={"userId": m.userId, "revokedAt": None}, data={"revokedAt": datetime.now(UTC)}
    )
    await audit.record(
        action="team.member_removed",
        resource_type="membership",
        resource_id=m.id,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        metadata={"userId": m.userId},
        ip=ip,
    )
