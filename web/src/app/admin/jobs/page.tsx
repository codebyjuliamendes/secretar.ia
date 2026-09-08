"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { Badge, Button, EmptyState, ErrorState, PageHeader, Select, Skeleton, Table, Td, Th } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/toast";
import { api, errorMessage } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { AdminJob } from "@/lib/types";
import { useQuery } from "@/lib/use-query";

const TONE: Record<AdminJob["status"], "info" | "warning" | "success" | "danger"> = { PENDING: "info", RUNNING: "warning", COMPLETED: "success", FAILED: "danger" };

function JobsInner() {
  const toast = useToast();
  const [status, setStatus] = useState(useSearchParams().get("status") ?? "");
  const { data, error, loading, refetch } = useQuery(() => api.get<{ tasks: string[]; items: AdminJob[] }>("admin/jobs", { status, limit: 100 }), [status]);

  async function retry(id: string) {
    try {
      await api.post(`admin/jobs/${id}/retry`);
      toast.success("Tarefa reenfileirada.");
      await refetch();
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  return (
    <>
      <PageHeader title="Fila de tarefas" description="Envios de WhatsApp, e-mails e campanhas processados em segundo plano." action={<Button variant="secondary" onClick={refetch}>Atualizar</Button>} />
      <Select aria-label="Status" value={status} onChange={(e) => setStatus(e.target.value)} className="mb-4 sm:w-56">
        <option value="">Todos</option>
        {(["PENDING", "RUNNING", "COMPLETED", "FAILED"] as const).map((s) => <option key={s} value={s}>{s}</option>)}
      </Select>
      {error ? (
        <ErrorState message={error} onRetry={refetch} />
      ) : loading && !data ? (
        <Skeleton className="h-64" />
      ) : !data || data.items.length === 0 ? (
        <EmptyState title="Nenhuma tarefa" description={`Executores registrados: ${data?.tasks.join(", ") ?? "—"}`} />
      ) : (
        <Table>
          <thead><tr><Th>Tarefa</Th><Th>Status</Th><Th>Tentativas</Th><Th>Executa em</Th><Th>Erro</Th><Th className="text-right">Ações</Th></tr></thead>
          <tbody>
            {data.items.map((j) => (
              <tr key={j.id}>
                <Td><p className="font-medium">{j.name}</p><p className="text-xs text-muted">{j.id}</p></Td>
                <Td><Badge tone={TONE[j.status]}>{j.status}</Badge></Td>
                <Td>{j.retries}/{j.maxRetries}</Td>
                <Td className="whitespace-nowrap">{formatDateTime(j.runAt)}</Td>
                <Td className="max-w-xs"><span className="block truncate text-xs text-muted" title={j.error ?? ""}>{j.error ?? "—"}</span></Td>
                <Td className="text-right">{j.status === "FAILED" && <Button size="sm" variant="secondary" onClick={() => retry(j.id)}>Reprocessar</Button>}</Td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
    </>
  );
}

export default function AdminJobsPage() {
  return (
    <Suspense fallback={<Skeleton className="h-64" />}>
      <JobsInner />
    </Suspense>
  );
}
