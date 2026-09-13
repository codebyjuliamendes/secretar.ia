import json

from app.config import get_settings
from app.security.signatures import sign_hub
from app.services import knowledge
from tests.conftest import auth_headers, register_user

DOC_PAGAMENTO = (
    "Formas de pagamento\n\n"
    "Aceitamos cartão de crédito em até 6 vezes sem juros, débito, Pix e dinheiro. "
    "Não aceitamos cheque.\n\n"
    "Política de cancelamento\n\n"
    "Cancelamentos com menos de 24 horas de antecedência têm cobrança de 30% do valor do procedimento."
)
DOC_PREPARO = (
    "Preparo para peeling químico\n\n"
    "Suspenda ácidos e retinoides 5 dias antes. Não faça depilação na área 48 horas antes. "
    "Venha sem maquiagem e evite exposição solar intensa na semana anterior."
)


def test_chunk_text_groups_paragraphs_and_splits_long_ones():
    chunks = knowledge.chunk_text(DOC_PAGAMENTO, target=120, maximum=200)
    assert len(chunks) >= 2 and all(len(c) <= 200 for c in chunks)
    assert chunks[0].startswith("Formas de pagamento")
    long_paragraph = " ".join(f"Frase número {i} fala de algo." for i in range(60))
    parts = knowledge.chunk_text(long_paragraph, target=300, maximum=300)
    assert len(parts) > 1 and all(len(p) <= 300 for p in parts)
    assert knowledge.chunk_text("   \n\n  ") == []


def test_fts_query_and_snippets_text():
    assert knowledge._fts_query("Vocês aceitam cartão de crédito?") == "vocês | aceitam | cartão | crédito"
    assert knowledge._fts_query("oi") is None
    text = knowledge.snippets_to_text(
        [knowledge.Snippet("A", "x" * 30, 1.0), knowledge.Snippet("B", "y" * 30, 0.5)], max_chars=50
    )
    assert text.startswith("- [A] xxx") and len(text) <= 51


async def test_knowledge_crud_retrieval_and_isolation(client, clean_db):
    reg = await register_user(client)
    tid, h = reg["tenantId"], auth_headers(reg)
    assert (await client.get(f"/api/clinic/{tid}/knowledge", headers=h)).json() == {"items": []}

    short = await client.post(f"/api/clinic/{tid}/knowledge", headers=h, json={"title": "X", "content": "curto"})
    assert short.status_code == 422

    d1 = await client.post(
        f"/api/clinic/{tid}/knowledge", headers=h, json={"title": "Pagamento e cancelamento", "content": DOC_PAGAMENTO}
    )
    assert d1.status_code == 201, d1.text
    assert d1.json()["chunkCount"] >= 1 and d1.json()["embedded"] is False  # sem chave de IA: só busca textual
    d2 = await client.post(
        f"/api/clinic/{tid}/knowledge", headers=h, json={"title": "Preparo peeling", "content": DOC_PREPARO}
    )
    assert d2.status_code == 201
    assert (
        await clean_db.knowledgechunk.count(where={"tenantId": tid})
        == d1.json()["chunkCount"] + d2.json()["chunkCount"]
    )

    lst = (await client.get(f"/api/clinic/{tid}/knowledge", headers=h)).json()["items"]
    assert [d["title"] for d in lst] == ["Preparo peeling", "Pagamento e cancelamento"]
    detail = (await client.get(f"/api/clinic/{tid}/knowledge/{d1.json()['id']}", headers=h)).json()
    assert detail["content"] == DOC_PAGAMENTO

    # Recuperação por texto completo (português, com stemming): pergunta → trecho certo primeiro.
    hits = (await client.post(f"/api/clinic/{tid}/knowledge/search?q=aceitam%20cartão%20parcelado", headers=h)).json()
    assert hits["items"] and "cartão de crédito" in hits["items"][0]["content"]
    hits = (
        await client.post(
            f"/api/clinic/{tid}/knowledge/search?q=posso%20me%20depilar%20antes%20do%20peeling", headers=h
        )
    ).json()
    assert hits["items"] and hits["items"][0]["title"] == "Preparo peeling"
    none = (await client.post(f"/api/clinic/{tid}/knowledge/search?q=estacionamento%20gratuito", headers=h)).json()
    assert none["items"] == []

    # Isolamento: outro tenant não vê nem recupera.
    other = await register_user(client)
    assert (await client.get(f"/api/clinic/{other['tenantId']}/knowledge", headers=auth_headers(other))).json() == {
        "items": []
    }
    assert (
        await client.get(f"/api/clinic/{other['tenantId']}/knowledge/{d1.json()['id']}", headers=auth_headers(other))
    ).status_code == 404
    assert await knowledge.retrieve(get_settings(), other["tenantId"], "cartão") == []

    # Reindex sem IA mantém tudo como busca textual; remoção apaga chunks em cascata.
    re = await client.post(f"/api/clinic/{tid}/knowledge/reindex", headers=h)
    assert re.json() == {"documents": 2, "embedded": 0}
    assert (await client.delete(f"/api/clinic/{tid}/knowledge/{d2.json()['id']}", headers=h)).status_code == 204
    assert await clean_db.knowledgechunk.count(where={"documentId": d2.json()["id"]}) == 0
    audit = (await client.get(f"/api/clinic/{tid}/audit", headers=h)).json()
    actions = {a["action"] for a in audit["items"]}
    assert {"knowledge.document_added", "knowledge.document_deleted", "knowledge.reindexed"} <= actions


