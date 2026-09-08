"use client";

import { useState, type FormEvent } from "react";
import { useTenant } from "@/app/app/[tenantId]/layout";
import { Badge, Button, Card, EmptyState, ErrorState, Field, Input, Select, Skeleton, Switch, Table, Td, Th } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/toast";
import { api, errorMessage } from "@/lib/api";
import { brl } from "@/lib/format";
import type { AvailabilityRule, Service } from "@/lib/types";
import { useQuery } from "@/lib/use-query";

const DAYS = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"];

type DayState = { enabled: boolean; start: string; end: string };

function toDayState(rules: AvailabilityRule[]): DayState[] {
  return DAYS.map((_, wd) => {
    const r = rules.filter((x) => x.weekday === wd).sort((a, b) => a.start.localeCompare(b.start));
    return r.length ? { enabled: true, start: r[0].start, end: r[r.length - 1].end } : { enabled: false, start: "09:00", end: "18:00" };
  });
}

export function AvailabilityCard({ canManage }: { canManage: boolean }) {
  const { tenant, reload } = useTenant();
  const toast = useToast();
  const { data, error, loading, refetch } = useQuery(
    () => api.get<{ rules: AvailabilityRule[]; slotMinutes: number }>(`clinic/${tenant.id}/availability/rules`),
    [tenant.id],
  );
  return (
    <Card title="Horários de atendimento" action={<span id="horarios" />}>
      {error ? (
        <ErrorState message={error} onRetry={refetch} />
      ) : loading || !data ? (
        <Skeleton className="h-48" />
      ) : (
        <AvailabilityForm key={JSON.stringify(data)} initial={data} canManage={canManage} onSaved={async () => { await Promise.all([refetch(), reload()]); toast.success("Horários salvos."); }} />
      )}
    </Card>
  );
}

