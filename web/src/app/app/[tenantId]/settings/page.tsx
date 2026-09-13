"use client";

import { useEffect, useRef, useState } from "react";
import { AvailabilityCard, ProfessionalsCard, ServicesCard } from "@/components/scheduling-settings";
import { Alert, Badge, Button, Card, EmptyState, ErrorState, Field, Input, PageHeader, Skeleton, Switch, Textarea } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/toast";
import { ApiError, api, errorMessage } from "@/lib/api";
import { TONE_LABEL } from "@/lib/format";
import type { FeatureAccess, GoogleCalendarStatus, KnowledgeDocument, KnowledgeSource, TenantSettings, Tone, UnansweredQuestion, WhatsAppStatus } from "@/lib/types";
import { useQuery } from "@/lib/use-query";
import { useTenant } from "../layout";

export default function SettingsPage() {
  const { tenant, reload } = useTenant();
  const canManage = tenant.role !== "STAFF";
  const { data, error, refetch } = useQuery(() => api.get<TenantSettings>(`clinic/${tenant.id}/settings`), [tenant.id]);

  return (
    <>
      <PageHeader title="Assistente & WhatsApp" description={canManage ? "Configure como a secretária virtual atende e conecte o número da clínica." : "Você pode visualizar as configurações; alterações são feitas por gerentes e proprietários."} />
      {error ? (
        <ErrorState message={error} onRetry={refetch} />
      ) : !data ? (
        <Skeleton className="h-96" />
      ) : (
        <div className="grid gap-4 lg:grid-cols-3">
          <div className="space-y-4 lg:col-span-2">
            <AssistantForm settings={data} canManage={canManage} onSaved={async () => { await Promise.all([refetch(), reload()]); }} />
            <ServicesCard canManage={canManage} />
            <ProfessionalsCard canManage={canManage} />
            <AvailabilityCard canManage={canManage} />
            <KnowledgeCard canManage={canManage} access={data.featureAccess} />
            <UpsellForm settings={data} canManage={canManage} onSaved={refetch} />
            <EngagementCard settings={data} canManage={canManage} onSaved={refetch} />
            <QuestionsCard canManage={canManage} />
          </div>
          <div className="space-y-4">
            <WhatsAppCard canManage={canManage} />
            <GoogleCalendarCard canManage={canManage} />
            <Card title="Como a IA usa estas informações">
              <ul className="list-disc space-y-1 pl-4 text-sm text-muted">
                <li>O tom define a personalidade; as regras já vêm prontas e a IA nunca inventa preços nem horários.</li>
                <li>Serviços e preços são a única fonte de valores; a IA não inventa preços.</li>
                <li>A base de conhecimento responde dúvidas sobre preparo, políticas e pagamento; fora dela, a IA encaminha à equipe.</li>
                <li>Pedidos de agendamento ficam pendentes até a confirmação da equipe.</li>
                <li>Quando o paciente pede uma pessoa, a equipe é avisada na inbox.</li>
                <li>Com o Google Calendar conectado, cada agendamento vira um evento na agenda da clínica, e compromissos criados direto no Google bloqueiam horários para a IA.</li>
              </ul>
            </Card>
          </div>
        </div>
      )}
    </>
  );
}

/** Interruptor com rótulo visível: o Switch sozinho só tem aria-label. */
function SwitchRow({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <p className="text-sm font-medium">{label}</p>
      <Switch checked={checked} onChange={onChange} label={label} />
    </div>
  );
}

