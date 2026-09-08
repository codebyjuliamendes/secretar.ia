"use client";

import { useParams } from "next/navigation";
import { createContext, useContext, type ReactNode } from "react";
import { AppShell } from "@/components/app-shell";
import { useSession } from "@/components/session";
import { ErrorState, LinkButton, Skeleton } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import type { TenantSummary } from "@/lib/types";
import { useQuery } from "@/lib/use-query";

const TenantContext = createContext<{ tenant: TenantSummary; reload: () => Promise<void> } | null>(null);

export function useTenant() {
  const ctx = useContext(TenantContext);
  if (!ctx) throw new Error("useTenant fora do layout da clínica");
  return ctx;
}

export default function TenantLayout({ children }: { children: ReactNode }) {
  const { tenantId } = useParams<{ tenantId: string }>();
  const { me, logout } = useSession();
  const { data, error, loading, refetch } = useQuery(() => api.get<TenantSummary>(`clinic/${tenantId}`), [tenantId]);

  if (loading && !data) {
    return (
      <div className="p-8">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="mt-4 h-40 w-full" />
      </div>
    );
  }
  if (error || !data) {
    const forbidden = !me.memberships.some((m) => m.tenantId === tenantId);
    return (
      <main className="mx-auto max-w-lg p-8">
        <ErrorState message={forbidden ? "Você não tem acesso a esta clínica." : error ?? "Erro ao carregar."} onRetry={forbidden ? undefined : refetch} />
        <div className="mt-4 text-center">
          <LinkButton href="/app" variant="secondary">
            Voltar
          </LinkButton>
        </div>
      </main>
    );
  }
  return (
    <TenantContext.Provider value={{ tenant: data, reload: refetch }}>
      <AppShell me={me} tenant={data} onLogout={logout}>
        {children}
      </AppShell>
    </TenantContext.Provider>
  );
}
