"""Ingestão de fontes externas na base de conhecimento: PDF enviado e página/PDF por URL.

- PDF: texto extraído com pypdf. Páginas sem camada de texto (digitalizadas) passam por OCR com o Gemini
  multimodal (mesmo provedor da IA): a maior imagem da página é enviada e a transcrição volta como texto.
  Sem chave de IA, ou se a IA não devolver texto, o PDF é recusado com mensagem clara em vez de virar um
  documento vazio.
- URL: só http/https; o host é resolvido e rejeitado se apontar para rede privada, loopback, link-local ou
  metadados de nuvem (SSRF). A conexão é feita ao IP validado (URL reescrita, `Host` e SNI com o nome
  original), então uma segunda resolução de DNS não pode trocar o destino (DNS rebinding). Redirecionamentos
  são seguidos manualmente (até 3) revalidando cada destino; o corpo é limitado a 2 MB; HTML vira texto por
  parágrafos (sem script/style/nav); PDF passa pelo mesmo extrator.
- Texto maior que um documento é dividido em partes ("Título (1/3)") respeitando parágrafos, e a cota de
  documentos do plano é verificada ANTES de gravar qualquer parte (importação é tudo-ou-nada).
"""

from __future__ import annotations

import asyncio
import io
import ipaddress
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any

import httpx
from pypdf import PdfReader

from app.config import Settings
from app.db import db
from app.domain.plans import knowledge_documents_limit, within_limit
from app.errors import AppError, QuotaExceededError
from app.integrations.gemini import AIProviderError
from app.logging import get_logger
from app.services import knowledge
from app.services import media as media_service

log = get_logger("knowledge_sources")

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_URL_BYTES = 2 * 1024 * 1024
URL_TIMEOUT_SECONDS = 10.0
MAX_REDIRECTS = 3
MIN_TEXT_CHARS = 20
PDF_MIME = "application/pdf"
HTML_MIMES = ("text/html", "application/xhtml+xml")
TEXT_MIMES = ("text/plain", "text/markdown")
USER_AGENT = "Secretar.ia/1.0 (base de conhecimento; +https://secretar.ia)"
OCR_MIN_PAGE_CHARS = 40  # página com menos texto que isso é tratada como digitalizada
OCR_MAX_PAGES = 20
PDF_MAX_PAGES = 300  # acima disso o parse ocupa a CPU por minutos; peça para dividir o arquivo
URL_TOTAL_TIMEOUT_SECONDS = 30.0  # teto da requisição inteira, contra servidor que goteja bytes
OCR_MAX_SIDE_PX = 2000
OCR_MAX_IMAGE_BYTES = media_service.MAX_IMAGE_BYTES
OCR_PROMPT = (
    "Esta é uma página digitalizada de um documento de uma clínica. Transcreva fielmente TODO o texto legível, "
    "em português, preservando títulos e parágrafos (separe parágrafos com uma linha em branco). Não resuma, "
    "não comente, não invente. Se não houver texto legível, responda exatamente: [sem texto]."
)

# Transporte httpx injetável (testes usam httpx.MockTransport; produção deixa None = rede real).
_transport: httpx.AsyncBaseTransport | None = None


@dataclass
class PdfText:
    text: str
    pages: int
    ocr_pages: int  # páginas lidas por OCR (IA)


@dataclass
class FetchedSource:
    text: str
    title: str | None
    final_url: str
    content_type: str
    kind: str  # html | pdf | text
    ocr_pages: int = 0


# ------------------------------------ PDF ------------------------------------


def _normalize_page(text: str) -> str:
    """Linhas quebradas pelo layout do PDF viram um parágrafo; linhas em branco separam parágrafos."""
    paragraphs = []
    for block in re.split(r"\n\s*\n", text):
        joined = " ".join(" ".join(line.split()) for line in block.splitlines() if line.strip())
        if joined:
            paragraphs.append(joined)
    return "\n\n".join(paragraphs)


def ocr_client(settings: Settings):
    """Mesmo cliente multimodal da mídia do WhatsApp; separado para os testes injetarem um falso."""
    return media_service.client_for(settings)


def page_image_for_ocr(page) -> tuple[bytes, str] | None:
    """Maior imagem da página, reencodada em JPEG (RGB, lado máx. 2000 px) para o provedor de IA."""
    best = None
    for img in page.images:
        try:
            pil = img.image
        except Exception:  # noqa: BLE001 - filtro exótico que o Pillow não decodifica
            continue
        if pil is None:
            continue
        area = pil.width * pil.height
        if best is None or area > best[0]:
            best = (area, pil)
    if best is None or best[0] < 100 * 100:
        return None
    pil = best[1]
    if pil.mode not in ("RGB", "L"):
        pil = pil.convert("RGB")
    if max(pil.size) > OCR_MAX_SIDE_PX:
        pil.thumbnail((OCR_MAX_SIDE_PX, OCR_MAX_SIDE_PX))
    buf = io.BytesIO()
    pil.save(buf, format="JPEG", quality=85)
    payload = buf.getvalue()
    if len(payload) > OCR_MAX_IMAGE_BYTES:
        return None
    return payload, "image/jpeg"


