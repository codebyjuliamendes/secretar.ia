"""Importar o catálogo de serviços de uma foto/PDF da tabela de preços (prévia → confirmação)."""

import json

from app.integrations.gemini import AIProviderError, AIResult
from app.services import service_import
from tests.conftest import auth_headers, register_user

JPEG_MAGIC = b"\xff\xd8\xff\xe0" + b"\x00" * 64


class FakeGemini:
    def __init__(self, text: str | None = None, fail: bool = False):
        self.text, self.fail, self.calls = text, fail, []

    async def describe_media(self, prompt, data, mime_type, *, max_output_tokens=None):
        self.calls.append(("image", mime_type, len(data)))
        if self.fail:
            raise AIProviderError("Gemini respondeu 503")
        return AIResult(text=self.text or "", input_tokens=500, output_tokens=80, model="fake-gemini")

    async def generate_json(self, system_prompt, messages, schema):
        self.calls.append(("text", None, len(messages[0]["content"])))
        return AIResult(text=self.text or "", input_tokens=500, output_tokens=80, model="fake-gemini")


async def test_photo_of_price_list_becomes_a_reviewable_service_catalog(client, clean_db, monkeypatch):
    reg = await register_user(client)
    tid, h = reg["tenantId"], auth_headers(reg)

    # Sem IA configurada: erro claro, nada gravado.
    no_ai = await client.post(
        f"/api/clinic/{tid}/services/import/preview",
        headers=h,
        files={"file": ("tabela.jpg", JPEG_MAGIC, "image/jpeg")},
    )
    assert no_ai.status_code == 503 and no_ai.json()["error"]["code"] == "ai_unavailable"

    extracted = {
        "items": [
            {"name": "Corte feminino", "priceCents": 9000, "durationMin": 60, "description": None},
            {"name": "Escova", "priceCents": 6000, "durationMin": None, "description": "cabelo médio"},
            {"name": "Corte feminino", "priceCents": 9000},  # duplicado: ignorado
            {"name": "X", "priceCents": 10},  # nome curto demais: ignorado
            {"name": "Hidratação", "priceCents": None, "durationMin": 45},
            "lixo",
        ]
    }
    fake = FakeGemini(text=json.dumps(extracted))
    monkeypatch.setattr(service_import, "client_for", lambda settings: fake)
    preview = await client.post(
        f"/api/clinic/{tid}/services/import/preview",
        headers=h,
        files={"file": ("tabela.jpg", JPEG_MAGIC, "image/jpeg")},
    )
    assert preview.status_code == 200, preview.text
    items = preview.json()["items"]
    assert [i["name"] for i in items] == ["Corte feminino", "Escova", "Hidratação"]
    assert items[1]["durationMin"] is None and items[2]["priceCents"] is None
    assert fake.calls[0][0] == "image"
    assert await clean_db.service.count(where={"tenantId": tid}) == 0  # prévia não grava

    # Cliente ajusta e confirma; um serviço já existente é pulado.
    await client.post(f"/api/clinic/{tid}/services", headers=h, json={"name": "Escova", "durationMin": 40})
    confirm = await client.post(
        f"/api/clinic/{tid}/services/import/confirm",
        headers=h,
        json={
            "items": [
                {"name": "Corte feminino", "priceCents": 9500, "durationMin": 60},
                {"name": "Escova", "priceCents": 6000, "durationMin": 60},
                {"name": "Hidratação", "priceCents": None, "durationMin": 45},
            ]
        },
    )
    assert confirm.status_code == 201, confirm.text
    body = confirm.json()
    assert [c["name"] for c in body["created"]] == ["Corte feminino", "Hidratação"] and body["skipped"] == ["Escova"]
    assert body["created"][0]["priceCents"] == 9500
    settings = (await client.get(f"/api/clinic/{tid}/settings", headers=h)).json()
    assert "Corte feminino" in (settings["prices"] or "")  # texto da IA sincronizado com o catálogo

    # Arquivo que não é foto nem PDF, e IA fora do ar.
    bad = await client.post(
        f"/api/clinic/{tid}/services/import/preview",
        headers=h,
        files={"file": ("tabela.docx", b"PK..", "application/zip")},
    )
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "unsupported_file"
    monkeypatch.setattr(service_import, "client_for", lambda settings: FakeGemini(fail=True))
    down = await client.post(
        f"/api/clinic/{tid}/services/import/preview", headers=h, files={"file": ("tabela.png", JPEG_MAGIC, "image/png")}
    )
    assert down.status_code == 502 and down.json()["error"]["code"] == "ai_failed"


async def test_pdf_price_list_goes_through_text_extraction(client, clean_db, monkeypatch):
    from tests.integration.test_knowledge_import import make_pdf

    reg = await register_user(client)
    tid, h = reg["tenantId"], auth_headers(reg)
    fake = FakeGemini(text=json.dumps({"items": [{"name": "Limpeza de pele", "priceCents": 15000, "durationMin": 50}]}))
    monkeypatch.setattr(service_import, "client_for", lambda settings: fake)
    pdf = make_pdf("Limpeza de pele ........ R$ 150,00 (50 min)")
    r = await client.post(
        f"/api/clinic/{tid}/services/import/preview", headers=h, files={"file": ("tabela.pdf", pdf, "application/pdf")}
    )
    assert r.status_code == 200, r.text
    assert r.json()["items"][0]["name"] == "Limpeza de pele" and fake.calls[0][0] == "text"
