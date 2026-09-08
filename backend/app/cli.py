"""Utilitários de linha de comando.

uv run python -m app.cli create-superadmin --email admin@x.com --password 'S3nha-forte' --name "Admin"
uv run python -m app.cli seed-demo          # dados de demonstração (apenas development/test)
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime, timedelta

from app.config import get_settings
from app.db import db
from app.security.passwords import hash_password, validate_password_policy


async def create_superadmin(email: str, password: str, name: str) -> None:
    if (err := validate_password_policy(password)) is not None:
        raise SystemExit(err)
    await db.connect()
    try:
        user = await db.user.upsert(
            where={"email": email.lower()},
            data={
                "create": {
                    "email": email.lower(),
                    "passwordHash": hash_password(password),
                    "name": name,
                    "platformRole": "SUPER_ADMIN",
                    "emailVerifiedAt": datetime.now(UTC),
                },
                "update": {"platformRole": "SUPER_ADMIN"},
            },
        )
        print(f"SUPER_ADMIN pronto: {user.email} ({user.id})")
    finally:
        await db.disconnect()


async def seed_demo() -> None:
    settings = get_settings()
    if settings.is_production_like:
        raise SystemExit("seed-demo não roda em produção/staging.")
    await db.connect()
    try:
        owner = await db.user.upsert(
            where={"email": "dona@harmonize.demo"},
            data={
                "create": {
                    "email": "dona@harmonize.demo",
                    "passwordHash": hash_password("Demo12345"),
                    "name": "Dra. Helena",
                    "emailVerifiedAt": datetime.now(UTC),
                },
                "update": {},
            },
        )
        tenant = await db.tenant.upsert(
            where={"whatsapp": "5581999998888"},
            data={
                "create": {
                    "name": "Clínica Harmonize",
                    "whatsapp": "5581999998888",
                    "status": "ACTIVE",
                    "plan": "PRO",
                    "prompt": "Você é a secretária virtual da Clínica Harmonize: elegante, educada e prestativa.",
                    "prices": "Toxina botulínica: R$ 990; Preenchimento labial: R$ 1.200; Peeling: R$ 250",
                    "businessHours": "Segunda a sexta, 09:00 às 18:00",
                    "upsellEnabled": True,
                },
                "update": {},
            },
        )
        await db.membership.upsert(
            where={"userId_tenantId": {"userId": owner.id, "tenantId": tenant.id}},
            data={"create": {"userId": owner.id, "tenantId": tenant.id, "role": "OWNER"}, "update": {}},
        )
        patient = await db.patient.upsert(
            where={"tenantId_phone": {"tenantId": tenant.id, "phone": "5581988887777"}},
            data={
                "create": {"tenantId": tenant.id, "phone": "5581988887777", "name": "Amanda Silva"},
                "update": {},
            },
        )
        existing = await db.appointment.count(where={"tenantId": tenant.id})
        if existing == 0:
            now = datetime.now(UTC)
            await db.appointment.create_many(
                data=[
                    {
                        "tenantId": tenant.id,
                        "patientId": patient.id,
                        "service": "Toxina botulínica",
                        "date": now - timedelta(days=152),
                        "status": "COMPLETED",
                        "priceCents": 99000,
                        "source": "MANUAL",
                    },
                    {
                        "tenantId": tenant.id,
                        "patientId": patient.id,
                        "service": "Peeling",
                        "date": now + timedelta(days=3),
                        "status": "CONFIRMED",
                        "priceCents": 25000,
                        "source": "AI",
                    },
                ]
            )
        print(f"Demo pronta. Login: dona@harmonize.demo / Demo12345 (tenant {tenant.id})")
    finally:
        await db.disconnect()


def main() -> None:
    parser = argparse.ArgumentParser(prog="secretaria")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("create-superadmin")
    p.add_argument("--email", required=True)
    p.add_argument("--password", required=True)
    p.add_argument("--name", default="Administrador")
    sub.add_parser("seed-demo")
    args = parser.parse_args()
    if args.cmd == "create-superadmin":
        asyncio.run(create_superadmin(args.email, args.password, args.name))
    elif args.cmd == "seed-demo":
        asyncio.run(seed_demo())


if __name__ == "__main__":
    main()
