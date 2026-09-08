"""RBAC do domínio de clínicas.

Papéis por tenant:
  OWNER   - dono da clínica: tudo, inclusive billing, equipe e exclusão.
  MANAGER - gerente: configura IA/integrações, gerencia agenda/pacientes e vê relatórios.
  STAFF   - recepção: opera agenda, pacientes e inbox; não altera configurações.

Papel de plataforma:
  SUPER_ADMIN - operador da Secretar.ia: administra tenants e planos. Não é membro automático
  de nenhum tenant; para atuar como clínica precisa de membership explícita.
"""

from __future__ import annotations

from enum import StrEnum


class TenantRole(StrEnum):
    OWNER = "OWNER"
    MANAGER = "MANAGER"
    STAFF = "STAFF"


class Permission(StrEnum):
    DASHBOARD_VIEW = "dashboard:view"
    APPOINTMENTS_VIEW = "appointments:view"
    APPOINTMENTS_MANAGE = "appointments:manage"
    PATIENTS_VIEW = "patients:view"
    PATIENTS_MANAGE = "patients:manage"
    INBOX_VIEW = "inbox:view"
    INBOX_MANAGE = "inbox:manage"
    SETTINGS_VIEW = "settings:view"
    SETTINGS_MANAGE = "settings:manage"
    INTEGRATIONS_MANAGE = "integrations:manage"
    TEAM_VIEW = "team:view"
    TEAM_MANAGE = "team:manage"
    BILLING_VIEW = "billing:view"
    BILLING_MANAGE = "billing:manage"
    AUDIT_VIEW = "audit:view"


_STAFF: frozenset[Permission] = frozenset(
    {
        Permission.DASHBOARD_VIEW,
        Permission.APPOINTMENTS_VIEW,
        Permission.APPOINTMENTS_MANAGE,
        Permission.PATIENTS_VIEW,
        Permission.PATIENTS_MANAGE,
        Permission.INBOX_VIEW,
        Permission.INBOX_MANAGE,
        Permission.SETTINGS_VIEW,
    }
)
_MANAGER: frozenset[Permission] = _STAFF | frozenset(
    {
        Permission.SETTINGS_MANAGE,
        Permission.INTEGRATIONS_MANAGE,
        Permission.TEAM_VIEW,
        Permission.BILLING_VIEW,
        Permission.AUDIT_VIEW,
    }
)
_OWNER: frozenset[Permission] = _MANAGER | frozenset({Permission.TEAM_MANAGE, Permission.BILLING_MANAGE})

ROLE_PERMISSIONS: dict[TenantRole, frozenset[Permission]] = {
    TenantRole.STAFF: _STAFF,
    TenantRole.MANAGER: _MANAGER,
    TenantRole.OWNER: _OWNER,
}

ROLE_RANK = {TenantRole.STAFF: 1, TenantRole.MANAGER: 2, TenantRole.OWNER: 3}


def has_permission(role: TenantRole | str, permission: Permission) -> bool:
    return permission in ROLE_PERMISSIONS[TenantRole(role)]


def can_assign_role(actor: TenantRole | str, target: TenantRole | str) -> bool:
    """Um membro só pode atribuir papéis iguais ou inferiores ao seu; apenas OWNER cria OWNER."""
    actor_r, target_r = TenantRole(actor), TenantRole(target)
    if target_r == TenantRole.OWNER:
        return actor_r == TenantRole.OWNER
    return ROLE_RANK[actor_r] >= ROLE_RANK[target_r]
