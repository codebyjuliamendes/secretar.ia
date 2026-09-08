"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState, type ReactNode } from "react";
import { api } from "@/lib/api";
import { PLAN_LABEL, STATUS_LABEL, STATUS_TONE } from "@/lib/format";
import type { Me, TenantRole, TenantSummary } from "@/lib/types";
import { ThemeToggle } from "./theme-toggle";
import { Alert, Badge, Button, Select, cx } from "./ui/primitives";
import { useToast } from "./ui/toast";

interface NavItem {
  href: string;
  label: string;
  roles?: TenantRole[];
  badge?: number;
}

export function AppShell({
  me,
  tenant,
  onLogout,
  children,
}: {
  me: Me;
  tenant: TenantSummary;
  onLogout: () => void;
  children: ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [resending, setResending] = useState(false);
  const [now] = useState(() => Date.now());
  const base = `/app/${tenant.id}`;

  const allNav: NavItem[] = [
    { href: base, label: "Visão geral" },
    { href: `${base}/calendar`, label: "Calendário" },
    { href: `${base}/appointments`, label: "Agenda" },
    { href: `${base}/patients`, label: "Pacientes" },
    { href: `${base}/inbox`, label: "Inbox", badge: tenant.unreadNotifications },
    { href: `${base}/settings`, label: "Assistente & WhatsApp", roles: ["OWNER", "MANAGER", "STAFF"] },
    { href: `${base}/team`, label: "Equipe", roles: ["OWNER", "MANAGER"] },
    { href: `${base}/billing`, label: "Plano & uso", roles: ["OWNER", "MANAGER"] },
    { href: `${base}/audit`, label: "Auditoria", roles: ["OWNER", "MANAGER"] },
  ];
  const nav = allNav.filter((item) => !item.roles || item.roles.includes(tenant.role));

  const trialDays = tenant.trialEndsAt ? Math.ceil((new Date(tenant.trialEndsAt).getTime() - now) / 86400000) : null;

  async function resend() {
    setResending(true);
    try {
      await api.post("auth/resend-verification");
      toast.success("E-mail de verificação reenviado.");
    } catch {
      toast.error("Não foi possível reenviar agora.");
    } finally {
      setResending(false);
    }
  }

  const sidebar = (
    <nav aria-label="Menu principal" className="flex h-full flex-col">
      <div className="border-b border-border p-4">
        <Link href="/app" className="text-lg font-semibold tracking-tight">
          Secretar<span className="text-primary">.ia</span>
        </Link>
        {me.memberships.length > 1 ? (
          <Select
            aria-label="Trocar clínica"
            className="mt-3 text-xs"
            value={tenant.id}
            onChange={(e) => {
              setOpen(false);
              router.push(`/app/${e.target.value}`);
            }}
          >
            {me.memberships.map((m) => (
              <option key={m.tenantId} value={m.tenantId}>
                {m.tenant.name}
              </option>
            ))}
          </Select>
        ) : (
          <p className="mt-3 truncate text-sm font-medium" title={tenant.name}>
            {tenant.name}
          </p>
        )}
        <div className="mt-2 flex flex-wrap gap-1">
          <Badge tone={STATUS_TONE[tenant.status]}>{STATUS_LABEL[tenant.status]}</Badge>
          <Badge tone="primary">{PLAN_LABEL[tenant.plan]}</Badge>
        </div>
      </div>
      <ul className="flex-1 space-y-0.5 p-3">
        {nav.map((item) => {
          const active = item.href === base ? pathname === base : pathname.startsWith(item.href);
          return (
            <li key={item.href}>
              <Link
                href={item.href}
                onClick={() => setOpen(false)}
                aria-current={active ? "page" : undefined}
                className={cx(
                  "flex items-center justify-between rounded-lg px-3 py-2 text-sm transition-colors",
                  active ? "bg-primary-soft font-medium text-primary" : "text-muted hover:bg-surface-2 hover:text-foreground",
                )}
              >
                {item.label}
                {item.badge ? <Badge tone="primary">{item.badge}</Badge> : null}
              </Link>
            </li>
          );
        })}
      </ul>
      <div className="border-t border-border p-3 text-xs text-muted">
        <p className="truncate font-medium text-foreground" title={me.email}>
          {me.name}
        </p>
        <p className="truncate">{me.email}</p>
        <div className="mt-2 flex items-center justify-between">
          <Link href="/account" className="text-primary hover:underline">
            Minha conta
          </Link>
          {me.platformRole === "SUPER_ADMIN" && (
            <Link href="/admin" className="text-primary hover:underline">
              Admin
            </Link>
          )}
          <button onClick={onLogout} className="hover:text-foreground">
            Sair
          </button>
        </div>
      </div>
    </nav>
  );

  return (
    <div className="flex min-h-screen">
      <aside className="hidden w-64 shrink-0 border-r border-border bg-surface lg:block">{sidebar}</aside>
      {open && (
        <div className="fixed inset-0 z-40 flex lg:hidden" role="dialog" aria-modal="true" aria-label="Menu">
          <div className="w-72 max-w-[85vw] bg-surface shadow-xl">{sidebar}</div>
          <button className="flex-1 bg-black/50" aria-label="Fechar menu" onClick={() => setOpen(false)} />
        </div>
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 items-center justify-between gap-3 border-b border-border bg-surface px-4">
          <Button variant="ghost" size="sm" className="lg:hidden" onClick={() => setOpen(true)} aria-label="Abrir menu">
            ☰
          </Button>
          <p className="truncate text-sm text-muted lg:hidden">{tenant.name}</p>
          <div className="ml-auto flex items-center gap-2">
            {!tenant.whatsappConnected && tenant.role !== "STAFF" && (
              <Link href={`${base}/settings#whatsapp`} className="hidden text-xs text-warning hover:underline sm:block">
                WhatsApp desconectado
              </Link>
            )}
            <ThemeToggle />
          </div>
        </header>
        <main className="flex-1 p-4 sm:p-6 lg:p-8">
          <div className="mx-auto max-w-6xl space-y-4">
            {!me.emailVerified && (
              <Alert tone="warning">
                Confirme seu e-mail para garantir a recuperação da conta.{" "}
                <button onClick={resend} disabled={resending} className="font-medium underline">
                  {resending ? "Enviando…" : "Reenviar e-mail"}
                </button>
              </Alert>
            )}
            {tenant.status === "TRIAL" && trialDays !== null && (
              <Alert tone={trialDays <= 3 ? "warning" : "info"}>
                {trialDays > 0 ? `Seu período de teste termina em ${trialDays} dia(s).` : "Seu período de teste terminou."}{" "}
                {tenant.role !== "STAFF" && (
                  <Link href={`${base}/billing`} className="font-medium underline">
                    Ver planos
                  </Link>
                )}
              </Alert>
            )}
            {tenant.status === "PAST_DUE" && (
              <Alert tone="danger" title="Pagamento pendente">
                O atendimento automático está pausado até a regularização da assinatura.
              </Alert>
            )}
            {children}
          </div>
        </main>
      </div>
    </div>
  );
}
