"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { NewAppointmentModal } from "@/components/appointment-modal";
import { Badge, Button, EmptyState, ErrorState, Input, PageHeader, Pagination, Select, Skeleton, Table, Td, Th } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/toast";
import { api, errorMessage } from "@/lib/api";
import { APPT_LABEL, APPT_TONE, brl, formatDateTime, formatPhone } from "@/lib/format";
import type { Appointment, AppointmentStatus, Paginated } from "@/lib/types";
import { useDebounced, useQuery } from "@/lib/use-query";
import { useTenant } from "../layout";

const NEXT: Record<AppointmentStatus, { label: string; to: AppointmentStatus; variant?: "primary" | "secondary" | "danger" }[]> = {
  PENDING: [
    { label: "Confirmar", to: "CONFIRMED" },
    { label: "Recusar", to: "CANCELED", variant: "danger" },
  ],
  CONFIRMED: [
    { label: "Realizado", to: "COMPLETED" },
    { label: "Faltou", to: "NO_SHOW", variant: "secondary" },
    { label: "Cancelar", to: "CANCELED", variant: "danger" },
  ],
  COMPLETED: [],
  CANCELED: [],
  NO_SHOW: [],
};

const LIMIT = 25;

function AppointmentsInner() {
  const { tenant } = useTenant();
  const toast = useToast();
  const initialStatus = (useSearchParams().get("status") as AppointmentStatus | null) ?? "";
  const [status, setStatus] = useState<string>(initialStatus);
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const [modal, setModal] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const q = useDebounced(search);
  const { data, error, loading, refetch } = useQuery(
    () => api.get<Paginated<Appointment>>(`clinic/${tenant.id}/appointments`, { status, search: q, limit: LIMIT, offset }),
    [tenant.id, status, q, offset],
  );

  async function transition(id: string, to: AppointmentStatus) {
    setBusy(id);
    try {
      await api.post(`clinic/${tenant.id}/appointments/${id}/status`, { status: to });
      toast.success(`Agendamento marcado como ${APPT_LABEL[to].toLowerCase()}.`);
      await refetch();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  return (
    <>
      <PageHeader title="Agenda" description="Pedidos feitos pela IA chegam como pendentes até a confirmação da equipe." action={<div className="flex gap-2"><a href={`/api/backend/clinic/${tenant.id}/export/appointments.csv`} download="agendamentos.csv" className="inline-flex items-center rounded-lg border border-border px-3 py-2 text-sm font-medium hover:bg-surface-2">Exportar planilha</a><Button onClick={() => setModal(true)}>Novo agendamento</Button></div>} />
      <div className="mb-4 flex flex-col gap-2 sm:flex-row">
        <Input aria-label="Buscar por paciente, telefone ou serviço" placeholder="Buscar paciente, telefone ou serviço" value={search} onChange={(e) => { setSearch(e.target.value); setOffset(0); }} className="sm:max-w-xs" />
        <Select aria-label="Filtrar por status" value={status} onChange={(e) => { setStatus(e.target.value); setOffset(0); }} className="sm:w-56">
          <option value="">Todos os status</option>
          {(Object.keys(APPT_LABEL) as AppointmentStatus[]).map((s) => (
            <option key={s} value={s}>{APPT_LABEL[s]}</option>
          ))}
        </Select>
      </div>
      {error ? (
        <ErrorState message={error} onRetry={refetch} />
      ) : loading && !data ? (
        <Skeleton className="h-64" />
      ) : !data || data.items.length === 0 ? (
        <EmptyState title={status || q ? "Nenhum agendamento com esses filtros" : "Nenhum agendamento ainda"} description={status || q ? "Ajuste a busca ou o filtro de status." : "Crie um agendamento manual ou aguarde os pedidos que chegam pelo WhatsApp."} action={!status && !q ? <Button variant="secondary" onClick={() => setModal(true)}>Criar agendamento</Button> : undefined} />
      ) : (
        <>
          <Table>
            <thead>
              <tr>
                <Th>Paciente</Th><Th>Serviço</Th><Th>Data</Th><Th>Duração</Th><Th>Valor</Th><Th>Status</Th><Th className="text-right">Ações</Th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((a) => (
                <tr key={a.id} className={busy === a.id ? "opacity-60" : undefined}>
                  <Td>
                    <p className="font-medium">{a.patient?.name ?? "Sem nome"}</p>
                    <p className="text-xs text-muted">{a.patient ? formatPhone(a.patient.phone) : "—"}</p>
                  </Td>
                  <Td>{a.service}{a.source === "AI" && <span className="ml-1 text-xs text-primary">via IA</span>}</Td>
                  <Td className="whitespace-nowrap">{formatDateTime(a.date)}</Td>
                  <Td>{a.durationMin} min</Td>
                  <Td>{a.priceCents != null ? brl(a.priceCents) : "—"}</Td>
                  <Td><Badge tone={APPT_TONE[a.status]}>{APPT_LABEL[a.status]}</Badge></Td>
                  <Td className="text-right">
                    <div className="flex justify-end gap-1">
                      {NEXT[a.status].map((n) => (
                        <Button key={n.to} size="sm" variant={n.variant ?? "primary"} disabled={busy === a.id} onClick={() => transition(a.id, n.to)}>{n.label}</Button>
                      ))}
                    </div>
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
          <Pagination total={data.total} limit={LIMIT} offset={offset} onChange={setOffset} />
        </>
      )}
      <NewAppointmentModal open={modal} onClose={() => setModal(false)} onCreated={() => { setModal(false); void refetch(); }} />
    </>
  );
}

export default function AppointmentsPage() {
  return (
    <Suspense fallback={<Skeleton className="h-64" />}>
      <AppointmentsInner />
    </Suspense>
  );
}
