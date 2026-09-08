"""Fábrica da aplicação FastAPI."""

from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app import jobs  # noqa: F401 - garante registro das tarefas
from app.api import admin, auth, clinic, internal, webhooks
from app.config import get_settings
from app.db import db
from app.errors import register_exception_handlers
from app.jobs import tasks  # noqa: F401
from app.jobs.queue import worker_loop
from app.jobs.scheduler import scheduler_loop
from app.logging import get_logger, request_id_var, setup_logging

log = get_logger("app")


async def ensure_super_admin(email: str) -> None:
    if not email:
        return
    user = await db.user.find_unique(where={"email": email.lower()})
    if user and str(user.platformRole) != "SUPER_ADMIN":
        await db.user.update(where={"id": user.id}, data={"platformRole": "SUPER_ADMIN"})
        log.info("super_admin_promoted", email=email)


def create_app(*, run_background: bool = True) -> FastAPI:
    settings = get_settings()
    setup_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await db.connect()
        await ensure_super_admin(settings.super_admin_email)
        stop = asyncio.Event()
        tasks_: list[asyncio.Task] = []
        if run_background:
            tasks_ = [asyncio.create_task(worker_loop(stop)), asyncio.create_task(scheduler_loop(stop))]
        log.info("app_started", env=settings.app_env, background=run_background)
        try:
            yield
        finally:
            stop.set()
            for t in tasks_:
                t.cancel()
            await asyncio.gather(*tasks_, return_exceptions=True)
            if db.is_connected():
                await db.disconnect()
            log.info("app_stopped")

    app = FastAPI(
        title="Secretar.ia API",
        version="1.0.0",
        description="Backend multi-tenant de atendimento por WhatsApp com IA para clínicas.",
        lifespan=lifespan,
        docs_url="/docs" if not settings.is_production_like else None,
        redoc_url=None,
        openapi_url="/openapi.json" if not settings.is_production_like else None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-Id"],
        expose_headers=["X-Request-Id"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        token = request_id_var.set(rid)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers["X-Request-Id"] = rid
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Cache-Control", "no-store")
        return response

    register_exception_handlers(app)

    app.include_router(internal.router)
    app.include_router(internal.cron_router, prefix="/api")
    app.include_router(auth.router, prefix="/api")
    app.include_router(admin.router, prefix="/api")
    app.include_router(clinic.router, prefix="/api")
    app.include_router(webhooks.router, prefix="/api")
    return app


app = create_app()
