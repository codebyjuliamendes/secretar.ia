"use client";

import { useRef, useState, type FormEvent } from "react";
import { ConfirmDialog, Modal } from "@/components/ui/modal";
import { Alert, Badge, Button, EmptyState, ErrorState, Field, Input, PageHeader, Pagination, Select, Skeleton, Table, Td, Textarea, Th } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/toast";
import { api, errorMessage } from "@/lib/api";
import { PLAN_LABEL, STATUS_LABEL, STATUS_TONE, formatDate, formatPhone } from "@/lib/format";
import type { AdminTenant, Paginated, Plan, TenantStatus } from "@/lib/types";
import { useDebounced, useQuery } from "@/lib/use-query";

const PLANS: Plan[] = ["BASIC", "PRO", "PREMIUM", "ENTERPRISE"];
const STATUSES: TenantStatus[] = ["PENDING", "ACTIVE", "PAST_DUE", "CANCELED", "SUSPENDED"];
const LIMIT = 25;

export default function AdminTenantsPage() {
  const toast = useToast();
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0);
  const [modal, setModal] = useState(false);
  const q = useDebounced(search);
  const { data, error, loading, refetch } = useQuery(() => api.get<Paginated<AdminTenant>>("admin/tenants", { search: q, status, limit: LIMIT, offset }), [q, status, offset]);

  const updating = useRef<Set<string>>(new Set());
  const [confirmStatus, setConfirmStatus] = useState<{ tenant: AdminTenant; status: TenantStatus } | null>(null);

  async function update(t: AdminTenant, patch: Partial<Pick<AdminTenant, "plan" | "status">>) {
    if (updating.current.has(t.id)) return;
    updating.current.add(t.id);
    try {
      await api.patch(`admin/tenants/${t.id}`, patch);
      toast.success(`Clínica ${t.name} atualizada.`);
      await refetch();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      updating.current.delete(t.id);
    }
  }

  return (
    <>
      <PageHeader title="Clínicas" description="Todas as clínicas da plataforma. Alterações aqui ficam registradas na auditoria de cada clínica." action={<Button onClick={() => setModal(true)}>Nova clínica</Button>} />
      <div className="mb-4 flex flex-col gap-2 sm:flex-row">
        <Input aria-label="Buscar clínica" placeholder="Nome ou WhatsApp" value={search} onChange={(e) => { setSearch(e.target.value); setOffset(0); }} className="sm:max-w-xs" />
        <Select aria-label="Status" value={status} onChange={(e) => { setStatus(e.target.value); setOffset(0); }} className="sm:w-56">
          <option value="">Todos os status</option>
          {STATUSES.map((s) => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}
        </Select>
      </div>
      {error ? (
        <ErrorState message={error} onRetry={refetch} />
      ) : loading && !data ? (
        <Skeleton className="h-64" />
      ) : !data || data.items.length === 0 ? (
        <EmptyState title="Nenhuma clínica encontrada" />
      ) : (
        <>
          <Table>
            <thead><tr><Th>Clínica</Th><Th>Status</Th><Th>Plano</Th><Th>Pacientes</Th><Th>Agend.</Th><Th>Equipe</Th><Th>WhatsApp</Th><Th>Criada</Th></tr></thead>
            <tbody>
              {data.items.map((t) => (
                <tr key={t.id}>
                  <Td><p className="font-medium">{t.name}</p><p className="text-xs text-muted">{formatPhone(t.whatsapp)}</p></Td>
                  <Td>
                    <Select aria-label={`Status de ${t.name}`} value={t.status} onChange={(e) => { const s = e.target.value as TenantStatus; if (s === "SUSPENDED" || s === "CANCELED") setConfirmStatus({ tenant: t, status: s }); else void update(t, { status: s }); }} className="w-44">
                      {STATUSES.map((s) => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}
                    </Select>
                  </Td>
                  <Td>
                    <Select aria-label={`Plano de ${t.name}`} value={t.plan} onChange={(e) => update(t, { plan: e.target.value as Plan })} className="w-36">
                      {PLANS.map((p) => <option key={p} value={p}>{PLAN_LABEL[p]}</option>)}
                    </Select>
                  </Td>
                  <Td>{t.patientCount}</Td><Td>{t.appointmentCount}</Td><Td>{t.memberCount}</Td>
                  <Td><Badge tone={t.whatsappConnected ? "success" : "neutral"}>{t.whatsappConnected ? "conectado" : "off"}</Badge></Td>
                  <Td className="whitespace-nowrap">{formatDate(t.createdAt)}<Badge tone={STATUS_TONE[t.status]} className="sr-only">{STATUS_LABEL[t.status]}</Badge></Td>
                </tr>
              ))}
            </tbody>
          </Table>
          <Pagination total={data.total} limit={LIMIT} offset={offset} onChange={setOffset} />
        </>
      )}
      <CreateTenantModal open={modal} onClose={() => setModal(false)} onCreated={() => { setModal(false); void refetch(); }} />
    <ConfirmDialog
        open={!!confirmStatus}
        onClose={() => setConfirmStatus(null)}
        onConfirm={async () => {
          if (!confirmStatus) return;
          await update(confirmStatus.tenant, { status: confirmStatus.status });
          setConfirmStatus(null);
        }}
        danger
        title={confirmStatus?.status === "CANCELED" ? "Cancelar clínica" : "Suspender clínica"}
        description={`${confirmStatus?.tenant.name ?? "A clínica"} deixará de atender pacientes pela assistente até voltar a ficar ativa.`}
        confirmLabel="Confirmar"
      />
      </>
  );
}

function CreateTenantModal({ open, onClose, onCreated }: { open: boolean; onClose: () => void; onCreated: () => void }) {
  const toast = useToast();
  const [form, setForm] = useState({ name: "", whatsapp: "", prompt: "Você é a secretária virtual da clínica. Seja cordial, objetiva e profissional.", prices: "", businessHours: "", plan: "BASIC" as Plan, status: "ACTIVE" as TenantStatus });
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSaving(true);
    try {
      await api.post("admin/tenants", { ...form, prices: form.prices || null, businessHours: form.businessHours || null });
      toast.success("Clínica criada. Convide um responsável pela equipe da clínica.");
      onCreated();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="Nova clínica" description="Cria o tenant sem usuários. O acesso é dado convidando um OWNER pela própria clínica ou via suporte." size="lg">
      <form onSubmit={submit} className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Nome" htmlFor="t-name" required><Input id="t-name" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
          <Field label="WhatsApp" htmlFor="t-wa" required><Input id="t-wa" required value={form.whatsapp} onChange={(e) => setForm({ ...form, whatsapp: e.target.value })} /></Field>
          <Field label="Plano" htmlFor="t-plan"><Select id="t-plan" value={form.plan} onChange={(e) => setForm({ ...form, plan: e.target.value as Plan })}>{PLANS.map((p) => <option key={p} value={p}>{PLAN_LABEL[p]}</option>)}</Select></Field>
          <Field label="Status" htmlFor="t-status"><Select id="t-status" value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value as TenantStatus })}>{STATUSES.map((s) => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}</Select></Field>
        </div>
        <Field label="Prompt" htmlFor="t-prompt" required><Textarea id="t-prompt" required value={form.prompt} onChange={(e) => setForm({ ...form, prompt: e.target.value })} /></Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Serviços e preços" htmlFor="t-prices"><Textarea id="t-prices" rows={3} value={form.prices} onChange={(e) => setForm({ ...form, prices: e.target.value })} /></Field>
          <Field label="Horário de funcionamento" htmlFor="t-hours"><Input id="t-hours" value={form.businessHours} onChange={(e) => setForm({ ...form, businessHours: e.target.value })} /></Field>
        </div>
        {error && <Alert tone="danger">{error}</Alert>}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>Cancelar</Button>
          <Button type="submit" loading={saving}>Criar</Button>
        </div>
      </form>
    </Modal>
  );
}
