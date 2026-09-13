"use client";

import { useEffect, useState } from "react";
import { Alert, Badge, Button, Card, ErrorState, LinkButton, PageHeader, Skeleton, cx } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/toast";
import { api, errorMessage } from "@/lib/api";
import { PLAN_LABEL, STATUS_LABEL, STATUS_TONE, brl, limitLabel, salesLink } from "@/lib/format";
import type { Billing, Plan } from "@/lib/types";
import { useQuery } from "@/lib/use-query";
import { useTenant } from "../layout";

function UsageBar({ label, used, limit }: { label: string; used: number; limit: number }) {
  const pct = limit < 0 ? 0 : Math.min(100, Math.round((used / limit) * 100));
  const tone = pct >= 90 ? "bg-danger" : pct >= 70 ? "bg-warning" : "bg-primary";
  return (
    <div>
      <div className="flex justify-between text-sm"><span>{label}</span><span className="tabular-nums text-muted">{used.toLocaleString("pt-BR")} / {limitLabel(limit)}</span></div>
      <div className="mt-1 h-2 rounded-full bg-surface-2" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label={label}>
        {limit >= 0 && <div className={cx("h-2 rounded-full", tone)} style={{ width: `${pct}%` }} />}
      </div>
    </div>
  );
}

type CheckoutResult = "success" | "cancel" | "console" | null;

/** Lê ?checkout=... da URL após o retorno do gateway e limpa a query para não repetir o aviso ao recarregar. */
function useCheckoutResult(): CheckoutResult {
  const [result, setResult] = useState<CheckoutResult>(null);
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const value = params.get("checkout") ?? (params.get("portal") === "console" ? "console" : null);
    if (value === "success" || value === "cancel" || value === "console") {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setResult(value);
      window.history.replaceState(null, "", window.location.pathname);
    }
  }, []);
  return result;
}

