"""Configuração centralizada e validada (fail-fast em produção)."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Env = Literal["development", "test", "staging", "production"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Env = "development"
    log_level: str = "INFO"
    host: str = "0.0.0.0"
    port: int = 8000

    database_url: str

    cors_origins: str = "http://localhost:4000"
    frontend_url: str = "http://localhost:4000"
    public_api_url: str = "http://localhost:8000"

    jwt_secret: str = ""
    access_token_minutes: int = 15
    refresh_token_days: int = 30

    whatsapp_app_secret: str = ""
    evolution_api_url: str = ""
    evolution_api_key: str = ""
    evolution_webhook_token: str = ""

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    ai_timeout_seconds: float = 20.0
    ai_max_output_tokens: int = 512

    stripe_webhook_secret: str = ""
    stripe_secret_key: str = ""
    stripe_price_basic: str = ""  # price_... do plano BASIC no Stripe
    stripe_price_pro: str = ""  # price_... do plano PRO no Stripe
    cron_secret: str = ""

    google_client_id: str = ""
    google_client_secret: str = ""
    token_encryption_key: str = ""  # Fernet; obrigatória em produção para integrações OAuth

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "Secretar.ia <no-reply@secretar.ia>"

    super_admin_email: str = ""

    # Limites operacionais
    queue_concurrency: int = Field(default=5, ge=1, le=50)
    queue_stuck_minutes: int = 10
    login_rate_limit_per_minute: int = 10

    @property
    def is_production_like(self) -> bool:
        return self.app_env in ("production", "staging")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @field_validator("jwt_secret")
    @classmethod
    def _jwt_len(cls, v: str) -> str:
        if v and len(v) < 32:
            raise ValueError("JWT_SECRET deve ter pelo menos 32 caracteres")
        return v

    @model_validator(mode="after")
    def _production_requirements(self) -> Settings:
        if self.is_production_like:
            missing = [
                name
                for name, value in (
                    ("JWT_SECRET", self.jwt_secret),
                    ("WHATSAPP_APP_SECRET", self.whatsapp_app_secret),
                    ("CRON_SECRET", self.cron_secret),
                )
                if not value
            ]
            if missing:
                raise ValueError(f"Variáveis obrigatórias ausentes em {self.app_env}: {', '.join(missing)}")
            if "*" in self.cors_origin_list:
                raise ValueError("CORS_ORIGINS não pode conter '*' em produção")
        elif not self.jwt_secret:
            # Em desenvolvimento/test usamos um segredo determinístico apenas para facilitar o setup.
            object.__setattr__(self, "jwt_secret", "dev-only-secret-change-me-please-0123456789abcdef")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
