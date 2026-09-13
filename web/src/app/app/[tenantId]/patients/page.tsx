"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState, type FormEvent } from "react";
import { Modal } from "@/components/ui/modal";
import { Button, EmptyState, ErrorState, Field, Input, PageHeader, Pagination, Skeleton, Table, Td, Textarea, Th } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/toast";
import { api, errorMessage } from "@/lib/api";
import { formatDate, formatPhone } from "@/lib/format";
import type { Paginated, Patient } from "@/lib/types";
import { useDebounced, useQuery } from "@/lib/use-query";
import { useTenant } from "../layout";

const LIMIT = 25;

export default function PatientsPage() {
  const { tenant } = useTenant();
  const toast = useToast();
  const [search, setSearch] = useState(useSearchParams().get("search") ?? "");
  const [offset, setOffset] = useState(0);
  const [modal, setModal] = useState(false);
  const q = useDebounced(search);
  const { data, error, loading, refetch } = useQuery(
    () => api.get<Paginated<Patient>>(`clinic/${tenant.id}/patients`, { search: q, limit: LIMIT, offset }),
    [tenant.id, q, offset],
  );
  const [form, setForm] = useState({ phone: "", name: "", notes: "" });
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const base = `/app/${tenant.id}/patients`;

  async function onCreate(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    setSaving(true);
    try {
      await api.post(`clinic/${tenant.id}/patients`, { phone: form.phone, name: form.name || null, notes: form.notes || null });
      toast.success("Paciente cadastrado.");
      setModal(false);
      setForm({ phone: "", name: "", notes: "" });
      await refetch();
    } catch (err) {
      setFormError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  const person = tenant.niche?.person ?? "paciente";
  const people = (tenant.niche?.people ?? "Pacientes").toLowerCase();
  return (
    <>
      <PageHeader title={tenant.niche?.people ?? "Pacientes"} description={`Todo contato pelo WhatsApp vira um ${person} automaticamente.`} action={<Button onClick={() => setModal(true)}>Novo {person}</Button>} />
      <Input aria-label="Buscar paciente" placeholder="Buscar por nome ou telefone" value={search} onChange={(e) => { setSearch(e.target.value); setOffset(0); }} className="mb-4 sm:max-w-xs" />
      {error ? (
        <ErrorState message={error} onRetry={refetch} />
      ) : loading && !data ? (
        <Skeleton className="h-64" />
      ) : !data || data.items.length === 0 ? (
        <EmptyState title={q ? `Nenhum ${person} encontrado` : `Nenhum ${person} ainda`} description={q ? "Tente outro nome ou telefone." : `Conecte o WhatsApp para que os ${people} sejam cadastrados automaticamente, ou cadastre manualmente.`} />
      ) : (
        <>
          <Table>
            <thead>
              <tr><Th>Nome</Th><Th>WhatsApp</Th><Th>Agendamentos</Th><Th>Último atendimento</Th><Th>Desde</Th></tr>
            </thead>
            <tbody>
              {data.items.map((p) => (
                <tr key={p.id}>
                  <Td><Link href={`${base}/${p.id}`} className="font-medium text-primary hover:underline">{p.name ?? "Sem nome"}</Link></Td>
                  <Td className="whitespace-nowrap">{formatPhone(p.phone)}</Td>
                  <Td>{p.appointmentCount ?? 0}</Td>
                  <Td>{formatDate(p.lastAppointmentAt)}</Td>
                  <Td>{formatDate(p.createdAt)}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
          <Pagination total={data.total} limit={LIMIT} offset={offset} onChange={setOffset} />
        </>
      )}
      <Modal open={modal} onClose={() => setModal(false)} title="Novo paciente">
        <form onSubmit={onCreate} className="space-y-4">
          <Field label="WhatsApp" htmlFor="p-phone" required>
            <Input id="p-phone" required inputMode="tel" placeholder="(81) 99999-8888" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
          </Field>
          <Field label="Nome" htmlFor="p-name">
            <Input id="p-name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </Field>
          <Field label="Observações" htmlFor="p-notes">
            <Textarea id="p-notes" value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
          </Field>
          {formError && <p role="alert" className="text-sm text-danger">{formError}</p>}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={() => setModal(false)}>Cancelar</Button>
            <Button type="submit" loading={saving}>Salvar</Button>
          </div>
        </form>
      </Modal>
    </>
  );
}
