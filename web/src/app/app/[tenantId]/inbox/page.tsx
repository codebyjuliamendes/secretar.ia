"use client";

import Link from "next/link";
import { useState } from "react";
import { Badge, Button, EmptyState, ErrorState, PageHeader, Skeleton, cx } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/toast";
import { api, errorMessage } from "@/lib/api";
import { formatPhone, formatRelative } from "@/lib/format";
import type { Notification } from "@/lib/types";
import { useQuery } from "@/lib/use-query";
import { useTenant } from "../layout";

const TYPE_LABEL: Record<Notification["type"], { label: string; tone: "primary" | "info" | "warning" | "danger" | "neutral" }> = {
  HUMAN_HANDOFF: { label: "Pediu atendimento humano", tone: "primary" },
  APPOINTMENT_REQUESTED: { label: "Pedido de agendamento", tone: "info" },
  APPOINTMENT_CANCELED: { label: "Cancelamento", tone: "warning" },
  BILLING: { label: "Assinatura", tone: "danger" },
  SYSTEM: { label: "Sistema", tone: "neutral" },
};

export default function InboxPage() {
  const { tenant, reload } = useTenant();
  const toast = useToast();
  const [unreadOnly, setUnreadOnly] = useState(false);
  const { data, error, loading, refetch } = useQuery(
    () => api.get<{ items: Notification[]; unreadCount: number }>(`clinic/${tenant.id}/notifications`, { unread: unreadOnly, limit: 50 }),
    [tenant.id, unreadOnly],
  );

  const [marking, setMarking] = useState<string | "all" | null>(null);

  async function markRead(id?: string) {
    if (marking) return;
    setMarking(id ?? "all");
    try {
      await api.post(`clinic/${tenant.id}/notifications/read`, undefined, id ? { id } : undefined);
      await Promise.all([refetch(), reload()]);
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setMarking(null);
    }
  }

  return (
    <>
      <PageHeader
        title="Inbox"
        description="Eventos que precisam da atenção da equipe: pedidos de humano, agendamentos e assinatura."
        action={
          <>
            <Button variant="secondary" onClick={() => setUnreadOnly(!unreadOnly)} aria-pressed={unreadOnly}>{unreadOnly ? "Mostrar todas" : "Só não lidas"}</Button>
            <Button variant="secondary" disabled={!data?.unreadCount} onClick={() => markRead()}>Marcar todas como lidas</Button>
          </>
        }
      />
      {error ? (
        <ErrorState message={error} onRetry={refetch} />
      ) : loading && !data ? (
        <Skeleton className="h-64" />
      ) : !data || data.items.length === 0 ? (
        <EmptyState title={unreadOnly ? "Nenhuma notificação não lida" : "Inbox vazia"} description="Quando um paciente pedir atendimento humano ou solicitar um horário, você verá aqui." />
      ) : (
        <ul className="space-y-2">
          {data.items.map((n) => {
            const meta = TYPE_LABEL[n.type];
            return (
              <li key={n.id} className={cx("rounded-xl border border-border bg-surface p-4", !n.readAt && "border-l-4 border-l-primary")}>
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge tone={meta.tone}>{meta.label}</Badge>
                      <span className="text-xs text-muted">{formatRelative(n.createdAt)}</span>
                    </div>
                    <p className="mt-1 font-medium">{n.title}</p>
                    <p className="text-sm text-muted">{n.body}</p>
                    {n.phone && (
                      <p className="mt-1 text-xs text-muted">
                        Paciente: {formatPhone(n.phone)} ·{" "}
                        <a href={`https://wa.me/${n.phone}`} target="_blank" rel="noreferrer noopener" className="text-primary hover:underline">
                          abrir no WhatsApp
                        </a>{" "}
                        · <Link href={`/app/${tenant.id}/patients?search=${n.phone}`} className="text-primary hover:underline">ver paciente</Link>
                      </p>
                    )}
                  </div>
                  {!n.readAt && (
                    <Button size="sm" variant="secondary" loading={marking === n.id} disabled={!!marking} onClick={() => markRead(n.id)}>Marcar como lida</Button>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </>
  );
}