export default function BillingPage() {
  const { tenant, reload } = useTenant();
  const toast = useToast();
  const canManage = tenant.role === "OWNER";
  const checkoutResult = useCheckoutResult();
  const { data, error, refetch } = useQuery(() => api.get<Billing>(`clinic/${tenant.id}/billing`), [tenant.id]);
  const [busy, setBusy] = useState<string | null>(null);

  // Após um checkout concluído, o webhook pode levar alguns segundos: recarrega uma vez depois.
  useEffect(() => {
    if (checkoutResult !== "success") return;
    const t = setTimeout(() => { void refetch(); void reload(); }, 4000);
    return () => clearTimeout(t);
  }, [checkoutResult, refetch, reload]);

  async function go(path: "checkout" | "portal", plan?: Plan) {
    setBusy(plan ?? path);
    try {
      const r = await api.post<{ url: string }>(`clinic/${tenant.id}/billing/${path}`, plan ? { plan } : undefined);
      window.location.assign(r.url);
    } catch (err) {
      toast.error(errorMessage(err));
      setBusy(null);
    }
  }

  const hasSubscription = !!data?.subscriptionId && (data.status === "ACTIVE" || data.status === "PAST_DUE");
  const talk = salesLink(data?.sales, `Olá! Sou de ${tenant.name} e quero falar sobre o plano Enterprise da Secretar.ia.`);
  const talkAbout = salesLink(data?.sales, `Olá! Sou de ${tenant.name} e quero falar sobre o plano da Secretar.ia.`);
  const salesName = data?.sales.name || "a equipe";

  return (
    <>
      <PageHeader
        title="Plano & uso"
        description="Consumo do mês e limites do seu plano. Os limites são aplicados pelo servidor."
        action={data?.hasCustomer && canManage ? <Button variant="secondary" loading={busy === "portal"} onClick={() => go("portal")}>Gerenciar assinatura</Button> : undefined}
      />
      {checkoutResult === "success" && <div className="mb-4"><Alert tone="success" title="Pagamento recebido">Sua assinatura está sendo ativada. O plano é atualizado automaticamente assim que o gateway confirmar.</Alert></div>}
      {checkoutResult === "cancel" && <div className="mb-4"><Alert tone="info">Checkout cancelado. Nenhuma cobrança foi feita.</Alert></div>}
      {checkoutResult === "console" && <div className="mb-4"><Alert tone="warning">Ambiente de desenvolvimento: o gateway de pagamento não está configurado, então nada foi cobrado.</Alert></div>}
      {error ? (
        <ErrorState message={error} onRetry={refetch} />
      ) : !data ? (
        <Skeleton className="h-64" />
      ) : (
        <div className="space-y-4">
          <Card title="Assinatura" action={<Badge tone={STATUS_TONE[data.status]}>{STATUS_LABEL[data.status]}</Badge>}>
            <dl className="grid gap-4 text-sm sm:grid-cols-3">
              <div><dt className="text-muted">Plano atual</dt><dd className="font-medium">{PLAN_LABEL[data.plan]}</dd></div>
              <div><dt className="text-muted">Período</dt><dd className="font-medium">{data.usage.period}</dd></div>
              <div><dt className="text-muted">Assinatura</dt><dd className="font-medium">{data.subscriptionId ? "Ativa no gateway" : data.status === "PENDING" ? "Aguardando liberação" : "Liberada pela equipe"}</dd></div>
            </dl>
            {data.usage.aiMessages.limit > 0 && data.usage.aiMessages.used >= data.usage.aiMessages.limit && (
              <div className="mt-4">
                <Alert tone="warning" title="Limite mensal de mensagens atingido">
                  <span className="flex flex-wrap items-center justify-between gap-3">
                    <span>A assistente continua respondendo normalmente. Vale conversar sobre a próxima faixa do plano.</span>
                    {talkAbout && <LinkButton href={talkAbout} external size="sm">Falar com {salesName}</LinkButton>}
                  </span>
                </Alert>
              </div>
            )}
            {data.usage.aiMessages.limit > 0 && data.usage.aiMessages.used < data.usage.aiMessages.limit && data.usage.aiMessages.used >= Math.ceil(data.usage.aiMessages.limit * 0.8) && (
              <div className="mt-4">
                <Alert tone="info" title="Você já usou 80% das mensagens do mês">
                  <span className="flex flex-wrap items-center justify-between gap-3">
                    <span>Nada muda por enquanto. Se o movimento se mantiver, a próxima faixa evita surpresas.</span>
                    {talkAbout && <LinkButton href={talkAbout} external size="sm">Falar com {salesName}</LinkButton>}
                  </span>
                </Alert>
              </div>
            )}
            {data.status === "PAST_DUE" && (
              <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
                <Alert tone="danger">Há um pagamento pendente. Regularize para reativar o atendimento automático.</Alert>
                {canManage && data.hasCustomer && <Button variant="secondary" loading={busy === "portal"} onClick={() => go("portal")}>Atualizar pagamento</Button>}
              </div>
            )}
            {!data.checkoutEnabled && !data.subscriptionId && (
              <div className="mt-4">
                <Alert tone="info">
                  <span className="flex flex-wrap items-center justify-between gap-3">
                    <span>Para contratar ou alterar o plano, fale com {salesName}. A liberação é feita na hora, sem cartão.</span>
                    {talkAbout && <LinkButton href={talkAbout} external size="sm">Falar com {salesName} no WhatsApp</LinkButton>}
                  </span>
                </Alert>
              </div>
            )}
            {data.checkoutEnabled && !canManage && !data.subscriptionId && (
              <div className="mt-4"><Alert tone="info">Apenas o proprietário da clínica pode contratar ou alterar o plano.</Alert></div>
            )}
          </Card>
          <Card title={`Uso em ${data.usage.period}`}>
            <div className="space-y-4">
              <UsageBar label="Mensagens atendidas pela IA" used={data.usage.aiMessages.used} limit={data.usage.aiMessages.limit} />
              <UsageBar label="Pacientes cadastrados" used={data.usage.patients.used} limit={data.usage.patients.limit} />
              <UsageBar label="Membros da equipe" used={data.usage.members.used} limit={data.usage.members.limit} />
              {data.usage.knowledgeDocuments.limit !== 0 && (
                <UsageBar label="Documentos na base de conhecimento" used={data.usage.knowledgeDocuments.used} limit={data.usage.knowledgeDocuments.limit} />
              )}
            </div>
          </Card>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            {data.plans.map((p) => {
              const current = p.plan === data.plan;
              const purchasable = data.purchasablePlans.includes(p.plan);
              const enterprise = p.plan === "ENTERPRISE";
              const showAction = !enterprise && canManage && data.checkoutEnabled && !current && (purchasable || hasSubscription);
              return (
                <div key={p.plan} className={cx("flex flex-col rounded-xl border bg-surface p-5", current ? "border-primary" : "border-border")}>
                  <div className="flex items-center justify-between"><h3 className="font-semibold">{PLAN_LABEL[p.plan]}</h3>{current && <Badge tone="primary">atual</Badge>}</div>
                  <p className="mt-2 text-2xl font-semibold">{p.priceFrom && <span className="text-sm font-normal text-muted">a partir de </span>}{brl(p.priceCentsMonth)}<span className="text-sm font-normal text-muted">/mês</span></p>
                  <ul className="mt-3 space-y-1 text-sm text-muted">
                    <li>{limitLabel(p.aiMessagesPerMonth)} mensagens de IA/mês</li>
                    <li>{limitLabel(p.maxPatients)} pacientes</li>
                    <li>{limitLabel(p.maxMembers)} membros</li>
                    <li>{p.upsellCampaigns ? "Campanha de retorno" : "Sem campanha de retorno"}</li>
                    <li>Lê áudio e imagem do paciente</li>
                    <li>Base de conhecimento ({limitLabel(p.maxKnowledgeDocuments)} documentos)</li>
                  </ul>
                  {showAction && (
                    <div className="mt-4 pt-1">
                      {hasSubscription ? (
                        <Button variant="secondary" size="sm" className="w-full" loading={busy === "portal"} onClick={() => go("portal")}>Mudar para este plano</Button>
                      ) : purchasable ? (
                        <Button size="sm" className="w-full" loading={busy === p.plan} onClick={() => go("checkout", p.plan)}>Assinar {PLAN_LABEL[p.plan]}</Button>
                      ) : null}
                    </div>
                  )}
                  {enterprise && !current && (
                    <div className="mt-4 space-y-2 pt-1">
                      <p className="text-xs text-muted">Sob medida: volume, integrações e atendimento combinados em conversa.</p>
                      {talk ? (
                        <LinkButton href={talk} external size="sm" className="w-full">Falar com {salesName}</LinkButton>
                      ) : (
                        <p className="text-xs text-muted">Fale com nossa equipe.</p>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </>
  );
}
