"""Comportamento da conversa sem IA (regras) e robustez do pipeline de mensagens."""

import json
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from app.domain.intents import Intent, asks_prices_or_hours, classify
from app.security.signatures import sign_hub
from app.services import scheduling
from app.services.ai import UNKNOWN_INFO_REPLY, AIService
from app.services.scheduling import Slot
from tests.conftest import auth_headers, register_user


def signed(payload: dict):
    body = json.dumps(payload, ensure_ascii=False).encode()
    return body, {"X-Hub-Signature-256": sign_hub(body, "test-whatsapp-secret"), "Content-Type": "application/json"}


@pytest.mark.parametrize(
    "text,expected",
    [
        ("quero falar com uma pessoa", Intent.HUMAN),
        ("me passa pra um atendente", Intent.HUMAN),
        ("quero agendar botox, pode me ajudar?", Intent.SCHEDULE),  # "ajuda" não é pedido de humano
        ("posso remarcar?", Intent.SCHEDULE),  # remarcar ≠ cancelar
        ("preciso adiar minha consulta", Intent.SCHEDULE),
        ("quero cancelar", Intent.CANCEL),
        ("😀", Intent.GREETING),
        ("...", Intent.GREETING),
        ("tem estacionamento?", Intent.INFO),
    ],
)
def test_classify_edge_cases(text, expected):
    assert classify(text) == expected


def test_asks_prices_or_hours():
    assert asks_prices_or_hours("quanto custa o botox?") and asks_prices_or_hours("que horário vocês abrem?")
    assert not asks_prices_or_hours("tem estacionamento?") and not asks_prices_or_hours("qual o endereço?")


def test_spread_slots_covers_several_days():
    tz = ZoneInfo("America/Sao_Paulo")
    slots = []
    for day in range(3):
        for hour in (12, 13, 14, 15):  # 09h–12h locais
            start = datetime(2031, 1, 13 + day, hour, tzinfo=UTC)
            slots.append(Slot(start, start.replace(hour=hour + 1)))
    picked = scheduling.spread_slots(slots, tz, per_day=2, limit=6)
    assert [s.start.day for s in picked] == [13, 13, 14, 14, 15, 15]
    assert [s.start.hour for s in picked][:2] == [12, 13]
    assert len(scheduling.spread_slots(slots, tz, per_day=1, limit=2)) == 2


async def test_unknown_question_goes_to_team_and_rules_do_not_consume_ai_quota(client, clean_db):
    reg = await register_user(client)
    tid, h = reg["tenantId"], auth_headers(reg)
    body, headers = signed(
        {"messageId": "r1", "phone": "5581999990000", "text": "tem estacionamento?", "tenantId": tid}
    )
    res = await client.post("/api/webhooks/whatsapp", content=body, headers=headers)
    # Primeiro contato: a apresentação da assistente vem antes da resposta por regras.
    assert res.status_code == 200 and res.json()["reply"].endswith(UNKNOWN_INFO_REPLY)
    assert res.json()["reply"].startswith("Olá! Sou a assistente virtual da ")
    inbox = (await client.get(f"/api/clinic/{tid}/notifications", headers=h)).json()
    assert any(n["type"] == "HUMAN_HANDOFF" for n in inbox["items"])
    # Pergunta de preço continua respondida pelo catálogo; nenhuma delas consumiu quota de IA.
    body, headers = signed({"messageId": "r2", "phone": "5581999990000", "text": "quanto custa?", "tenantId": tid})
    res = await client.post("/api/webhooks/whatsapp", content=body, headers=headers)
    assert "Nossa equipe atende" in res.json()["reply"] or "serviços e valores" in res.json()["reply"]
    assert await clean_db.usagecounter.count(where={"tenantId": tid}) == 0
    # Histórico em ordem estável: user → assistant.
    msgs = await clean_db.message.find_many(where={"tenantId": tid}, order=[{"createdAt": "asc"}, {"id": "asc"}])
    assert [str(m.role) for m in msgs] == ["USER", "ASSISTANT", "USER", "ASSISTANT"]


async def test_unexpected_failure_releases_the_message_claim(client, clean_db, monkeypatch):
    reg = await register_user(client)
    tid = reg["tenantId"]

    async def boom(self, *args, **kwargs):
        raise RuntimeError("provedor explodiu de um jeito não previsto")

    monkeypatch.setattr(AIService, "decide", boom)
    body, headers = signed({"messageId": "x1", "phone": "5581999990002", "text": "oi", "tenantId": tid})
    # O cliente de teste relança exceções da aplicação (em produção vira 500 pelo handler global).
    with pytest.raises(RuntimeError):
        await client.post("/api/webhooks/whatsapp", content=body, headers=headers)
    assert await clean_db.processedmessage.count(where={"tenantId": tid, "messageId": "x1"}) == 0
    monkeypatch.undo()
    # O reenvio do provedor é processado normalmente (não vira duplicate_ignored).
    res = await client.post("/api/webhooks/whatsapp", content=body, headers=headers)
    assert res.status_code == 200 and res.json()["status"] == "processed"


async def test_degraded_cancel_request_waits_for_team_confirmation(client, clean_db):
    reg = await register_user(client)
    tid, h = reg["tenantId"], auth_headers(reg)
    created = await client.post(
        f"/api/clinic/{tid}/appointments",
        headers=h,
        json={"phone": "5581999990003", "patientName": "Bia", "service": "Peeling", "date": "2031-02-03T13:00:00Z"},
    )
    assert created.status_code == 201
    body, headers = signed(
        {"messageId": "c1", "phone": "5581999990003", "text": "quero cancelar minha consulta", "tenantId": tid}
    )
    res = await client.post("/api/webhooks/whatsapp", content=body, headers=headers)
    assert res.json()["intent"] == "CANCELAR" and res.json()["degraded"] is True
    appt = await clean_db.appointment.find_unique(where={"id": created.json()["id"]})
    assert str(appt.status) == "CONFIRMED"  # sem IA, ninguém desmarca automaticamente
    inbox = (await client.get(f"/api/clinic/{tid}/notifications", headers=h)).json()
    titles = [n["title"] for n in inbox["items"]]
    assert any(t.startswith("Pedido de cancelamento para confirmar") for t in titles)
    assert not any(t.startswith("Cancelamento solicitado") for t in titles)
