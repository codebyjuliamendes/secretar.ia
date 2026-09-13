"""Exportação em planilha (CSV): contatos e agendamentos da conta.

Portabilidade tira o medo de "ficar preso". CSV com BOM e ponto-e-vírgula abre direto no Excel em pt-BR.
"""

from __future__ import annotations

import csv
import io
from datetime import UTC
from zoneinfo import ZoneInfo

from app.db import db

BOM = "﻿"


def _csv(rows: list[list[str]]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";", lineterminator="\r\n")
    writer.writerows(rows)
    return BOM + buf.getvalue()


def _local(dt, tz: str) -> str:
    if dt is None:
        return ""
    try:
        zone = ZoneInfo(tz)
    except Exception:  # noqa: BLE001 - fuso inválido cai em UTC em vez de quebrar a exportação
        zone = UTC
    return dt.astimezone(zone).strftime("%d/%m/%Y %H:%M")


async def patients_csv(tenant) -> str:
    rows = await db.patient.find_many(where={"tenantId": tenant.id}, order={"createdAt": "asc"})
    out = [["Nome", "Telefone", "Observações", "Não receber campanhas", "Cadastrado em"]]
    for p in rows:
        out.append(
            [
                p.name or "",
                f"+{p.phone}" if p.phone and not p.phone.startswith("+") else (p.phone or ""),
                (p.notes or "").replace("\r", " ").replace("\n", " "),
                "sim" if p.marketingOptOut else "não",
                _local(p.createdAt, tenant.timezone),
            ]
        )
    return _csv(out)


async def appointments_csv(tenant) -> str:
    rows = await db.appointment.find_many(
        where={"tenantId": tenant.id}, order={"date": "asc"}, include={"patient": True}
    )
    out = [["Data e hora", "Serviço", "Contato", "Telefone", "Status", "Origem", "Criado em"]]
    for a in rows:
        out.append(
            [
                _local(a.date, tenant.timezone),
                a.service or "",
                (a.patient.name if a.patient else "") or "",
                f"+{a.patient.phone}" if a.patient and a.patient.phone else "",
                str(a.status),
                a.source or "",
                _local(a.createdAt, tenant.timezone),
            ]
        )
    return _csv(out)
