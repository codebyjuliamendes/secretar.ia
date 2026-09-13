"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { NewAppointmentModal } from "@/components/appointment-modal";
import { Badge, Button, ErrorState, PageHeader, Skeleton, cx } from "@/components/ui/primitives";
import { useToast } from "@/components/ui/toast";
import { api, errorMessage } from "@/lib/api";
import { APPT_LABEL, APPT_TONE } from "@/lib/format";
import { addCalendarDays, dayOfKey, dayStartUtc, formatInZone, minutesInZone, mondayKey, zonedParts, zonedToUtc } from "@/lib/tz";
import type { AppointmentStatus, CalendarData } from "@/lib/types";
import { useQuery } from "@/lib/use-query";
import { useTenant } from "../layout";

const DAY_LABELS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"];
const PX_PER_MIN = 1.1;

/** Distribui blocos que se sobrepõem em colunas lado a lado (encaixes com `force` não se escondem). */
function layoutColumns<T extends { start: string; end: string }>(items: T[]) {
  const sorted = [...items].sort((a, b) => new Date(a.start).getTime() - new Date(b.start).getTime());
  const placed: { item: T; col: number; cols: number }[] = [];
  let cluster: { item: T; col: number; cols: number }[] = [];
  let clusterEnd = -Infinity;
  const flush = () => {
    const cols = Math.max(1, ...cluster.map((c) => c.col + 1));
    for (const c of cluster) c.cols = cols;
    placed.push(...cluster);
    cluster = [];
  };
  for (const item of sorted) {
    const s = new Date(item.start).getTime();
    const e = new Date(item.end).getTime();
    if (cluster.length && s >= clusterEnd) flush();
    const taken = new Set(cluster.filter((c) => new Date(c.item.end).getTime() > s).map((c) => c.col));
    let col = 0;
    while (taken.has(col)) col++;
    cluster.push({ item, col, cols: 1 });
    clusterEnd = Math.max(clusterEnd, e);
  }
  if (cluster.length) flush();
  return placed;
}

function hhmmToMin(v: string) {
  const [h, m] = v.split(":").map(Number);
  return h * 60 + m;
}

const STATUS_BG: Record<AppointmentStatus, string> = {
  PENDING: "bg-warning-soft border-warning text-warning",
  CONFIRMED: "bg-info-soft border-info text-info",
  COMPLETED: "bg-success-soft border-success text-success",
  CANCELED: "bg-surface-2 border-border text-muted line-through",
  NO_SHOW: "bg-danger-soft border-danger text-danger",
};

