import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { LegalFooter } from "@/components/legal-page";
import { Pricing } from "@/components/pricing";
import { LinkButton } from "@/components/ui/primitives";
import { demoLink } from "@/lib/format";
import { NICHE_PAGES, nichePageBySlug } from "@/lib/niche-pages";
import { getPublicConfig } from "@/lib/server/public-config";

export const dynamicParams = false;

export function generateStaticParams() {
  return NICHE_PAGES.map((n) => ({ nicho: n.slug }));
}

export async function generateMetadata({ params }: { params: Promise<{ nicho: string }> }): Promise<Metadata> {
  const page = nichePageBySlug((await params).nicho);
  if (!page) return {};
  return {
    title: `${page.label}`,
    description: page.sub,
    robots: { index: true, follow: true },
    alternates: { canonical: `/para/${page.slug}` },
  };
}

export default async function NicheLanding({ params }: { params: Promise<{ nicho: string }> }) {
  const page = nichePageBySlug((await params).nicho);
  if (!page) notFound();
  const config = await getPublicConfig();
  const demo = demoLink(config?.sales);
  return (
    <main className="mx-auto flex min-h-screen max-w-5xl flex-col px-6 py-10">
      <header className="flex items-center justify-between">
        <Link href="/" className="text-lg font-semibold tracking-tight">
          Secretar<span className="text-primary">.ia</span>
        </Link>
        <nav className="flex gap-2">
          <LinkButton href="/login" variant="secondary" size="sm">
            Entrar
          </LinkButton>
          <LinkButton href="/register" size="sm">
            Criar conta
          </LinkButton>
        </nav>
      </header>

      <section className="grid items-center gap-10 py-16 lg:grid-cols-2">
        <div>
          <p className="mb-3 text-sm font-medium uppercase tracking-widest text-primary">{page.eyebrow}</p>
          <h1 className="text-4xl font-semibold tracking-tight [text-wrap:balance] sm:text-5xl">{page.headline}</h1>
          <p className="mt-5 max-w-xl text-lg text-muted">{page.sub}</p>
          <div className="mt-8 flex flex-wrap gap-3">
            {demo ? (
              <LinkButton href={demo} external>
                Converse com a assistente agora
              </LinkButton>
            ) : (
              <LinkButton href="/register">Criar conta</LinkButton>
            )}
            <LinkButton href={demo ? "/register" : "#planos"} variant="secondary">
              {demo ? "Criar conta" : "Ver planos"}
            </LinkButton>
          </div>
          <p className="mt-4 text-xs text-muted">Sem cartão. Você configura, a equipe libera e a assistente começa a atender.</p>
        </div>
        <ChatExample chat={page.chat} />
      </section>

      <section className="grid gap-4 sm:grid-cols-3" aria-label="Como funciona para o seu ramo">
        {page.features.map((f) => (
          <div key={f.title} className="rounded-xl border border-border bg-surface p-5">
            <h2 className="font-semibold">{f.title}</h2>
            <p className="mt-1 text-sm text-muted">{f.text}</p>
          </div>
        ))}
      </section>

      <p className="mt-6 rounded-lg border border-border bg-surface-2 p-4 text-sm text-muted">
        <span className="font-medium text-foreground">Regra do ramo, já configurada: </span>
        {page.care} Você não precisa escrever nada.
      </p>

      <Pricing config={config} people={page.people} niche={page.label.toLowerCase()} />

      <section className="mt-16" aria-label="Outros ramos">
        <h2 className="text-sm font-medium uppercase tracking-widest text-muted">Também para</h2>
        <div className="mt-3 flex flex-wrap gap-2">
          {NICHE_PAGES.filter((n) => n.slug !== page.slug).map((n) => (
            <Link key={n.slug} href={`/para/${n.slug}`} className="rounded-full border border-border px-3 py-1 text-sm hover:border-primary hover:text-primary">
              {n.label}
            </Link>
          ))}
        </div>
      </section>

      <LegalFooter />
    </main>
  );
}

/** Conversa de exemplo no vocabulário do ramo: mostra o produto antes de qualquer cadastro. */
function ChatExample({ chat }: { chat: { from: "cliente" | "assistente"; text: string }[] }) {
  return (
    <div className="rounded-2xl border border-border bg-surface p-4 shadow-sm" role="figure" aria-label="Exemplo de conversa no WhatsApp">
      <div className="mb-3 flex items-center gap-2 border-b border-border pb-3 text-sm">
        <span className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-primary-soft font-semibold text-primary">S</span>
        <div>
          <p className="font-medium">Assistente</p>
          <p className="text-xs text-muted">responde em segundos</p>
        </div>
      </div>
      <ol className="space-y-2">
        {chat.map((m, i) => (
          <li key={i} className={m.from === "cliente" ? "flex justify-end" : "flex justify-start"}>
            <p className={`max-w-[85%] rounded-2xl px-3 py-2 text-sm ${m.from === "cliente" ? "rounded-br-sm bg-primary text-white" : "rounded-bl-sm bg-surface-2"}`}>{m.text}</p>
          </li>
        ))}
      </ol>
    </div>
  );
}