function AvailabilityForm({ initial, canManage, onSaved }: { initial: { rules: AvailabilityRule[]; slotMinutes: number }; canManage: boolean; onSaved: () => Promise<void> }) {
  const { tenant } = useTenant();
  const toast = useToast();
  const [days, setDays] = useState<DayState[]>(() => toDayState(initial.rules));
  const [slot, setSlot] = useState(String(initial.slotMinutes));
  const [saving, setSaving] = useState(false);

  async function save() {
    setSaving(true);
    try {
      const rules = days.flatMap((d, wd) => (d.enabled ? [{ weekday: wd, start: d.start, end: d.end }] : []));
      await api.put(`clinic/${tenant.id}/availability/rules`, { rules, slotMinutes: Number(slot) });
      await onSaved();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <fieldset disabled={!canManage} className="space-y-3">
      <p className="text-sm text-muted">A IA só oferece horários dentro destas janelas e sem conflito com outros agendamentos.</p>
      <div className="space-y-2">
        {days.map((d, wd) => (
          <div key={wd} className="grid grid-cols-[1fr_auto_auto_auto] items-center gap-2 text-sm">
            <label className="flex items-center gap-3">
              <Switch checked={d.enabled} onChange={(v) => setDays(days.map((x, i) => (i === wd ? { ...x, enabled: v } : x)))} label={`Atende ${DAYS[wd]}`} disabled={!canManage} />
              <span className={d.enabled ? "" : "text-muted"}>{DAYS[wd]}</span>
            </label>
            <Input type="time" aria-label={`Início ${DAYS[wd]}`} value={d.start} disabled={!d.enabled} onChange={(e) => setDays(days.map((x, i) => (i === wd ? { ...x, start: e.target.value } : x)))} className="w-28" />
            <span className="text-muted">até</span>
            <Input type="time" aria-label={`Fim ${DAYS[wd]}`} value={d.end} disabled={!d.enabled} onChange={(e) => setDays(days.map((x, i) => (i === wd ? { ...x, end: e.target.value } : x)))} className="w-28" />
          </div>
        ))}
      </div>
      <Field label="Intervalo entre horários oferecidos" htmlFor="slot" hint="Passo usado para sugerir horários (ex.: 30 min).">
        <Select id="slot" value={slot} onChange={(e) => setSlot(e.target.value)} className="sm:w-40">
          {[15, 20, 30, 45, 60].map((m) => <option key={m} value={m}>{m} min</option>)}
        </Select>
      </Field>
      {canManage && <Button onClick={save} loading={saving}>Salvar horários</Button>}
    </fieldset>
  );
}

export function ServicesCard({ canManage }: { canManage: boolean }) {
  const { tenant } = useTenant();
  const toast = useToast();
  const { data, error, loading, refetch } = useQuery(() => api.get<{ items: Service[] }>(`clinic/${tenant.id}/services`), [tenant.id]);
  const [form, setForm] = useState({ name: "", duration: "60", price: "" });
  const [saving, setSaving] = useState(false);

  async function add(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      await api.post(`clinic/${tenant.id}/services`, {
        name: form.name,
        durationMin: Number(form.duration),
        priceCents: form.price ? Math.round(Number(form.price.replace(",", ".")) * 100) : null,
      });
      setForm({ name: "", duration: "60", price: "" });
      toast.success("Serviço adicionado.");
      await refetch();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  async function toggle(s: Service) {
    try {
      await api.patch(`clinic/${tenant.id}/services/${s.id}`, { active: !s.active });
      await refetch();
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  async function remove(s: Service) {
    try {
      await api.delete(`clinic/${tenant.id}/services/${s.id}`);
      toast.success("Serviço removido.");
      await refetch();
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  return (
    <Card title="Catálogo de serviços">
      <p className="mb-3 text-sm text-muted">Duração define o bloco na agenda; preço e nome são o que a IA informa aos pacientes.</p>
      {error ? (
        <ErrorState message={error} onRetry={refetch} />
      ) : loading || !data ? (
        <Skeleton className="h-32" />
      ) : data.items.length === 0 ? (
        <EmptyState title="Nenhum serviço cadastrado" description="Adicione os procedimentos da clínica para a IA informar valores e durações corretas." />
      ) : (
        <Table>
          <thead><tr><Th>Serviço</Th><Th>Duração</Th><Th>Valor</Th><Th>Status</Th>{canManage && <Th className="text-right">Ações</Th>}</tr></thead>
          <tbody>
            {data.items.map((s) => (
              <tr key={s.id}>
                <Td className="font-medium">{s.name}</Td>
                <Td>{s.durationMin} min</Td>
                <Td>{s.priceCents != null ? brl(s.priceCents) : "sob consulta"}</Td>
                <Td><Badge tone={s.active ? "success" : "neutral"}>{s.active ? "ativo" : "inativo"}</Badge></Td>
                {canManage && (
                  <Td className="text-right">
                    <div className="flex justify-end gap-1">
                      <Button size="sm" variant="secondary" onClick={() => toggle(s)}>{s.active ? "Desativar" : "Ativar"}</Button>
                      <Button size="sm" variant="danger" onClick={() => remove(s)}>Remover</Button>
                    </div>
                  </Td>
                )}
              </tr>
            ))}
          </tbody>
        </Table>
      )}
      {canManage && (
        <form onSubmit={add} className="mt-4 grid gap-2 sm:grid-cols-[1fr_120px_140px_auto] sm:items-end">
          <Field label="Nome" htmlFor="svc-name" required><Input id="svc-name" required minLength={2} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
          <Field label="Duração (min)" htmlFor="svc-dur" required><Input id="svc-dur" type="number" min={5} max={600} step={5} required value={form.duration} onChange={(e) => setForm({ ...form, duration: e.target.value })} /></Field>
          <Field label="Valor (R$)" htmlFor="svc-price"><Input id="svc-price" inputMode="decimal" placeholder="990,00" value={form.price} onChange={(e) => setForm({ ...form, price: e.target.value })} /></Field>
          <Button type="submit" loading={saving}>Adicionar</Button>
        </form>
      )}
    </Card>
  );
}
