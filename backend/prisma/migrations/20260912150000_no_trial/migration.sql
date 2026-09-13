-- Sem período de teste: clínicas nascem ATIVAS no plano FREE e o plano pago é liberado manualmente pelo admin.
UPDATE "Tenant" SET "status" = 'ACTIVE' WHERE "status" = 'TRIAL';

-- AlterEnum
BEGIN;
CREATE TYPE "TenantStatus_new" AS ENUM ('ACTIVE', 'PAST_DUE', 'CANCELED', 'SUSPENDED');
ALTER TABLE "Tenant" ALTER COLUMN "status" DROP DEFAULT;
ALTER TABLE "Tenant" ALTER COLUMN "status" TYPE "TenantStatus_new" USING ("status"::text::"TenantStatus_new");
ALTER TYPE "TenantStatus" RENAME TO "TenantStatus_old";
ALTER TYPE "TenantStatus_new" RENAME TO "TenantStatus";
DROP TYPE "TenantStatus_old";
ALTER TABLE "Tenant" ALTER COLUMN "status" SET DEFAULT 'ACTIVE';
COMMIT;

-- AlterTable
ALTER TABLE "Tenant" DROP COLUMN "trialEndsAt";
