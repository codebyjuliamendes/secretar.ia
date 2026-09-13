"use client";

import Link from "next/link";
import { useState } from "react";
import { DailyBars, HorizontalBars } from "@/components/charts";
import { Badge, Card, EmptyState, ErrorState, LinkButton, PageHeader, Select, Skeleton, StatTile } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { APPT_LABEL, APPT_TONE, INTENT_LABEL, brl, formatDateTime, limitLabel } from "@/lib/format";
import type { Dashboard } from "@/lib/types";
import { useQuery } from "@/lib/use-query";
import { useTenant } from "./layout";

function delta(current: number, previous: number) {
  if (previous === 0) return current > 0 ? "novo no período" : "sem variação";
  const pct = Math.round(((current - previous) / previous) * 100);
  return `${pct >= 0 ? "+" : ""}${pct}% vs. período anterior`;
}

export default function DashboardPage() {
  const { tenant } = useTenant();
  const [days, setDays] = useState(30);
  const { data, error, refetch } = useQuery(() => api.get<Dashboard>(`clinic/${tenant.id}/dashboard`, { days }), [tenant.id, days]);
  const base = `/app/${tenant.id}`;

  return (
    <>
      <PageHeader
        title="Visão geral"
        description="Indicadores reais da sua clínica no período selecionado."
        action={
          <Select aria-label="Período" value={days} onChange={(e) => setDays(Number(e.target.value))} className="w-40">
            <option value={7}>Últimos 7 dias</option>
            <option value={30}>Últimos 30 dias</option>
            <option value={90}>Últimos 90 dias</option>
          </Select>
        }
      />
      {error ? (
        <ErrorState message={error} onRetry={refetch} />
      ) : !data ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
      ) : (
        <div className="space-y-6">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatTile label="Pedidos de agendamento" value={data.kpis.appointmentsCreated} hint={delta(data.kpis.appointmentsCreated, data.kpis.appointmentsCreatedPrev)} />
            <StatTile label="Aguardando confirmação" value={data.kpis.appointmentsPending} hint={data.kpis.appointmentsPending ? <Link href={`${base}/appointments?status=PENDING`} className="text-primary hover:underline">Confirmar agora</Link> : "Tudo confirmado"} tone={data.kpis.appointmentsPending ? "primary" : undefined} />
            <StatTile label="Novos pacientes" value={data.kpis.patientsNew} hint={`${data.kpis.patientsTotal} no total · ${delta(data.kpis.patientsNew, data.kpis.patientsNewPrev)}`} />
            <StatTile label="Receita de atendimentos realizados" value={brl(data.kpis.revenueCompletedCents)} hint={data.kpis.revenueCompletedCents ? `${brl(data.kpis.revenueFromAICents)} originados pela IA` : "Informe o valor nos agendamentos para acompanhar"} />
            <StatTile label="Mensagens atendidas pela IA" value={data.kpis.aiMessages} hint={data.kpis.aiDegraded ? `${data.kpis.aiDegraded} em modo simplificado` : data.kpis.aiAvgResponseMs ? `${data.kpis.aiAvgResponseMs} ms em média` : undefined} />
            <StatTile label="Pedidos de atendimento humano" value={data.kpis.humanHandoffs} hint={data.kpis.unreadNotifications ? <Link href={`${base}/inbox`} className="text-primary hover:underline">{data.kpis.unreadNotifications} não lidas na inbox</Link> : "Inbox em dia"} />
            <StatTile label="Próximos confirmados" value={data.kpis.appointmentsUpcoming} hint="agendamentos futuros" />
            <StatTile label="Uso do plano (mês)" value={`${data.usage.aiMessages.used} / ${limitLabel(data.usage.aiMessages.limit)}`} hint="mensagens de IA" />
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card title="Pedidos de agendamento por dia">
              <DailyBars data={data.series} valueKey="appointments" title="Pedidos de agendamento" />
            </Card>
            <Card title="Mensagens atendidas por dia">
              <DailyBars data={data.series} valueKey="messages" title="Mensagens" color="var(--c-chart-2)" />
            </Card>
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <Card title="Últimos agendamentos" className="lg:col-span-2" action={<LinkButton href={`${base}/appointments`} variant="ghost" size="sm">Ver agenda</LinkButton>}>
              {data.recentAppointments.length === 0 ? (
                <EmptyState title="Nenhum agendamento ainda" description="Quando pacientes pedirem horários pelo WhatsApp, eles aparecem aqui." action={<LinkButton href={`${base}/appointments`} size="sm" variant="secondary">Criar manualmente</LinkButton>} />
              ) : (
                <ul className="divide-y divide-border">
                  {data.recentAppointments.map((a) => (
                    <li key={a.id} className="flex items-center justify-between gap-3 py-2.5 text-sm">
                      <div className="min-w-0">
                        <p className="truncate font-medium">{a.patientName}</p>
                        <p className="truncate text-muted">
                          {a.service} · {formatDateTime(a.date)} {a.source === "AI" && <span className="text-primary">· via IA</span>}
                        </p>
                      </div>
                      <Badge tone={APPT_TONE[a.status]}>{APPT_LABEL[a.status]}</Badge>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
            <Card title="O que os pacientes pediram">
              <HorizontalBars items={data.intents.map((i) => ({ label: INTENT_LABEL[i.intent] ?? i.intent, value: i.count }))} />
            </Card>
          </div>
        </div>
      )}
    </>
  );
}
