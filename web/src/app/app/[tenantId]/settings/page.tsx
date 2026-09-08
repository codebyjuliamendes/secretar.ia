"use client";

import { useEffect, useState } from "react";
import { AvailabilityCard, ServicesCard } from "@/components/scheduling-settings";
import { Alert, Badge, Button, Card, ErrorState, Field, Input, PageHeader, Skeleton, Switch, Textarea } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/toast";
import { ApiError, api, errorMessage } from "@/lib/api";
import type { TenantSettings, WhatsAppStatus } from "@/lib/types";
import { useQuery } from "@/lib/use-query";
import { useTenant } from "../layout";

export default function SettingsPage() {
  const { tenant, reload } = useTenant();
  const canManage = tenant.role !== "STAFF";
  const { data, error, loading, refetch } = useQuery(() => api.get<TenantSettings>(`clinic/${tenant.id}/settings`), [tenant.id]);

  return (
    <>
      <PageHeader title="Assistente & WhatsApp" description={canManage ? "Configure como a secretária virtual atende e conecte o número da clínica." : "Você pode visualizar as configurações; alterações são feitas por gerentes e proprietários."} />
      {error ? (
        <ErrorState message={error} onRetry={refetch} />
      ) : loading || !data ? (
        <Skeleton className="h-96" />
      ) : (
        <div className="grid gap-4 lg:grid-cols-3">
          <div className="space-y-4 lg:col-span-2">
            <AssistantForm settings={data} canManage={canManage} onSaved={async () => { await Promise.all([refetch(), reload()]); }} />
            <ServicesCard canManage={canManage} />
            <AvailabilityCard canManage={canManage} />
            <UpsellForm settings={data} canManage={canManage} onSaved={refetch} />
          </div>
          <div className="space-y-4">
            <WhatsAppCard canManage={canManage} />
            <Card title="Como a IA usa estas informações">
              <ul className="list-disc space-y-1 pl-4 text-sm text-muted">
                <li>O prompt define a personalidade e as regras da clínica.</li>
                <li>Serviços e preços são a única fonte de valores; a IA não inventa preços.</li>
                <li>Pedidos de agendamento ficam pendentes até a confirmação da equipe.</li>
                <li>Quando o paciente pede uma pessoa, a equipe é avisada na inbox.</li>
              </ul>
            </Card>
          </div>
        </div>
      )}
    </>
  );
}

