"use client";

import { useRef, useState, type FormEvent } from "react";
import { Modal } from "@/components/ui/modal";
import { useTenant } from "@/app/app/[tenantId]/layout";
import { Alert, Badge, Button, Card, EmptyState, ErrorState, Field, Input, Select, Skeleton, Switch, Table, Td, Th } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/toast";
import { api, errorMessage } from "@/lib/api";
import { brl } from "@/lib/format";
import type { AvailabilityRule, Professional, Service } from "@/lib/types";
import { useQuery } from "@/lib/use-query";

const DAYS = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"];

type DayState = { enabled: boolean; start: string; end: string };

function toDayState(rules: AvailabilityRule[]): DayState[] {
  return DAYS.map((_, wd) => {
    const r = rules.filter((x) => x.weekday === wd).sort((a, b) => a.start.localeCompare(b.start));
    return r.length ? { enabled: true, start: r[0].start, end: r[r.length - 1].end } : { enabled: false, start: "09:00", end: "18:00" };
  });
}

/**
 * Monta as regras a salvar. Um dia com mais de uma janela (ex.: 08–12 e 14–18, criado pela API) aparece aqui
 * colapsado; se a equipe não mexeu nele, as janelas originais são preservadas em vez de virar uma só.
 */
function toRules(days: DayState[], original: AvailabilityRule[], initial: DayState[]): AvailabilityRule[] {
  return days.flatMap((d, wd) => {
    const untouched = d.enabled === initial[wd].enabled && d.start === initial[wd].start && d.end === initial[wd].end;
    const originalDay = original.filter((r) => r.weekday === wd);
    if (untouched && originalDay.length > 1) return originalDay;
    return d.enabled ? [{ weekday: wd, start: d.start, end: d.end }] : [];
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
      const rules = toRules(days, initial.rules, toDayState(initial.rules));
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
      {initial.rules.some((r, i, all) => all.findIndex((o) => o.weekday === r.weekday) !== i) && (
        <Alert tone="info">Alguns dias têm mais de uma janela (ex.: manhã e tarde). Elas aparecem resumidas aqui e são mantidas se você não alterar o dia.</Alert>
      )}
      {!days.some((d) => d.enabled) && (
        <Alert tone="warning">Nenhum dia ativo: a assistente não vai oferecer horários e o calendário fica sem áreas de atendimento. Ligue os dias em que a clínica atende.</Alert>
      )}
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

  const inFlight = useRef<Set<string>>(new Set());
  const [importing, setImporting] = useState(false);

  async function toggle(s: Service) {
    if (inFlight.current.has(s.id)) return;
    inFlight.current.add(s.id);
    try {
      await api.patch(`clinic/${tenant.id}/services/${s.id}`, { active: !s.active });
      await refetch();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      inFlight.current.delete(s.id);
    }
  }

  async function remove(s: Service) {
    if (inFlight.current.has(s.id)) return;
    inFlight.current.add(s.id);
    try {
      await api.delete(`clinic/${tenant.id}/services/${s.id}`);
      toast.success("Serviço removido.");
      await refetch();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      inFlight.current.delete(s.id);
    }
  }

  return (
    <Card title="Catálogo de serviços" action={canManage ? <Button size="sm" variant="secondary" onClick={() => setImporting(true)}>Importar de foto ou PDF</Button> : undefined}>
      <p className="mb-3 text-sm text-muted">Duração define o bloco na agenda; preço e nome são o que a IA informa. Tem uma tabela de preços pronta? Mande a foto e a gente preenche.</p>
      <ImportServicesModal open={importing} onClose={() => setImporting(false)} onImported={async () => { setImporting(false); await refetch(); }} />
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

type Draft = { name: string; priceCents: number | null; durationMin: number | null; description: string | null };

/** Foto/print/PDF da tabela de preços → prévia editável → confirmar. Nada é gravado sem o cliente ver. */
function ImportServicesModal({ open, onClose, onImported }: { open: boolean; onClose: () => void; onImported: () => Promise<void> | void }) {
  const { tenant } = useTenant();
  const toast = useToast();
  const [file, setFile] = useState<File | null>(null);
  const [items, setItems] = useState<Draft[] | null>(null);
  const [busy, setBusy] = useState<"read" | "save" | null>(null);
  const [error, setError] = useState<string | null>(null);

  function reset() {
    setFile(null);
    setItems(null);
    setError(null);
    setBusy(null);
  }

  async function read() {
    if (!file) return;
    setBusy("read");
    setError(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const r = await api.upload<{ items: Draft[] }>(`clinic/${tenant.id}/services/import/preview`, form);
      setItems(r.items);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  async function confirm() {
    if (!items?.length) return;
    setBusy("save");
    try {
      const r = await api.post<{ created: unknown[]; skipped: string[] }>(`clinic/${tenant.id}/services/import/confirm`, {
        items: items.map((i, idx) => ({ name: i.name, priceCents: i.priceCents, durationMin: i.durationMin ?? 60, description: i.description, active: true, sortOrder: idx })),
      });
      toast.success(`${r.created.length} serviço(s) importado(s)${r.skipped.length ? `; ${r.skipped.length} já existiam` : ""}.`);
      reset();
      await onImported();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  function edit(idx: number, patch: Partial<Draft>) {
    setItems((prev) => (prev ? prev.map((it, i) => (i === idx ? { ...it, ...patch } : it)) : prev));
  }

  return (
    <Modal open={open} onClose={() => { reset(); onClose(); }} title="Importar serviços" description="Mande a foto da sua tabela de preços, um print ou um PDF. A IA lê e você confere antes de salvar." size="lg">
      {items === null ? (
        <div className="space-y-4">
          <Field label="Arquivo" htmlFor="svc-import-file" hint="JPG, PNG, WebP ou PDF, até 10 MB.">
            <Input id="svc-import-file" type="file" accept="image/*,.pdf" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          </Field>
          {error && <Alert tone="danger">{error}</Alert>}
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => { reset(); onClose(); }}>Cancelar</Button>
            <Button onClick={read} disabled={!file} loading={busy === "read"}>Ler arquivo</Button>
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          <p className="text-sm text-muted">Encontrei {items.length} serviço(s). Ajuste o que precisar e confirme; os que já existem no catálogo são pulados.</p>
          <div className="max-h-80 overflow-auto">
            <Table>
              <thead><tr><Th>Serviço</Th><Th>Valor (R$)</Th><Th>Duração (min)</Th><Th /></tr></thead>
              <tbody>
                {items.map((it, idx) => (
                  <tr key={idx}>
                    <Td><Input aria-label={`Nome do serviço ${idx + 1}`} value={it.name} onChange={(e) => edit(idx, { name: e.target.value })} /></Td>
                    <Td><Input aria-label={`Valor do serviço ${idx + 1}`} inputMode="decimal" value={it.priceCents == null ? "" : (it.priceCents / 100).toFixed(2).replace(".", ",")} onChange={(e) => { const v = e.target.value.replace(/\./g, "").replace(",", "."); edit(idx, { priceCents: v ? Math.round(Number(v) * 100) : null }); }} className="w-28" /></Td>
                    <Td><Input aria-label={`Duração do serviço ${idx + 1}`} type="number" min={5} max={600} step={5} value={it.durationMin ?? 60} onChange={(e) => edit(idx, { durationMin: Number(e.target.value) || 60 })} className="w-24" /></Td>
                    <Td className="text-right"><Button size="sm" variant="ghost" onClick={() => setItems(items.filter((_, i) => i !== idx))}>Remover</Button></Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </div>
          {error && <Alert tone="danger">{error}</Alert>}
          <div className="flex justify-between gap-2">
            <Button variant="secondary" onClick={() => setItems(null)}>Voltar</Button>
            <Button onClick={confirm} disabled={!items.length} loading={busy === "save"}>Salvar {items.length} serviço(s)</Button>
          </div>
        </div>
      )}
    </Modal>
  );
}

/** Profissionais: "quero com a Paula". Com N ativos, a agenda aceita N atendimentos ao mesmo tempo. */
export function ProfessionalsCard({ canManage }: { canManage: boolean }) {
  const { tenant } = useTenant();
  const toast = useToast();
  const { data, error, loading, refetch } = useQuery(() => api.get<{ items: Professional[] }>(`clinic/${tenant.id}/professionals`), [tenant.id]);
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);

  async function add(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      await api.post(`clinic/${tenant.id}/professionals`, { name: name.trim() });
      setName("");
      toast.success("Profissional adicionado.");
      await refetch();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  async function toggle(p: Professional) {
    setBusy(p.id);
    try {
      await api.patch(`clinic/${tenant.id}/professionals/${p.id}`, { active: !p.active });
      await refetch();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  async function remove(p: Professional) {
    setBusy(p.id);
    try {
      await api.delete(`clinic/${tenant.id}/professionals/${p.id}`);
      toast.success("Profissional removido. Os agendamentos dele ficam na agenda.");
      await refetch();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card title="Profissionais">
      <p className="mb-3 text-sm text-muted">Opcional. Cadastre quem atende para a assistente aceitar “quero com a Paula” e para a agenda permitir um atendimento por profissional no mesmo horário.</p>
      {error ? (
        <ErrorState message={error} onRetry={refetch} />
      ) : loading || !data ? (
        <Skeleton className="h-16" />
      ) : data.items.length === 0 ? (
        <p className="text-sm text-muted">Nenhum profissional cadastrado: a agenda funciona como uma só.</p>
      ) : (
        <ul className="divide-y divide-border">
          {data.items.map((p) => (
            <li key={p.id} className="flex items-center justify-between gap-2 py-2 text-sm">
              <span className="flex items-center gap-2"><span className="font-medium">{p.name}</span><Badge tone={p.active ? "success" : "neutral"}>{p.active ? "ativo" : "inativo"}</Badge></span>
              {canManage && (
                <span className="flex gap-1">
                  <Button size="sm" variant="secondary" onClick={() => toggle(p)} loading={busy === p.id}>{p.active ? "Desativar" : "Ativar"}</Button>
                  <Button size="sm" variant="danger" onClick={() => remove(p)} loading={busy === p.id}>Remover</Button>
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
      {canManage && (
        <form onSubmit={add} className="mt-4 flex gap-2">
          <Input aria-label="Nome do profissional" placeholder="Nome, ex.: Paula" value={name} onChange={(e) => setName(e.target.value)} minLength={2} required />
          <Button type="submit" loading={saving}>Adicionar</Button>
        </form>
      )}
    </Card>
  );
}
