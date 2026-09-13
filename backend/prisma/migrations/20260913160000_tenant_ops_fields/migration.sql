ALTER TABLE "Tenant" ADD COLUMN "introEnabled" BOOLEAN NOT NULL DEFAULT true,
                     ADD COLUMN "hardLimit" BOOLEAN NOT NULL DEFAULT false,
                     ADD COLUMN "paidUntil" TIMESTAMP(3),
                     ADD COLUMN "paymentMethod" TEXT NOT NULL DEFAULT '',
                     ADD COLUMN "billingNote" TEXT,
                     ADD COLUMN "welcomeSentAt" TIMESTAMP(3),
                     ADD COLUMN "lastReportPeriod" TEXT;
