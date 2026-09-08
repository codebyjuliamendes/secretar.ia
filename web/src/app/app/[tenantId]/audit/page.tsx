"use client";

import { useState } from "react";
import { Button, EmptyState, ErrorState, PageHeader, Skeleton, Table, Td, Th } from "@/components/ui/primitives";
import { api, errorMessage } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { AuditEntry } from "@/lib/types";
import { useQuery } from "@/lib/use-query";
import { useTenant } from "../layout";

const ACTION_LABEL: Record<string, string> = {
  "auth.register": "Cadastro da conta",
  "auth.login": "Login",
  "tenant.settings_updated": "Configurações alteradas",
  "appointment.created": "Agendamento criado",
  "appointment.status_changed": "Status de agendamento alterado",
  "appointment.updated": "Agendamento editado",
  "patient.created": "Paciente criado",
  "patient.updated": "Paciente editado",
  "patient.deleted": "Paciente excluído",
  "team.member_invited": "Membro convidado",
  "team.role_changed": "Papel alterado",
  "team.member_removed": "Membro removido",
  "whatsapp.connect_started": "Conexão do WhatsApp iniciada",
  "whatsapp.disconnected": "WhatsApp desconectado",
};

export default function AuditPage() {
  const { tenant } = useTenant();
  const [items, setItems] = useState<AuditEntry[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [moreError, setMoreError] = useState<string | null>(null);
  const { error, loading, refetch } = useQuery(async () => {
    const r = await api.get<{ items: AuditEntry[]; nextCursor: string | null }>(`clinic/${tenant.id}/audit`, { limit: 50 });
    setItems(r.items);
    setCursor(r.nextCursor);
    return r;
  }, [tenant.id]);

  async function more() {
    if (!cursor) return;
    setLoadingMore(true);
    setMoreError(null);
    try {
      const r = await api.get<{ items: AuditEntry[]; nextCursor: string | null }>(`clinic/${tenant.id}/audit`, { limit: 50, cursor });
      setItems((prev) => [...prev, ...r.items]);
      setCursor(r.nextCursor);
    } catch (err) {
      setMoreError(errorMessage(err));
    } finally {
      setLoadingMore(false);
    }
  }

  return (
    <>
      <PageHeader title="Auditoria" description="Quem fez o quê, quando. Útil para suporte e investigação." />
      {error ? (
        <ErrorState message={error} onRetry={refetch} />
      ) : loading && items.length === 0 ? (
        <Skeleton className="h-64" />
      ) : items.length === 0 ? (
        <EmptyState title="Nenhum evento registrado" />
      ) : (
        <>
          <Table>
            <thead><tr><Th>Quando</Th><Th>Ação</Th><Th>Quem</Th><Th>Detalhes</Th></tr></thead>
            <tbody>
              {items.map((a) => (
                <tr key={a.id}>
                  <Td className="whitespace-nowrap">{formatDateTime(a.createdAt)}</Td>
                  <Td><p className="font-medium">{ACTION_LABEL[a.action] ?? a.action}</p><p className="text-xs text-muted">{a.resourceType}{a.resourceId ? ` · ${a.resourceId}` : ""}</p></Td>
                  <Td>{a.actor ? <><p>{a.actor.name}</p><p className="text-xs text-muted">{a.actor.email}</p></> : <span className="text-muted">sistema</span>}</Td>
                  <Td className="max-w-xs"><code className="block truncate text-xs text-muted" title={a.metadata ? JSON.stringify(a.metadata) : ""}>{a.metadata ? JSON.stringify(a.metadata) : "—"}</code></Td>
                </tr>
              ))}
            </tbody>
          </Table>
          {moreError && <p role="alert" className="mt-2 text-sm text-danger">{moreError}</p>}
          {cursor && <div className="mt-4 text-center"><Button variant="secondary" onClick={more} loading={loadingMore}>Carregar mais</Button></div>}
        </>
      )}
    </>
  );
}