async def test_knowledge_feeds_whatsapp_reply_in_degraded_mode(client, clean_db):
    reg = await register_user(client)
    tid, h = reg["tenantId"], auth_headers(reg)
    await clean_db.tenant.update(where={"id": tid}, data={"status": "ACTIVE"})
    await client.post(
        f"/api/clinic/{tid}/knowledge", headers=h, json={"title": "Pagamento e cancelamento", "content": DOC_PAGAMENTO}
    )
    payload = {"messageId": "kb-1", "phone": "5581999990000", "text": "vocês aceitam cartão?", "tenantId": tid}
    body = json.dumps(payload).encode()
    res = await client.post(
        "/api/webhooks/whatsapp",
        content=body,
        headers={"X-Hub-Signature-256": sign_hub(body, "test-whatsapp-secret"), "Content-Type": "application/json"},
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["intent"] == "INFO" and data["degraded"] is True
    assert "cartão de crédito em até 6 vezes" in data["reply"]  # resposta por regras usa o trecho recuperado

    # Pergunta fora da base: resposta padrão, sem inventar.
    payload2 = {**payload, "messageId": "kb-2", "text": "tem estacionamento?"}
    body2 = json.dumps(payload2).encode()
    res2 = await client.post(
        "/api/webhooks/whatsapp",
        content=body2,
        headers={"X-Hub-Signature-256": sign_hub(body2, "test-whatsapp-secret"), "Content-Type": "application/json"},
    )
    assert "o que temos registrado" not in res2.json()["reply"]


def test_system_prompt_includes_knowledge_block():
    from datetime import UTC, datetime
    from types import SimpleNamespace

    from app.services.ai import build_system_prompt

    tenant = SimpleNamespace(name="H", prompt="Você é a secretária.", businessHours=None, prices=None, timezone="UTC")
    with_kb = build_system_prompt(
        tenant, now_local=datetime.now(UTC), upcoming=[], knowledge_text="- [Pagamento] Pix ok"
    )
    assert "Base de conhecimento da clínica" in with_kb and "- [Pagamento] Pix ok" in with_kb
    assert "confirmar com a equipe" in with_kb
    without = build_system_prompt(tenant, now_local=datetime.now(UTC), upcoming=[])
    assert "Base de conhecimento" not in without


class FakeEmbedder:
    """Embeddings determinísticos por assunto: permitem exercitar a busca vetorial sem rede."""

    def __init__(self):
        self.calls: list[str] = []

    async def embed(self, texts, *, model, task_type, dims):
        self.calls.append(task_type)
        out = []
        for t in texts:
            low = t.lower()
            axis = 0 if "cartão" in low or "pagamento" in low else 1 if "peeling" in low else 2
            vec = [0.0] * dims
            vec[axis] = 1.0
            vec[3] = 0.1  # evita vetores idênticos entre eixos diferentes virarem NaN no cosseno
            out.append(vec)
        return out


async def test_vector_retrieval_uses_hnsw_index_and_ranks_by_cosine(client, clean_db, monkeypatch):
    fake = FakeEmbedder()
    monkeypatch.setattr(knowledge, "embedding_client", lambda settings: fake)
    idx = await clean_db.query_raw(
        "SELECT indexdef FROM pg_indexes WHERE tablename = 'KnowledgeChunk' "
        "AND indexname = 'KnowledgeChunk_embedding_idx'"
    )
    assert idx and "USING hnsw" in idx[0]["indexdef"] and "vector_cosine_ops" in idx[0]["indexdef"]

    reg = await register_user(client)
    tid, h = reg["tenantId"], auth_headers(reg)
    d1 = await client.post(
        f"/api/clinic/{tid}/knowledge", headers=h, json={"title": "Pagamento e cancelamento", "content": DOC_PAGAMENTO}
    )
    d2 = await client.post(
        f"/api/clinic/{tid}/knowledge", headers=h, json={"title": "Preparo peeling", "content": DOC_PREPARO}
    )
    assert d1.json()["embedded"] is True and d2.json()["embedded"] is True
    assert await clean_db.query_raw('SELECT count(*) AS n FROM "KnowledgeChunk" WHERE embedding IS NULL') == [{"n": 0}]

    hits = await knowledge.retrieve(get_settings(), tid, "posso pagar no cartão?")
    assert hits and hits[0].title == "Pagamento e cancelamento" and hits[0].score > 0.99
    hits = await knowledge.retrieve(get_settings(), tid, "como me preparo para o peeling")
    assert hits and hits[0].title == "Preparo peeling"
    assert fake.calls[-1] == "RETRIEVAL_QUERY"
    # Outro tenant com base própria não vaza: o filtro por tenant vale também na busca vetorial.
    other = await register_user(client)
    assert await knowledge.retrieve(get_settings(), other["tenantId"], "cartão") == []
