FROM python:3.12-slim AS base

# PRISMA_*: cache do Prisma (CLI Node + engines) dentro de /app para ficar acessivel ao usuario nao-root
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PRISMA_HOME_DIR=/app/.prisma \
    PRISMA_NODEENV_CACHE_DIR=/app/.prisma/.cache/prisma-python/nodeenv

WORKDIR /app

# libatomic1: exigida pelo binario do Node que o Prisma Python baixa
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates libatomic1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /uvx /bin/

# Dependencias primeiro (cache de camada)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Codigo
COPY . .
RUN uv sync --frozen --no-dev && uv run prisma generate --schema=prisma/schema.prisma

# Usuario nao-root
RUN useradd --create-home --uid 1001 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD curl -fsS http://localhost:8000/health || exit 1

# Aplica migrations (desligue com RUN_MIGRATIONS_ON_START=false quando houver release command separado) e sobe a
# API com `exec`: o Uvicorn vira PID 1 e recebe SIGTERM (shutdown gracioso do worker/scheduler no rolling deploy).
CMD ["sh", "-c", "if [ \"${RUN_MIGRATIONS_ON_START:-true}\" = \"true\" ]; then uv run prisma migrate deploy --schema=prisma/schema.prisma; fi && exec uv run uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --timeout-keep-alive 15 --limit-concurrency 300 --timeout-graceful-shutdown 25"]
