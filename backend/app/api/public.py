"""Rotas públicas (sem login): o que a landing precisa saber sobre planos, nichos e contato."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from pydantic import AwareDatetime, BaseModel, Field

from app.config import Settings, get_settings
from app.deps import client_ip
from app.domain.niches import niche_options
from app.domain.plans import Plan, plan_public_view
from app.errors import RateLimitedError
from app.security.ratelimit import PostgresRateLimiter
from app.services import public_booking
from app.services.billing import sales_contact

router = APIRouter(prefix="/public", tags=["public"])

_booking_limiter = PostgresRateLimiter("public.booking", limit=10, window_seconds=3600)
_slots_limiter = PostgresRateLimiter("public.slots", limit=120, window_seconds=600)


class BookingIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    phone: str = Field(min_length=8, max_length=32)
    start: AwareDatetime
    serviceId: str | None = Field(default=None, max_length=64)
    professionalId: str | None = Field(default=None, max_length=64)


async def _limit(limiter: PostgresRateLimiter, key: str | None) -> None:
    if not await limiter.allow(key or "unknown"):
        raise RateLimitedError("Muitos pedidos deste dispositivo. Tente de novo em instantes.")


@router.get("/booking/{slug}")
async def booking_info(slug: str):
    return await public_booking.booking_info(slug)


@router.get("/booking/{slug}/slots")
async def booking_slots(
    slug: str,
    request: Request,
    serviceId: str | None = Query(default=None, max_length=64),
    professionalId: str | None = Query(default=None, max_length=64),
    days: int = Query(default=14, ge=1, le=21),
):
    await _limit(_slots_limiter, client_ip(request))
    return await public_booking.booking_slots(slug, service_id=serviceId, days=days, professional_id=professionalId)


@router.post("/booking/{slug}", status_code=201)
async def create_booking(slug: str, data: BookingIn, request: Request):
    ip = client_ip(request)
    await _limit(_booking_limiter, ip)
    start: datetime = data.start
    return await public_booking.create_booking(
        slug,
        name=data.name,
        phone=data.phone,
        start=start,
        service_id=data.serviceId,
        professional_id=data.professionalId,
        ip=ip,
    )


@router.get("/config")
async def public_config(settings: Settings = Depends(get_settings)):
    return {
        "plans": [plan_public_view(p) for p in Plan],
        "niches": niche_options(),
        "sales": sales_contact(settings),
    }
