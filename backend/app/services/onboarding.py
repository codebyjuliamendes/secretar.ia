"""Onboarding feito pela Júlia: checklist da conta e boas-vindas com o passo a passo.

Como a liberação é manual, o admin vê o que falta (plano, WhatsApp, serviços, boas-vindas) e dispara o e-mail
de boas-vindas para os OWNERs. O mesmo texto volta como link wa.me para ela mandar pelo WhatsApp se preferir.
"""

from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import quote

from app.config import Settings
from app.db import db
from app.domain.niches import niche_for
from app.jobs.queue import enqueue
from app.jobs.tasks import SEND_EMAIL
from app.services import audit
from app.services.reports import owner_emails


def checklist(row: dict) -> dict[str, bool]:
    """Quatro passos que a conta precisa para funcionar; calculado da listagem do admin (sem consultas extras)."""
    return {
        "plan": row["status"] == "ACTIVE",
        "whatsapp": bool(row["whatsappConnected"]),
        "services": int(row.get("serviceCount") or 0) > 0,
        "welcome": row.get("welcomeSentAt") is not None,
    }


def welcome_text(settings: Settings, tenant) -> tuple[str, str]:
    niche = niche_for(getattr(tenant, "niche", None))
    people = niche.people.lower()
    base = settings.frontend_url.rstrip("/")
    lines = [
        f"Olá! Sua conta de {tenant.name} na Secretar.ia está liberada. Em 5 minutos a assistente começa a atender.",
        "",
        f"1) Entre em {base}/login e vá em “Assistente & WhatsApp”.",
        "2) Clique em “Conectar WhatsApp” e leia o QR Code com o WhatsApp do negócio (como no WhatsApp Web).",
        "3) Tem uma tabela de preços? No “Catálogo de serviços”, clique em “Importar de foto ou PDF” e mande a foto: "
        "a assistente preenche os serviços e você só confere.",
        "4) Confira os horários de atendimento (já vêm seg a sex, 9h às 18h) e ajuste se precisar.",
        "",
        f"Pronto: seus {people} já podem escrever. A assistente se apresenta como assistente, responde em segundos, "
        f"agenda só nos horários livres e chama você quando alguém pede uma pessoa.",
        "",
        f"Sua assistente vem configurada para {niche.label.lower()} no tom {tenant.tone}. Se quiser trocar o tom ou "
        "acrescentar informações (formas de pagamento, endereço, como funciona um procedimento), está tudo em "
        "“Assistente & WhatsApp”.",
        "",
        f"Qualquer dúvida, é só responder este e-mail ou falar com {settings.sales_contact_name}.",
        "",
        "Secretar.ia",
    ]
    return f"Bem-vindo(a) à Secretar.ia - {tenant.name}", "\n".join(lines)


async def send_welcome(settings: Settings, tenant_id: str, *, actor_user_id: str, ip: str | None) -> dict:
    from app.services.tenants import get_tenant_or_404  # import tardio: tenants.py usa checklist() daqui

    tenant = await get_tenant_or_404(tenant_id)
    subject, text = welcome_text(settings, tenant)
    emails = await owner_emails(tenant_id)
    for to in emails:
        await enqueue(SEND_EMAIL, {"to": to, "subject": subject, "text": text})
    now = datetime.now(UTC)
    await db.tenant.update(where={"id": tenant_id}, data={"welcomeSentAt": now})
    await audit.record(
        action="admin.welcome_sent",
        resource_type="tenant",
        resource_id=tenant_id,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        metadata={"emails": len(emails)},
        ip=ip,
    )
    digits = "".join(ch for ch in tenant.whatsapp if ch.isdigit())
    return {
        "emails": emails,
        "sentAt": now.isoformat(),
        "whatsappLink": f"https://wa.me/{digits}?text={quote(text)}" if digits else None,
        "text": text,
    }
