import Link from "next/link";
import { LEGAL_UPDATED_AT, type LegalSection } from "@/lib/legal";

/** Layout comum da Política de Privacidade e dos Termos: leitura em coluna única, sem depender de login. */
export function LegalPage({
  title,
  intro,
  sections,
  entity,
  doc,
  other,
}: {
  title: string;
  intro: string;
  sections: LegalSection[];
  entity: string;
  doc: string;
  other: { href: string; label: string };
}) {
  return (
    <main className="mx-auto max-w-2xl px-6 py-10">
      <header className="border-b border-border pb-6">
        <Link href="/" className="text-lg font-semibold tracking-tight">
          Secretar<span className="text-primary">.ia</span>
        </Link>
        <h1 className="mt-6 text-3xl font-semibold tracking-tight [text-wrap:balance]">{title}</h1>
        <p className="mt-3 text-sm text-muted">{intro}</p>
        <p className="mt-3 text-xs text-muted">
          Última atualização: {LEGAL_UPDATED_AT}
          {entity ? ` · ${entity}` : ""}
          {doc ? ` · CNPJ ${doc}` : ""}
        </p>
      </header>

      <div className="mt-8 space-y-8">
        {sections.map((s) => (
          <section key={s.title}>
            <h2 className="text-lg font-semibold tracking-tight">{s.title}</h2>
            {s.paragraphs?.map((p) => (
              <p key={p} className="mt-2 text-sm leading-relaxed text-muted">
                {p}
              </p>
            ))}
            {s.bullets && (
              <ul className="mt-2 list-disc space-y-1 pl-5 text-sm leading-relaxed text-muted">
                {s.bullets.map((b) => (
                  <li key={b}>{b}</li>
                ))}
              </ul>
            )}
          </section>
        ))}
      </div>

      <footer className="mt-12 flex flex-wrap items-center justify-between gap-3 border-t border-border pt-6 text-xs text-muted">
        <Link href={other.href} className="text-primary hover:underline">
          {other.label}
        </Link>
        <Link href="/" className="hover:underline">
          Voltar ao início
        </Link>
      </footer>
    </main>
  );
}

/** Rodapé com os links legais, usado nas páginas públicas. */
export function LegalFooter({ className }: { className?: string }) {
  return (
    <footer className={className ?? "mt-12 text-center text-xs text-muted"}>
      © {new Date().getFullYear()} Secretar.ia ·{" "}
      <Link href="/privacidade" className="hover:underline">
        Privacidade
      </Link>{" "}
      ·{" "}
      <Link href="/termos" className="hover:underline">
        Termos
      </Link>
    </footer>
  );
}
