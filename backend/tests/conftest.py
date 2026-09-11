"""Fixtures compartilhadas.

Testes de integração usam um PostgreSQL real (DATABASE_URL). Se o banco não estiver acessível,
eles são pulados com uma mensagem clara em vez de falhar silenciosamente.
"""

from __future__ import annotations

import os
import subprocess
import uuid
from datetime import timedelta

import pytest

os.environ.setdefault("APP_ENV", "test")
# Banco de TESTE separado do de desenvolvimento: a suíte TRUNCA todas as tabelas.
os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/secretaria_test?schema=public")
# Segredos FIXOS: os testes assinam webhooks e chamam o cron com estes literais, então valores vindos
# do ambiente (CI, shell do dev) não podem sobrescrevê-los.
os.environ["JWT_SECRET"] = "test-secret-test-secret-test-secret-0123456789"
os.environ["WHATSAPP_APP_SECRET"] = "test-whatsapp-secret"
os.environ["EVOLUTION_WEBHOOK_TOKEN"] = "test-evolution-token"
os.environ["STRIPE_WEBHOOK_SECRET"] = "whsec_test"
os.environ["CRON_SECRET"] = "test-cron-secret"
os.environ.setdefault("CORS_ORIGINS", "http://localhost:4000")
os.environ["GEMINI_API_KEY"] = ""  # testes nunca chamam provedor externo
os.environ["EVOLUTION_API_URL"] = ""
os.environ["SMTP_HOST"] = ""
os.environ["SUPER_ADMIN_EMAIL"] = ""

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

TABLES = [
    "RateLimitBucket",
    "CalendarConnection",
    "KnowledgeChunk",
    "KnowledgeDocument",
    "UpsellDispatch",
    "UsageCounter",
    "AuditLog",
    "Notification",
    "Job",
    "ExecutionLog",
    "Message",
    "WebhookEvent",
    "ProcessedMessage",
    "Appointment",
    "Patient",
    "VerificationToken",
    "RefreshToken",
    "Membership",
    "Tenant",
    "User",
]


def pytest_collection_modifyitems(config, items):
    for item in items:
        if "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)


@pytest.fixture(scope="session")
async def database():
    from app.db import db

    if "secretaria_test" not in os.environ["DATABASE_URL"] and os.environ.get("ALLOW_NON_TEST_DB") != "1":
        pytest.skip(
            "DATABASE_URL não aponta para um banco de teste (a suíte trunca tabelas). "
            "Use *_test ou ALLOW_NON_TEST_DB=1."
        )
    # Garante o schema no banco de teste (idempotente).
    subprocess.run(  # noqa: ASYNC221 - roda uma vez por sessão, antes de qualquer I/O assíncrono
        ["uv", "run", "prisma", "migrate", "deploy", "--schema=prisma/schema.prisma"],
        check=True,
        capture_output=True,
        cwd=os.path.dirname(os.path.dirname(__file__)),
        env={**os.environ, "PYTHONUTF8": "1"},
    )
    try:
        await db.connect(timeout=timedelta(seconds=10))
        await db.query_raw("SELECT 1")
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"PostgreSQL indisponível para testes de integração: {exc}")
    yield db
    if db.is_connected():
        await db.disconnect()


@pytest.fixture
async def clean_db(database):
    await database.execute_raw("TRUNCATE TABLE " + ", ".join(f'"{t}"' for t in TABLES) + " CASCADE")
    yield database


@pytest.fixture
async def client(clean_db):
    from httpx import ASGITransport, AsyncClient

    from app.main import create_app

    app = create_app(run_background=False)  # RateLimitBucket é truncada por clean_db
    # Sem lifespan: a conexão do banco é gerida pela fixture de sessão.
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def unique_email(prefix: str = "user") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}@example.com"


def unique_phone() -> str:
    return "5581" + str(uuid.uuid4().int)[:9]


async def register_user(client, *, clinic: str = "Clínica Teste", role_email: str | None = None) -> dict:
    payload = {
        "name": "Pessoa Teste",
        "email": role_email or unique_email(),
        "password": "Senha1234",
        "clinicName": clinic,
        "whatsapp": unique_phone(),
    }
    res = await client.post("/api/auth/register", json=payload)
    assert res.status_code == 201, res.text
    body = res.json()
    return {
        **body,
        "password": payload["password"],
        "email": payload["email"],
        "tenantId": body["user"]["memberships"][0]["tenantId"],
    }


def auth_headers(tokens: dict) -> dict:
    return {"Authorization": f"Bearer {tokens['accessToken']}"}
