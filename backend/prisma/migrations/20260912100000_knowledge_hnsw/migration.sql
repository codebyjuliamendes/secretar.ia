-- Índice HNSW (distância de cosseno) para a busca vetorial da base de conhecimento.
-- Nome igual ao que o Prisma geraria para `@@index([embedding])`, para o diff schema/migrations fechar.
-- Um btree aqui não serviria: vetores de 768 dims excedem o tamanho máximo de entrada do btree.
CREATE INDEX "KnowledgeChunk_embedding_idx" ON "KnowledgeChunk" USING hnsw (embedding vector_cosine_ops);
