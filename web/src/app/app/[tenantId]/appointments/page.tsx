"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useState, type FormEvent } from "react";
import { Modal } from "@/components/ui/modal";
import { Badge, Button, EmptyState, ErrorState, Field, Input, PageHeader, Pagination, Select, Skeleton, Table, Td, Th } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/toast";
import { api, errorMessage } from "@/lib/api";
import { APPT_LABEL, APPT_TONE, brl, formatDateTime, formatPhone, toLocalInputValue } from "@/lib/format";
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
      <PageHeader title="Agenda" description="Pedidos feitos pela IA chegam como pendentes até a confirmação da equipe." action={<Button onClick={() => setModal(true)}>Novo agendamento</Button>} />
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
                <Th>Paciente</Th><Th>Serviço</Th><Th>Data</Th><Th>Valor</Th><Th>Status</Th><Th className="text-right">Ações</Th>
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

function NewAppointmentModal({ open, onClose, onCreated }: { open: boolean; onClose: () => void; onCreated: () => void }) {
  const { tenant } = useTenant();
  const toast = useToast();
  const [form, setForm] = useState({ phone: "", patientName: "", service: "", date: toLocalInputValue(), price: "", notes: "" });
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await api.post(`clinic/${tenant.id}/appointments`, {
        phone: form.phone,
        patientName: form.patientName || null,
        service: form.service,
        date: new Date(form.date).toISOString(),
        priceCents: form.price ? Math.round(Number(form.price.replace(",", ".")) * 100) : null,
        notes: form.notes || null,
      });
      toast.success("Agendamento criado.");
      setForm({ phone: "", patientName: "", service: "", date: toLocalInputValue(), price: "", notes: "" });
      onCreated();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="Novo agendamento" description="Criado como confirmado, por ser um registro manual da equipe.">
      <form onSubmit={onSubmit} className="space-y-4" id="new-appt">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="WhatsApp do paciente" htmlFor="phone" required>
            <Input id="phone" required inputMode="tel" placeholder="(81) 99999-8888" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
          </Field>
          <Field label="Nome do paciente" htmlFor="patientName">
            <Input id="patientName" value={form.patientName} onChange={(e) => setForm({ ...form, patientName: e.target.value })} />
          </Field>
          <Field label="Procedimento" htmlFor="service" required>
            <Input id="service" required value={form.service} onChange={(e) => setForm({ ...form, service: e.target.value })} />
          </Field>
          <Field label="Data e hora" htmlFor="date" required>
            <Input id="date" type="datetime-local" required value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} />
          </Field>
          <Field label="Valor (R$)" htmlFor="price" hint="Usado no cálculo de receita.">
            <Input id="price" inputMode="decimal" placeholder="990,00" value={form.price} onChange={(e) => setForm({ ...form, price: e.target.value })} />
          </Field>
          <Field label="Observações" htmlFor="notes">
            <Input id="notes" value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
          </Field>
        </div>
        {error && <p role="alert" className="text-sm text-danger">{error}</p>}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button type="submit" loading={loading}>Salvar</Button>
        </div>
      </form>
    </Modal>
  );
}

export default function AppointmentsPage() {
  return (
    <Suspense fallback={<Skeleton className="h-64" />}>
      <AppointmentsInner />
    </Suspense>
  );
}