function AssistantForm({ settings, canManage, onSaved }: { settings: TenantSettings; canManage: boolean; onSaved: () => Promise<void> | void }) {
  const { tenant } = useTenant();
  const toast = useToast();
  const [form, setForm] = useState({ name: settings.name, prompt: settings.prompt, prices: settings.prices ?? "", businessHours: settings.businessHours ?? "", timezone: settings.timezone });
  const [saving, setSaving] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  async function save() {
    setSaving(true);
    setFieldErrors({});
    try {
      await api.patch(`clinic/${tenant.id}/settings`, { ...form, prices: form.prices || null, businessHours: form.businessHours || null });
      toast.success("Configurações do assistente salvas.");
      await onSaved();
    } catch (err) {
      if (err instanceof ApiError && err.details?.length) setFieldErrors(Object.fromEntries(err.details.map((d) => [d.field, d.message])));
      toast.error(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card title="Assistente virtual">
      <fieldset disabled={!canManage} className="space-y-4">
        <Field label="Nome da clínica" htmlFor="name" required error={fieldErrors.name}><Input id="name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
        <Field label="Prompt (personalidade e regras)" htmlFor="prompt" required error={fieldErrors.prompt} hint="Mínimo de 10 caracteres. Ex.: tom de voz, o que pode e não pode prometer.">
          <Textarea id="prompt" rows={5} value={form.prompt} onChange={(e) => setForm({ ...form, prompt: e.target.value })} />
        </Field>
        <Field label="Informações extras para a IA" htmlFor="prices" hint="Opcional. O catálogo de serviços abaixo preenche este campo automaticamente; use para detalhes como formas de pagamento ou endereço." error={fieldErrors.prices}>
          <Textarea id="prices" rows={4} value={form.prices} onChange={(e) => setForm({ ...form, prices: e.target.value })} />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Horário de funcionamento (texto)" htmlFor="hours" error={fieldErrors.businessHours} hint="Gerado a partir dos horários de atendimento abaixo."><Input id="hours" placeholder="Seg a sex, 09h às 18h" value={form.businessHours} onChange={(e) => setForm({ ...form, businessHours: e.target.value })} /></Field>
          <Field label="Fuso horário" htmlFor="tz" error={fieldErrors.timezone} hint="Formato IANA, ex.: America/Sao_Paulo"><Input id="tz" value={form.timezone} onChange={(e) => setForm({ ...form, timezone: e.target.value })} /></Field>
        </div>
        {canManage && <Button onClick={save} loading={saving}>Salvar assistente</Button>}
      </fieldset>
    </Card>
  );
}

function UpsellForm({ settings, canManage, onSaved }: { settings: TenantSettings; canManage: boolean; onSaved: () => Promise<void> | void }) {
  const { tenant } = useTenant();
  const toast = useToast();
  const allowed = settings.planLimits.upsellCampaigns;
  const [enabled, setEnabled] = useState(settings.upsellEnabled);
  const [message, setMessage] = useState(settings.upsellMessage ?? "");
  const [days, setDays] = useState(String(settings.upsellDays));
  const [saving, setSaving] = useState(false);
  const [preview, setPreview] = useState<number | null>(null);

  async function save() {
    setSaving(true);
    try {
      await api.patch(`clinic/${tenant.id}/settings`, { upsellEnabled: enabled, upsellMessage: message || null, upsellDays: Number(days) });
      toast.success("Campanha de retorno salva.");
      await onSaved();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  async function runPreview() {
    try {
      const r = await api.post<{ messagesQueued: number }>(`clinic/${tenant.id}/marketing/upsell/preview`);
      setPreview(r.messagesQueued);
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  return (
    <Card title="Campanha de retorno (retenção)" action={<Badge tone={enabled && allowed ? "success" : "neutral"}>{enabled && allowed ? "Ativa" : "Inativa"}</Badge>}>
      {!allowed && <div className="mb-4"><Alert tone="info">Disponível a partir do plano Básico. Veja a página Plano & uso.</Alert></div>}
      <fieldset disabled={!canManage || !allowed} className="space-y-4">
        <div className="flex items-center justify-between gap-4">
          <div>
            <p className="text-sm font-medium">Enviar convite de retorno automaticamente</p>
            <p className="text-xs text-muted">Um envio por atendimento realizado, apenas para quem não tem retorno marcado.</p>
          </div>
          <Switch checked={enabled} onChange={setEnabled} label="Ativar campanha de retorno" />
        </div>
        <Field label="Dias após o procedimento" htmlFor="days" hint="Ex.: 150 dias (aprox. 5 meses) para toxina botulínica."><Input id="days" type="number" min={7} max={730} value={days} onChange={(e) => setDays(e.target.value)} className="sm:max-w-40" /></Field>
        <Field label="Mensagem" htmlFor="upsell-msg" hint="Use {nome}, {clinica} e {servico}. Deixe vazio para usar a mensagem padrão.">
          <Textarea id="upsell-msg" rows={4} value={message} onChange={(e) => setMessage(e.target.value)} />
        </Field>
        {canManage && allowed && (
          <div className="flex flex-wrap items-center gap-2">
            <Button onClick={save} loading={saving}>Salvar campanha</Button>
            <Button variant="secondary" onClick={runPreview}>Simular envio de hoje</Button>
            {preview !== null && <span className="text-sm text-muted">{preview} paciente(s) seriam contatados hoje.</span>}
          </div>
        )}
      </fieldset>
    </Card>
  );
}

function WhatsAppCard({ canManage }: { canManage: boolean }) {
  const { tenant, reload } = useTenant();
  const toast = useToast();
  const { data, error, loading, refetch, setData } = useQuery(() => api.get<WhatsAppStatus>(`clinic/${tenant.id}/whatsapp/status`), [tenant.id]);
  const [busy, setBusy] = useState(false);

  // Enquanto o QR estiver aberto, consulta o estado periodicamente.
  useEffect(() => {
    if (!data || data.connected || !data.qrCode) return;
    const t = setInterval(() => void refetch(), 5000);
    return () => clearInterval(t);
  }, [data, refetch]);

  async function act(path: "connect" | "disconnect") {
    setBusy(true);
    try {
      const r = await api.post<WhatsAppStatus>(`clinic/${tenant.id}/whatsapp/${path}`);
      setData(r);
      await reload();
      if (path === "disconnect") toast.success("WhatsApp desconectado.");
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title="WhatsApp da clínica" action={data ? <Badge tone={data.connected ? "success" : "warning"}>{data.connected ? "Conectado" : "Desconectado"}</Badge> : undefined}>
      <div id="whatsapp" className="space-y-3">
        {error ? (
          <ErrorState message={error} onRetry={refetch} />
        ) : loading || !data ? (
          <Skeleton className="h-24" />
        ) : data.connected ? (
          <>
            <p className="text-sm text-muted">Número {tenant.whatsapp} pronto para receber e responder pacientes.</p>
            {canManage && <Button variant="danger" size="sm" loading={busy} onClick={() => act("disconnect")}>Desconectar</Button>}
          </>
        ) : data.qrCode ? (
          <>
            <p className="text-sm text-muted">No celular da clínica: WhatsApp → Aparelhos conectados → Conectar aparelho. Aponte para o código:</p>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={`data:image/png;base64,${data.qrCode}`} alt="QR Code para conectar o WhatsApp" className="mx-auto h-56 w-56 rounded-lg bg-white p-2" />
            <p className="text-center text-xs text-muted">Atualizando automaticamente… estado: {data.state}</p>
            <Button variant="secondary" size="sm" onClick={() => refetch()}>Atualizar código</Button>
          </>
        ) : (
          <>
            <p className="text-sm text-muted">Conecte o número da clínica para a secretária virtual começar a atender.</p>
            {canManage ? (
              <Button loading={busy} onClick={() => act("connect")}>Gerar QR Code</Button>
            ) : (
              <p className="text-xs text-muted">Peça a um gerente ou proprietário para conectar.</p>
            )}
          </>
        )}
      </div>
    </Card>
  );
}
