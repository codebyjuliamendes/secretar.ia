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
    # Medido em 14/set/2026 com chave nova: o lite responde em ~1s e os modelos maiores levavam 12s a 20s,
    # com erros de sobrecarga. Em conversa de WhatsApp, velocidade vale mais que sofisticação.
    gemini_model: str = "gemini-3.5-flash-lite"
    gemini_embedding_model: str = "gemini-embedding-001"
    gemini_tts_model: str = "gemini-2.5-flash-preview-tts"  # responder áudio com áudio (experimental)
    tts_timeout_seconds: float = 60.0  # voz é mais lenta que texto e roda em segundo plano; não prende ninguém
    tts_voice: str = "Kore"  # voz fixa por plataforma; simples e previsível

    # Identificação da operadora nas páginas de Privacidade e Termos. Vazio = a página omite a linha.
    legal_entity: str = ""  # razão social
    legal_doc: str = ""  # CNPJ
    privacy_email: str = ""  # canal do encarregado (LGPD); vazio cai em ALERTS_EMAIL/SUPER_ADMIN_EMAIL

    @property
    def privacy_contact(self) -> str:
        return self.privacy_email or self.alerts_email or self.super_admin_email

    ai_timeout_seconds: float = 20.0
    ai_max_output_tokens: int = 512

    stripe_webhook_secret: str = ""
    stripe_secret_key: str = ""
    stripe_price_basic: str = ""  # price_... do plano BASIC no Stripe
    stripe_price_pro: str = ""  # price_... do plano PRO no Stripe
    stripe_price_premium: str = ""  # price_... do plano PREMIUM no Stripe
    cron_secret: str = ""

    google_client_id: str = ""
    google_client_secret: str = ""
    # Notificações push do Google Calendar (events.watch). Exige PUBLIC_API_URL em https com certificado válido;
    # sem isso a leitura periódica (pull-calendar) continua sozinha.
    google_push_enabled: bool = True
    token_encryption_key: str = ""  # Fernet; obrigatória em produção para integrações OAuth

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "Secretar.ia <no-reply@secretar.ia>"

    super_admin_email: str = ""

    # Contato comercial: WhatsApp (só dígitos, com DDI, ex.: 5581999998888) e nome de quem atende.
    # Aparece no botão "Falar com a Júlia" do plano Enterprise e no rodapé da landing.
    sales_whatsapp: str = ""
    sales_contact_name: str = "Júlia"
    # WhatsApp da conta demo (só dígitos): botão "Converse com a assistente agora" na landing. Vazio = sem botão.
    demo_whatsapp: str = ""
    # Para onde vão os alertas operacionais (cota em 80%/100%, relatórios com erro). Vazio = SUPER_ADMIN_EMAIL.
    alerts_email: str = ""

    @property
    def alerts_to(self) -> str:
        return self.alerts_email or self.super_admin_email

    # Confiar em X-Real-IP / X-Forwarded-For (o BFF Next.js e o proxy da plataforma os preenchem). Desligue
    # se o backend estiver exposto diretamente à internet, senão qualquer cliente forja o IP e zera os limites.
    trust_proxy_headers: bool = True

    # Worker da fila e agendador neste processo. Em várias réplicas, deixe true em UMA (ou em um processo
    # dedicado) e false nas demais, senão a concorrência da fila e o polling se multiplicam.
    run_background_jobs: bool = True

    # Limites operacionais
    max_request_body_bytes: int = 32 * 1024 * 1024  # webhook normalizado aceita até 24 MB de mídia em base64
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
            for name, url in (("PUBLIC_API_URL", self.public_api_url), ("FRONTEND_URL", self.frontend_url)):
                if not url.startswith("https://"):
                    # Sem isso o OAuth do Google, o webhook da Evolution e os links de e-mail apontam para localhost.
                    raise ValueError(f"{name} deve ser https em {self.app_env} (valor atual: {url})")
        elif not self.jwt_secret:
            # Em desenvolvimento/test usamos um segredo determinístico apenas para facilitar o setup.
            object.__setattr__(self, "jwt_secret", "dev-only-secret-change-me-please-0123456789abcdef")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
