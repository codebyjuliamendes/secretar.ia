"""Regras puras do endurecimento (sem banco e sem rede)."""

from datetime import UTC, datetime

import httpx
import pytest

from app.domain.phones import mask_phone
from app.domain.roles import Permission, TenantRole, has_permission
from app.integrations import gemini
from app.jobs.scheduler import DAILY_HOUR_UTC, daily_due
from app.main import _safe_request_id
from app.services.conversation import wants_data_deletion
from app.services.exports import safe_cell


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('=HYPERLINK("http://x","y")', '\'=HYPERLINK("http://x","y")'),
        ("+cmd|' /C calc'!A0", "'+cmd|' /C calc'!A0"),
        ("-2+3+cmd|x", "'-2+3+cmd|x"),
        ("@SUM(A1)", "'@SUM(A1)"),
        ("\t=1", "'\t=1"),
        ("＝1+1", "'＝1+1"),  # sinal de igual de largura total também vira fórmula no Excel
        ("+5581999990000", "+5581999990000"),
        ("-15,50", "-15,50"),
        ("Ana Souza", "Ana Souza"),
        ("", ""),
    ],
)
def test_safe_cell_neutralizes_formulas_but_keeps_numbers(raw, expected):
    assert safe_cell(raw) == expected


def test_mask_phone_keeps_only_last_digits():
    assert mask_phone("5581999998888") == "*********8888"
    assert mask_phone("123") == "***"
    assert mask_phone(None) == ""


def test_daily_routine_catches_up_after_missing_the_hour():
    day = datetime(2026, 10, 27, tzinfo=UTC)
    assert not daily_due(day.replace(hour=DAILY_HOUR_UTC - 1), None)
    assert daily_due(day.replace(hour=DAILY_HOUR_UTC), None)
    assert daily_due(day.replace(hour=23), None)  # processo subiu depois do horário: ainda roda hoje
    assert not daily_due(day.replace(hour=23), "2026-10-27")


def test_request_id_is_bounded_and_printable():
    assert _safe_request_id("req-1:abc.def_2") == "req-1:abc.def_2"
    for bad in (None, "", "a" * 65, "line\nbreak", 'quote"'):
        generated = _safe_request_id(bad)
        assert len(generated) == 16 and generated.isalnum()


def test_only_managers_and_owners_export_the_base():
    assert not has_permission(TenantRole.STAFF, Permission.DATA_EXPORT)
    assert has_permission(TenantRole.MANAGER, Permission.DATA_EXPORT)
    assert has_permission(TenantRole.OWNER, Permission.DATA_EXPORT)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Vocês seguem a LGPD?", False),
        ("Quero que apaguem... não, quero que APAGUE MEUS DADOS", True),
        ("quero excluir meu cadastro", True),
        ("direito ao esquecimento, por favor", True),
        ("bom dia", False),
    ],
)
def test_deletion_request_detection(text, expected):
    assert wants_data_deletion(text) is expected


async def test_gemini_key_travels_in_header_not_in_url(monkeypatch):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200, json={"candidates": [{"content": {"parts": [{"text": '{"ok": true}'}]}}], "usageMetadata": {}}
        )

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        gemini.httpx, "AsyncClient", lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw)
    )
    client = gemini.GeminiClient("chave-secreta", "modelo-x", timeout=5, max_output_tokens=64)
    result = await client.generate_json("sistema", [{"role": "user", "content": "oi"}], {"type": "OBJECT"})
    assert result.text == '{"ok": true}'
    assert seen[0].headers["x-goog-api-key"] == "chave-secreta"
    assert "chave-secreta" not in str(seen[0].url)
