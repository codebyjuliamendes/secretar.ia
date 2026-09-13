import type { Metadata } from "next";
import { LegalPage } from "@/components/legal-page";
import { termsSections } from "@/lib/legal";
import { getPublicConfig } from "@/lib/server/public-config";

export const metadata: Metadata = {
  title: "Termos de Uso",
  description: "As regras do serviço: conta, planos, pagamento, uso permitido, limites e encerramento.",
  robots: { index: true, follow: true },
  alternates: { canonical: "/termos" },
};

export default async function TermosPage() {
  const config = await getPublicConfig();
  const legal = config?.legal;
  return (
    <LegalPage
      title="Termos de Uso"
      intro="O que a Secretar.ia entrega, o que esperamos de você e o que acontece se algo der errado."
      sections={termsSections(legal?.privacyEmail ?? "")}
      entity={legal?.entity ?? ""}
      doc={legal?.doc ?? ""}
      other={{ href: "/privacidade", label: "Ler a Política de Privacidade" }}
    />
  );
}
