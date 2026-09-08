"""Planos, limites e features. A verificação de quota acontece no backend (nunca no frontend)."""

from __future__ import annotations

from dataclasses import dataclass
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
    ),
    Plan.PRO: PlanLimits(
        ai_messages_per_month=10_000,
        max_patients=10_000,
        max_members=15,
        upsell_campaigns=True,
        ai_model_tier="premium",
        price_cents_month=59_700,
    ),
    Plan.ENTERPRISE: PlanLimits(
        ai_messages_per_month=-1,
        max_patients=-1,
        max_members=-1,
        upsell_campaigns=True,
        ai_model_tier="premium",
        price_cents_month=0,  # negociado
    ),
}

TRIAL_DAYS = 14


def limits_for(plan: Plan | str) -> PlanLimits:
    return PLAN_LIMITS[Plan(plan)]


def within_limit(current: int, limit: int) -> bool:
    return limit < 0 or current < limit


def plan_public_view(plan: Plan) -> dict:
    lim = PLAN_LIMITS[plan]
    return {
        "plan": plan.value,
        "aiMessagesPerMonth": lim.ai_messages_per_month,
        "maxPatients": lim.max_patients,
        "maxMembers": lim.max_members,
        "upsellCampaigns": lim.upsell_campaigns,
        "priceCentsMonth": lim.price_cents_month,
    }
