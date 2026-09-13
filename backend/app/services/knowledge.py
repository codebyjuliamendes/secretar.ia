"""Base de conhecimento da clínica (RAG): documentos → trechos → embeddings em pgvector → recuperação.

- Embeddings via Gemini (`gemini-embedding-001`, 768 dims). Sem chave de IA, os trechos ficam sem vetor e a
  busca cai para texto completo do Postgres (`to_tsvector('portuguese')`), então a funcionalidade continua
  útil em modo degradado e os testes rodam sem rede.
- Os trechos recuperados entram no prompt do sistema como fonte de verdade; a IA é instruída a encaminhar à
  equipe o que a base não cobrir.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.config import Settings
from app.db import db
from app.domain.plans import feature_enabled, knowledge_documents_limit, within_limit
from app.errors import AppError, NotFoundError, PlanFeatureLockedError, QuotaExceededError
from app.integrations.gemini import AIProviderError, GeminiClient
from app.logging import get_logger
from app.services import audit

log = get_logger("knowledge")

EMBEDDING_DIMS = 768
CHUNK_TARGET_CHARS = 800
CHUNK_MAX_CHARS = 1200
MAX_DOCUMENT_CHARS = 30_000
RETRIEVE_LIMIT = 4
MIN_TERM_LEN = 3


@dataclass
class Snippet:
    title: str
    content: str
    score: float


def chunk_text(text: str, *, target: int = CHUNK_TARGET_CHARS, maximum: int = CHUNK_MAX_CHARS) -> list[str]:
    """Agrupa parágrafos até ~`target` caracteres; parágrafos maiores que `maximum` são partidos por frase."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n|\r\n\s*\r\n", text.strip()) if p.strip()]
    units: list[str] = []
    for p in paragraphs:
        if len(p) <= maximum:
            units.append(p)
            continue
        current = ""
        for sentence in re.split(r"(?<=[.!?])\s+", p):
            if current and len(current) + len(sentence) + 1 > maximum:
                units.append(current)
                current = sentence
            else:
                current = f"{current} {sentence}".strip()
        if current:
            units.append(current)
    # Unidade sem pontuação (tabela de preços numa linha só) ainda pode passar de `maximum`: corte por palavra,
    # senão o embedding do lote inteiro falha (limite de tokens) e o documento cai para busca textual.
    bounded: list[str] = []
    for u in units:
        while len(u) > maximum:
            cut = u.rfind(" ", 0, maximum)
            cut = cut if cut > maximum // 2 else maximum
            bounded.append(u[:cut].strip())
            u = u[cut:].strip()
        if u:
            bounded.append(u)
    units = bounded
    chunks: list[str] = []
    buf = ""
    for u in units:
        if buf and len(buf) + len(u) + 1 > target:
            chunks.append(buf)
            buf = u
        else:
            buf = f"{buf}\n{u}".strip()
    if buf:
        chunks.append(buf)
    return chunks


def assert_enabled(tenant) -> None:
    """Base de conhecimento é recurso de plano (BASIC+). Documentos existentes de uma
    clínica que voltou ao FREE ficam guardados, mas não são alterados nem usados pela IA."""
    if not feature_enabled(tenant, "knowledge"):
        raise PlanFeatureLockedError(
            "A base de conhecimento não está incluída no seu plano. Faça upgrade em Plano & uso para usá-la.",
            code="plan_feature_locked",
            details={"feature": "knowledge", "plan": str(tenant.plan)},
        )


def embedding_client(settings: Settings) -> GeminiClient | None:
    if not settings.gemini_api_key:
        return None
    return GeminiClient(settings.gemini_api_key, settings.gemini_model, settings.ai_timeout_seconds, 64)


def _vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{v:.7f}" for v in values) + "]"


def document_view(d, chunk_count: int | None = None) -> dict[str, Any]:
    return {
        "id": d.id,
        "title": d.title,
        "chars": len(d.content),
        "chunkCount": chunk_count if chunk_count is not None else d.chunkCount,
        "embedded": d.embeddingModel is not None,
        "source": d.source,
        "sourceRef": d.sourceRef,
        "createdAt": d.createdAt.isoformat(),
        "updatedAt": d.updatedAt.isoformat(),
    }


async def list_documents(tenant_id: str) -> list[dict[str, Any]]:
    rows = await db.knowledgedocument.find_many(where={"tenantId": tenant_id}, order={"createdAt": "desc"})
    return [document_view(d) for d in rows]


