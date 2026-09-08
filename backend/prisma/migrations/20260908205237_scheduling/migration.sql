-- AlterTable
ALTER TABLE "Appointment" ADD COLUMN     "durationMin" INTEGER NOT NULL DEFAULT 60,
ADD COLUMN     "endAt" TIMESTAMP(3),
ADD COLUMN     "serviceId" TEXT;

-- AlterTable
ALTER TABLE "Tenant" ADD COLUMN     "slotMinutes" INTEGER NOT NULL DEFAULT 30;

-- CreateTable
CREATE TABLE "Service" (
    "id" TEXT NOT NULL,
    "tenantId" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "durationMin" INTEGER NOT NULL DEFAULT 60,
    "priceCents" INTEGER,
    "description" TEXT,
    "active" BOOLEAN NOT NULL DEFAULT true,
    "sortOrder" INTEGER NOT NULL DEFAULT 0,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "Service_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "AvailabilityRule" (
    "id" TEXT NOT NULL,
    "tenantId" TEXT NOT NULL,
    "weekday" INTEGER NOT NULL,
    "startMin" INTEGER NOT NULL,
    "endMin" INTEGER NOT NULL,

    CONSTRAINT "AvailabilityRule_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE INDEX "Service_tenantId_active_idx" ON "Service"("tenantId", "active");

-- CreateIndex
CREATE UNIQUE INDEX "Service_tenantId_name_key" ON "Service"("tenantId", "name");

-- CreateIndex
CREATE INDEX "AvailabilityRule_tenantId_weekday_idx" ON "AvailabilityRule"("tenantId", "weekday");

-- CreateIndex
CREATE INDEX "Appointment_tenantId_date_endAt_idx" ON "Appointment"("tenantId", "date", "endAt");

-- AddForeignKey
ALTER TABLE "Service" ADD CONSTRAINT "Service_tenantId_fkey" FOREIGN KEY ("tenantId") REFERENCES "Tenant"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "AvailabilityRule" ADD CONSTRAINT "AvailabilityRule_tenantId_fkey" FOREIGN KEY ("tenantId") REFERENCES "Tenant"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Appointment" ADD CONSTRAINT "Appointment_serviceId_fkey" FOREIGN KEY ("serviceId") REFERENCES "Service"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- Dados: janelas padrão (seg-sex 09:00-18:00) para clínicas que ainda não têm regras
INSERT INTO "AvailabilityRule" (id, "tenantId", weekday, "startMin", "endMin")
SELECT md5(random()::text || t.id || d.weekday::text), t.id, d.weekday, 540, 1080
FROM "Tenant" t CROSS JOIN (VALUES (0), (1), (2), (3), (4)) AS d(weekday)
WHERE NOT EXISTS (SELECT 1 FROM "AvailabilityRule" r WHERE r."tenantId" = t.id);

-- Dados: endAt para agendamentos existentes
UPDATE "Appointment" SET "endAt" = date + ("durationMin" * INTERVAL '1 minute') WHERE "endAt" IS NULL;
