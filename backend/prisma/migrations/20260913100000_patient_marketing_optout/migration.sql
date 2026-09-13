-- Paciente pode pedir para não receber convites de retorno (LGPD).
ALTER TABLE "Patient" ADD COLUMN "marketingOptOut" BOOLEAN NOT NULL DEFAULT false;
