"""Dependências FastAPI: usuário autenticado, membership do tenant e permissões.

Regra central de isolamento: o tenant SEMPRE vem da URL (/api/clinic/{tenant_id}/...) e é validado
contra a membership do usuário autenticado. Nunca confiamos em tenantId vindo de body/query.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Header, Path, Request

from app.config import Settings, get_settings
from app.db import db
from app.domain.roles import Permission, TenantRole, has_permission
from app.errors import ForbiddenError, UnauthorizedError
from app.logging import tenant_id_var, user_id_var
from app.security.tokens import decode_access_token


@dataclass
class CurrentUser:
    id: str
    platform_role: str

    @property
    def is_super_admin(self) -> bool:
        return self.platform_role == "SUPER_ADMIN"


@dataclass
class TenantContext:
    user: CurrentUser
    tenant: object  # generated_prisma.models.Tenant
    role: TenantRole

    @property
    def tenant_id(self) -> str:
        return self.tenant.id


def client_ip(request: Request) -> str | None:
    if get_settings().trust_proxy_headers:
        real = request.headers.get("x-real-ip")
        if real:
            return real.strip()[:64]
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()[:64]
    return request.client.host if request.client else None


def get_settings_dep() -> Settings:
    return get_settings()


async def current_user(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings_dep),
) -> CurrentUser:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise UnauthorizedError("Autenticação necessária.", code="missing_token")
    payload = decode_access_token(authorization.split(" ", 1)[1].strip(), settings.jwt_secret)
    if payload is None:
        raise UnauthorizedError("Sessão expirada ou inválida.", code="invalid_token")
    user_id_var.set(payload["sub"])
    return CurrentUser(id=payload["sub"], platform_role=str(payload.get("prl") or "USER"))


async def require_super_admin(user: CurrentUser = Depends(current_user)) -> CurrentUser:
    # Confirma no banco: um token antigo não deve manter privilégios após rebaixamento.
    row = await db.user.find_unique(where={"id": user.id})
    if row is None or str(row.platformRole) != "SUPER_ADMIN":
        raise ForbiddenError("Acesso restrito à administração da plataforma.")
    return user


async def tenant_context(
    tenant_id: str = Path(..., min_length=1, max_length=64),
    user: CurrentUser = Depends(current_user),
) -> TenantContext:
    membership = await db.membership.find_unique(
        where={"userId_tenantId": {"userId": user.id, "tenantId": tenant_id}}, include={"tenant": True}
    )
    if membership is None or membership.tenant is None:
        # 404 e não 403: não revelamos a existência de tenants alheios.
        raise ForbiddenError("Você não tem acesso a esta clínica.", code="tenant_forbidden", status_code=404)
    tenant_id_var.set(tenant_id)
    return TenantContext(user=user, tenant=membership.tenant, role=TenantRole(str(membership.role)))


def require_permission(permission: Permission):
    async def _dep(ctx: TenantContext = Depends(tenant_context)) -> TenantContext:
        if not has_permission(ctx.role, permission):
            raise ForbiddenError("Seu papel não permite esta ação.", code="permission_denied")
        return ctx

    return _dep
