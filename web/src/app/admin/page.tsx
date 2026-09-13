"use client";

import Link from "next/link";
import { Badge, Card, ErrorState, PageHeader, Skeleton, StatTile } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { PLAN_LABEL, brl, formatDate, formatPhone } from "@/lib/format";
import type { AdminHealth, AdminOverview, HealthItem } from "@/lib/types";
import { useQuery } from "@/lib/use-query";

export default function AdminOverviewPage() {
  const { data, error, loading, refetch } = useQuery(() => api.get<AdminOverview>("admin/overview"), []);
  const health = useQuery(() => api.get<AdminHealth>("admin/health"), []);
  return (
    <>
      <PageHeader title="Visão geral da plataforma" description="Números reais consolidados de todas as clínicas." />
      {error ? (
        <ErrorState message={error} onRetry={refetch} />
      ) : loading || !data ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">{Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-24" />)}</div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatTile label="MRR (planos ativos)" value={brl(data.mrrCents)} hint="soma dos preços de tabela das clínicas ativas" tone="primary" />
          <StatTile label="Clínicas ativas" value={data.tenants.active} hint={`${data.tenants.pending} aguardando liberação · ${data.tenants.total} no total`} />
          <StatTile label="Pagamento pendente" value={data.tenants.pastDue} hint={`${data.tenants.inactive} canceladas/suspensas`} />
          <StatTile label="Mensagens de IA no mês" value={data.aiMessagesThisMonth.toLocaleString("pt-BR")} hint={data.failedJobs ? <Link href="/admin/jobs?status=FAILED" className="text-danger hover:underline">{data.failedJobs} tarefas falharam</Link> : "fila saudável"} />
        </div>
      )}
      <section className="mt-8" aria-label="Saúde da carteira">
        <h2 className="text-lg font-semibold">Para quem ligar hoje</h2>
        <p className="text-sm text-muted">Quem não usa cancela; quem está no limite compra upgrade. A lista abaixo é atualizada a cada carga.</p>
        {health.error ? (
          <ErrorState message={health.error} onRetry={health.refetch} />
        ) : !health.data ? (
          <Skeleton className="mt-4 h-40" />
        ) : (
          <div className="mt-4 grid gap-4 md:grid-cols-2">
            <HealthList title="Aguardando liberação" tone="warning" items={health.data.pending} render={(i) => `${i.days} dia(s) esperando`} empty="Nenhuma conta pendente." />
            <HealthList title="Ativas sem WhatsApp conectado (3+ dias)" tone="danger" items={health.data.noWhatsapp} render={(i) => `conta com ${i.days} dias`} empty="Todas as ativas conectaram." />
            <HealthList title="Sem nenhuma mensagem em 7 dias" tone="warning" items={health.data.silent} render={() => "uso zero na semana"} empty="Todas tiveram movimento." />
            <HealthList title="Perto do limite do plano (80%+)" tone="info" items={health.data.nearLimit} render={(i) => `${i.used?.toLocaleString("pt-BR")} / ${i.limit?.toLocaleString("pt-BR")} · ${i.pct}%`} empty="Ninguém perto do limite." />
            <HealthList title="Vencendo em 7 dias ou vencidas (Pix/boleto)" tone="danger" items={health.data.expiring} render={(i) => (i.days ?? 0) < 0 ? `vencida em ${formatDate(i.paidUntil)}` : `vence em ${formatDate(i.paidUntil)}`} empty="Nenhum vencimento próximo." />
          </div>
        )}
      </section>
    </>
  );
}

function HealthList({ title, tone, items, render, empty }: { title: string; tone: "info" | "warning" | "danger"; items: HealthItem[]; render: (i: HealthItem) => string; empty: string }) {
  return (
    <Card title={title} action={<Badge tone={items.length ? tone : "success"}>{items.length}</Badge>}>
      {items.length === 0 ? (
        <p className="text-sm text-muted">{empty}</p>
      ) : (
        <ul className="divide-y divide-border">
          {items.slice(0, 8).map((i) => (
            <li key={i.id} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
              <span><Link href="/admin/tenants" className="font-medium hover:underline">{i.name}</Link> <span className="text-xs text-muted">· {PLAN_LABEL[i.plan]} · {render(i)}</span></span>
              <a href={`https://wa.me/${i.whatsapp.replace(/\D/g, "")}`} target="_blank" rel="noopener noreferrer" className="text-xs text-primary hover:underline">{formatPhone(i.whatsapp)} ↗</a>
            </li>
          ))}
          {items.length > 8 && <li className="py-2 text-xs text-muted">e mais {items.length - 8}…</li>}
        </ul>
      )}
    </Card>
  );
}