async def get_document(tenant_id: str, document_id: str) -> dict[str, Any]:
    d = await db.knowledgedocument.find_first(where={"id": document_id, "tenantId": tenant_id})
    if d is None:
        raise NotFoundError("Documento não encontrado.")
    return {**document_view(d), "content": d.content}


async def _embed(settings: Settings, texts: list[str], *, task_type: str) -> list[list[float] | None]:
    client = embedding_client(settings)
    if client is None or not texts:
        return [None] * len(texts)
    try:
        vectors = await client.embed(
            texts, model=settings.gemini_embedding_model, task_type=task_type, dims=EMBEDDING_DIMS
        )
    except AIProviderError as exc:
        log.warning("embedding_failed", error=str(exc)[:200], count=len(texts))
        return [None] * len(texts)
    return [v if v and len(v) == EMBEDDING_DIMS else None for v in vectors]


async def _store_chunks(settings: Settings, tenant_id: str, document_id: str, chunks: list[str]) -> bool:
    vectors = await _embed(settings, chunks, task_type="RETRIEVAL_DOCUMENT")
    await db.execute_raw('DELETE FROM "KnowledgeChunk" WHERE "documentId" = $1', document_id)
    for i, (content, vec) in enumerate(zip(chunks, vectors, strict=True)):
        await db.execute_raw(
            """
            INSERT INTO "KnowledgeChunk" (id, "tenantId", "documentId", position, content, embedding)
            VALUES (gen_random_uuid()::text, $1, $2, $3, $4, $5::vector)
            """,
            tenant_id,
            document_id,
            i,
            content,
            _vector_literal(vec) if vec else None,
        )
    return all(v is not None for v in vectors) and bool(vectors)


async def add_document(
    settings: Settings,
    tenant,
    *,
    title: str,
    content: str,
    actor_user_id: str,
    ip: str | None,
    source: str = "text",
    source_ref: str | None = None,
) -> dict[str, Any]:
    assert_enabled(tenant)
    tenant_id = tenant.id
    title, content = title.strip(), content.strip()
    if len(content) > MAX_DOCUMENT_CHARS:
        raise AppError(
            f"Documento acima de {MAX_DOCUMENT_CHARS} caracteres; divida em partes.", code="document_too_long"
        )
    limit = knowledge_documents_limit(tenant)
    if not within_limit(await db.knowledgedocument.count(where={"tenantId": tenant_id}), limit):
        raise QuotaExceededError(
            f"Seu plano permite {limit} documentos na base de conhecimento.",
            code="knowledge_limit",
            details={"limit": limit},
        )
    chunks = chunk_text(content)
    if not chunks:
        raise AppError("Conteúdo vazio.", code="empty_document")
    doc = await db.knowledgedocument.create(
        data={
            "tenantId": tenant_id,
            "title": title,
            "content": content,
            "chunkCount": len(chunks),
            "source": source,
            "sourceRef": (source_ref or None) and source_ref[:500],
        }
    )
    embedded = await _store_chunks(settings, tenant_id, doc.id, chunks)
    doc = await db.knowledgedocument.update(
        where={"id": doc.id}, data={"embeddingModel": settings.gemini_embedding_model if embedded else None}
    )
    await audit.record(
        action="knowledge.document_added",
        resource_type="knowledge_document",
        resource_id=doc.id,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        metadata={"title": title, "chunks": len(chunks), "embedded": embedded, "source": source},
        ip=ip,
    )
    return document_view(doc)


async def delete_document(tenant_id: str, document_id: str, *, actor_user_id: str, ip: str | None) -> None:
    d = await db.knowledgedocument.find_first(where={"id": document_id, "tenantId": tenant_id})
    if d is None:
        raise NotFoundError("Documento não encontrado.")
    await db.knowledgedocument.delete(where={"id": d.id})  # chunks caem em cascata
    await audit.record(
        action="knowledge.document_deleted",
        resource_type="knowledge_document",
        resource_id=d.id,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        metadata={"title": d.title},
        ip=ip,
    )


