"use client";

import { useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, errorMessage } from "@/lib/api";
import type { Me } from "@/lib/types";
import { ErrorState, Spinner } from "./ui/primitives";

interface SessionValue {
  me: Me;
  reload: () => Promise<void>;
  logout: () => Promise<void>;
}

const SessionContext = createContext<SessionValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      setMe(await api.get<Me>("auth/me"));
      setError(null);
    } catch (err) {
      setError(errorMessage(err));
    }
  }, []);

  useEffect(() => {
    // Carregamento inicial da sessão; setState acontece após o await da API.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void reload();
  }, [reload]);

  const logout = useCallback(async () => {
    try {
      await api.post("auth/logout");
    } finally {
      router.replace("/login");
    }
  }, [router]);

  const value = useMemo(() => (me ? { me, reload, logout } : null), [me, reload, logout]);

  if (error) {
    return (
      <div className="p-8">
        <ErrorState message={error} onRetry={reload} />
      </div>
    );
  }
  if (!value) {
    return (
      <div className="flex min-h-screen items-center justify-center" role="status" aria-label="Carregando sessão">
        <Spinner className="h-6 w-6 text-primary" />
      </div>
    );
  }
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession() {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession fora de SessionProvider");
  return ctx;
}
