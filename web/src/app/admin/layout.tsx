"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { SessionProvider, useSession } from "@/components/session";
import { ThemeToggle } from "@/components/theme-toggle";
import { Button, EmptyState, LinkButton, cx } from "@/components/ui/primitives";

function AdminShell({ children }: { children: React.ReactNode }) {
  const { me, logout } = useSession();
  const pathname = usePathname();
  if (me.platformRole !== "SUPER_ADMIN") {
    return (
      <main className="mx-auto max-w-lg p-8">
        <EmptyState title="Acesso restrito" description="Esta área é exclusiva da administração da plataforma." action={<LinkButton href="/app">Ir para o painel</LinkButton>} />
      </main>
    );
  }
  const nav = [
    { href: "/admin", label: "Visão geral" },
    { href: "/admin/tenants", label: "Clínicas" },
    { href: "/admin/jobs", label: "Fila de tarefas" },
  ];
  return (
    <div className="min-h-screen">
      <header className="border-b border-border bg-surface">
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-4">
          <div className="flex items-center gap-6">
            <Link href="/admin" className="font-semibold">Secretar<span className="text-primary">.ia</span> <span className="text-xs font-normal text-muted">admin</span></Link>
            <nav className="flex gap-1" aria-label="Administração">
              {nav.map((n) => (
                <Link key={n.href} href={n.href} aria-current={pathname === n.href ? "page" : undefined} className={cx("rounded-md px-3 py-1.5 text-sm", pathname === n.href ? "bg-primary-soft text-primary" : "text-muted hover:text-foreground")}>{n.label}</Link>
              ))}
            </nav>
          </div>
          <div className="flex items-center gap-2">
            <Link href="/app" className="text-sm text-muted hover:text-foreground">Painel das clínicas</Link>
            <ThemeToggle />
            <Button variant="ghost" size="sm" onClick={logout}>Sair</Button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl p-4 sm:p-6">{children}</main>
    </div>
  );
}

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <SessionProvider>
      <AdminShell>{children}</AdminShell>
    </SessionProvider>
  );
}
