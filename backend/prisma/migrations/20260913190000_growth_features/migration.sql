-- Tenant: link público, indicação, sinal Pix, voz, lembrete, grupo
ALTER TABLE "Tenant" ADD COLUMN "slug" TEXT,
                     ADD COLUMN "publicBooking" BOOLEAN NOT NULL DEFAULT true,
                     ADD COLUMN "referralCode" TEXT,
                     ADD COLUMN "referredById" TEXT,
                     ADD COLUMN "depositEnabled" BOOLEAN NOT NULL DEFAULT false,
                     ADD COLUMN "depositCents" INTEGER,
                     ADD COLUMN "pixKey" TEXT,
                     ADD COLUMN "voiceReplies" BOOLEAN NOT NULL DEFAULT false,
                     ADD COLUMN "reminderEnabled" BOOLEAN NOT NULL DEFAULT true,
                     ADD COLUMN "parentTenantId" TEXT,
                     ADD COLUMN "lastQuestionsDigestAt" TIMESTAMP(3);

-- Contas existentes ganham slug e código de indicação derivados do nome/id
UPDATE "Tenant" SET
  "slug" = trim(both '-' from regexp_replace(lower(translate(name,
      'áàâãäéèêëíìîïóòôõöúùûüçÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇ', 'aaaaaeeeeiiiiooooouuuucAAAAAEEEEIIIIOOOOOUUUUC')),
      '[^a-z0-9]+', '-', 'g')) || '-' || substr(id, length(id) - 3, 4),
  "referralCode" = upper(substr(md5(id), 1, 6))
WHERE "slug" IS NULL;

CREATE UNIQUE INDEX "Tenant_slug_key" ON "Tenant"("slug");
CREATE UNIQUE INDEX "Tenant_referralCode_key" ON "Tenant"("referralCode");

-- Appointment: profissional, lembrete, sinal
ALTER TABLE "Appointment" ADD COLUMN "professionalId" TEXT,
                          ADD COLUMN "reminderSentAt" TIMESTAMP(3),
                          ADD COLUMN "depositStatus" TEXT NOT NULL DEFAULT '';

CREATE TABLE "Professional" (
    "id" TEXT NOT NULL,
    "tenantId" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "active" BOOLEAN NOT NULL DEFAULT true,
    "sortOrder" INTEGER NOT NULL DEFAULT 0,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "Professional_pkey" PRIMARY KEY ("id")
);
CREATE UNIQUE INDEX "Professional_tenantId_name_key" ON "Professional"("tenantId", "name");
ALTER TABLE "Professional" ADD CONSTRAINT "Professional_tenantId_fkey" FOREIGN KEY ("tenantId") REFERENCES "Tenant"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "Appointment" ADD CONSTRAINT "Appointment_professionalId_fkey" FOREIGN KEY ("professionalId") REFERENCES "Professional"("id") ON DELETE SET NULL ON UPDATE CASCADE;

CREATE TABLE "WaitlistEntry" (
    "id" TEXT NOT NULL,
    "tenantId" TEXT NOT NULL,
    "patientId" TEXT NOT NULL,
    "desiredDay" TIMESTAMP(3) NOT NULL,
    "service" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "notifiedAt" TIMESTAMP(3),
    CONSTRAINT "WaitlistEntry_pkey" PRIMARY KEY ("id")
);
CREATE INDEX "WaitlistEntry_tenantId_desiredDay_notifiedAt_idx" ON "WaitlistEntry"("tenantId", "desiredDay", "notifiedAt");
ALTER TABLE "WaitlistEntry" ADD CONSTRAINT "WaitlistEntry_tenantId_fkey" FOREIGN KEY ("tenantId") REFERENCES "Tenant"("id") ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE "WaitlistEntry" ADD CONSTRAINT "WaitlistEntry_patientId_fkey" FOREIGN KEY ("patientId") REFERENCES "Patient"("id") ON DELETE CASCADE ON UPDATE CASCADE;

CREATE TABLE "UnansweredQuestion" (
    "id" TEXT NOT NULL,
    "tenantId" TEXT NOT NULL,
    "phone" TEXT NOT NULL,
    "question" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "resolvedAt" TIMESTAMP(3),
    CONSTRAINT "UnansweredQuestion_pkey" PRIMARY KEY ("id")
);
CREATE INDEX "UnansweredQuestion_tenantId_resolvedAt_createdAt_idx" ON "UnansweredQuestion"("tenantId", "resolvedAt", "createdAt");
ALTER TABLE "UnansweredQuestion" ADD CONSTRAINT "UnansweredQuestion_tenantId_fkey" FOREIGN KEY ("tenantId") REFERENCES "Tenant"("id") ON DELETE CASCADE ON UPDATE CASCADE;