async def _ocr_pages(settings: Settings, pages_to_read: list) -> dict[int, str]:
    """OCR via Gemini das páginas indicadas [(índice, page)]. Devolve {índice: texto}. Vazio sem IA/falha."""
    client = ocr_client(settings)
    if client is None or not pages_to_read:
        return {}
    out: dict[int, str] = {}
    for idx, page in pages_to_read[:OCR_MAX_PAGES]:
        image = await asyncio.to_thread(page_image_for_ocr, page)  # decodificação de imagem é CPU
        if image is None:
            continue
        try:
            result = await client.describe_media(OCR_PROMPT, image[0], image[1], max_output_tokens=4096)
        except AIProviderError as exc:
            log.warning("pdf_ocr_failed", page=idx, error=str(exc)[:200])
            continue
        text = _normalize_page(result.text or "")
        if text and "[sem texto]" not in text.lower():
            out[idx] = text
        log.info(
            "pdf_ocr_page", page=idx, chars=len(text), tokens=(result.input_tokens or 0) + (result.output_tokens or 0)
        )
    return out


def _parse_pdf_sync(data: bytes) -> tuple[list, list[str]]:
    """Parse + extração de texto (CPU): roda fora do event loop para não travar a API com um PDF pesado."""
    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception as exc:  # noqa: BLE001
            raise AppError("O PDF está protegido por senha.", code="pdf_encrypted") from exc
    if len(reader.pages) > PDF_MAX_PAGES:
        raise AppError(f"O PDF tem mais de {PDF_MAX_PAGES} páginas; divida o arquivo.", code="pdf_too_many_pages")
    pages = list(reader.pages)
    return pages, [_normalize_page(page.extract_text() or "") for page in pages]


async def extract_pdf_text(settings: Settings, data: bytes) -> PdfText:
    if not data.startswith(b"%PDF"):
        raise AppError("O arquivo não é um PDF válido.", code="pdf_invalid")
    try:
        pages, texts = await asyncio.to_thread(_parse_pdf_sync, data)
    except AppError:
        raise
    except Exception as exc:  # noqa: BLE001 - pypdf lança várias classes para arquivo corrompido
        log.warning("pdf_parse_failed", error=str(exc)[:200])
        raise AppError("Não foi possível ler o PDF (arquivo corrompido?).", code="pdf_invalid") from exc
    scanned = [(i, pages[i]) for i, t in enumerate(texts) if len(t) < OCR_MIN_PAGE_CHARS]
    ocr_text = await _ocr_pages(settings, scanned) if scanned else {}
    for i, t in ocr_text.items():
        texts[i] = t
    text = "\n\n".join(t for t in texts if t)
    if len(text.strip()) < MIN_TEXT_CHARS:
        if scanned and ocr_client(settings) is None:
            raise AppError(
                "O PDF parece digitalizado e a leitura de imagens por IA não está configurada neste ambiente. "
                "Cole o conteúdo como texto.",
                code="pdf_no_text",
            )
        raise AppError(
            "Não encontramos texto legível no PDF (nem por leitura das imagens). Cole o conteúdo como texto.",
            code="pdf_no_text",
        )
    return PdfText(text=text, pages=len(pages), ocr_pages=len(ocr_text))


def title_from_filename(name: str) -> str:
    base = re.sub(r"\.(pdf|txt|md)$", "", name.strip(), flags=re.IGNORECASE)
    base = re.sub(r"[_\-]+", " ", base).strip()
    return (base or "Documento")[:120]


# ------------------------------------ HTML -----------------------------------

_BLOCK_TAGS = {
    "p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "table", "tr", "td", "th",
    "section", "article", "header", "footer", "blockquote", "pre", "dd", "dt", "dl", "hr", "main", "aside",
    "nav", "figure", "figcaption", "summary", "details",
}  # fmt: skip
_SKIP_TAGS = {"script", "style", "noscript", "template", "svg", "iframe", "canvas", "nav", "head"}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title_parts: list[str] = []
        self._skip = 0
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self._in_title = True
        if tag in _SKIP_TAGS:
            self._skip += 1
        if tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if tag in _SKIP_TAGS and self._skip:
            self._skip -= 1
        if tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._in_title:
            self.title_parts.append(data)
        elif not self._skip:
            self.parts.append(data)


