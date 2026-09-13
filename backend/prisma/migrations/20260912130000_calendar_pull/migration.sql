-- Leitura do Google Calendar: token de sincronização incremental e eventos externos que bloqueiam horários.
ALTER TABLE "CalendarConnection" ADD COLUMN "syncToken" TEXT,
ADD COLUMN "lastPullAt" TIMESTAMP(3),
ADD COLUMN "lastFullPullAt" TIMESTAMP(3);

-- CreateTable
CREATE TABLE "ExternalBusy" (
    "id" TEXT NOT NULL,
    "tenantId" TEXT NOT NULL,
    "externalId" TEXT NOT NULL,
    "summary" TEXT,
    "startAt" TIMESTAMP(3) NOT NULL,
    "endAt" TIMESTAMP(3) NOT NULL,
    "allDay" BOOLEAN NOT NULL DEFAULT false,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "ExternalBusy_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "ExternalBusy_tenantId_externalId_key" ON "ExternalBusy"("tenantId", "externalId");

-- CreateIndex
CREATE INDEX "ExternalBusy_tenantId_startAt_endAt_idx" ON "ExternalBusy"("tenantId", "startAt", "endAt");

-- AddForeignKey
ALTER TABLE "ExternalBusy" ADD CONSTRAINT "ExternalBusy_tenantId_fkey" FOREIGN KEY ("tenantId") REFERENCES "Tenant"("id") ON DELETE CASCADE ON UPDATE CASCADE;
