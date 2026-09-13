"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { SessionProvider, useSession } from "@/components/session";
import { Alert, Badge, Button, Card, Field, Input, PageHeader } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/toast";
import { ConfirmDialog } from "@/components/ui/modal";
import { api, errorMessage } from "@/lib/api";
import { ROLE_LABEL } from "@/lib/format";

function AccountInner() {
  const { me, reload, logout } = useSession();
  const toast = useToast();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [closing, setClosing] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [requested, setRequested] = useState<string[]>([]);

  async function change(e: FormEvent) {
    e.preventDefault();
    if (next !== confirm) return setError("As senhas não coincidem.");
    setError(null);
    setSaving(true);
    try {
      await api.post("auth/change-password", { currentPassword: current, newPassword: next });
      toast.success("Senha alterada. Outras sessões foram encerradas.");
      setCurrent(""); setNext(""); setConfirm("");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  async function resend() {
    try {
      await api.post("auth/resend-verification");
      toast.success("E-mail de verificação reenviado.");
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  async function logoutAll() {
    try {
      await api.post("auth/logout", { allSessions: true });
    } finally {
      await logout();
    }
  }

  return (
    <main className="mx-auto max-w-3xl p-6">
      <div className="mb-4 text-sm"><Link href="/app" className="text-primary hover:underline">← Voltar ao painel</Link></div>
      <PageHeader title="Minha conta" description={me.email} />
      <div className="space-y-4">
        <Card title="Perfil">
          <dl className="grid gap-3 text-sm sm:grid-cols-2">
            <div><dt className="text-muted">Nome</dt><dd className="font-medium">{me.name}</dd></div>
            <div><dt className="text-muted">E-mail</dt><dd className="flex items-center gap-2 font-medium">{me.email} <Badge tone={me.emailVerified ? "success" : "warning"}>{me.emailVerified ? "verificado" : "não verificado"}</Badge></dd></div>
          </dl>
          {!me.emailVerified && <div className="mt-3"><Button size="sm" variant="secondary" onClick={resend}>Reenviar e-mail de verificação</Button></div>}
        </Card>
        <Card title="Clínicas">
          <ul className="divide-y divide-border text-sm">
            {me.memberships.map((m) => (
              <li key={m.tenantId} className="flex items-center justify-between py-2">
                <Link href={`/app/${m.tenantId}`} className="font-medium text-primary hover:underline">{m.tenant.name}</Link>
                <span className="text-muted">{ROLE_LABEL[m.role]}</span>
              </li>
            ))}
            {me.memberships.length === 0 && <li className="py-2 text-muted">Nenhuma clínica.</li>}
          </ul>
        </Card>
        <Card title="Alterar senha">
          <form onSubmit={change} className="space-y-4 sm:max-w-sm">
            <Field label="Senha atual" htmlFor="cur" required><Input id="cur" type="password" autoComplete="current-password" required value={current} onChange={(e) => setCurrent(e.target.value)} /></Field>
            <Field label="Nova senha" htmlFor="new" required hint="Mínimo de 8 caracteres com letras e números."><Input id="new" type="password" autoComplete="new-password" required value={next} onChange={(e) => setNext(e.target.value)} /></Field>
            <Field label="Confirmar nova senha" htmlFor="cnf" required><Input id="cnf" type="password" autoComplete="new-password" required value={confirm} onChange={(e) => setConfirm(e.target.value)} /></Field>
            {error && <Alert tone="danger">{error}</Alert>}
            <Button type="submit" loading={saving}>Alterar senha</Button>
          </form>
        </Card>
        <Card title="Encerrar conta">
          <p className="mb-3 text-sm text-muted">Antes de encerrar, exporte contatos e agendamentos em planilha pelas telas de Contatos e Agenda. O pedido vai para a nossa equipe, que confirma com você e apaga tudo: cadastro, conversas e histórico.</p>
          <ul className="divide-y divide-border text-sm">
            {me.memberships.filter((m) => m.role === "OWNER").map((m) => (
              <li key={m.tenantId} className="flex flex-wrap items-center justify-between gap-2 py-2">
                <span className="font-medium">{m.tenant.name}</span>
                {requested.includes(m.tenantId) ? (
                  <Badge tone="warning">encerramento pedido</Badge>
                ) : (
                  <Button size="sm" variant="danger" onClick={() => { setReason(""); setClosing(m.tenantId); }}>Pedir encerramento</Button>
                )}
              </li>
            ))}
            {me.memberships.filter((m) => m.role === "OWNER").length === 0 && (
              <li className="py-2 text-muted">Só o proprietário pode pedir o encerramento.</li>
            )}
          </ul>
        </Card>
        <ConfirmDialog
          open={!!closing}
          onClose={() => setClosing(null)}
          onConfirm={async () => {
            if (!closing) return;
            try {
              await api.post(`clinic/${closing}/account/deletion-request`, { reason: reason || null });
              setRequested((r) => [...r, closing]);
              toast.success("Pedido enviado. Nossa equipe fala com você antes de apagar qualquer coisa.");
            } catch (err) {
              toast.error(errorMessage(err));
            } finally {
              setClosing(null);
            }
          }}
          danger
          title="Pedir encerramento da conta"
          description="Nada é apagado agora. Nossa equipe recebe o pedido, confirma com você e faz a exclusão definitiva, que não tem volta."
          confirmLabel="Enviar pedido"
        />
        <Card title="Sessões">
          <p className="mb-3 text-sm text-muted">Encerra o acesso em todos os dispositivos, incluindo este.</p>
          <Button variant="danger" onClick={logoutAll}>Sair de todos os dispositivos</Button>
          <Button variant="ghost" className="ml-2" onClick={() => void reload()}>Atualizar dados</Button>
        </Card>
      </div>
    </main>
  );
}

export default function AccountPage() {
  return (
    <SessionProvider>
      <AccountInner />
    </SessionProvider>
  );
}
