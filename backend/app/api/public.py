"""Rotas públicas (sem login): o que a landing precisa saber sobre planos, nichos e contato."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.config import Settings, get_settings
from app.domain.niches import niche_options
from app.domain.plans import Plan, plan_public_view
from app.services.billing import sales_contact

router = APIRouter(prefix="/public", tags=["public"])


@router.get("/config")
async def public_config(settings: Settings = Depends(get_settings)):
    return {
        "plans": [plan_public_view(p) for p in Plan],
        "niches": niche_options(),
        "sales": sales_contact(settings),
    }