function AssistantForm({ settings, canManage, onSaved }: { settings: TenantSettings; canManage: boolean; onSaved: () => Promise<void> | void }) {
  const { tenant } = useTenant();
  const toast = useToast();
  const [form, setForm] = useState({ name: settings.name, tone: settings.tone, prompt: settings.prompt, prices: settings.prices ?? "", businessHours: settings.businessHours ?? "", timezone: settings.timezone, introEnabled: settings.introEnabled });
  const [showExtra, setShowExtra] = useState(Boolean(settings.prompt));
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
        <Alert tone="info">A assistente já vem pronta: cumprimenta, informa serviços e horários, oferece agendamento e chama a equipe quando precisa. Você só escolhe o tom.</Alert>
        <fieldset>
          <legend className="mb-2 text-sm font-medium">Tom da assistente</legend>
          <div className="grid gap-2 sm:grid-cols-3">
            {(Object.keys(TONE_LABEL) as Tone[]).map((t) => (
              <label key={t} className={`flex cursor-pointer flex-col rounded-lg border p-3 text-sm ${form.tone === t ? "border-primary bg-primary-soft" : "border-border"}`}>
                <span className="flex items-center gap-2 font-medium"><input type="radio" name="tone" value={t} checked={form.tone === t} onChange={() => setForm({ ...form, tone: t })} />{TONE_LABEL[t].label}</span>
                <span className="mt-1 text-xs text-muted">{TONE_LABEL[t].hint}</span>
              </label>
            ))}
          </div>
        </fieldset>
        <div className="rounded-lg border border-border p-3">
          <SwitchRow label="Apresentar-se como assistente no primeiro contato" checked={form.introEnabled} onChange={(v) => setForm({ ...form, introEnabled: v })} />
          <p className="mt-2 text-xs text-muted">Na primeira mensagem de cada pessoa, antes da resposta: “{settings.introPreview}”</p>
        </div>
        {showExtra ? (
          <Field label="Instruções extras (opcional)" htmlFor="prompt" error={fieldErrors.prompt} hint="Só se quiser algo além do padrão. Ex.: “não prometa desconto”, “convênios: Unimed e Bradesco”.">
            <Textarea id="prompt" rows={3} value={form.prompt} onChange={(e) => setForm({ ...form, prompt: e.target.value })} />
          </Field>
        ) : (
          <button type="button" className="text-sm text-primary hover:underline" onClick={() => setShowExtra(true)}>Adicionar instruções extras (opcional)</button>
        )}
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
        <Field label="Dias após o atendimento" htmlFor="days" hint="Sugerido pelo seu ramo; ajuste se quiser."><Input id="days" type="number" min={7} max={730} value={days} onChange={(e) => setDays(e.target.value)} className="sm:max-w-40" /></Field>
        <Field label="Mensagem" htmlFor="upsell-msg" hint="Já vem pronta para o seu ramo. Se quiser a sua, use {nome}, {negocio} e {servico}.">
          <Textarea id="upsell-msg" rows={4} value={message} placeholder={settings.upsellDefaultMessage} onChange={(e) => setMessage(e.target.value)} />
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
  const { data, error, refetch, setData } = useQuery(() => api.get<WhatsAppStatus>(`clinic/${tenant.id}/whatsapp/status`), [tenant.id]);
  const [busy, setBusy] = useState(false);

  // Enquanto o QR estiver aberto, consulta o estado a cada 5 s por até 5 minutos (o código expira).
  const [, setPolls] = useState(0);
  const [pollExpired, setPollExpired] = useState(false);
  const wasConnected = useRef<boolean | null>(null);
  useEffect(() => {
    if (!data) return;
    // Conectou durante o polling: o shell (badge "WhatsApp conectado") precisa saber.
    if (wasConnected.current === false && data.connected) void reload();
    wasConnected.current = data.connected;
  }, [data, reload]);
  useEffect(() => {
    if (!data || data.connected || !data.qrCode || pollExpired) return;
    const t = setInterval(() => {
      setPolls((n) => {
        if (n + 1 >= 60) {
          setPollExpired(true);
          return n;
        }
        void refetch();
        return n + 1;
      });
    }, 5000);
    return () => clearInterval(t);
  }, [data, refetch, pollExpired]);

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
        ) : !data ? (
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
            <p className="text-center text-xs text-muted">{pollExpired ? "O código pode ter expirado." : `Atualizando automaticamente… estado: ${data.state}`}</p>
            <Button variant="secondary" size="sm" onClick={() => { setPolls(0); setPollExpired(false); void refetch(); }}>{pollExpired ? "Gerar novo código" : "Atualizar código"}</Button>
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

function GoogleCalendarCard({ canManage }: { canManage: boolean }) {
  const { tenant } = useTenant();
  const toast = useToast();
  const { data, error, refetch, setData } = useQuery(() => api.get<GoogleCalendarStatus>(`clinic/${tenant.id}/integrations/google`), [tenant.id]);
  const [busy, setBusy] = useState<string | null>(null);

  // Retorno do OAuth: ?google=pending&code=…&state=… (concluímos aqui, autenticados) | ?google=error&reason=…
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const result = params.get("google");
    if (!result) return;
    window.history.replaceState(null, "", window.location.pathname);
    if (result === "pending") {
      void (async () => {
        try {
          const r = await api.post<GoogleCalendarStatus>(`clinic/${tenant.id}/integrations/google/complete`, { code: params.get("code"), state: params.get("state") });
          setData(r);
          toast.success("Google Calendar conectado. Os agendamentos futuros serão sincronizados.");
        } catch (err) {
          toast.error(`Não foi possível conectar o Google Calendar. ${errorMessage(err)}`);
        }
      })();
      return;
    }
    toast.error(`Não foi possível conectar o Google Calendar (${params.get("reason") ?? "erro"}).`);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function connect() {
    setBusy("connect");
    try {
      const r = await api.post<{ url: string }>(`clinic/${tenant.id}/integrations/google/connect`);
      window.location.assign(r.url);
    } catch (err) {
      toast.error(errorMessage(err));
      setBusy(null);
    }
  }

  async function disconnect() {
    setBusy("disconnect");
    try {
      const r = await api.post<GoogleCalendarStatus>(`clinic/${tenant.id}/integrations/google/disconnect`);
      setData({ ...r, available: data?.available ?? true });
      toast.success("Google Calendar desconectado.");
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  async function resync() {
    setBusy("sync");
    try {
      const r = await api.post<{ queued: number }>(`clinic/${tenant.id}/integrations/google/sync`);
      toast.success(`${r.queued} agendamento(s) enviados para sincronização.`);
      await refetch();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  const tone = !data ? undefined : data.connected && data.syncEnabled ? "success" : data.connected ? "warning" : "neutral";
  const label = !data ? "" : data.connected && data.syncEnabled ? "Conectado" : data.connected ? "Atenção" : "Não conectado";

  return (
    <Card title="Google Calendar" action={data ? <Badge tone={tone}>{label}</Badge> : undefined}>
      <div className="space-y-3">
        {error ? (
          <ErrorState message={error} onRetry={refetch} />
        ) : !data ? (
          <Skeleton className="h-24" />
        ) : !data.available ? (
          <p className="text-sm text-muted">Integração não configurada neste ambiente. Fale com o suporte.</p>
        ) : data.connected ? (
          <>
            <p className="text-sm text-muted">Agenda <span className="font-medium text-foreground">{data.accountEmail ?? "Google"}</span>. Agendamentos criados, remarcados, confirmados ou cancelados são refletidos automaticamente. No sentido inverso, compromissos criados direto no Google bloqueiam horários da assistente ({data.pushActive ? "notificação em tempo real, com leitura de segurança a cada 10 minutos" : "leitura a cada 10 minutos"}).</p>
            <p className="text-xs text-muted">
              {data.externalEvents} compromisso(s) do Google bloqueando horários
              {data.lastPullAt ? ` · última leitura ${new Date(data.lastPullAt).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}` : " · primeira leitura em andamento"}
            </p>
            {data.lastError && <Alert tone="warning">{data.syncEnabled ? data.lastError : `Sincronização pausada: ${data.lastError}. Reconecte para retomar.`}</Alert>}
            {data.lastSyncAt && <p className="text-xs text-muted">Última sincronização: {new Date(data.lastSyncAt).toLocaleString("pt-BR")}</p>}
            {canManage && (
              <div className="flex flex-wrap gap-2">
                {data.syncEnabled ? (
                  <Button variant="secondary" size="sm" loading={busy === "sync"} onClick={resync}>Sincronizar agora</Button>
                ) : (
                  <Button size="sm" loading={busy === "connect"} onClick={connect}>Reconectar</Button>
                )}
                <Button variant="danger" size="sm" loading={busy === "disconnect"} onClick={disconnect}>Desconectar</Button>
              </div>
            )}
          </>
        ) : (
          <>
            <p className="text-sm text-muted">Conecte a agenda Google da clínica para ver os agendamentos da Secretar.ia no calendário que a equipe já usa.</p>
            {canManage ? (
              <Button loading={busy === "connect"} onClick={connect}>Conectar Google Calendar</Button>
            ) : (
              <p className="text-xs text-muted">Peça a um gerente ou proprietário para conectar.</p>
            )}
          </>
        )}
      </div>
    </Card>
  );
}

const SOURCE_LABEL: Record<KnowledgeSource, string> = { text: "Texto", pdf: "PDF", url: "Página", file: "Arquivo" };

function KnowledgeCard({ canManage, access }: { canManage: boolean; access: FeatureAccess }) {
  const { tenant } = useTenant();
  const locked = !access.knowledge;
  const docLimit = access.maxKnowledgeDocuments;
  const toast = useToast();
  const { data, error, refetch } = useQuery(() => api.get<{ items: KnowledgeDocument[] }>(`clinic/${tenant.id}/knowledge`), [tenant.id]);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<{ title: string; content: string }[] | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [fileTitle, setFileTitle] = useState("");
  const [url, setUrl] = useState("");
  const [importing, setImporting] = useState<"file" | "url" | null>(null);

  async function importFile() {
    if (!file) return;
    setImporting("file");
    try {
      const form = new FormData();
      form.append("file", file);
      if (fileTitle.trim()) form.append("title", fileTitle.trim());
      const r = await api.upload<{ items: KnowledgeDocument[]; ocrPages: number }>(`clinic/${tenant.id}/knowledge/upload`, form);
      setFile(null);
      setFileTitle("");
      const parts = r.items.length > 1 ? ` em ${r.items.length} partes` : "";
      const ocr = r.ocrPages > 0 ? ` (${r.ocrPages} página(s) digitalizada(s) lida(s) por IA)` : "";
      toast.success(`Arquivo importado${parts}${ocr}.`);
      await refetch();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setImporting(null);
    }
  }

  async function importUrl() {
    setImporting("url");
    try {
      const r = await api.post<{ items: KnowledgeDocument[] }>(`clinic/${tenant.id}/knowledge/import-url`, { url: url.trim() });
      setUrl("");
      toast.success(r.items.length > 1 ? `Página importada em ${r.items.length} partes.` : "Página importada para a base de conhecimento.");
      await refetch();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setImporting(null);
    }
  }

  async function add() {
    setSaving(true);
    try {
      await api.post(`clinic/${tenant.id}/knowledge`, { title, content });
      setTitle("");
      setContent("");
      toast.success("Documento adicionado à base de conhecimento.");
      await refetch();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  async function remove(id: string) {
    setDeleting(id);
    try {
      await api.delete(`clinic/${tenant.id}/knowledge/${id}`);
      await refetch();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setDeleting(null);
    }
  }

  async function search() {
    try {
      const r = await api.post<{ items: { title: string; content: string }[] }>(`clinic/${tenant.id}/knowledge/search`, undefined, { q: query });
      setResults(r.items);
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  return (
    <Card title="Base de conhecimento" action={data ? <Badge tone={locked ? "warning" : data.items.length ? "success" : "neutral"}>{locked ? "não incluída no plano" : `${data.items.length}${docLimit >= 0 ? ` / ${docLimit}` : ""} documento(s)`}</Badge> : undefined}>
      <div className="space-y-4">
        <p className="text-sm text-muted">Cole aqui textos que a assistente pode usar para responder dúvidas: preparo para procedimentos, políticas de cancelamento, formas de pagamento, endereço e estacionamento, perguntas frequentes. Ela cita apenas o que estiver aqui.</p>
        {locked && (
          <Alert tone="warning" title="Recurso não incluído no seu plano">
            A assistente não consulta a base de conhecimento no plano atual{data && data.items.length > 0 ? "; os documentos ficam guardados e voltam a valer ao fazer upgrade" : ""}. Veja os planos em Plano &amp; uso.
          </Alert>
        )}
        {error ? (
          <ErrorState message={error} onRetry={refetch} />
        ) : !data ? (
          <Skeleton className="h-24" />
        ) : data.items.length === 0 ? (
          <EmptyState title="Nenhum documento ainda" description="Comece com as perguntas que a recepção mais recebe." />
        ) : (
          <ul className="divide-y divide-border rounded-lg border border-border">
            {data.items.map((d) => (
              <li key={d.id} className="flex items-center justify-between gap-3 px-4 py-2.5 text-sm">
                <div className="min-w-0">
                  <p className="flex items-center gap-2 truncate font-medium">
                    <span className="truncate">{d.title}</span>
                    {d.source !== "text" && <Badge tone="neutral">{SOURCE_LABEL[d.source]}</Badge>}
                  </p>
                  <p className="truncate text-xs text-muted" title={d.sourceRef ?? undefined}>{d.chars.toLocaleString("pt-BR")} caracteres · {d.chunkCount} trecho(s) · {d.embedded ? "busca semântica" : "busca por palavras"}{d.sourceRef ? ` · ${d.sourceRef}` : ""}</p>
                </div>
                {canManage && <Button variant="ghost" size="sm" loading={deleting === d.id} onClick={() => remove(d.id)}>Remover</Button>}
              </li>
            ))}
          </ul>
        )}
        {canManage && !locked && (
          <fieldset className="space-y-3 rounded-lg border border-dashed border-border p-4">
            <Field label="Título" htmlFor="kb-title" required><Input id="kb-title" placeholder="Ex.: Preparo para peeling" value={title} onChange={(e) => setTitle(e.target.value)} /></Field>
            <Field label="Conteúdo" htmlFor="kb-content" required hint="Texto livre, até 30 mil caracteres. Separe assuntos em parágrafos.">
              <Textarea id="kb-content" rows={5} value={content} onChange={(e) => setContent(e.target.value)} />
            </Field>
            <Button onClick={add} loading={saving} disabled={title.trim().length < 2 || content.trim().length < 20}>Adicionar documento</Button>
          </fieldset>
        )}
        {canManage && !locked && (
          <div className="grid gap-3 md:grid-cols-2">
            <fieldset className="space-y-3 rounded-lg border border-dashed border-border p-4">
              <p className="text-sm font-medium">Importar PDF ou arquivo de texto</p>
              <input
                type="file"
                accept="application/pdf,.pdf,.txt,.md,text/plain,text/markdown"
                aria-label="Arquivo PDF ou texto para importar"
                className="block w-full text-sm text-muted file:mr-3 file:rounded-md file:border file:border-border file:bg-surface file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-foreground"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
              <Input aria-label="Título do documento importado" placeholder="Título (opcional; usa o nome do arquivo)" value={fileTitle} onChange={(e) => setFileTitle(e.target.value)} />
              <p className="text-xs text-muted">Até 10 MB. PDFs digitalizados são lidos pela IA (até 20 páginas). Textos longos são divididos em partes.</p>
              <Button variant="secondary" onClick={importFile} loading={importing === "file"} disabled={!file}>Importar arquivo</Button>
            </fieldset>
            <fieldset className="space-y-3 rounded-lg border border-dashed border-border p-4">
              <p className="text-sm font-medium">Importar de uma página pública</p>
              <Input aria-label="Endereço da página pública" placeholder="https://suaclinica.com.br/perguntas-frequentes" value={url} onChange={(e) => setUrl(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && url.trim().length >= 8) void importUrl(); }} />
              <p className="text-xs text-muted">Página HTML, PDF ou texto acessível sem login. O título vem da página; você pode editar depois removendo e recriando.</p>
              <Button variant="secondary" onClick={importUrl} loading={importing === "url"} disabled={url.trim().length < 8}>Importar página</Button>
            </fieldset>
          </div>
        )}
        {data && data.items.length > 0 && !locked && (
          <div className="space-y-2">
            <Field label="Testar: o que a assistente encontraria para..." htmlFor="kb-q">
              <div className="flex gap-2">
                <Input id="kb-q" placeholder="Ex.: aceitam cartão?" value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && query.trim().length >= 2) void search(); }} />
                <Button variant="secondary" onClick={search} disabled={query.trim().length < 2}>Buscar</Button>
              </div>
            </Field>
            {results && (results.length === 0 ? <p className="text-sm text-muted">Nenhum trecho relevante; a assistente encaminharia à equipe.</p> : (
              <ul className="space-y-2">
                {results.map((r, i) => (
                  <li key={i} className="rounded-lg bg-surface-2 p-3 text-sm"><p className="text-xs font-medium text-muted">{r.title}</p><p className="mt-1 whitespace-pre-wrap">{r.content}</p></li>
                ))}
              </ul>
            ))}
          </div>
        )}
      </div>
    </Card>
  );
}

/** Lembrete de véspera, sinal por Pix, link público de agendamento e voz: tudo por regra, nada de prompt. */
function EngagementCard({ settings, canManage, onSaved }: { settings: TenantSettings; canManage: boolean; onSaved: () => Promise<void> | void }) {
  const { tenant } = useTenant();
  const toast = useToast();
  const [form, setForm] = useState({
    reminderEnabled: settings.reminderEnabled,
    depositEnabled: settings.depositEnabled,
    depositValue: settings.depositCents != null ? (settings.depositCents / 100).toFixed(2).replace(".", ",") : "",
    pixKey: settings.pixKey ?? "",
    publicBooking: settings.publicBooking,
    slug: settings.slug ?? "",
    voiceReplies: settings.voiceReplies,
  });
  const [saving, setSaving] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const bookingUrl = settings.bookingUrl?.replace(settings.slug ?? "", form.slug || settings.slug || "");

  async function save() {
    setSaving(true);
    setFieldErrors({});
    try {
      const cents = form.depositValue ? Math.round(Number(form.depositValue.replace(/\./g, "").replace(",", ".")) * 100) : null;
      await api.patch(`clinic/${tenant.id}/settings`, {
        reminderEnabled: form.reminderEnabled,
        depositEnabled: form.depositEnabled,
        depositCents: cents,
        pixKey: form.pixKey || null,
        publicBooking: form.publicBooking,
        slug: form.slug || null,
        voiceReplies: form.voiceReplies,
      });
      toast.success("Preferências salvas.");
      await onSaved();
    } catch (err) {
      if (err instanceof ApiError && err.details?.length) setFieldErrors(Object.fromEntries(err.details.map((d) => [d.field, d.message])));
      toast.error(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  async function copyLink() {
    if (!bookingUrl) return;
    try {
      await navigator.clipboard.writeText(bookingUrl);
      toast.success("Link copiado.");
    } catch {
      toast.info(bookingUrl);
    }
  }

  return (
    <Card title="Confirmação, sinal e agendamento online">
      <fieldset disabled={!canManage} className="space-y-5">
        <div className="rounded-lg border border-border p-3">
          <SwitchRow label="Lembrete de véspera com confirmação por resposta" checked={form.reminderEnabled} onChange={(v) => setForm({ ...form, reminderEnabled: v })} />
          <p className="mt-2 text-xs text-muted">Na véspera: “{tenant.name}: {`{serviço}`} amanhã às {`{hora}`}. Responda SIM para confirmar ou NÃO para cancelar.” Quem responde NÃO libera o horário, e quem estava na lista de espera daquele dia é avisado na hora.</p>
        </div>
        <div className="rounded-lg border border-border p-3">
          <SwitchRow label="Pedir sinal por Pix para reservar o horário" checked={form.depositEnabled} onChange={(v) => setForm({ ...form, depositEnabled: v })} />
          <p className="mt-2 text-xs text-muted">A assistente informa o valor e a chave ao registrar o pedido; o horário só é confirmado pela equipe depois do comprovante.</p>
          {form.depositEnabled && (
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              <Field label="Valor do sinal (R$)" htmlFor="dep-value" error={fieldErrors.depositCents}><Input id="dep-value" inputMode="decimal" placeholder="50,00" value={form.depositValue} onChange={(e) => setForm({ ...form, depositValue: e.target.value })} /></Field>
              <Field label="Chave Pix" htmlFor="dep-key" error={fieldErrors.pixKey}><Input id="dep-key" placeholder="CPF, e-mail, telefone ou aleatória" value={form.pixKey} onChange={(e) => setForm({ ...form, pixKey: e.target.value })} /></Field>
            </div>
          )}
        </div>
        <div className="rounded-lg border border-border p-3">
          <SwitchRow label="Página pública de agendamento" checked={form.publicBooking} onChange={(v) => setForm({ ...form, publicBooking: v })} />
          <p className="mt-2 text-xs text-muted">Coloque o link na bio do Instagram: a pessoa escolhe serviço e horário livre sem falar com ninguém. Usa a mesma agenda e as mesmas regras.</p>
          <div className="mt-3 grid gap-3 sm:grid-cols-[1fr_auto] sm:items-end">
            <Field label="Endereço" htmlFor="slug" error={fieldErrors.slug} hint={bookingUrl ?? "Salve para gerar o link."}>
              <Input id="slug" value={form.slug} onChange={(e) => setForm({ ...form, slug: e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, "-") })} placeholder="minha-barbearia" />
            </Field>
            <Button type="button" variant="secondary" onClick={copyLink} disabled={!bookingUrl}>Copiar link</Button>
          </div>
        </div>
        <div className="rounded-lg border border-border p-3">
          <SwitchRow label="Responder áudio com áudio (experimental)" checked={form.voiceReplies} onChange={(v) => setForm({ ...form, voiceReplies: v })} />
          <p className="mt-2 text-xs text-muted">Quem manda áudio recebe a resposta em áudio, com uma voz fixa. Se a voz falhar, a resposta vai em texto.</p>
        </div>
        {canManage && <Button onClick={save} loading={saving}>Salvar preferências</Button>}
      </fieldset>
    </Card>
  );
}

/** O que a assistente não soube responder vira sugestão para a base de conhecimento. */
function QuestionsCard({ canManage }: { canManage: boolean }) {
  const { tenant } = useTenant();
  const toast = useToast();
  const { data, error, refetch } = useQuery(() => api.get<{ items: UnansweredQuestion[] }>(`clinic/${tenant.id}/questions`), [tenant.id]);
  const [answering, setAnswering] = useState<UnansweredQuestion | null>(null);
  const [answer, setAnswer] = useState("");
  const [busy, setBusy] = useState<string | null>(null);

  async function resolve(q: UnansweredQuestion) {
    setBusy(q.id);
    try {
      await api.post(`clinic/${tenant.id}/questions/resolve`, { ids: q.ids });
      await refetch();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  async function addToKnowledge() {
    if (!answering || answer.trim().length < 10) return;
    setBusy(answering.id);
    try {
      await api.post(`clinic/${tenant.id}/knowledge`, { title: answering.question.slice(0, 120), content: `Pergunta: ${answering.question}\nResposta: ${answer.trim()}` });
      await api.post(`clinic/${tenant.id}/questions/resolve`, { ids: answering.ids });
      toast.success("Adicionado à base. A assistente já responde isso sozinha.");
      setAnswering(null);
      setAnswer("");
      await refetch();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card title="Perguntas que a assistente não soube responder">
      <div id="perguntas" />
      {error ? (
        <ErrorState message={error} onRetry={refetch} />
      ) : !data ? (
        <Skeleton className="h-16" />
      ) : data.items.length === 0 ? (
        <p className="text-sm text-muted">Nenhuma nos últimos 30 dias. Quando alguém perguntar algo que a assistente não sabe, aparece aqui com um botão para adicionar a resposta à base.</p>
      ) : (
        <ul className="divide-y divide-border">
          {data.items.map((q) => (
            <li key={q.id} className="flex flex-wrap items-start justify-between gap-2 py-3">
              <div className="min-w-0 flex-1">
                <p className="text-sm">“{q.question}”</p>
                <p className="text-xs text-muted">{q.people} pessoa(s) · {q.count} vez(es)</p>
                {answering?.id === q.id && (
                  <div className="mt-2 space-y-2">
                    <Textarea rows={3} value={answer} onChange={(e) => setAnswer(e.target.value)} placeholder="Escreva a resposta como você diria ao cliente." aria-label="Resposta" />
                    <div className="flex gap-2">
                      <Button size="sm" onClick={addToKnowledge} loading={busy === q.id} disabled={answer.trim().length < 10}>Salvar na base</Button>
                      <Button size="sm" variant="ghost" onClick={() => setAnswering(null)}>Cancelar</Button>
                    </div>
                  </div>
                )}
              </div>
              {canManage && answering?.id !== q.id && (
                <div className="flex gap-1">
                  <Button size="sm" variant="secondary" onClick={() => { setAnswering(q); setAnswer(""); }}>Adicionar à base</Button>
                  <Button size="sm" variant="ghost" onClick={() => resolve(q)} loading={busy === q.id}>Ignorar</Button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
