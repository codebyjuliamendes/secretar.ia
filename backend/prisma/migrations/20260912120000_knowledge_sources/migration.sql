-- Origem dos documentos da base de conhecimento (colado, PDF, URL, arquivo de texto).
ALTER TABLE "KnowledgeDocument" ADD COLUMN "source" TEXT NOT NULL DEFAULT 'text',
ADD COLUMN "sourceRef" TEXT;
