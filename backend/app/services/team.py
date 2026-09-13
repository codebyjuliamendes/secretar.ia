"""Equipe da clínica: convites com aceite pelo link do e-mail, papéis e remoção.

Ninguém vira membro sem aceitar: o convite guarda e-mail, papel e um token de uso único (7 dias). Ao aceitar,
quem já tem conta precisa estar logado com aquele e-mail; quem não tem cria a conta na mesma tela (o clique no
link do e-mail já prova a posse do endereço). O OWNER nunca descobre se um e-mail já tem conta na plataforma.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

from app.config import Settings
from app.db import db
from app.domain.plans import limits_for, within_limit
from app.domain.roles import TenantRole, can_assign_role
from app.errors import AppError, ConflictError, ForbiddenError, NotFoundError, QuotaExceededError
from app.jobs.queue import enqueue
from app.jobs.tasks import SEND_EMAIL
from app.security.passwords import hash_password_async, validate_password_policy
from app.security.tokens import hash_token
from app.services import audit
from app.services.auth import issue_tokens, me
from generated_prisma.errors import UniqueViolationError

INVITE_TTL = timedelta(days=7)


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


def invite_view(i) -> dict:
    return {
        "id": i.id,
        "email": i.email,
        "name": i.name,
        "role": str(i.role),
        "expiresAt": i.expiresAt.isoformat(),
        "createdAt": i.createdAt.isoformat(),
    }


async def list_members(tenant_id: str) -> list[dict]:
    rows = await db.membership.find_many(
        where={"tenantId": tenant_id}, include={"user": True}, order={"createdAt": "asc"}
    )
    return [member_view(m) for m in rows]


async def list_invites(tenant_id: str) -> list[dict]:
    rows = await db.teaminvite.find_many(
        where={"tenantId": tenant_id, "acceptedAt": None, "expiresAt": {"gt": datetime.now(UTC)}},
        order={"createdAt": "asc"},
    )
    return [invite_view(i) for i in rows]


def _invite_link(settings: Settings, raw: str) -> str:
    return f"{settings.frontend_url.rstrip('/')}/invite?token={raw}"


async def _send_invite_email(settings: Settings, tenant, invite, raw: str) -> None:
    body = (
        f"Olá {invite.name},\n\nVocê foi convidado(a) para a equipe da clínica {tenant.name} na Secretar.ia "
        f"com o papel {invite.role}.\nAceite o convite em: {_invite_link(settings, raw)}\n\n"
        "O link expira em 7 dias. Se você não esperava este convite, ignore este e-mail."
    )
    await enqueue(
        SEND_EMAIL, {"to": invite.email, "subject": f"Convite para {tenant.name} - Secretar.ia", "text": body}
    )


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
    email = email.strip().lower()
    now = datetime.now(UTC)
    existing = await db.user.find_unique(where={"email": email})
    if existing and await db.membership.find_unique(
        where={"userId_tenantId": {"userId": existing.id, "tenantId": tenant.id}}
    ):
        raise ConflictError("Esta pessoa já faz parte da equipe.", code="already_member")
    # Membros + convites pendentes contam para o limite do plano (senão o limite vira letra morta até o aceite).
    members = await db.membership.count(where={"tenantId": tenant.id})
    pending = await db.teaminvite.count(
        where={"tenantId": tenant.id, "acceptedAt": None, "expiresAt": {"gt": now}, "email": {"not": email}}
    )
    if not within_limit(members + pending, limits_for(str(tenant.plan)).max_members):
        raise QuotaExceededError("Limite de membros do plano atingido.", code="member_limit")
    # Um convite por e-mail por clínica: reenviar substitui o anterior (token antigo deixa de valer).
    await db.teaminvite.delete_many(where={"tenantId": tenant.id, "email": email, "acceptedAt": None})
    raw = secrets.token_urlsafe(32)
    invite = await db.teaminvite.create(
        data={
            "tenantId": tenant.id,
            "email": email,
            "name": name.strip(),
            "role": role,
            "tokenHash": hash_token(raw),
            "invitedById": actor_user_id,
            "expiresAt": now + INVITE_TTL,
        }
    )
    await _send_invite_email(settings, tenant, invite, raw)
    await audit.record(
        action="team.invite_sent",
        resource_type="team_invite",
        resource_id=invite.id,
        tenant_id=tenant.id,
        actor_user_id=actor_user_id,
        metadata={"role": role},
        ip=ip,
    )
    return invite_view(invite)


async def resend_invite(settings: Settings, tenant, invite_id: str, *, actor_user_id: str, ip: str | None) -> dict:
    invite = await db.teaminvite.find_first(where={"id": invite_id, "tenantId": tenant.id, "acceptedAt": None})
    if invite is None:
        raise NotFoundError("Convite não encontrado.")
    raw = secrets.token_urlsafe(32)
    invite = await db.teaminvite.update(
        where={"id": invite.id}, data={"tokenHash": hash_token(raw), "expiresAt": datetime.now(UTC) + INVITE_TTL}
    )
    await _send_invite_email(settings, tenant, invite, raw)
    await audit.record(
        action="team.invite_resent",
        resource_type="team_invite",
        resource_id=invite.id,
        tenant_id=tenant.id,
        actor_user_id=actor_user_id,
        ip=ip,
    )
    return invite_view(invite)


async def cancel_invite(tenant_id: str, invite_id: str, *, actor_user_id: str, ip: str | None) -> None:
    invite = await db.teaminvite.find_first(where={"id": invite_id, "tenantId": tenant_id})
    if invite is None:
        raise NotFoundError("Convite não encontrado.")
    await db.teaminvite.delete(where={"id": invite.id})
    await audit.record(
        action="team.invite_canceled",
        resource_type="team_invite",
        resource_id=invite.id,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        metadata={"email": invite.email},
        ip=ip,
    )


async def _pending_invite(token: str):
    invite = await db.teaminvite.find_unique(where={"tokenHash": hash_token(token)}, include={"tenant": True})
    if invite is None or invite.acceptedAt is not None:
        raise AppError("Convite inválido ou já utilizado.", code="invalid_invite", status_code=404)
    if invite.expiresAt < datetime.now(UTC):
        raise AppError("Este convite expirou. Peça um novo à clínica.", code="invite_expired", status_code=410)
    return invite


async def invite_info(token: str) -> dict:
    """O que a tela de aceite precisa saber, sem revelar nada além do que o e-mail já continha."""
    invite = await _pending_invite(token)
    user = await db.user.find_unique(where={"email": invite.email})
    return {
        "clinicName": invite.tenant.name,
        "email": invite.email,
        "name": invite.name,
        "role": str(invite.role),
        "userExists": user is not None,
        "expiresAt": invite.expiresAt.isoformat(),
    }


async def accept_invite(
    settings: Settings,
    *,
    token: str,
    current_user_id: str | None,
    name: str | None,
    password: str | None,
    user_agent: str | None,
    ip: str | None,
) -> dict:
    """Cria a membership (e a conta, se preciso) e devolve tokens de sessão para a pessoa já entrar na clínica."""
    invite = await _pending_invite(token)
    user = await db.user.find_unique(where={"email": invite.email})
    if user is not None:
        # Conta já existe: só o próprio dono dela (logado) pode aceitar.
        if current_user_id != user.id:
            raise ForbiddenError(
                f"Entre com a conta {invite.email} para aceitar este convite.", code="invite_login_required"
            )
    else:
        if not password:
            raise AppError("Defina uma senha para criar sua conta.", code="password_required")
        if (err := validate_password_policy(password)) is not None:
            raise AppError(err, code="weak_password")
        user = await db.user.create(
            data={
                "email": invite.email,
                "passwordHash": await hash_password_async(password),
                "name": (name or invite.name).strip()[:120],
                "emailVerifiedAt": datetime.now(UTC),  # o link chegou nesse e-mail
            }
        )
    try:
        membership = await db.membership.create(
            data={"userId": user.id, "tenantId": invite.tenantId, "role": str(invite.role)}
        )
    except UniqueViolationError:
        membership = await db.membership.find_unique(
            where={"userId_tenantId": {"userId": user.id, "tenantId": invite.tenantId}}
        )
    await db.teaminvite.update(where={"id": invite.id}, data={"acceptedAt": datetime.now(UTC)})
    await audit.record(
        action="team.invite_accepted",
        resource_type="membership",
        resource_id=membership.id,
        tenant_id=invite.tenantId,
        actor_user_id=user.id,
        metadata={"role": str(invite.role)},
        ip=ip,
    )
    tokens = await issue_tokens(settings, user, user_agent=user_agent, ip=ip)
    return {**tokens, "tenantId": invite.tenantId, "user": await me(user.id)}


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
