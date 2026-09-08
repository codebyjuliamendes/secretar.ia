"""Envio de e-mail transacional (SMTP). Sem SMTP configurado em desenvolvimento, loga no console."""

from __future__ import annotations

from email.message import EmailMessage

import aiosmtplib

from app.config import Settings
from app.errors import IntegrationUnavailableError
from app.logging import get_logger

log = get_logger("integrations.email")


class EmailTransientError(Exception):
    pass


class EmailSender:
    async def send(self, to: str, subject: str, text: str, html: str | None = None) -> None: ...


class ConsoleEmailSender(EmailSender):
    async def send(self, to: str, subject: str, text: str, html: str | None = None) -> None:
        log.info("email_console_send", to=to, subject=subject, body=text)


class SmtpEmailSender(EmailSender):
    def __init__(self, settings: Settings):
        self._s = settings

    async def send(self, to: str, subject: str, text: str, html: str | None = None) -> None:
        msg = EmailMessage()
        msg["From"] = self._s.smtp_from
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(text)
        if html:
            msg.add_alternative(html, subtype="html")
        try:
            await aiosmtplib.send(
                msg,
                hostname=self._s.smtp_host,
                port=self._s.smtp_port,
                username=self._s.smtp_user or None,
                password=self._s.smtp_password or None,
                start_tls=self._s.smtp_port == 587,
                use_tls=self._s.smtp_port == 465,
                timeout=20,
            )
        except (aiosmtplib.SMTPException, OSError) as exc:
            raise EmailTransientError(f"SMTP falhou: {exc.__class__.__name__}") from exc


def build_email_sender(settings: Settings) -> EmailSender:
    if settings.smtp_host:
        return SmtpEmailSender(settings)
    if settings.is_production_like:
        raise IntegrationUnavailableError("SMTP não configurado.", code="email_not_configured")
    return ConsoleEmailSender()