def html_to_text(html: str) -> tuple[str | None, str]:
    """Devolve (título, texto por parágrafos). Blocos consecutivos viram parágrafos separados por linha vazia."""
    parser = _TextExtractor()
    parser.feed(html)
    parser.close()
    raw = "".join(parser.parts)
    lines = [" ".join(line.split()) for line in raw.splitlines()]
    text = "\n".join(lines)
    text = re.sub(r"\n{2,}", "\n\n", text).strip()
    # Um único "\n" entre blocos ainda separa parágrafos para o chunker; normaliza para linha vazia.
    text = re.sub(r"(?<!\n)\n(?!\n)", "\n\n", text)
    title = " ".join("".join(parser.title_parts).split()) or None
    return title, text


# ------------------------------------ URL ------------------------------------


def _validate_url(url: str) -> httpx.URL:
    try:
        parsed = httpx.URL(url.strip())
    except (httpx.InvalidURL, TypeError) as exc:
        raise AppError("URL inválida.", code="url_invalid") from exc
    if parsed.scheme not in ("http", "https") or not parsed.host:
        raise AppError("Informe uma URL completa começando com http:// ou https://.", code="url_invalid")
    if parsed.userinfo:
        raise AppError("URL com credenciais não é aceita.", code="url_invalid")
    return parsed


_NAT64 = ipaddress.ip_network("64:ff9b::/96")