export default function CalendarPage() {
  const { tenant } = useTenant();
  const toast = useToast();
  // Tudo aqui é no fuso da CLÍNICA: a grade, o "agora", o clique no horário e o que vai para o servidor.
  const tz = tenant.timezone || "America/Sao_Paulo";
  const [weekKey, setWeekKey] = useState(() => mondayKey(new Date(), tz));
  const [modal, setModal] = useState<{ open: boolean; date?: Date }>({ open: false });
  const [showCanceled, setShowCanceled] = useState(false);
  const weekStart = useMemo(() => dayStartUtc(weekKey, tz), [weekKey, tz]);
  const weekEnd = useMemo(() => dayStartUtc(addCalendarDays(weekKey, 7), tz), [weekKey, tz]);
  const browserTz = Intl.DateTimeFormat().resolvedOptions().timeZone;
  const { data, error, loading, refetch } = useQuery(
    () => api.get<CalendarData>(`clinic/${tenant.id}/calendar`, { from: weekStart.toISOString(), to: weekEnd.toISOString() }),
    [tenant.id, weekKey],
  );

  const range = useMemo(() => {
    const rules = data?.rules ?? [];
    let min = rules.length ? Math.min(...rules.map((r) => hhmmToMin(r.start))) : 8 * 60;
    let max = rules.length ? Math.max(...rules.map((r) => hhmmToMin(r.end))) : 19 * 60;
    for (const a of data?.appointments ?? []) {
      min = Math.min(min, minutesInZone(new Date(a.start), tz));
      max = Math.max(max, minutesInZone(new Date(a.end), tz) || max);
    }
    min = Math.max(0, Math.floor(min / 60) * 60 - 60);
    max = Math.min(24 * 60, Math.ceil(max / 60) * 60 + 60);
    return { min, max };
  }, [data, tz]);

  const dayKeys = Array.from({ length: 7 }, (_, i) => addCalendarDays(weekKey, i));
  const hours: number[] = [];
  for (let m = range.min; m < range.max; m += 60) hours.push(m);
  const height = (range.max - range.min) * PX_PER_MIN;
  const now = new Date();
  const todayKey = zonedParts(now, tz).dateKey;

  async function quickStatus(id: string, status: AppointmentStatus) {
    try {
      await api.post(`clinic/${tenant.id}/appointments/${id}/status`, { status });
      toast.success(`Marcado como ${APPT_LABEL[status].toLowerCase()}.`);
      await refetch();
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  function atMinutes(dayKey: string, minutes: number) {
    const [y, m, d] = dayKey.split("-").map(Number);
    return zonedToUtc(y, m, d, Math.floor(minutes / 60), minutes % 60, tz);
  }

  function onSlotClick(dayKey: string, e: React.MouseEvent<HTMLDivElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    const minutes = range.min + (e.clientY - rect.top) / PX_PER_MIN;
    const step = data?.slotMinutes ?? 30;
    const snapped = Math.floor(minutes / step) * step;
    setModal({ open: true, date: atMinutes(dayKey, snapped) });
  }

  const visible = (data?.appointments ?? []).filter((a) => showCanceled || a.status !== "CANCELED");
  const fmtDay = (key: string, opts: Intl.DateTimeFormatOptions) => formatInZone(dayStartUtc(key, tz), tz, opts);

  return (
    <>
      <PageHeader
        title="Calendário"
        description="Semana da clínica. Clique em um horário livre para criar um agendamento."
        action={
          <>
            <Button variant="secondary" onClick={() => setWeekKey(addCalendarDays(weekKey, -7))} aria-label="Semana anterior">‹</Button>
            <Button variant="secondary" onClick={() => setWeekKey(mondayKey(new Date(), tz))}>Hoje</Button>
            <Button variant="secondary" onClick={() => setWeekKey(addCalendarDays(weekKey, 7))} aria-label="Próxima semana">›</Button>
            <Button onClick={() => setModal({ open: true })}>Novo agendamento</Button>
          </>
        }
      />
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2 text-sm text-muted">
        <span>
          {fmtDay(weekKey, { day: "2-digit", month: "short" })} a {fmtDay(addCalendarDays(weekKey, 6), { day: "2-digit", month: "short", year: "numeric" })}
          {data && <> · fuso {data.timezone} · passo {data.slotMinutes} min</>}
        </span>
        {browserTz !== tz && (
          <span className="basis-full text-warning">Seu computador está no fuso {browserTz}; a agenda está no fuso da clínica ({tz}).</span>
        )}
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={showCanceled} onChange={(e) => setShowCanceled(e.target.checked)} /> mostrar cancelados
        </label>
      </div>
      {error ? (
        <ErrorState message={error} onRetry={refetch} />
      ) : loading && !data ? (
        <Skeleton className="h-[520px]" />
      ) : (
        <div className="overflow-x-auto rounded-xl border border-border bg-surface">
          <div className="grid min-w-[880px]" style={{ gridTemplateColumns: "56px repeat(7, 1fr)" }}>
            <div className="border-b border-border" />
            {dayKeys.map((key, wd) => (
              <div key={key} className={cx("border-b border-l border-border px-2 py-2 text-center text-xs font-medium", key === todayKey && "text-primary")}>
                {DAY_LABELS[wd]} <span className="text-muted">{String(dayOfKey(key)).padStart(2, "0")}</span>
              </div>
            ))}
            <div className="relative" style={{ height }}>
              {hours.map((m) => (
                <div key={m} className="absolute right-1 -translate-y-1/2 text-[10px] text-muted" style={{ top: (m - range.min) * PX_PER_MIN }}>
                  {String(m / 60).padStart(2, "0")}:00
                </div>
              ))}
            </div>
            {dayKeys.map((key, wd) => {
              const dayRules = (data?.rules ?? []).filter((r) => r.weekday === wd);
              const dayStart = dayStartUtc(key, tz);
              const dayEnd = dayStartUtc(addCalendarDays(key, 1), tz);
              const dayAppts = visible.filter((a) => zonedParts(new Date(a.start), tz).dateKey === key);
              const dayExternal = (data?.external ?? []).filter((x) => new Date(x.start) < dayEnd && new Date(x.end) > dayStart);
              return (
                <div
                  key={key}
                  role="button"
                  tabIndex={0}
                  aria-label={`Criar agendamento em ${fmtDay(key, { day: "2-digit", month: "2-digit", year: "numeric" })}`}
                  onClick={(e) => onSlotClick(key, e)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") setModal({ open: true, date: atMinutes(key, range.min) });
                  }}
                  className="relative cursor-pointer border-l border-border bg-surface-2/40"
                  style={{ height }}
                >
                  {dayRules.map((r, i) => (
                    <div key={i} aria-hidden className="absolute inset-x-0 bg-surface" style={{ top: (hhmmToMin(r.start) - range.min) * PX_PER_MIN, height: (hhmmToMin(r.end) - hhmmToMin(r.start)) * PX_PER_MIN }} />
                  ))}
                  {hours.map((m) => (
                    <div key={m} aria-hidden className="absolute inset-x-0 border-t border-border/60" style={{ top: (m - range.min) * PX_PER_MIN }} />
                  ))}
                  {key === todayKey && (
                    <div aria-hidden className="absolute inset-x-0 border-t-2 border-primary" style={{ top: (minutesInZone(now, tz) - range.min) * PX_PER_MIN }} />
                  )}
                  {dayExternal.map((x) => {
                    const s = new Date(x.start);
                    const e = new Date(x.end);
                    const fromMin = s <= dayStart ? range.min : minutesInZone(s, tz);
                    const toMin = e >= dayEnd ? range.max : minutesInZone(e, tz);
                    const top = (fromMin - range.min) * PX_PER_MIN;
                    const h = Math.max(22, (toMin - fromMin) * PX_PER_MIN - 2);
                    return (
                      <div
                        key={x.id}
                        aria-hidden
                        className="absolute inset-x-1 overflow-hidden rounded-md border-l-4 border-border bg-surface-2/80 px-1.5 py-0.5 text-[11px] leading-tight text-muted"
                        style={{ top, height: h, backgroundImage: "repeating-linear-gradient(135deg, transparent 0 6px, rgba(0,0,0,0.05) 6px 8px)" }}
                        title={`${x.summary ?? "Compromisso"} · Google Calendar`}
                      >
                        <p className="truncate font-semibold">{x.allDay ? "Dia todo" : formatInZone(s, tz, { hour: "2-digit", minute: "2-digit" })} · Google</p>
                        <p className="truncate">{x.summary ?? "Compromisso"}</p>
                      </div>
                    );
                  })}
                  {layoutColumns(dayAppts).map(({ item: a, col, cols }) => {
                    const s = new Date(a.start);
                    const e = new Date(a.end);
                    const top = (minutesInZone(s, tz) - range.min) * PX_PER_MIN;
                    const h = Math.max(22, ((e.getTime() - s.getTime()) / 60000) * PX_PER_MIN - 2);
                    const width = `calc((100% - 8px) / ${cols})`;
                    const left = `calc(4px + (100% - 8px) * ${col} / ${cols})`;
                    return (
                      <div
                        key={a.id}
                        tabIndex={0}
                        onClick={(ev) => ev.stopPropagation()}
                        onKeyDown={(ev) => ev.stopPropagation()}
                        className={cx("group absolute overflow-hidden rounded-md border-l-4 px-1.5 py-0.5 text-[11px] leading-tight shadow-sm focus:outline-none focus:ring-2 focus:ring-primary", STATUS_BG[a.status])}
                        style={{ top, height: h, left, width }}
                        title={`${a.service} · ${a.patient?.name ?? a.patient?.phone ?? ""} · ${APPT_LABEL[a.status]}`}
                      >
                        <p className="truncate font-semibold">{formatInZone(s, tz, { hour: "2-digit", minute: "2-digit" })} {a.patient?.name ?? a.patient?.phone ?? "Paciente"}</p>
                        <p className="truncate">{a.service}{a.source === "AI" && " · IA"}</p>
                        {h > 60 && (
                          <div className="mt-1 hidden gap-1 group-hover:flex group-focus-within:flex">
                            {a.status === "PENDING" && <button className="rounded bg-surface px-1 text-[10px] text-foreground" onClick={() => quickStatus(a.id, "CONFIRMED")}>Confirmar</button>}
                            {a.status === "CONFIRMED" && <button className="rounded bg-surface px-1 text-[10px] text-foreground" onClick={() => quickStatus(a.id, "COMPLETED")}>Realizado</button>}
                            {(a.status === "PENDING" || a.status === "CONFIRMED") && <button className="rounded bg-surface px-1 text-[10px] text-foreground" onClick={() => quickStatus(a.id, "CANCELED")}>Cancelar</button>}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              );
            })}
          </div>
        </div>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-muted">
        Legenda:
        {(Object.keys(APPT_LABEL) as AppointmentStatus[]).map((s) => <Badge key={s} tone={APPT_TONE[s]}>{APPT_LABEL[s]}</Badge>)}
        {(data?.external.length ?? 0) > 0 && <Badge tone="neutral">Google Calendar</Badge>}
        <span className="ml-auto">Áreas claras são horários de atendimento. <Link href={`/app/${tenant.id}/settings#horarios`} className="text-primary hover:underline">Editar horários</Link></span>
      </div>
      <NewAppointmentModal open={modal.open} initialDate={modal.date} onClose={() => setModal({ open: false })} onCreated={() => { setModal({ open: false }); void refetch(); }} />
    </>
  );
}
