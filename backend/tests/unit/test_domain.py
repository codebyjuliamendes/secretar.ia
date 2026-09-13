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
        ("Quero desmarcar e agendar outro dia", Intent.SCHEDULE),  # remarcação: oferecer horários, não desmarcar
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
    assert limits_for(Plan.BASIC).ai_messages_per_month == 1_500 and limits_for(Plan.BASIC).price_cents_month == 75_000
    assert limits_for(Plan.PRO).price_cents_month == 100_000 and limits_for(Plan.PREMIUM).price_cents_month == 150_000
    assert limits_for(Plan.ENTERPRISE).price_cents_month == 200_000 and limits_for(Plan.ENTERPRISE).price_from
    assert limits_for("ENTERPRISE").ai_messages_per_month == -1
    assert within_limit(199, 200) and not within_limit(200, 200) and within_limit(10_000, -1)
    assert [limits_for(p).label for p in Plan] == ["Essencial", "Profissional", "Premium", "Enterprise"]


def test_plan_features_follow_the_contracted_plan():
    from types import SimpleNamespace

    from app.domain.plans import feature_access_view, feature_enabled, feature_plan, knowledge_documents_limit

    basic = SimpleNamespace(plan="BASIC", status="PENDING")
    assert feature_plan(basic) == Plan.BASIC
    assert feature_enabled(basic, "media") and feature_enabled(basic, "knowledge")
    assert knowledge_documents_limit(basic) == 10 and feature_access_view(basic)["featurePlan"] == "BASIC"
    assert knowledge_documents_limit(SimpleNamespace(plan="PRO", status="ACTIVE")) == 30
    assert knowledge_documents_limit(SimpleNamespace(plan="PREMIUM", status="ACTIVE")) == 100
    enterprise = SimpleNamespace(plan="ENTERPRISE", status="PAST_DUE")
    assert knowledge_documents_limit(enterprise) == -1 and within_limit(10_000, knowledge_documents_limit(enterprise))
    with pytest.raises(ValueError):
        feature_enabled(basic, "teleporte")
