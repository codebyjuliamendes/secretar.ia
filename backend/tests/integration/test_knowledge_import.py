"""Ingestão de PDF e URL na base de conhecimento (sem rede: transporte httpx e DNS injetados)."""

import httpx
import pytest

from app.services import knowledge_sources as ks
from tests.conftest import auth_headers, register_user


def make_pdf(*lines: str, empty: bool = False) -> bytes:
    """PDF mínimo e válido (xref correto) com uma página de texto Helvetica. ASCII apenas."""
    ops = ["BT /F1 12 Tf 72 720 Td 14 TL"] + [f"({ln}) Tj T*" for ln in lines] + ["ET"]
    stream = ("" if empty else "\n".join(ops)).encode("latin-1")
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n".encode() + b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


FAQ_HTML = (
    "<html><head><title>FAQ da Clinica Harmonize</title><script>x()</script></head><body>"
    "<h1>Formas de pagamento</h1><p>Aceitamos cartão de crédito em até 6 vezes sem juros, débito e Pix.</p>"
    "<h2>Cancelamento</h2><p>Cancelamentos com menos de 24 horas têm cobrança de 30% do valor.</p>"
    "</body></html>"
)


def _handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if request.url.host != "clinica.example":
        return httpx.Response(404)
    if path == "/faq":
        return httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"}, text=FAQ_HTML)
    if path == "/antigo":
        return httpx.Response(301, headers={"location": "/faq"})
    if path == "/interno":
        return httpx.Response(302, headers={"location": "http://127.0.0.1:8000/admin"})
    if path == "/manual.pdf":
        return httpx.Response(
            200,
            headers={"content-type": "application/pdf"},
            content=make_pdf("Manual de preparo para peeling.", "Suspenda acidos 5 dias antes."),
        )
    if path == "/gigante":
        return httpx.Response(200, headers={"content-type": "text/html"}, text="<p>" + "x" * (ks.MAX_URL_BYTES + 10))
    if path == "/longo":
        paragraphs = "".join(f"<p>Secao {i}. " + "conteudo " * 400 + "</p>" for i in range(20))
        return httpx.Response(200, headers={"content-type": "text/html"}, text=f"<title>Guia</title>{paragraphs}")
    if path == "/foto.png":
        return httpx.Response(200, headers={"content-type": "image/png"}, content=b"\x89PNG....")
    if path == "/loop":
        return httpx.Response(302, headers={"location": "/loop"})
    return httpx.Response(404)


@pytest.fixture
def offline_web(monkeypatch: pytest.MonkeyPatch):
    async def resolve(host: str) -> list[str]:
        return {"clinica.example": ["93.184.216.34"], "localhost": ["127.0.0.1"]}.get(host, [])

    monkeypatch.setattr(ks, "_transport", httpx.MockTransport(_handler))
    monkeypatch.setattr(ks, "_resolve_host", resolve)


async def _paid_tenant(client, clean_db, plan: str = "PRO"):
    reg = await register_user(client)
    tid, h = reg["tenantId"], auth_headers(reg)
    await clean_db.tenant.update(where={"id": tid}, data={"status": "ACTIVE", "plan": plan})
    return tid, h


async def test_pdf_upload_creates_document_and_rejects_scanned_or_wrong_files(client, clean_db):
    tid, h = await _paid_tenant(client, clean_db)
    pdf = make_pdf("Aceitamos cartao de credito em ate 6 vezes sem juros.", "Nao aceitamos cheque.")
    res = await client.post(
        f"/api/clinic/{tid}/knowledge/upload",
        headers=h,
        files={"file": ("formas_de-pagamento.pdf", pdf, "application/pdf")},
    )
    assert res.status_code == 201, res.text
    (doc,) = res.json()["items"]
    assert doc["title"] == "formas de pagamento" and doc["source"] == "pdf"
    assert doc["sourceRef"] == "formas_de-pagamento.pdf" and doc["chunkCount"] >= 1
    detail = (await client.get(f"/api/clinic/{tid}/knowledge/{doc['id']}", headers=h)).json()
    assert "cartao de credito em ate 6 vezes" in detail["content"] and "Nao aceitamos cheque" in detail["content"]
    hits = (await client.post(f"/api/clinic/{tid}/knowledge/search?q=aceitam%20cheque", headers=h)).json()
    assert hits["items"] and hits["items"][0]["title"] == "formas de pagamento"

    # Título explícito e arquivo .txt também entram.
    txt = await client.post(
        f"/api/clinic/{tid}/knowledge/upload",
        headers=h,
        data={"title": "Horários especiais"},
        files={"file": ("horarios.txt", b"Em dezembro atendemos aos sabados ate 14h.\n", "text/plain")},
    )
    assert txt.status_code == 201 and txt.json()["items"][0]["title"] == "Horários especiais"
    assert txt.json()["items"][0]["source"] == "file"

    scanned = await client.post(
        f"/api/clinic/{tid}/knowledge/upload",
        headers=h,
        files={"file": ("scan.pdf", make_pdf(empty=True), "application/pdf")},
    )
    assert scanned.status_code == 400 and scanned.json()["error"]["code"] == "pdf_no_text"
    fake = await client.post(
        f"/api/clinic/{tid}/knowledge/upload", headers=h, files={"file": ("x.pdf", b"nao e pdf", "application/pdf")}
    )
    assert fake.json()["error"]["code"] == "pdf_invalid"
    img = await client.post(
        f"/api/clinic/{tid}/knowledge/upload", headers=h, files={"file": ("foto.png", b"\x89PNG", "image/png")}
    )
    assert img.json()["error"]["code"] == "unsupported_file"
    big = await client.post(
        f"/api/clinic/{tid}/knowledge/upload",
        headers=h,
        files={"file": ("big.pdf", b"%PDF-" + b"0" * (ks.MAX_UPLOAD_BYTES + 1), "application/pdf")},
    )
    assert big.status_code == 413
    assert await clean_db.knowledgedocument.count(where={"tenantId": tid}) == 2


