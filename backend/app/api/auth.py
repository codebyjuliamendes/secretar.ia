from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Request, status
from pydantic import BaseModel, EmailStr, Field

from app.config import Settings, get_settings
from app.deps import CurrentUser, client_ip, current_user, get_settings_dep
from app.errors import RateLimitedError
from app.security.ratelimit import PostgresRateLimiter
from app.services import auth as auth_service
from app.services import team as team_service

router = APIRouter(prefix="/auth", tags=["auth"])

# Persistidos no Postgres: valem para todas as réplicas (ADR-008).
_login_limiter = PostgresRateLimiter("auth.login", limit=get_settings().login_rate_limit_per_minute, window_seconds=60)
# Teto por conta (independe do IP: fecha spray com IPs rotativos ou X-Forwarded-For forjado) e por IP
# (fecha "uma senha em mil e-mails", que vira DoS de CPU pelo bcrypt).
_login_email_limiter = PostgresRateLimiter("auth.login.email", limit=30, window_seconds=600)
_login_ip_limiter = PostgresRateLimiter("auth.login.ip", limit=100, window_seconds=60)
_register_limiter = PostgresRateLimiter("auth.register", limit=20, window_seconds=3600)
_forgot_limiter = PostgresRateLimiter("auth.forgot", limit=5, window_seconds=600)


async def reset_rate_limiters() -> None:
    """Usado em testes para isolar cenários; sem efeito em produção."""
    for limiter in (_login_limiter, _login_email_limiter, _login_ip_limiter, _register_limiter, _forgot_limiter):
        await limiter.reset()


async def _limit(limiter: PostgresRateLimiter, key: str | None) -> None:
    if not await limiter.allow(key or "unknown"):
        raise RateLimitedError("Muitas tentativas. Aguarde um instante e tente novamente.")


class RegisterIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    clinicName: str = Field(min_length=2, max_length=120)
    whatsapp: str = Field(min_length=8, max_length=32)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class RefreshIn(BaseModel):
    refreshToken: str = Field(min_length=10, max_length=512)


class LogoutIn(BaseModel):
    refreshToken: str | None = Field(default=None, max_length=512)
    allSessions: bool = False


class EmailIn(BaseModel):
    email: EmailStr


class TokenIn(BaseModel):
    token: str = Field(min_length=10, max_length=512)


class ResetIn(TokenIn):
    password: str = Field(min_length=8, max_length=128)


class ChangePasswordIn(BaseModel):
    currentPassword: str = Field(min_length=1, max_length=128)
    newPassword: str = Field(min_length=8, max_length=128)


class InviteAcceptIn(TokenIn):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    password: str | None = Field(default=None, min_length=8, max_length=128)


async def optional_user(
    authorization: str | None = Header(default=None), settings: Settings = Depends(get_settings_dep)
) -> CurrentUser | None:
    if not authorization:
        return None
    return await current_user(authorization=authorization, settings=settings)


@router.get("/invites/{token}")
async def invite_details(token: str):
    return await team_service.invite_info(token)


@router.post("/invites/accept")
async def accept_invite(
    data: InviteAcceptIn,
    request: Request,
    user: CurrentUser | None = Depends(optional_user),
    settings: Settings = Depends(get_settings_dep),
    user_agent: str | None = Header(default=None),
):
    return await team_service.accept_invite(
        settings,
        token=data.token,
        current_user_id=user.id if user else None,
        name=data.name,
        password=data.password,
        user_agent=user_agent,
        ip=client_ip(request),
    )


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    data: RegisterIn,
    request: Request,
    settings: Settings = Depends(get_settings_dep),
    user_agent: str | None = Header(default=None),
):
    ip = client_ip(request)
    await _limit(_register_limiter, ip)
    return await auth_service.register(
        settings,
        name=data.name,
        email=data.email,
        password=data.password,
        clinic_name=data.clinicName,
        whatsapp=data.whatsapp,
        user_agent=user_agent,
        ip=ip,
    )


@router.post("/login")
async def login(
    data: LoginIn,
    request: Request,
    settings: Settings = Depends(get_settings_dep),
    user_agent: str | None = Header(default=None),
):
    ip = client_ip(request)
    await _limit(_login_ip_limiter, ip)
    await _limit(_login_email_limiter, data.email.lower())
    await _limit(_login_limiter, f"{ip}:{data.email.lower()}")
    return await auth_service.login(settings, email=data.email, password=data.password, user_agent=user_agent, ip=ip)


@router.post("/refresh")
async def refresh(
    data: RefreshIn,
    request: Request,
    settings: Settings = Depends(get_settings_dep),
    user_agent: str | None = Header(default=None),
):
    return await auth_service.refresh(
        settings, refresh_token=data.refreshToken, user_agent=user_agent, ip=client_ip(request)
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    data: LogoutIn,
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings_dep),
):
    user_id = None
    if data.allSessions and authorization:
        try:
            user_id = (await current_user(authorization, settings)).id
        except Exception:  # noqa: BLE001 - logout nunca falha para o cliente
            user_id = None
    await auth_service.logout(data.refreshToken, user_id=user_id, all_sessions=data.allSessions)
    return None


@router.get("/me")
async def me(user: CurrentUser = Depends(current_user)):
    return await auth_service.me(user.id)


@router.post("/verify-email")
async def verify_email(data: TokenIn):
    await auth_service.verify_email(data.token)
    return {"verified": True}


@router.post("/resend-verification", status_code=status.HTTP_202_ACCEPTED)
async def resend_verification(
    user: CurrentUser = Depends(current_user), settings: Settings = Depends(get_settings_dep)
):
    await auth_service.resend_verification(settings, user.id)
    return {"sent": True}


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
async def forgot_password(data: EmailIn, request: Request, settings: Settings = Depends(get_settings_dep)):
    await _limit(_forgot_limiter, client_ip(request))
    await auth_service.forgot_password(settings, data.email)
    return {"sent": True}


@router.post("/reset-password")
async def reset_password(data: ResetIn):
    await auth_service.reset_password(data.token, data.password)
    return {"reset": True}


@router.post("/change-password")
async def change_password(data: ChangePasswordIn, user: CurrentUser = Depends(current_user)):
    await auth_service.change_password(user.id, current_password=data.currentPassword, new_password=data.newPassword)
    return {"changed": True}
