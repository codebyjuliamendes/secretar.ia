"""Planos, limites e features. A verificação de quota acontece no backend (nunca no frontend)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum


class Plan(StrEnum):
    FREE = "FREE"
    BASIC = "BASIC"
    PRO = "PRO"
    ENTERPRISE = "ENTERPRISE"


@dataclass(frozen=True)
class PlanLimits:
    ai_messages_per_month: int  # -1 = ilimitado
    max_patients: int
    max_members: int
    upsell_campaigns: bool
    ai_model_tier: str  # "rules" | "standard" | "premium"
    price_cents_month: int
    media_understanding: bool = False  # áudio e imagem do paciente lidos pela IA
    knowledge_base: bool = False  # base de conhecimento (RAG) no atendimento
    max_knowledge_documents: int = 0  # -1 = ilimitado


PLAN_LIMITS: dict[Plan, PlanLimits] = {
    Plan.FREE: PlanLimits(
        ai_messages_per_month=200,
        max_patients=100,
        max_members=2,
        upsell_campaigns=False,
        ai_model_tier="standard",
        price_cents_month=0,
    ),
    Plan.BASIC: PlanLimits(
        ai_messages_per_month=2_000,
        max_patients=1_000,
        max_members=5,
        upsell_campaigns=True,
        ai_model_tier="standard",
        price_cents_month=29_700,
        media_understanding=True,
        knowledge_base=True,
        max_knowledge_documents=10,
    ),
    Plan.PRO: PlanLimits(
        ai_messages_per_month=10_000,
        max_patients=10_000,
        max_members=15,
        upsell_campaigns=True,
        ai_model_tier="premium",
        price_cents_month=59_700,
        media_understanding=True,
        knowledge_base=True,
        max_knowledge_documents=50,
    ),
    Plan.ENTERPRISE: PlanLimits(
        ai_messages_per_month=-1,
        max_patients=-1,
        max_members=-1,
        upsell_campaigns=True,
        ai_model_tier="premium",
        price_cents_month=0,  # negociado
        media_understanding=True,
        knowledge_base=True,
        max_knowledge_documents=-1,
    ),
}

TRIAL_DAYS = 14
# Durante o período de teste a clínica experimenta os RECURSOS deste plano (mídia, base de conhecimento);
# os limites de volume (mensagens, pacientes, membros) continuam sendo os do plano contratado (FREE).
TRIAL_FEATURE_PLAN = Plan.PRO

FEATURES = ("media", "knowledge")


def limits_for(plan: Plan | str) -> PlanLimits:
    return PLAN_LIMITS[Plan(plan)]


def within_limit(current: int, limit: int) -> bool:
    return limit < 0 or current < limit


def in_trial(tenant, now: datetime | None = None) -> bool:
    if str(tenant.status) != "TRIAL":
        return False
    ends = getattr(tenant, "trialEndsAt", None)
    return ends is None or ends > (now or datetime.now(UTC))


def feature_plan(tenant, now: datetime | None = None) -> Plan:
    """Plano cujos RECURSOS valem para o tenant: PRO durante o trial, senão o plano contratado."""
    return TRIAL_FEATURE_PLAN if in_trial(tenant, now) else Plan(str(tenant.plan))


def feature_enabled(tenant, feature: str, now: datetime | None = None) -> bool:
    if feature not in FEATURES:
        raise ValueError(f"feature desconhecida: {feature}")
    lim = PLAN_LIMITS[feature_plan(tenant, now)]
    return lim.media_understanding if feature == "media" else lim.knowledge_base


def knowledge_documents_limit(tenant, now: datetime | None = None) -> int:
    return PLAN_LIMITS[feature_plan(tenant, now)].max_knowledge_documents


def feature_access_view(tenant, now: datetime | None = None) -> dict:
    """O que a clínica pode usar agora e por quê (trial ou plano) — para a UI explicar bloqueios."""
    plan = feature_plan(tenant, now)
    lim = PLAN_LIMITS[plan]
    return {
        "source": "trial" if in_trial(tenant, now) else "plan",
        "featurePlan": plan.value,
        "media": lim.media_understanding,
        "knowledge": lim.knowledge_base,
        "maxKnowledgeDocuments": lim.max_knowledge_documents,
    }


def plan_public_view(plan: Plan) -> dict:
    lim = PLAN_LIMITS[plan]
    return {
        "plan": plan.value,
        "aiMessagesPerMonth": lim.ai_messages_per_month,
        "maxPatients": lim.max_patients,
        "maxMembers": lim.max_members,
        "upsellCampaigns": lim.upsell_campaigns,
        "mediaUnderstanding": lim.media_understanding,
        "knowledgeBase": lim.knowledge_base,
        "maxKnowledgeDocuments": lim.max_knowledge_documents,
        "priceCentsMonth": lim.price_cents_month,
    }