async def test_url_import_html_pdf_redirects_and_ssrf_protection(client, clean_db, offline_web):
    tid, h = await _paid_tenant(client, clean_db)
    res = await client.post(
        f"/api/clinic/{tid}/knowledge/import-url", headers=h, json={"url": "https://clinica.example/antigo"}
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["sourceUrl"] == "https://clinica.example/faq" and body["kind"] == "html"
    (doc,) = body["items"]
    assert doc["title"] == "FAQ da Clinica Harmonize" and doc["source"] == "url"
    detail = (await client.get(f"/api/clinic/{tid}/knowledge/{doc['id']}", headers=h)).json()
    assert "x()" not in detail["content"] and "cartão de crédito em até 6 vezes" in detail["content"]
    assert "Formas de pagamento\n\nAceitamos" in detail["content"]  # parágrafos preservados para o chunker

    pdf = await client.post(
        f"/api/clinic/{tid}/knowledge/import-url",
        headers=h,
        json={"url": "https://clinica.example/manual.pdf", "title": "Manual de preparo"},
    )
    assert pdf.status_code == 201 and pdf.json()["kind"] == "pdf"
    assert pdf.json()["items"][0]["title"] == "Manual de preparo"

    for url, code in [
        ("http://127.0.0.1:8000/admin", "url_not_allowed"),
        ("http://localhost/x", "url_not_allowed"),
        ("http://169.254.169.254/latest/meta-data/", "url_not_allowed"),
        ("http://[::1]/", "url_not_allowed"),
        ("https://clinica.example/interno", "url_not_allowed"),  # redirect para IP interno
        ("https://clinica.example/gigante", "url_too_large"),
        ("https://clinica.example/foto.png", "url_unsupported_content"),
        ("https://clinica.example/loop", "url_fetch_failed"),
        ("https://clinica.example/nao-existe", "url_fetch_failed"),
        ("ftp://clinica.example/faq", "url_invalid"),
    ]:
        r = await client.post(f"/api/clinic/{tid}/knowledge/import-url", headers=h, json={"url": url})
        assert r.status_code == 400 and r.json()["error"]["code"] == code, (url, r.text)
    assert await clean_db.knowledgedocument.count(where={"tenantId": tid}) == 2


async def test_long_url_is_split_and_quota_is_checked_before_writing(client, clean_db, offline_web):
    tid, h = await _paid_tenant(client, clean_db, plan="BASIC")  # 10 documentos
    res = await client.post(
        f"/api/clinic/{tid}/knowledge/import-url", headers=h, json={"url": "https://clinica.example/longo"}
    )
    assert res.status_code == 201, res.text
    items = res.json()["items"]
    assert len(items) >= 2 and items[0]["title"].startswith("Guia (1/")
    assert all(d["sourceRef"] == "https://clinica.example/longo" for d in items)
    before = await clean_db.knowledgedocument.count(where={"tenantId": tid})
    # Uma segunda importação estouraria os 10 documentos: nada é gravado.
    for _ in range(3):
        again = await client.post(
            f"/api/clinic/{tid}/knowledge/import-url", headers=h, json={"url": "https://clinica.example/longo"}
        )
        if again.status_code == 402:
            break
    assert again.status_code == 402 and again.json()["error"]["code"] == "knowledge_limit"
    assert again.json()["error"]["details"]["limit"] == 10
    assert await clean_db.knowledgedocument.count(where={"tenantId": tid}) <= 10
    assert await clean_db.knowledgedocument.count(where={"tenantId": tid}) >= before


async def test_import_requires_plan_with_knowledge_base(client, clean_db, offline_web):
    tid, h = await _paid_tenant(client, clean_db, plan="FREE")
    res = await client.post(
        f"/api/clinic/{tid}/knowledge/import-url", headers=h, json={"url": "https://clinica.example/faq"}
    )
    assert res.status_code == 402 and res.json()["error"]["code"] == "plan_feature_locked"
    up = await client.post(
        f"/api/clinic/{tid}/knowledge/upload", headers=h, files={"file": ("a.pdf", make_pdf("x"), "application/pdf")}
    )
    assert up.status_code == 402