def is_public_ip(ip: str) -> bool:
    """Só endereços globais; IPv6 com IPv4 embutido (mapeado, 6to4, Teredo, NAT64) é julgado pelo IPv4."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if addr.version == 6:
        embedded = addr.ipv4_mapped or addr.sixtofour or (addr.teredo[1] if addr.teredo else None)
        if embedded is None and addr in _NAT64:
            embedded = ipaddress.IPv4Address(int(addr) & 0xFFFFFFFF)
        if embedded is not None:
            return is_public_ip(str(embedded))
    return addr.is_global and not addr.is_multicast


async def _resolve_host(host: str) -> list[str]:
    """Separado para os testes injetarem respostas de DNS sem rede."""
    infos = await asyncio.get_running_loop().getaddrinfo(host, None)
    return sorted({info[4][0] for info in infos})


async def assert_public_host(host: str) -> list[str]:
    """Resolve o host e devolve os IPs, todos públicos; qualquer IP interno recusa a URL inteira."""
    literal = host.strip("[]")
    try:
        ipaddress.ip_address(literal)
        ips = [literal]
    except ValueError:
        try:
            ips = await _resolve_host(host)
        except OSError as exc:
            raise AppError("Não foi possível resolver o endereço da URL.", code="url_fetch_failed") from exc
    if not ips or any(not is_public_ip(ip) for ip in ips):
        raise AppError("Esta URL aponta para um endereço interno e não pode ser importada.", code="url_not_allowed")
    return ips


def pinned_request(url: httpx.URL, ip: str) -> tuple[httpx.URL, dict[str, str], dict[str, Any]]:
    """Conecta ao IP já validado, preservando nome do host (Host/SNI) para o servidor e para o certificado."""
    host_header = url.host if url.port is None else f"{url.host}:{url.port}"
    target = url.copy_with(host=f"[{ip}]" if ":" in ip else ip)
    extensions: dict[str, Any] = {"sni_hostname": url.host} if url.scheme == "https" else {}
    return target, {"Host": host_header}, extensions


async def fetch_url(settings: Settings, url: str) -> FetchedSource:
    try:
        async with asyncio.timeout(URL_TOTAL_TIMEOUT_SECONDS):
            return await _fetch_url(settings, url)
    except TimeoutError as exc:
        raise AppError("A página demorou demais para responder.", code="url_fetch_failed") from exc


async def _fetch_url(settings: Settings, url: str) -> FetchedSource:
    current = _validate_url(url)
    body = bytearray()
    ctype = ""
    charset: str | None = None
    for _ in range(MAX_REDIRECTS + 1):
        ips = await assert_public_host(current.host)
        target, host_headers, extensions = pinned_request(current, ips[0])
        async with httpx.AsyncClient(
            timeout=URL_TIMEOUT_SECONDS,
            follow_redirects=False,
            transport=_transport,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/pdf,text/plain;q=0.9,*/*;q=0.5"},
        ) as client:
            try:
                async with client.stream("GET", target, headers=host_headers, extensions=extensions) as resp:
                    if resp.status_code in (301, 302, 303, 307, 308):
                        location = resp.headers.get("location")
                        if not location:
                            raise AppError("A página redirecionou sem destino.", code="url_fetch_failed")
                        current = _validate_url(str(current.join(location)))
                        continue
                    if resp.status_code >= 400:
                        raise AppError(f"A página respondeu {resp.status_code}.", code="url_fetch_failed")
                    ctype = resp.headers.get("content-type", "").split(";")[0].strip().lower()
                    charset = resp.charset_encoding
                    async for chunk in resp.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > MAX_URL_BYTES:
                            raise AppError("A página é grande demais para importar (máx. 2 MB).", code="url_too_large")
            except httpx.HTTPError as exc:
                log.warning("url_fetch_failed", url=str(current)[:200], error=exc.__class__.__name__)
                raise AppError("Não foi possível acessar a URL.", code="url_fetch_failed") from exc
        break
    else:
        raise AppError("A URL redireciona demais.", code="url_fetch_failed")

    data = bytes(body)
    if ctype == PDF_MIME or data[:5] == b"%PDF-":
        pdf = await extract_pdf_text(settings, data)
        return FetchedSource(pdf.text, None, str(current), PDF_MIME, "pdf", ocr_pages=pdf.ocr_pages)
    try:
        decoded = data.decode(charset or "utf-8", errors="replace")
    except LookupError:  # charset inventado no cabeçalho
        decoded = data.decode("utf-8", errors="replace")
    if ctype in HTML_MIMES or (not ctype and "<html" in decoded[:2000].lower()):
        title, text = html_to_text(decoded)
        kind = "html"
    elif ctype in TEXT_MIMES:
        title, text, kind = None, decoded.strip(), "text"
    else:
        raise AppError("Conteúdo não suportado: importe páginas HTML, PDF ou texto.", code="url_unsupported_content")
    if len(text.strip()) < MIN_TEXT_CHARS:
        raise AppError("A página não tem texto legível para importar.", code="url_no_text")
    return FetchedSource(text, title, str(current), ctype, kind)


def title_from_url(url: str) -> str:
    parsed = httpx.URL(url)
    path = parsed.path.strip("/").replace("-", " ").replace("_", " ")
    return f"{parsed.host} {path}".strip()[:120] or parsed.host[:120]


# ------------------------------- Divisão e gravação ----------------------------


def split_for_documents(text: str, *, max_chars: int = knowledge.MAX_DOCUMENT_CHARS) -> list[str]:
    """Divide em partes de até `max_chars` em limites de parágrafo (e de palavra, se um parágrafo for enorme)."""
    text = text.strip()
    if len(text) <= max_chars:
        return [text] if text else []
    parts: list[str] = []
    buf = ""
    for paragraph in re.split(r"\n\s*\n", text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        while len(paragraph) > max_chars:
            if buf:
                parts.append(buf)
                buf = ""
            cut = paragraph.rfind(" ", 0, max_chars)
            cut = cut if cut > max_chars // 2 else max_chars
            parts.append(paragraph[:cut].strip())
            paragraph = paragraph[cut:].strip()
        if buf and len(buf) + len(paragraph) + 2 > max_chars:
            parts.append(buf)
            buf = paragraph
        else:
            buf = f"{buf}\n\n{paragraph}".strip()
    if buf:
        parts.append(buf)
    return parts


def part_titles(title: str, count: int) -> list[str]:
    title = title.strip()[:120]
    if count <= 1:
        return [title]
    suffix_len = len(f" ({count}/{count})")
    base = title[: 120 - suffix_len].rstrip()
    return [f"{base} ({i}/{count})" for i in range(1, count + 1)]


async def assert_document_slot(tenant) -> None:
    """Antes de gastar rede/CPU/IA com o arquivo: há vaga para pelo menos um documento?"""
    knowledge.assert_enabled(tenant)
    limit = knowledge_documents_limit(tenant)
    used = await db.knowledgedocument.count(where={"tenantId": tenant.id})
    if not within_limit(used, limit):
        raise QuotaExceededError(
            f"Seu plano permite {limit} documentos na base de conhecimento.",
            code="knowledge_limit",
            details={"limit": limit},
        )


async def import_text(
    settings: Settings,
    tenant,
    *,
    title: str,
    text: str,
    source: str,
    source_ref: str | None,
    actor_user_id: str,
    ip: str | None,
) -> list[dict]:
    knowledge.assert_enabled(tenant)
    parts = split_for_documents(text)
    if not parts:
        raise AppError("Conteúdo vazio.", code="empty_document")
    limit = knowledge_documents_limit(tenant)
    used = await db.knowledgedocument.count(where={"tenantId": tenant.id})
    if limit >= 0 and used + len(parts) > limit:
        raise QuotaExceededError(
            f"Este conteúdo vira {len(parts)} documento(s); seu plano permite {limit} e você já tem {used}.",
            code="knowledge_limit",
            details={"limit": limit, "used": used, "needed": len(parts)},
        )
    docs = []
    for part_title, content in zip(part_titles(title, len(parts)), parts, strict=True):
        docs.append(
            await knowledge.add_document(
                settings,
                tenant,
                title=part_title,
                content=content,
                source=source,
                source_ref=source_ref,
                actor_user_id=actor_user_id,
                ip=ip,
            )
        )
    log.info("knowledge_imported", source=source, parts=len(parts), chars=len(text))
    return docs
