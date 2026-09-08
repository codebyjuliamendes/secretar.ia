import pytest

from app.domain.intents import Intent, classify, coerce_intent
from app.domain.phones import normalize_phone
from app.domain.plans import Plan, limits_for, within_limit
from app.domain.roles import Permission, TenantRole, can_assign_role, has_permission


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Quero agendar botox amanhã", Intent.SCHEDULE),
        ("Preciso cancelar minha consulta", Intent.CANCEL),
        ("Qual o valor do preenchimento?", Intent.INFO),
        ("Quero falar com um atendente humano", Intent.HUMAN),
        ("Oi", Intent.GREETING),
        ("bom dia!", Intent.GREETING),
        ("Vocês abrem sábado?", Intent.INFO),
        ("URGENTE, preciso de ajuda", Intent.HUMAN),
        ("Quero desmarcar e agendar outro dia", Intent.CANCEL),
    ],
)
def test_classify(text, expected):
    assert classify(text) == expected


def test_coerce_intent_aliases():
    assert coerce_intent("agendar") == Intent.SCHEDULE
    assert coerce_intent("HUMAN") == Intent.HUMAN
    assert coerce_intent("saudação") == Intent.GREETING
    assert coerce_intent("banana") is None
    assert coerce_intent(None) is None


def test_normalize_phone():
    assert normalize_phone("+55 (81) 99999-8888") == "5581999998888"
    assert normalize_phone("81999998888") == "5581999998888"
    assert normalize_phone("5581999998888@s.whatsapp.net") == "5581999998888"
    with pytest.raises(ValueError):
        normalize_phone("123")
    with pytest.raises(ValueError):
        normalize_phone("")


def test_role_permissions():
    assert has_permission(TenantRole.STAFF, Permission.APPOINTMENTS_MANAGE)
    assert not has_permission(TenantRole.STAFF, Permission.SETTINGS_MANAGE)
    assert has_permission(TenantRole.MANAGER, Permission.SETTINGS_MANAGE)
    assert not has_permission(TenantRole.MANAGER, Permission.TEAM_MANAGE)
    assert has_permission(TenantRole.OWNER, Permission.BILLING_MANAGE)
    assert has_permission("OWNER", Permission.TEAM_MANAGE)


def test_can_assign_role():
    assert can_assign_role(TenantRole.OWNER, TenantRole.OWNER)
    assert not can_assign_role(TenantRole.MANAGER, TenantRole.OWNER)
    assert can_assign_role(TenantRole.MANAGER, TenantRole.STAFF)
    assert not can_assign_role(TenantRole.STAFF, TenantRole.MANAGER)


def test_plan_limits():
    assert limits_for(Plan.FREE).ai_messages_per_month == 200
    assert limits_for("ENTERPRISE").ai_messages_per_month == -1
    assert within_limit(199, 200)
    assert not within_limit(200, 200)
    assert within_limit(10_000_000, -1)
    assert not limits_for(Plan.FREE).upsell_campaigns
    assert limits_for(Plan.BASIC).upsell_campaigns
