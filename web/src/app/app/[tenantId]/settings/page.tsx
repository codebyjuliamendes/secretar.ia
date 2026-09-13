"use client";

import { useEffect, useState } from "react";
import { AvailabilityCard, ServicesCard } from "@/components/scheduling-settings";
import { Alert, Badge, Button, Card, EmptyState, ErrorState, Field, Input, PageHeader, Skeleton, Switch, Textarea } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/toast";
import { ApiError, api, errorMessage } from "@/lib/api";
import type { FeatureAccess, GoogleCalendarStatus, KnowledgeDocument, KnowledgeSource, TenantSettings, WhatsAppStatus } from "@/lib/types";
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
            <KnowledgeCard canManage={canManage} access={data.featureAccess} />
            <UpsellForm settings={data} canManage={canManage} onSaved={refetch} />
          </div>
          <div className="space-y-4">
            <WhatsAppCard canManage={canManage} />
            <GoogleCalendarCard canManage={canManage} />
            <Card title="Como a IA usa estas informações">
              <ul className="list-disc space-y-1 pl-4 text-sm text-muted">
                <li>O prompt define a personalidade e as regras da clínica.</li>
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

function GoogleCalendarCard({ canManage }: { canManage: boolean }) {
  const { tenant } = useTenant();
  const toast = useToast();
  const { data, error, loading, refetch, setData } = useQuery(() => api.get<GoogleCalendarStatus>(`clinic/${tenant.id}/integrations/google`), [tenant.id]);
  const [busy, setBusy] = useState<string | null>(null);

  // Retorno do OAuth: ?google=connected|error&reason=...
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const result = params.get("google");
    if (!result) return;
    if (result === "connected") toast.success("Google Calendar conectado. Os agendamentos futuros serão sincronizados.");
    else toast.error(`Não foi possível conectar o Google Calendar (${params.get("reason") ?? "erro"}).`);
    window.history.replaceState(null, "", window.location.pathname);
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
        ) : loading || !data ? (
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
  const { data, error, loading, refetch } = useQuery(() => api.get<{ items: KnowledgeDocument[] }>(`clinic/${tenant.id}/knowledge`), [tenant.id]);
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
        ) : loading || !data ? (
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
                className="block w-full text-sm text-muted file:mr-3 file:rounded-md file:border file:border-border file:bg-surface file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-foreground"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
              <Input placeholder="Título (opcional; usa o nome do arquivo)" value={fileTitle} onChange={(e) => setFileTitle(e.target.value)} />
              <p className="text-xs text-muted">Até 10 MB. PDFs digitalizados são lidos pela IA (até 20 páginas). Textos longos são divididos em partes.</p>
              <Button variant="secondary" onClick={importFile} loading={importing === "file"} disabled={!file}>Importar arquivo</Button>
            </fieldset>
            <fieldset className="space-y-3 rounded-lg border border-dashed border-border p-4">
              <p className="text-sm font-medium">Importar de uma página pública</p>
              <Input placeholder="https://suaclinica.com.br/perguntas-frequentes" value={url} onChange={(e) => setUrl(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && url.trim().length >= 8) void importUrl(); }} />
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
