"""Fábrica da aplicação FastAPI."""

from __future__ import annotations

import asyncio
import re
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import jobs  # noqa: F401 - garante registro das tarefas
from app.api import admin, auth, clinic, integrations, internal, public, webhooks
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


_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")


def _safe_request_id(value: str | None) -> str:
    """Reaproveita o id do chamador (BFF, proxy) só se for curto e sem caracteres de controle; senão gera um."""
    if value and _REQUEST_ID_RE.match(value):
        return value
    return uuid.uuid4().hex[:16]


class BodySizeLimitMiddleware:
    """ASGI puro: corpo sem Content-Length (chunked) é lido aqui, com teto, antes de chegar à aplicação.

    Com Content-Length o middleware HTTP abaixo recusa antes de ler qualquer byte; sem ele, nada impediria um POST
    infinito de ocupar memória. O corpo aceito é reentregue intacto à aplicação."""

    def __init__(self, app, max_bytes: int):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or any(k == b"content-length" for k, _ in scope.get("headers", [])):
            await self.app(scope, receive, send)
            return
        chunks: list[bytes] = []
        size = 0
        more = True
        while more:
            message = await receive()
            if message["type"] != "http.request":  # desconexão no meio do envio
                await self.app(scope, _replay([], message, receive), send)
                return
            body = message.get("body", b"")
            size += len(body)
            if size > self.max_bytes:
                response = JSONResponse(
                    status_code=413,
                    content={"error": {"code": "payload_too_large", "message": "Corpo da requisição grande demais."}},
                )
                await response(scope, receive, send)
                return
            chunks.append(body)
            more = message.get("more_body", False)
        await self.app(scope, _replay(chunks, None, receive), send)


def _replay(chunks: list[bytes], pending: dict | None, receive):
    delivered = False

    async def replay_receive():
        nonlocal delivered
        if not delivered:
            delivered = True
            if pending is not None:
                return pending
            return {"type": "http.request", "body": b"".join(chunks), "more_body": False}
        return await receive()

    return replay_receive


def create_app(*, run_background: bool = True) -> FastAPI:
    settings = get_settings()
    setup_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await db.connect()
        await ensure_super_admin(settings.super_admin_email)
        stop = asyncio.Event()
        tasks_: list[asyncio.Task] = []
        background = run_background and settings.run_background_jobs
        if background:
            tasks_ = [asyncio.create_task(worker_loop(stop)), asyncio.create_task(scheduler_loop(stop))]
        log.info("app_started", env=settings.app_env, background=background)
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
        rid = _safe_request_id(request.headers.get("x-request-id"))
        token = request_id_var.set(rid)
        started = time.perf_counter()
        try:
            # Teto de corpo antes de ler qualquer byte: um POST gigante não ocupa memória nem CPU.
            declared = request.headers.get("content-length")
            if declared and declared.isdigit() and int(declared) > settings.max_request_body_bytes:
                response = JSONResponse(
                    status_code=413,
                    content={"error": {"code": "payload_too_large", "message": "Corpo da requisição grande demais."}},
                )
            else:
                response = await call_next(request)
            if request.url.path not in ("/health", "/ready"):
                log.info(
                    "http_request",
                    method=request.method,
                    path=request.url.path,
                    status=response.status_code,
                    ms=round((time.perf_counter() - started) * 1000),
                )
        finally:
            request_id_var.reset(token)
        response.headers["X-Request-Id"] = rid
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Cache-Control", "no-store")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-site")
        if settings.is_production_like:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response

    register_exception_handlers(app)
    # Por fora de tudo: conta os bytes de corpos sem Content-Length (chunked), que o teto acima não enxerga.
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_request_body_bytes)

    app.include_router(internal.router)
    app.include_router(internal.cron_router, prefix="/api")
    app.include_router(auth.router, prefix="/api")
    app.include_router(admin.router, prefix="/api")
    app.include_router(clinic.router, prefix="/api")
    app.include_router(public.router, prefix="/api")
    app.include_router(webhooks.router, prefix="/api")
    app.include_router(integrations.router, prefix="/api")
    return app


app = create_app()
