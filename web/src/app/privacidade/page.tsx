import type { Metadata } from "next";
import { LegalPage } from "@/components/legal-page";
import { privacySections } from "@/lib/legal";
import { getPublicConfig } from "@/lib/server/public-config";

export const metadata: Metadata = {
  title: "Política de Privacidade",
  description: "Como a Secretar.ia trata dados pessoais, com quem compartilha e como exercer seus direitos.",
  robots: { index: true, follow: true },
  alternates: { canonical: "/privacidade" },
};

export default async function PrivacidadePage() {
  const config = await getPublicConfig();
  const legal = config?.legal;
  return (
    <LegalPage
      title="Política de Privacidade"
      intro="O que guardamos, por que guardamos, com quem compartilhamos e o que você pode pedir a qualquer momento."
      sections={privacySections(legal?.privacyEmail ?? "")}
      entity={legal?.entity ?? ""}
      doc={legal?.doc ?? ""}
      other={{ href: "/termos", label: "Ler os Termos de Uso" }}
    />
  );
}
