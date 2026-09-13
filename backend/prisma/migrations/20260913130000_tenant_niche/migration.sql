-- Nicho do negócio (clínica, salão, pet, advocacia...): escolhido pelo admin ao liberar a conta.
ALTER TABLE "Tenant" ADD COLUMN "niche" TEXT NOT NULL DEFAULT 'clinica';
