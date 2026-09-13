import { LinkButton } from "@/components/ui/primitives";
import { PLAN_LABEL, brl, limitLabel, salesLink } from "@/lib/format";
import type { PublicConfig } from "@/lib/types";

/** Tabela de planos das páginas públicas. Enterprise não tem checkout: vira conversa no WhatsApp comercial. */
export function Pricing({ config, people = "contatos", niche }: { config: PublicConfig | null; people?: string; niche?: string }) {
  if (!config) return null;
  const salesName = config.sales.name || "a equipe";
  const talk = salesLink(config.sales, `Olá! Quero falar sobre o plano Enterprise da Secretar.ia${niche ? ` para ${niche}` : ""}.`);
  return (
    <section id="planos" aria-label="Planos" className="mt-16">
      <h2 className="text-center text-2xl font-semibold tracking-tight">Planos</h2>
      <p className="mx-auto mt-2 max-w-xl text-center text-sm text-muted">
        Todos os planos leem áudio e imagem, usam base de conhecimento e trazem a assistente pronta. O que muda é o volume.
        Sem cartão no cadastro: {salesName} libera o plano para você.
      </p>
      <div className="mt-8 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {config.plans.map((p) => {
          const enterprise = p.plan === "ENTERPRISE";
          return (
            <div key={p.plan} className="flex flex-col rounded-xl border border-border bg-surface p-5">
              <h3 className="font-semibold">{PLAN_LABEL[p.plan]}</h3>
              <p className="mt-2 text-2xl font-semibold">
                {p.priceFrom && <span className="text-sm font-normal text-muted">a partir de </span>}
                {brl(p.priceCentsMonth)}
                <span className="text-sm font-normal text-muted">/mês</span>
              </p>
              <p className="mt-1 text-xs text-muted">ou {brl(p.priceCentsYear)}/ano (11 mensalidades)</p>
              <ul className="mt-3 flex-1 space-y-1 text-sm text-muted">
                <li>{limitLabel(p.aiMessagesPerMonth)} mensagens de IA/mês</li>
                <li>
                  {limitLabel(p.maxPatients)} {people}
                </li>
                <li>{limitLabel(p.maxMembers)} membros na equipe</li>
                <li>Base de conhecimento ({limitLabel(p.maxKnowledgeDocuments)} documentos)</li>
              </ul>
              <div className="mt-4">
                {enterprise ? (
                  talk ? (
                    <LinkButton href={talk} external size="sm" className="w-full">
                      Falar com {salesName}
                    </LinkButton>
                  ) : (
                    <p className="text-xs text-muted">Condições sob medida, em conversa.</p>
                  )
                ) : (
                  <LinkButton href="/register" variant="secondary" size="sm" className="w-full">
                    Começar
                  </LinkButton>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
