"""Avisos de cota: 80% e 100% do plano geram aviso no painel e e-mail para a equipe Secretar.ia.

Decisão de produto (13/set/2026): estourar a cota NÃO corta o atendimento; a assistente segue respondendo e a
Julia decide com o cliente se faz upgrade. O admin pode ligar "cortar ao estourar" por conta (Tenant.hardLimit).
Os avisos são deduplicados por período: o contador só passa por cada valor uma vez, então comparamos o valor
exato devolvido pelo incremento atômico em vez de reler o banco.
"""

from __future__ import annotations

import math

from app.config import Settings
from app.domain.niches import niche_for
from app.domain.plans import limits_for
from app.jobs.queue import enqueue
from app.jobs.tasks import SEND_EMAIL
from app.services import notifications
from app.services.usage import current_period

WARN_RATIO = 0.8


def warn_threshold(limit: int) -> int:
    return math.ceil(limit * WARN_RATIO)


async def _alert_team(settings: Settings, subject: str, text: str) -> None:
    if settings.alerts_to:
        await enqueue(SEND_EMAIL, {"to": settings.alerts_to, "subject": subject, "text": text})


async def after_ai_message(settings: Settings, tenant, used_now: int) -> None:
    """Chamado com o valor do contador logo após incrementar. Dispara o aviso de 80% e o de 100%."""
    limit = limits_for(str(tenant.plan)).ai_messages_per_month
    if limit <= 0:
        return
    period = current_period()
    people = niche_for(getattr(tenant, "niche", None)).people.lower()
    admin_link = f"{settings.frontend_url.rstrip('/')}/admin/tenants"
    if used_now == warn_threshold(limit):
        created = await notifications.notify(
            tenant.id,
            type_="BILLING",
            title=f"80% das mensagens do mês usadas ({period})",
            body=(
                f"A assistente já respondeu {used_now} de {limit} mensagens de {people} neste mês. "
                "Nada muda por enquanto: ela continua atendendo. Se o movimento se mantiver, vale conversar "
                "sobre a próxima faixa do plano."
            ),
            dedupe_minutes=45 * 24 * 60,
        )
        if not created:  # retentativa do mesmo valor: já avisamos
            return
        await _alert_team(
            settings,
            f"[Secretar.ia] {tenant.name} chegou a 80% da cota ({used_now}/{limit})",
            f"{tenant.name} (plano {tenant.plan}) usou {used_now} de {limit} mensagens em {period}.\n"
            f"Bom momento para oferecer a próxima faixa. Admin: {admin_link}",
        )
    elif used_now == limit:
        title = f"Limite mensal de mensagens atingido ({period})"
        body = f"O plano permite {limit} mensagens de IA por mês e a assistente chegou lá. " + (
            "O atendimento automático fica pausado até o próximo mês ou até a mudança de plano."
            if tenant.hardLimit
            else "Ela continua respondendo normalmente; a equipe Secretar.ia vai falar com você sobre o plano."
        )
        created = await notifications.notify(
            tenant.id, type_="BILLING", title=title, body=body, dedupe_minutes=45 * 24 * 60
        )
        if not created:
            return
        await _alert_team(
            settings,
            f"[Secretar.ia] {tenant.name} estourou a cota ({limit}/{limit})",
            f"{tenant.name} (plano {tenant.plan}) atingiu {limit} mensagens em {period}. "
            + ("A conta está com corte ligado: a IA parou." if tenant.hardLimit else "A IA segue respondendo.")
            + f"\nAdmin: {admin_link}",
        )
