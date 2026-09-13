"""Agenda real da clínica: catálogo de serviços, janelas de atendimento, horários livres e conflitos.

Convenções:
  - weekday: 0 = segunda ... 6 = domingo (Python `date.weekday()`).
  - startMin/endMin: minutos locais desde 00:00 no fuso do tenant.
  - Todas as datas persistidas em UTC; conversão local só na geração de slots e na apresentação.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.db import db
from app.errors import AppError, ConflictError, NotFoundError
from app.services import audit
from generated_prisma.errors import UniqueViolationError

BLOCKING_STATUSES = ["PENDING", "CONFIRMED"]
DEFAULT_DURATION_MIN = 60
DEFAULT_RULES = [(wd, 9 * 60, 18 * 60) for wd in range(5)]  # seg-sex 09:00-18:00
WEEKDAY_NAMES = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]


@dataclass(frozen=True)
class Rule:
    weekday: int
    start_min: int
    end_min: int


@dataclass(frozen=True)
class Busy:
    start: datetime  # UTC
    end: datetime  # UTC


@dataclass(frozen=True)
class Slot:
    start: datetime  # UTC
    end: datetime  # UTC

    def label(self, tz: ZoneInfo) -> str:
        local = self.start.astimezone(tz)
        return f"{WEEKDAY_NAMES[local.weekday()]} {local.strftime('%d/%m às %H:%M')}"


def _fmt_min(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


def rules_to_text(rules: list[Rule]) -> str:
    """Descrição legível dos horários, usada no prompt da IA e como fallback de `businessHours`."""
    if not rules:
        return "horários de atendimento não configurados"
    by_day: dict[int, list[str]] = {}
    for r in sorted(rules, key=lambda r: (r.weekday, r.start_min)):
        by_day.setdefault(r.weekday, []).append(f"{_fmt_min(r.start_min)}-{_fmt_min(r.end_min)}")
    return "; ".join(f"{WEEKDAY_NAMES[d]} {', '.join(w)}" for d, w in by_day.items())


def _busy_over_capacity(spans: list[tuple[datetime, datetime]], capacity: int) -> list[Busy]:
    """Com capacidade 1, cada compromisso bloqueia. Com N profissionais, só os trechos onde N ou mais se sobrepõem."""
    if capacity <= 1:
        return [Busy(s, e) for s, e in spans]
    events = sorted([(s, 1) for s, _ in spans] + [(e, -1) for _, e in spans], key=lambda x: (x[0], x[1]))
    out: list[Busy] = []
    depth = 0
    opened: datetime | None = None
    for at, delta in events:
        depth += delta
        if depth >= capacity and opened is None:
            opened = at
        elif depth < capacity and opened is not None:
            if at > opened:
                out.append(Busy(opened, at))
            opened = None
    return out


def overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    return a_start < b_end and b_start < a_end


def generate_slots(
    *,
    rules: list[Rule],
    busy: list[Busy],
    tz: ZoneInfo,
    start_from: datetime,
    days: int,
    duration_min: int,
    step_min: int,
    limit: int | None = None,
) -> list[Slot]:
    """Gera horários livres (UTC) a partir das janelas locais, descontando compromissos. Função pura."""
    if not rules or duration_min <= 0 or step_min <= 0:
        return []
    out: list[Slot] = []
    horizon = start_from + timedelta(days=days)
    day0 = start_from.astimezone(tz).date()
    last_day = horizon.astimezone(tz).date()
    for offset in range((last_day - day0).days + 1):
        d: date = day0 + timedelta(days=offset)
        for r in rules:
            if r.weekday != d.weekday():
                continue
            m = r.start_min
            while m + duration_min <= r.end_min:
                local_dt = datetime(d.year, d.month, d.day, m // 60, m % 60, tzinfo=tz)
                s = local_dt.astimezone(UTC)
                e = s + timedelta(minutes=duration_min)
                if start_from <= s < horizon and not any(overlaps(s, e, b.start, b.end) for b in busy):
                    out.append(Slot(s, e))
                    if limit and len(out) >= limit:
                        return out
                m += step_min
    return out


def spread_slots(slots: list[Slot], tz: ZoneInfo, *, per_day: int = 2, limit: int = 6) -> list[Slot]:
    """Escolhe até `per_day` horários por dia, em ordem, para a sugestão cobrir vários dias (e não só a manhã
    do primeiro dia livre)."""
    out: list[Slot] = []
    per_day_count: dict[date, int] = {}
    for s in slots:
        d = s.start.astimezone(tz).date()
        if per_day_count.get(d, 0) >= per_day:
            continue
        per_day_count[d] = per_day_count.get(d, 0) + 1
        out.append(s)
        if len(out) >= limit:
            break
    return out


async def lock_tenant_agenda(tx, tenant_id: str) -> None:
    """Serializa verificações+criações de horário do tenant dentro da transação (evita reserva dupla do
    mesmo slot por duas mensagens/cliques simultâneos). Liberado no commit."""
    # `IS NULL` transforma o retorno void em boolean: o Prisma não desserializa colunas void.
    await tx.query_raw("SELECT pg_advisory_xact_lock(hashtext($1)) IS NULL AS locked", f"agenda:{tenant_id}")


def within_rules(start_utc: datetime, duration_min: int, rules: list[Rule], tz: ZoneInfo) -> bool:
    local = start_utc.astimezone(tz)
    start_m = local.hour * 60 + local.minute
    end_m = start_m + duration_min
    return any(r.weekday == local.weekday() and r.start_min <= start_m and end_m <= r.end_min for r in rules)


# ------------------------------- Persistência -------------------------------


async def get_rules(tenant_id: str) -> list[Rule]:
    rows = await db.availabilityrule.find_many(
        where={"tenantId": tenant_id}, order=[{"weekday": "asc"}, {"startMin": "asc"}]
    )
    return [Rule(r.weekday, r.startMin, r.endMin) for r in rows]


def rules_view(rules: list[Rule]) -> list[dict]:
    return [{"weekday": r.weekday, "start": _fmt_min(r.start_min), "end": _fmt_min(r.end_min)} for r in rules]


def _parse_hhmm(value: str) -> int:
    try:
        h, m = value.split(":")
        h_i, m_i = int(h), int(m)
    except (ValueError, AttributeError) as exc:
        raise AppError(f"Horário inválido: {value}", code="invalid_time") from exc
    if not (0 <= h_i <= 24 and 0 <= m_i < 60) or h_i * 60 + m_i > 24 * 60:
        raise AppError(f"Horário inválido: {value}", code="invalid_time")
    return h_i * 60 + m_i


async def set_rules(
    tenant_id: str, rules_in: list[dict[str, Any]], *, actor_user_id: str, ip: str | None
) -> list[dict]:
    parsed: list[Rule] = []
    for item in rules_in:
        wd = int(item["weekday"])
        if not 0 <= wd <= 6:
            raise AppError("Dia da semana inválido.", code="invalid_weekday")
        s, e = _parse_hhmm(item["start"]), _parse_hhmm(item["end"])
        if e <= s:
            raise AppError("O fim da janela deve ser depois do início.", code="invalid_window")
        parsed.append(Rule(wd, s, e))
    for a in parsed:
        for b in parsed:
            if a is not b and a.weekday == b.weekday and overlaps_min(a, b):
                raise AppError(f"Janelas sobrepostas em {WEEKDAY_NAMES[a.weekday]}.", code="overlapping_windows")
    async with db.tx() as tx:
        await tx.availabilityrule.delete_many(where={"tenantId": tenant_id})
        if parsed:
            await tx.availabilityrule.create_many(
                data=[
                    {"tenantId": tenant_id, "weekday": r.weekday, "startMin": r.start_min, "endMin": r.end_min}
                    for r in parsed
                ]
            )
        await tx.tenant.update(where={"id": tenant_id}, data={"businessHours": rules_to_text(parsed)})
    await audit.record(
        action="scheduling.rules_updated",
        resource_type="tenant",
        resource_id=tenant_id,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        metadata={"rules": len(parsed)},
        ip=ip,
    )
    return rules_view(parsed)


def overlaps_min(a: Rule, b: Rule) -> bool:
    return a.start_min < b.end_min and b.start_min < a.end_min


async def ensure_default_rules(tenant_id: str) -> None:
    if await db.availabilityrule.count(where={"tenantId": tenant_id}) == 0:
        await db.availabilityrule.create_many(
            data=[{"tenantId": tenant_id, "weekday": wd, "startMin": s, "endMin": e} for wd, s, e in DEFAULT_RULES]
        )


async def busy_between(
    tenant_id: str,
    start: datetime,
    end: datetime,
    *,
    exclude_id: str | None = None,
    professional_id: str | None = None,
) -> list[Busy]:
    """Ocupações que bloqueiam um horário. Com profissional: só os compromissos dele (e os sem profissional).
    Sem profissional, com equipe cadastrada: um horário só fica ocupado quando TODOS os profissionais ativos
    estão tomados (capacidade = nº de profissionais)."""
    where: dict[str, Any] = {
        "tenantId": tenant_id,
        "status": {"in": BLOCKING_STATUSES},
        "date": {"lt": end},
        "OR": [
            {"endAt": {"gt": start}},
            {"endAt": None, "date": {"gt": start - timedelta(minutes=DEFAULT_DURATION_MIN)}},
        ],
    }
    if exclude_id:
        where["id"] = {"not": exclude_id}
    if professional_id:
        # Compromissos do profissional pedido ou sem profissional definido.
        span_or = where.pop("OR")
        where["AND"] = [{"OR": span_or}, {"OR": [{"professionalId": professional_id}, {"professionalId": None}]}]
    rows = await db.appointment.find_many(where=where)
    spans = [(a.date, a.endAt or a.date + timedelta(minutes=a.durationMin or DEFAULT_DURATION_MIN)) for a in rows]
    capacity = 1
    if not professional_id:
        capacity = max(1, await db.professional.count(where={"tenantId": tenant_id, "active": True}))
    busy = _busy_over_capacity(spans, capacity)
    # Compromissos criados direto no Google Calendar da clínica também ocupam horário.
    external = await db.externalbusy.find_many(
        where={"tenantId": tenant_id, "startAt": {"lt": end}, "endAt": {"gt": start}}
    )
    busy.extend(Busy(x.startAt, x.endAt) for x in external)
    return busy


async def free_slots(
    tenant,
    *,
    start_from: datetime | None = None,
    days: int = 7,
    duration_min: int = DEFAULT_DURATION_MIN,
    limit: int | None = None,
    professional_id: str | None = None,
) -> list[Slot]:
    tz = ZoneInfo(tenant.timezone or "America/Sao_Paulo")
    start_from = start_from or datetime.now(UTC)
    rules = await get_rules(tenant.id)
    if not rules:
        return []
    busy = await busy_between(
        tenant.id, start_from, start_from + timedelta(days=days + 1), professional_id=professional_id
    )
    return generate_slots(
        rules=rules,
        busy=busy,
        tz=tz,
        start_from=start_from,
        days=days,
        duration_min=duration_min,
        step_min=tenant.slotMinutes or 30,
        limit=limit,
    )


async def check_availability(
    tenant, start_utc: datetime, duration_min: int, *, exclude_id: str | None = None, professional_id: str | None = None
) -> tuple[bool, str | None]:
    """Retorna (disponível, motivo). Sem regras configuradas, só verifica conflitos."""
    tz = ZoneInfo(tenant.timezone or "America/Sao_Paulo")
    # Conflito e janela vêm antes de "past": quem lança retroativo (permitido) ainda vê a sobreposição.
    end = start_utc + timedelta(minutes=duration_min)
    if await busy_between(tenant.id, start_utc, end, exclude_id=exclude_id, professional_id=professional_id):
        return False, "conflict"
    rules = await get_rules(tenant.id)
    if rules and not within_rules(start_utc, duration_min, rules, tz):
        return False, "outside_hours"
    if start_utc < datetime.now(UTC):
        return False, "past"
    return True, None


# --------------------------------- Serviços ---------------------------------


def service_view(s) -> dict:
    return {
        "id": s.id,
        "name": s.name,
        "durationMin": s.durationMin,
        "priceCents": s.priceCents,
        "description": s.description,
        "active": s.active,
        "sortOrder": s.sortOrder,
    }


async def list_services(tenant_id: str, *, only_active: bool = False) -> list[dict]:
    where: dict[str, Any] = {"tenantId": tenant_id}
    if only_active:
        where["active"] = True
    rows = await db.service.find_many(where=where, order=[{"sortOrder": "asc"}, {"name": "asc"}])
    return [service_view(s) for s in rows]


def services_to_text(services: list[dict]) -> str:
    parts = []
    for s in services:
        price = (
            f"R$ {s['priceCents'] / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            if s.get("priceCents") is not None
            else "valor sob consulta"
        )
        parts.append(f"{s['name']} ({s['durationMin']} min, {price})")
    return "; ".join(parts)


async def create_service(tenant_id: str, data: dict[str, Any], *, actor_user_id: str, ip: str | None) -> dict:
    try:
        s = await db.service.create(data={"tenantId": tenant_id, **data})
    except UniqueViolationError as exc:
        raise ConflictError("Já existe um serviço com este nome.", code="service_exists") from exc
    await _sync_prices_text(tenant_id)
    await audit.record(
        action="service.created",
        resource_type="service",
        resource_id=s.id,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        metadata={"name": s.name},
        ip=ip,
    )
    return service_view(s)


async def update_service(
    tenant_id: str, service_id: str, data: dict[str, Any], *, actor_user_id: str, ip: str | None
) -> dict:
    s = await db.service.find_first(where={"id": service_id, "tenantId": tenant_id})
    if s is None:
        raise NotFoundError("Serviço não encontrado.")
    payload = {k: v for k, v in data.items() if v is not None}
    try:
        updated = await db.service.update(where={"id": s.id}, data=payload)
    except UniqueViolationError as exc:
        raise ConflictError("Já existe um serviço com este nome.", code="service_exists") from exc
    await _sync_prices_text(tenant_id)
    await audit.record(
        action="service.updated",
        resource_type="service",
        resource_id=s.id,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        metadata={"fields": sorted(payload)},
        ip=ip,
    )
    return service_view(updated)


async def delete_service(tenant_id: str, service_id: str, *, actor_user_id: str, ip: str | None) -> None:
    s = await db.service.find_first(where={"id": service_id, "tenantId": tenant_id})
    if s is None:
        raise NotFoundError("Serviço não encontrado.")
    await db.service.delete(where={"id": s.id})  # agendamentos mantêm o nome (serviceId vira NULL)
    await _sync_prices_text(tenant_id)
    await audit.record(
        action="service.deleted",
        resource_type="service",
        resource_id=s.id,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        metadata={"name": s.name},
        ip=ip,
    )


async def _sync_prices_text(tenant_id: str) -> None:
    """Mantém o campo textual `prices` coerente com o catálogo (usado pela IA e exibido nas configurações)."""
    services = await list_services(tenant_id, only_active=True)
    if services:
        await db.tenant.update(where={"id": tenant_id}, data={"prices": services_to_text(services)})


def match_service(services: list[dict], name: str | None) -> dict | None:
    """Casa o nome informado pela IA/paciente com o catálogo (case-insensitive, prefixo ou contido)."""
    if not name:
        return None
    n = name.strip().lower()
    for s in services:
        if s["name"].lower() == n:
            return s
    for s in services:
        sl = s["name"].lower()
        if n in sl or sl in n:
            return s
    return None


# ------------------------------- Calendário ---------------------------------


async def calendar(tenant, *, start: datetime, end: datetime) -> dict:
    if end <= start or end - start > timedelta(days=62):
        raise AppError("Intervalo inválido (máximo de 62 dias).", code="invalid_range")
    rows = await db.appointment.find_many(
        where={"tenantId": tenant.id, "date": {"gte": start - timedelta(hours=12), "lt": end}},
        include={"patient": True},
        order={"date": "asc"},
    )
    rules = await get_rules(tenant.id)
    external = await db.externalbusy.find_many(
        where={"tenantId": tenant.id, "startAt": {"lt": end}, "endAt": {"gt": start}}, order={"startAt": "asc"}
    )
    return {
        "timezone": tenant.timezone,
        "slotMinutes": tenant.slotMinutes,
        "rules": rules_view(rules),
        "external": [
            {
                "id": x.id,
                "summary": x.summary,
                "start": x.startAt.isoformat(),
                "end": x.endAt.isoformat(),
                "allDay": x.allDay,
            }
            for x in external
        ],
        "appointments": [
            {
                "id": a.id,
                "service": a.service,
                "start": a.date.isoformat(),
                "end": (a.endAt or a.date + timedelta(minutes=a.durationMin or DEFAULT_DURATION_MIN)).isoformat(),
                "status": str(a.status),
                "source": a.source,
                "patient": {"id": a.patient.id, "name": a.patient.name, "phone": a.patient.phone}
                if a.patient
                else None,
            }
            for a in rows
        ],
    }
