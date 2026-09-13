"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { ConfirmDialog } from "@/components/ui/modal";
import { Badge, Button, Card, EmptyState, ErrorState, Field, Input, PageHeader, Skeleton, Switch, Textarea } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/toast";
import { api, errorMessage } from "@/lib/api";
import { APPT_LABEL, APPT_TONE, formatDateTime, formatPhone } from "@/lib/format";
import type { PatientDetail } from "@/lib/types";
import { useQuery } from "@/lib/use-query";
import { useTenant } from "../../layout";

export default function PatientDetailPage() {
  const { tenant } = useTenant();
  const { patientId } = useParams<{ patientId: string }>();
  const router = useRouter();
  const toast = useToast();
  const { data, error, loading, refetch } = useQuery(() => api.get<PatientDetail>(`clinic/${tenant.id}/patients/${patientId}`), [tenant.id, patientId]);
  const [confirm, setConfirm] = useState(false);
  const [deleting, setDeleting] = useState(false);

  async function remove() {
    setDeleting(true);
    try {
      await api.delete(`clinic/${tenant.id}/patients/${patientId}`);
      toast.success("Paciente removido.");
      router.replace(`/app/${tenant.id}/patients`);
    } catch (err) {
      toast.error(errorMessage(err));
      setDeleting(false);
    }
  }

  if (error) return <ErrorState message={error} onRetry={refetch} />;
  if (loading || !data) return <Skeleton className="h-96" />;

  return (
    <>
      <PageHeader
        title={data.name ?? "Paciente sem nome"}
        description={formatPhone(data.phone)}
        action={
          <>
            <Link href={`/app/${tenant.id}/patients`} className="inline-flex h-10 items-center rounded-lg border border-border px-4 text-sm">Voltar</Link>
            <Button variant="danger" onClick={() => setConfirm(true)}>Excluir</Button>
          </>
        }
      />
      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="Dados" className="lg:col-span-1">
          <PatientForm key={`${data.id}:${data.name}:${data.notes}:${data.marketingOptOut}`} patient={data} onSaved={refetch} />
        </Card>
        <Card title="Agendamentos" className="lg:col-span-2">
          {data.appointments.length === 0 ? (
            <EmptyState title="Sem agendamentos" />
          ) : (
            <ul className="divide-y divide-border text-sm">
              {data.appointments.map((a) => (
                <li key={a.id} className="flex items-center justify-between py-2">
                  <span>{a.service} · {formatDateTime(a.date)}</span>
                  <Badge tone={APPT_TONE[a.status]}>{APPT_LABEL[a.status]}</Badge>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card title="Conversa recente no WhatsApp" className="lg:col-span-3">
          {data.conversation.length === 0 ? (
            <EmptyState title="Nenhuma conversa registrada" description="As mensagens trocadas com a secretária virtual aparecem aqui." />
          ) : (
            <ol className="space-y-2">
              {data.conversation.map((m, i) => (
                <li key={i} className={`flex ${m.role === "USER" ? "justify-start" : "justify-end"}`}>
                  <div className={`max-w-[80%] rounded-xl px-3 py-2 text-sm ${m.role === "USER" ? "bg-surface-2" : "bg-primary-soft text-foreground"}`}>
                    <p className="whitespace-pre-wrap">{m.content}</p>
                    <p className="mt-1 text-[10px] text-muted">{m.role === "USER" ? "Paciente" : "Assistente"} · {formatDateTime(m.createdAt)}</p>
                  </div>
                </li>
              ))}
            </ol>
          )}
        </Card>
      </div>
      <ConfirmDialog open={confirm} onClose={() => setConfirm(false)} onConfirm={remove} loading={deleting} danger title="Excluir paciente" description="Isso remove o paciente e o histórico dele. Pacientes com agendamentos futuros precisam ter esses agendamentos cancelados antes. Esta ação não pode ser desfeita." confirmLabel="Excluir" />
    </>
  );
}

function PatientForm({ patient, onSaved }: { patient: PatientDetail; onSaved: () => Promise<void> }) {
  const { tenant } = useTenant();
  const toast = useToast();
  const [name, setName] = useState(patient.name ?? "");
  const [notes, setNotes] = useState(patient.notes ?? "");
  const [optOut, setOptOut] = useState(patient.marketingOptOut);
  const [saving, setSaving] = useState(false);

  async function save() {
    setSaving(true);
    try {
      await api.patch(`clinic/${tenant.id}/patients/${patient.id}`, { name: name || null, notes: notes || null, marketingOptOut: optOut });
      toast.success("Paciente atualizado.");
      await onSaved();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-4">
      <Field label="Nome" htmlFor="name"><Input id="name" value={name} onChange={(e) => setName(e.target.value)} /></Field>
      <Field label="Observações internas" htmlFor="notes" hint="Visível apenas para a equipe."><Textarea id="notes" value={notes} onChange={(e) => setNotes(e.target.value)} /></Field>
      <div className="flex items-center justify-between gap-3 rounded-lg border border-border px-3 py-2">
        <div>
          <p className="text-sm font-medium">Não enviar campanha de retorno</p>
          <p className="text-xs text-muted">Ligado automaticamente quando o paciente pede para não receber mensagens.</p>
        </div>
        <Switch checked={optOut} onChange={setOptOut} label="Não enviar campanha de retorno" />
      </div>
      <Button onClick={save} loading={saving}>Salvar</Button>
    </div>
  );
}
