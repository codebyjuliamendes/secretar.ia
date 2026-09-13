"use client";

import Link from "next/link";
import { ErrorState, PageHeader, Skeleton, StatTile } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { brl } from "@/lib/format";
import type { AdminOverview } from "@/lib/types";
import { useQuery } from "@/lib/use-query";

export default function AdminOverviewPage() {
  const { data, error, loading, refetch } = useQuery(() => api.get<AdminOverview>("admin/overview"), []);
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
          <StatTile label="Clínicas ativas" value={data.tenants.active} hint={`${data.tenants.free} no plano gratuito · ${data.tenants.total} no total`} />
          <StatTile label="Pagamento pendente" value={data.tenants.pastDue} hint={`${data.tenants.inactive} canceladas/suspensas`} />
          <StatTile label="Mensagens de IA no mês" value={data.aiMessagesThisMonth.toLocaleString("pt-BR")} hint={data.failedJobs ? <Link href="/admin/jobs?status=FAILED" className="text-danger hover:underline">{data.failedJobs} tarefas falharam</Link> : "fila saudável"} />
        </div>
      )}
    </>
  );
}