async def reindex(settings: Settings, tenant, *, actor_user_id: str, ip: str | None) -> dict[str, int]:
    """Recalcula embeddings de todos os documentos (ex.: após configurar a chave de IA)."""
    assert_enabled(tenant)
    tenant_id = tenant.id
    docs = await db.knowledgedocument.find_many(where={"tenantId": tenant_id})
    embedded = 0
    for d in docs:
        ok = await _store_chunks(settings, tenant_id, d.id, chunk_text(d.content))
        await db.knowledgedocument.update(
            where={"id": d.id}, data={"embeddingModel": settings.gemini_embedding_model if ok else None}
        )
        embedded += int(ok)
    await audit.record(
        action="knowledge.reindexed",
        resource_type="tenant",
        resource_id=tenant_id,
        tenant_id=tenant_id,
        actor_user_id=actor_user_id,
        metadata={"documents": len(docs), "embedded": embedded},
        ip=ip,
    )
    return {"documents": len(docs), "embedded": embedded}


def _fts_query(text: str) -> str | None:
    terms = [t for t in re.findall(r"[\wÀ-ÿ]+", text.lower()) if len(t) >= MIN_TERM_LEN]
    return " | ".join(dict.fromkeys(terms)) if terms else None


async def retrieve(settings: Settings, tenant_id: str, query: str, *, limit: int = RETRIEVE_LIMIT) -> list[Snippet]:
    """Trechos mais relevantes para `query`: vetorial quando há embeddings; senão, texto completo."""
    query = query.strip()
    if not query or await db.knowledgedocument.count(where={"tenantId": tenant_id}) == 0:
        return []
    rows: list[dict] = []
    (qvec,) = await _embed(settings, [query[:2000]], task_type="RETRIEVAL_QUERY")
    if qvec is not None:
        rows = await _vector_search(tenant_id, qvec, limit)
    if not rows and (tsq := _fts_query(query)):
        rows = await db.query_raw(
            """
            SELECT d.title, c.content,
                   ts_rank(to_tsvector('portuguese', c.content), to_tsquery('portuguese', $2)) AS score
            FROM "KnowledgeChunk" c JOIN "KnowledgeDocument" d ON d.id = c."documentId"
            WHERE c."tenantId" = $1 AND to_tsvector('portuguese', c.content) @@ to_tsquery('portuguese', $2)
            ORDER BY score DESC
            LIMIT $3
            """,
            tenant_id,
            tsq,
            limit,
        )
    return [Snippet(title=r["title"], content=r["content"], score=float(r["score"] or 0)) for r in rows]


VECTOR_SEARCH_SQL = """
    SELECT d.title, c.content, 1 - (c.embedding <=> $2::vector) AS score
    FROM "KnowledgeChunk" c JOIN "KnowledgeDocument" d ON d.id = c."documentId"
    WHERE c."tenantId" = $1 AND c.embedding IS NOT NULL
    ORDER BY c.embedding <=> $2::vector
    LIMIT $3
"""


async def _vector_search(tenant_id: str, qvec: list[float], limit: int) -> list[dict]:
    """Busca por cosseno usando o índice HNSW (`KnowledgeChunk_embedding_idx`).

    O filtro por tenant é aplicado DEPOIS da vizinhança aproximada; com muitas clínicas, os `ef_search`
    vizinhos mais próximos podem não conter nenhum trecho desta clínica e a busca voltaria vazia. A varredura
    iterativa do pgvector (>= 0.8) continua percorrendo o grafo até preencher o LIMIT, e `SET LOCAL` limita o
    ajuste à transação. Se o servidor não conhecer o parâmetro, cai na consulta simples.
    """
    params = (tenant_id, _vector_literal(qvec), limit)
    try:
        async with db.tx() as tx:
            await tx.execute_raw("SET LOCAL hnsw.iterative_scan = relaxed_order")
            return await tx.query_raw(VECTOR_SEARCH_SQL, *params)
    except Exception as exc:  # noqa: BLE001 - pgvector antigo sem iterative_scan
        log.warning("vector_search_iterative_unavailable", error=str(exc)[:200])
        return await db.query_raw(VECTOR_SEARCH_SQL, *params)


def snippets_to_text(snippets: list[Snippet], *, max_chars: int = 3500) -> str | None:
    if not snippets:
        return None
    out: list[str] = []
    total = 0
    for s in snippets:
        piece = f"- [{s.title}] {s.content}"
        if total + len(piece) > max_chars:
            piece = piece[: max(0, max_chars - total)]
        if piece:
            out.append(piece)
            total += len(piece)
        if total >= max_chars:
            break
    return "\n".join(out) or None
