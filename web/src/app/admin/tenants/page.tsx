"use client";

import { useRef, useState, type FormEvent } from "react";
import { ConfirmDialog, Modal } from "@/components/ui/modal";
import { Alert, Badge, Button, EmptyState, ErrorState, Field, Input, LinkButton, PageHeader, Pagination, Select, Skeleton, Table, Td, Textarea, Th } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/toast";
import { api, errorMessage } from "@/lib/api";
import { CYCLE_LABEL, PAYMENT_LABEL, PLAN_LABEL, STATUS_LABEL, STATUS_TONE, formatDate, formatDateTime, formatPhone, limitLabel } from "@/lib/format";
import type { AdminTenant, Paginated, Plan, TenantStatus } from "@/lib/types";
import { useDebounced, useQuery } from "@/lib/use-query";

const PLANS: Plan[] = ["BASIC", "PRO", "PREMIUM", "ENTERPRISE"];
const STATUSES: TenantStatus[] = ["PENDING", "ACTIVE", "PAST_DUE", "CANCELED", "SUSPENDED"];
const NICHES: { key: string; label: string }[] = [
  { key: "clinica", label: "Clínica de saúde/estética" },
  { key: "odontologia", label: "Odontologia" },
  { key: "psicologia", label: "Psicologia/terapia" },
  { key: "fisioterapia", label: "Fisioterapia/pilates" },
  { key: "salao", label: "Salão de beleza" },
  { key: "barbearia", label: "Barbearia" },
  { key: "pet", label: "Pet shop / veterinária" },
  { key: "advocacia", label: "Escritório de advocacia" },
  { key: "contabilidade", label: "Contabilidade/consultoria" },
  { key: "academia", label: "Academia / personal" },
  { key: "outro", label: "Outro negócio" },
];
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
  const [detail, setDetail] = useState<AdminTenant | null>(null);
  const [now] = useState(() => Date.now()); // uma leitura por carga: render puro

  async function update(t: AdminTenant, patch: Partial<Pick<AdminTenant, "plan" | "status" | "niche" | "hardLimit">>) {
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
            <thead><tr><Th>Negócio</Th><Th>Status</Th><Th>Plano</Th><Th>Nicho</Th><Th>IA no mês</Th><Th>Onboarding</Th><Th>Pago até</Th><Th>Contatos</Th><Th>Agend.</Th><Th>Equipe</Th><Th>WhatsApp</Th><Th>Criada</Th></tr></thead>
            <tbody>
              {data.items.map((t) => (
                <tr key={t.id}>
                  <Td className="min-w-44"><button type="button" className="text-left font-medium text-primary hover:underline" onClick={() => setDetail(t)}>{t.name}</button><p className="text-xs text-muted">{formatPhone(t.whatsapp)}</p></Td>
                  <Td>
                    <Select aria-label={`Status de ${t.name}`} value={t.status} onChange={(e) => { const s = e.target.value as TenantStatus; if (s === "SUSPENDED" || s === "CANCELED") setConfirmStatus({ tenant: t, status: s }); else void update(t, { status: s }); }} className="min-w-40">
                      {STATUSES.map((s) => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}
                    </Select>
                  </Td>
                  <Td>
                    <Select aria-label={`Plano de ${t.name}`} value={t.plan} onChange={(e) => update(t, { plan: e.target.value as Plan })} className="min-w-32">
                      {PLANS.map((p) => <option key={p} value={p}>{PLAN_LABEL[p]}</option>)}
                    </Select>
                  </Td>
                  <Td>
                    <Select aria-label={`Nicho de ${t.name}`} value={t.niche} onChange={(e) => update(t, { niche: e.target.value })} className="min-w-48">
                      {NICHES.map((n) => <option key={n.key} value={n.key}>{n.label}</option>)}
                    </Select>
                  </Td>
                  <Td><QuotaCell t={t} onToggle={(v) => update(t, { hardLimit: v })} /></Td>
                  <Td><ChecklistBadge t={t} onOpen={() => setDetail(t)} /></Td>
                  <Td><PaidUntilBadge t={t} now={now} /></Td>
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
      <TenantDetailModal tenant={detail} onClose={() => setDetail(null)} onChanged={async () => { await refetch(); }} />
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

const CHECK_LABEL: Record<keyof AdminTenant["checklist"], string> = { plan: "Plano liberado", whatsapp: "WhatsApp conectado", services: "Serviços cadastrados", welcome: "Boas-vindas enviadas" };

function ChecklistBadge({ t, onOpen }: { t: AdminTenant; onOpen: () => void }) {
  const done = Object.values(t.checklist).filter(Boolean).length;
  const total = Object.keys(t.checklist).length;
  return (
    <button type="button" onClick={onOpen} className="text-left" aria-label={`Onboarding de ${t.name}: ${done} de ${total}`}>
      <Badge tone={done === total ? "success" : done >= 2 ? "warning" : "neutral"}>{done}/{total}</Badge>
    </button>
  );
}

function PaidUntilBadge({ t, now }: { t: AdminTenant; now: number }) {
  if (t.hasSubscription) return <Badge tone="info">cartão</Badge>;
  if (!t.paidUntil) return <span className="text-xs text-muted">—</span>;
  const days = Math.floor((new Date(t.paidUntil).getTime() - now) / 86_400_000);
  const tone = days < 0 ? "danger" : days <= 7 ? "warning" : "success";
  return <Badge tone={tone} className="whitespace-nowrap">{formatDate(t.paidUntil)}{t.paymentMethod ? ` · ${PAYMENT_LABEL[t.paymentMethod] ?? t.paymentMethod}` : ""}</Badge>;
}

/** Soma meses a uma data yyyy-mm-dd (ou a hoje, se vazia), para os atalhos "+1 mês" / "+12 meses". */
function addMonths(ymd: string, months: number): string {
  const base = ymd ? new Date(`${ymd}T12:00:00`) : new Date();
  base.setMonth(base.getMonth() + months);
  return base.toISOString().slice(0, 10);
}

type WelcomeResult = { emails: string[]; sentAt: string; whatsappLink: string | null };
type ReportResult = { period: string; emails: string[]; data: Record<string, number> };

/** Tudo que a Júlia faz com uma conta além de plano/status/nicho: checklist, boas-vindas, cobrança e relatório. */
function TenantDetailModal({ tenant, onClose, onChanged }: { tenant: AdminTenant | null; onClose: () => void; onChanged: () => Promise<void> }) {
  const toast = useToast();
  const [busy, setBusy] = useState<"welcome" | "billing" | "report" | null>(null);
  const [welcome, setWelcome] = useState<WelcomeResult | null>(null);
  const [report, setReport] = useState<ReportResult | null>(null);
  const [method, setMethod] = useState("");
  const [paidUntil, setPaidUntil] = useState("");
  const [note, setNote] = useState("");
  const [cycle, setCycle] = useState("MONTHLY");
  const [key, setKey] = useState<string | null>(null);

  // Reidrata o formulário quando a conta aberta muda.
  if (tenant && key !== tenant.id) {
    setKey(tenant.id);
    setMethod(tenant.paymentMethod || "PIX");
    setPaidUntil(tenant.paidUntil ? tenant.paidUntil.slice(0, 10) : "");
    setNote(tenant.billingNote ?? "");
    setCycle(tenant.billingCycle || "MONTHLY");
    setWelcome(null);
    setReport(null);
  }
  if (!tenant) return null;

  async function sendWelcome() {
    if (!tenant) return;
    setBusy("welcome");
    try {
      const r = await api.post<WelcomeResult>(`admin/tenants/${tenant.id}/welcome`);
      setWelcome(r);
      toast.success(r.emails.length ? `Boas-vindas enviadas para ${r.emails.join(", ")}.` : "Conta sem responsável com e-mail; use o link do WhatsApp.");
      await onChanged();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  async function saveBilling() {
    if (!tenant) return;
    setBusy("billing");
    try {
      await api.patch(`admin/tenants/${tenant.id}`, {
        paymentMethod: method,
        paidUntil: paidUntil ? new Date(`${paidUntil}T23:59:59`).toISOString() : null,
        billingNote: note || null,
        billingCycle: cycle,
      });
      toast.success("Cobrança registrada.");
      await onChanged();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  async function sendReport() {
    if (!tenant) return;
    setBusy("report");
    try {
      const r = await api.post<ReportResult>(`admin/tenants/${tenant.id}/report`);
      setReport(r);
      toast.success(r.emails.length ? `Relatório de ${r.period} enviado.` : "Relatório gerado, mas a conta não tem responsável com e-mail.");
      await onChanged();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  return (
    <Modal open onClose={onClose} title={tenant.name} description={`${formatPhone(tenant.whatsapp)} · ${PLAN_LABEL[tenant.plan]} · ${STATUS_LABEL[tenant.status]}`} size="lg">
      <div className="space-y-6">
        <section>
          <h3 className="text-sm font-semibold">Onboarding</h3>
          <ul className="mt-2 grid gap-2 sm:grid-cols-2">
            {(Object.keys(tenant.checklist) as (keyof AdminTenant["checklist"])[]).map((k) => (
              <li key={k} className="flex items-center gap-2 text-sm"><Badge tone={tenant.checklist[k] ? "success" : "neutral"}>{tenant.checklist[k] ? "ok" : "falta"}</Badge>{CHECK_LABEL[k]}</li>
            ))}
          </ul>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <Button size="sm" onClick={sendWelcome} loading={busy === "welcome"}>{tenant.welcomeSentAt ? "Reenviar boas-vindas" : "Enviar boas-vindas por e-mail"}</Button>
            {welcome?.whatsappLink && <LinkButton href={welcome.whatsappLink} external size="sm" variant="secondary">Mandar o mesmo texto no WhatsApp</LinkButton>}
            {tenant.welcomeSentAt && <span className="text-xs text-muted">enviadas em {formatDateTime(tenant.welcomeSentAt)}</span>}
          </div>
        </section>

        <section>
          <h3 className="text-sm font-semibold">Cobrança</h3>
          {tenant.hasSubscription ? (
            <p className="mt-1 text-sm text-muted">Esta conta paga por cartão no Stripe; o status acompanha o gateway.</p>
          ) : (
            <>
              <p className="mt-1 text-xs text-muted">Pix, boleto ou transferência: registre até quando está pago. Data futura reativa uma conta pendente; vencida há mais de 3 dias, a rotina diária pausa a assistente.</p>
              <div className="mt-2 grid gap-3 sm:grid-cols-[120px_140px_180px_1fr]">
                <Field label="Ciclo" htmlFor="pay-cycle"><Select id="pay-cycle" value={cycle} onChange={(e) => setCycle(e.target.value)}>{Object.entries(CYCLE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select></Field>
                <Field label="Forma" htmlFor="pay-method"><Select id="pay-method" value={method} onChange={(e) => setMethod(e.target.value)}>{["PIX", "BOLETO", "OUTRO"].map((m) => <option key={m} value={m}>{PAYMENT_LABEL[m]}</option>)}</Select></Field>
                <Field label="Pago até" htmlFor="pay-until"><Input id="pay-until" type="date" value={paidUntil} onChange={(e) => setPaidUntil(e.target.value)} /></Field>
                <Field label="Observação" htmlFor="pay-note"><Input id="pay-note" placeholder="ex.: Pix de 750 em 10/09" value={note} onChange={(e) => setNote(e.target.value)} /></Field>
              </div>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <Button size="sm" onClick={saveBilling} loading={busy === "billing"}>Registrar pagamento</Button>
                <Button size="sm" variant="ghost" onClick={() => setPaidUntil(addMonths(paidUntil, 1))}>+1 mês</Button>
                <Button size="sm" variant="ghost" onClick={() => setPaidUntil(addMonths(paidUntil, 12))}>+12 meses</Button>
                <span className="text-xs text-muted">Anual = 11 mensalidades ({PLAN_LABEL[tenant.plan]}).</span>
              </div>
            </>
          )}
        </section>

        <section>
          <h3 className="text-sm font-semibold">Relatório mensal</h3>
          <p className="mt-1 text-xs text-muted">Vai sozinho todo início de mês para os responsáveis{tenant.lastReportPeriod ? ` (último: ${tenant.lastReportPeriod})` : ""}. Aqui você reenvia o do mês passado.</p>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <Button size="sm" variant="secondary" onClick={sendReport} loading={busy === "report"}>Enviar relatório do mês passado</Button>
            {report && <span className="text-xs text-muted">{report.data.answered} mensagens · {report.data.appointments} agendamentos · {report.data.new_people} novos contatos</span>}
          </div>
        </section>
      </div>
    </Modal>
  );
}

/** Uso de IA no mês com cor por faixa e o interruptor "cortar ao estourar" (padrão: avisa e segue). */
function QuotaCell({ t, onToggle }: { t: AdminTenant; onToggle: (v: boolean) => void }) {
  const unlimited = t.aiMessagesLimit < 0;
  const pct = unlimited ? 0 : Math.round((t.aiMessagesThisMonth / Math.max(1, t.aiMessagesLimit)) * 100);
  const tone = unlimited ? "neutral" : pct >= 100 ? "danger" : pct >= 80 ? "warning" : "success";
  return (
    <div className="space-y-1">
      <Badge tone={tone} className="whitespace-nowrap">{t.aiMessagesThisMonth.toLocaleString("pt-BR")} / {limitLabel(t.aiMessagesLimit)}{!unlimited && ` · ${pct}%`}</Badge>
      {!unlimited && (
        <label className="flex items-center gap-1 whitespace-nowrap text-xs text-muted">
          <input type="checkbox" checked={t.hardLimit} onChange={(e) => onToggle(e.target.checked)} aria-label={`Cortar ao estourar: ${t.name}`} />
          cortar ao estourar
        </label>
      )}
    </div>
  );
}

function CreateTenantModal({ open, onClose, onCreated }: { open: boolean; onClose: () => void; onCreated: () => void }) {
  const toast = useToast();
  const [form, setForm] = useState({ name: "", whatsapp: "", prompt: "", prices: "", businessHours: "", plan: "BASIC" as Plan, status: "ACTIVE" as TenantStatus, niche: "clinica" });
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
          <Field label="Nicho" htmlFor="t-niche"><Select id="t-niche" value={form.niche} onChange={(e) => setForm({ ...form, niche: e.target.value })}>{NICHES.map((n) => <option key={n.key} value={n.key}>{n.label}</option>)}</Select></Field>
          <Field label="Plano" htmlFor="t-plan"><Select id="t-plan" value={form.plan} onChange={(e) => setForm({ ...form, plan: e.target.value as Plan })}>{PLANS.map((p) => <option key={p} value={p}>{PLAN_LABEL[p]}</option>)}</Select></Field>
          <Field label="Status" htmlFor="t-status"><Select id="t-status" value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value as TenantStatus })}>{STATUSES.map((s) => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}</Select></Field>
        </div>
        <Field label="Instruções extras (opcional)" htmlFor="t-prompt" hint="A assistente já vem pronta pelo nicho e pelo tom; use só para algo específico deste negócio."><Textarea id="t-prompt" value={form.prompt} onChange={(e) => setForm({ ...form, prompt: e.target.value })} /></Field>
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
