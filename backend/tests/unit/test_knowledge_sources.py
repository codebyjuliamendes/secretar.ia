import pytest

from app.errors import AppError
from app.services import knowledge_sources as ks

HTML = """<!doctype html><html><head><title>  Perguntas   frequentes – Clínica </title>
<style>p{color:red}</style><script>alert(1)</script></head>
<body><nav><a href="/">Início</a><a href="/x">Menu que não interessa</a></nav>
<h1>Formas de pagamento</h1>
<p>Aceitamos cartão de crédito em até <b>6 vezes</b> sem juros, débito e Pix.</p>
<p>Não aceitamos cheque.</p>
<ul><li>Estacionamento gratuito</li><li>Acesso para cadeirantes</li></ul>
<footer>© Clínica</footer></body></html>"""


def test_html_to_text_extracts_title_and_paragraphs_without_scripts_or_nav():
    title, text = ks.html_to_text(HTML)
    assert title == "Perguntas frequentes – Clínica"
    assert "alert(1)" not in text and "color:red" not in text and "Menu que não interessa" not in text
    paragraphs = text.split("\n\n")
    assert paragraphs[0] == "Formas de pagamento"
    assert "cartão de crédito em até 6 vezes sem juros" in paragraphs[1]
    assert "Estacionamento gratuito" in paragraphs and "© Clínica" in paragraphs


def test_split_for_documents_respects_paragraphs_and_titles():
    paragraphs = [f"Parágrafo {i} " + "x" * 90 for i in range(10)]
    text = "\n\n".join(paragraphs)
    parts = ks.split_for_documents(text, max_chars=250)
    assert len(parts) > 1 and all(len(p) <= 250 for p in parts)
    assert "".join(parts).count("Parágrafo") == 10  # nada se perde
    assert all(not p.startswith("x") for p in parts)  # cortes em limite de parágrafo
    giant = "palavra " * 200
    hard = ks.split_for_documents(giant, max_chars=100)
    assert all(len(p) <= 100 for p in hard) and " ".join(hard).split() == giant.split()
    assert ks.split_for_documents("   ") == []
    assert ks.part_titles("Manual", 1) == ["Manual"]
    assert ks.part_titles("Manual", 3) == ["Manual (1/3)", "Manual (2/3)", "Manual (3/3)"]
    assert all(len(t) <= 120 for t in ks.part_titles("T" * 200, 12))


@pytest.mark.parametrize(
    "ip,public",
    [
        ("93.184.216.34", True),
        ("2606:2800:220:1:248:1893:25c8:1946", True),
        ("127.0.0.1", False),
        ("10.1.2.3", False),
        ("192.168.0.10", False),
        ("172.16.5.5", False),
        ("169.254.169.254", False),  # metadados de nuvem
        ("100.64.0.1", False),
        ("0.0.0.0", False),
        ("::1", False),
        ("::ffff:127.0.0.1", False),
        ("fe80::1", False),
        ("lixo", False),
    ],
)
def test_is_public_ip(ip, public):
    assert ks.is_public_ip(ip) is public


def test_validate_url_rejects_non_http_and_credentials():
    assert str(ks._validate_url(" https://clinica.example/faq ")) == "https://clinica.example/faq"
    for bad in ("ftp://x.example/a", "file:///etc/passwd", "clinica.example", "https://user:pw@x.example/"):
        with pytest.raises(AppError) as exc:
            ks._validate_url(bad)
        assert exc.value.code == "url_invalid"


async def test_assert_public_host_uses_literal_ips_without_dns(monkeypatch: pytest.MonkeyPatch):
    async def no_dns(host):
        raise AssertionError("não deveria resolver IP literal")

    monkeypatch.setattr(ks, "_resolve_host", no_dns)
    with pytest.raises(AppError) as exc:
        await ks.assert_public_host("127.0.0.1")
    assert exc.value.code == "url_not_allowed"
    assert await ks.assert_public_host("93.184.216.34") == ["93.184.216.34"]
    target, headers, ext = ks.pinned_request(ks._validate_url("https://clinica.example:8443/faq?x=1"), "93.184.216.34")
    assert str(target) == "https://93.184.216.34:8443/faq?x=1"
    assert headers == {"Host": "clinica.example:8443"} and ext == {"sni_hostname": "clinica.example"}
    target6, _, ext6 = ks.pinned_request(
        ks._validate_url("http://clinica.example/"), "2606:2800:220:1:248:1893:25c8:1946"
    )
    assert target6.host == "2606:2800:220:1:248:1893:25c8:1946" and ext6 == {}

    async def resolves_private(host):
        return ["93.184.216.34", "10.0.0.5"]  # basta um IP privado para recusar

    monkeypatch.setattr(ks, "_resolve_host", resolves_private)
    with pytest.raises(AppError):
        await ks.assert_public_host("evil.example")


def test_extract_pdf_text_rejects_non_pdf_and_filename_titles():
    with pytest.raises(AppError) as exc:
        ks.extract_pdf_text(b"isto nao e um pdf")
    assert exc.value.code == "pdf_invalid"
    assert ks.title_from_filename("preparo_para-peeling.PDF") == "preparo para peeling"
    assert ks.title_from_filename(".pdf") == "Documento"
    assert ks.title_from_url("https://clinica.example/faq/pagamento") == "clinica.example faq/pagamento"
