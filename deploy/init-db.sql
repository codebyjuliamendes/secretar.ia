-- Roda uma única vez, quando o Postgres é criado pela primeira vez no servidor.
-- A Evolution API guarda a sessão do WhatsApp em um banco próprio, separado do nosso.
CREATE DATABASE evolution;
