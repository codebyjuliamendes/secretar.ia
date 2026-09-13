-- Sem plano gratuito: 4 faixas pagas (Essencial, Profissional, Premium, Enterprise). A clínica nasce
-- "aguardando liberação" (PENDING) e o admin libera o plano. Persona da assistente gerada pelo tom.

-- AlterEnum TenantStatus (novo valor PENDING) — antes de qualquer UPDATE que use o valor
BEGIN;
CREATE TYPE "TenantStatus_new" AS ENUM ('PENDING', 'ACTIVE', 'PAST_DUE', 'CANCELED', 'SUSPENDED');
ALTER TABLE "Tenant" ALTER COLUMN "status" DROP DEFAULT;
ALTER TABLE "Tenant" ALTER COLUMN "status" TYPE "TenantStatus_new" USING ("status"::text::"TenantStatus_new");
ALTER TYPE "TenantStatus" RENAME TO "TenantStatus_old";
ALTER TYPE "TenantStatus_new" RENAME TO "TenantStatus";
DROP TYPE "TenantStatus_old";
ALTER TABLE "Tenant" ALTER COLUMN "status" SET DEFAULT 'PENDING';
COMMIT;

-- Clínicas que estavam no FREE ficam aguardando liberação com o plano de entrada como placeholder.
UPDATE "Tenant" SET "status" = 'PENDING' WHERE "plan" = 'FREE' AND "status" = 'ACTIVE';
UPDATE "Tenant" SET "plan" = 'BASIC' WHERE "plan" = 'FREE';

-- AlterEnum Plan (sem FREE, com PREMIUM)
BEGIN;
CREATE TYPE "Plan_new" AS ENUM ('BASIC', 'PRO', 'PREMIUM', 'ENTERPRISE');
ALTER TABLE "Tenant" ALTER COLUMN "plan" DROP DEFAULT;
ALTER TABLE "Tenant" ALTER COLUMN "plan" TYPE "Plan_new" USING ("plan"::text::"Plan_new");
ALTER TYPE "Plan" RENAME TO "Plan_old";
ALTER TYPE "Plan_new" RENAME TO "Plan";
DROP TYPE "Plan_old";
ALTER TABLE "Tenant" ALTER COLUMN "plan" SET DEFAULT 'BASIC';
COMMIT;

-- AlterTable: prompt opcional (persona vem do tom) e tom da assistente
ALTER TABLE "Tenant" ALTER COLUMN "prompt" SET DEFAULT '';
ALTER TABLE "Tenant" ADD COLUMN "tone" TEXT NOT NULL DEFAULT 'acolhedor';
