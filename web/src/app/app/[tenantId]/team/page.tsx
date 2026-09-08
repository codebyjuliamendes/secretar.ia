"use client";

import { useState, type FormEvent } from "react";
import { useSession } from "@/components/session";
import { ConfirmDialog, Modal } from "@/components/ui/modal";
import { Alert, Badge, Button, ErrorState, Field, Input, PageHeader, Select, Skeleton, Table, Td, Th } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/toast";
import { api, errorMessage } from "@/lib/api";
import { ROLE_LABEL, formatDate } from "@/lib/format";
import type { Member, TenantRole } from "@/lib/types";
import { useQuery } from "@/lib/use-query";
import { useTenant } from "../layout";

const ROLES: TenantRole[] = ["STAFF", "MANAGER", "OWNER"];

export default function TeamPage() {
  const { tenant } = useTenant();
  const { me } = useSession();
  const toast = useToast();
  const canManage = tenant.role === "OWNER";
  const { data, error, loading, refetch } = useQuery(() => api.get<{ items: Member[] }>(`clinic/${tenant.id}/team`), [tenant.id]);
  const [modal, setModal] = useState(false);
  const [form, setForm] = useState({ email: "", name: "", role: "STAFF" as TenantRole });
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [removing, setRemoving] = useState<Member | null>(null);
  const [busy, setBusy] = useState(false);

  async function invite(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    setSaving(true);
    try {
      await api.post(`clinic/${tenant.id}/team`, form);
      toast.success("Convite enviado por e-mail.");
      setModal(false);
      setForm({ email: "", name: "", role: "STAFF" });
      await refetch();
    } catch (err) {
      setFormError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  async function changeRole(m: Member, role: TenantRole) {
    try {
      await api.patch(`clinic/${tenant.id}/team/${m.id}`, { role });
      toast.success("Papel atualizado.");
      await refetch();
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  async function remove() {
    if (!removing) return;
    setBusy(true);
    try {
      await api.delete(`clinic/${tenant.id}/team/${removing.id}`);
      toast.success("Membro removido.");
      setRemoving(null);
      await refetch();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader title="Equipe" description="Quem acessa o painel desta clínica e com qual papel." action={canManage ? <Button onClick={() => setModal(true)}>Convidar</Button> : undefined} />
      <div className="mb-4 grid gap-2 sm:grid-cols-3">
        {ROLES.map((r) => (
          <div key={r} className="rounded-lg border border-border bg-surface p-3 text-xs">
            <p className="font-semibold">{ROLE_LABEL[r]}</p>
            <p className="text-muted">
              {r === "OWNER" && "Tudo, incluindo equipe e plano."}
              {r === "MANAGER" && "Configura o assistente, WhatsApp e campanhas; vê equipe, auditoria e plano."}
              {r === "STAFF" && "Opera agenda, pacientes e inbox."}
            </p>
          </div>
        ))}
      </div>
      {error ? (
        <ErrorState message={error} onRetry={refetch} />
      ) : loading || !data ? (
        <Skeleton className="h-48" />
      ) : (
        <Table>
          <thead><tr><Th>Nome</Th><Th>E-mail</Th><Th>Papel</Th><Th>Desde</Th>{canManage && <Th className="text-right">Ações</Th>}</tr></thead>
          <tbody>
            {data.items.map((m) => {
              const self = m.user?.id === me.id;
              return (
                <tr key={m.id}>
                  <Td className="font-medium">{m.user?.name ?? "—"}{self && <Badge tone="neutral" className="ml-2">você</Badge>}</Td>
                  <Td>{m.user?.email ?? "—"}{m.user && !m.user.emailVerified && <span className="ml-2 text-xs text-warning">não verificado</span>}</Td>
                  <Td>
                    {canManage && !self ? (
                      <Select aria-label={`Papel de ${m.user?.name}`} value={m.role} onChange={(e) => changeRole(m, e.target.value as TenantRole)} className="w-44">
                        {ROLES.map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
                      </Select>
                    ) : (
                      ROLE_LABEL[m.role]
                    )}
                  </Td>
                  <Td>{formatDate(m.createdAt)}</Td>
                  {canManage && <Td className="text-right">{!self && <Button size="sm" variant="danger" onClick={() => setRemoving(m)}>Remover</Button>}</Td>}
                </tr>
              );
            })}
          </tbody>
        </Table>
      )}
      <Modal open={modal} onClose={() => setModal(false)} title="Convidar para a equipe" description="A pessoa recebe um e-mail para definir a senha e acessar.">
        <form onSubmit={invite} className="space-y-4">
          <Field label="Nome" htmlFor="inv-name" required><Input id="inv-name" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
          <Field label="E-mail" htmlFor="inv-email" required><Input id="inv-email" type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></Field>
          <Field label="Papel" htmlFor="inv-role" required>
            <Select id="inv-role" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as TenantRole })}>
              {ROLES.map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
            </Select>
          </Field>
          {formError && <Alert tone="danger">{formError}</Alert>}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="secondary" onClick={() => setModal(false)}>Cancelar</Button>
            <Button type="submit" loading={saving}>Enviar convite</Button>
          </div>
        </form>
      </Modal>
      <ConfirmDialog open={!!removing} onClose={() => setRemoving(null)} onConfirm={remove} loading={busy} danger title="Remover membro" description={`${removing?.user?.name ?? "Esta pessoa"} perderá o acesso à clínica imediatamente.`} confirmLabel="Remover" />
    </>
  );
}
