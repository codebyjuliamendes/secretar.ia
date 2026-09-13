"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { Alert, Button, Field, Input, Skeleton, cx } from "@/components/ui/primitives";
import { errorMessage } from "@/lib/api";
import { brl } from "@/lib/format";
import { useQuery } from "@/lib/use-query";

type Info = {
  name: string;
  slug: string;
  timezone: string;
  niche: { key: string; label: string; person: string; people: string; appointment: string };
  hours: string | null;
  services: { id: string; name: string; durationMin: number; priceCents: number | null }[];
  professionals: { id: string; name: string }[];
  deposit: string | null;
};
type Slots = { durationMin: number; days: { date: string; weekday: string; slots: { start: string; label: string }[] }[] };
type Done = { service: string; when: string; professional: string | null; deposit: string | null; whatsappConfirmation: boolean };

async function pub<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api/backend/public/booking/${path}`, { ...init, cache: "no-store", headers: { "content-type": "application/json", ...(init?.headers ?? {}) } });
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new Error(data?.error?.message ?? "Não foi possível concluir.");
  return data as T;
}

/** Fluxo em três passos, sem login: o cliente do negócio escolhe serviço, horário e deixa nome + WhatsApp. */
export default function PublicBookingPage() {
  const { slug } = useParams<{ slug: string }>();
  const info = useQuery(() => pub<Info>(slug), [slug]);
  const [serviceId, setServiceId] = useState<string | null>(null);
  const [professionalId, setProfessionalId] = useState<string>("");
  const [dayPick, setDayPick] = useState<string | null>(null);
  const [startPick, setStartPick] = useState<string | null>(null);
  const [form, setForm] = useState({ name: "", phone: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<Done | null>(null);

  const ready = !!info.data && (info.data.services.length === 0 || !!serviceId);
  const slotsQ = useQuery(() => {
    if (!ready) return Promise.resolve<Slots | null>(null);
    const q = new URLSearchParams({ days: "14" });
    if (serviceId) q.set("serviceId", serviceId);
    if (professionalId) q.set("professionalId", professionalId);
    return pub<Slots>(`${slug}/slots?${q}`);
  }, [ready, serviceId, professionalId, slug]);

  // Dia e horário são derivados: se a lista mudou e a escolha não existe mais, cai no primeiro dia / nenhum horário.
  const days = slotsQ.data?.days ?? [];
  const day = dayPick && days.some((d) => d.date === dayPick) ? dayPick : days[0]?.date ?? null;
  const dayData = days.find((d) => d.date === day) ?? null;
  const start = startPick && dayData?.slots.some((s) => s.start === startPick) ? startPick : null;

  async function submit() {
    if (!start) return;
    setBusy(true);
    setError(null);
    try {
      const r = await pub<Done>(slug, {
        method: "POST",
        body: JSON.stringify({ name: form.name, phone: form.phone, start, serviceId, professionalId: professionalId || null }),
      });
      setDone(r);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  if (info.error) {
    return (
      <main className="mx-auto max-w-lg px-6 py-16 text-center">
        <h1 className="text-xl font-semibold">Página não encontrada</h1>
        <p className="mt-2 text-sm text-muted">Este link de agendamento não existe ou está desligado.</p>
        <Link href="/" className="mt-6 inline-block text-sm text-primary hover:underline">Secretar.ia</Link>
      </main>
    );
  }
  if (!info.data) {
    return <main className="mx-auto max-w-lg px-6 py-16"><Skeleton className="h-64" /></main>;
  }
  const data = info.data;
  const service = data.services.find((s) => s.id === serviceId) ?? null;
  const stepOffset = data.services.length ? 1 : 0;

  return (
    <main className="mx-auto max-w-lg px-6 py-10">
      <header className="mb-8">
        <p className="text-xs font-medium uppercase tracking-widest text-primary">{data.niche.label}</p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight">{data.name}</h1>
        <p className="mt-1 text-sm text-muted">Escolha o {data.niche.appointment} e o horário. A equipe confirma pelo WhatsApp.</p>
        {data.hours && <p className="mt-1 text-xs text-muted">Atendimento: {data.hours}</p>}
      </header>

      {done ? (
        <div className="rounded-xl border border-border bg-surface p-6">
          <h2 className="text-lg font-semibold">Pedido enviado</h2>
          <p className="mt-2 text-sm">{done.service} em <span className="font-medium">{done.when}</span>{done.professional ? ` com ${done.professional}` : ""}.</p>
          <p className="mt-2 text-sm text-muted">{done.whatsappConfirmation ? "Você recebe a confirmação no seu WhatsApp assim que a equipe aprovar." : "A equipe entra em contato pelo WhatsApp para confirmar."}</p>
          {done.deposit && <div className="mt-3"><Alert tone="info" title="Sinal">{done.deposit}</Alert></div>}
          <Button className="mt-6" variant="secondary" onClick={() => { setDone(null); setStartPick(null); void slotsQ.refetch(); }}>Fazer outro pedido</Button>
        </div>
      ) : (
        <div className="space-y-6">
          {data.services.length > 0 && (
            <section>
              <h2 className="text-sm font-semibold">1. Serviço</h2>
              <div className="mt-2 grid gap-2 sm:grid-cols-2">
                {data.services.map((s) => (
                  <button key={s.id} type="button" onClick={() => setServiceId(s.id)} className={cx("rounded-lg border p-3 text-left text-sm", serviceId === s.id ? "border-primary bg-primary-soft" : "border-border bg-surface hover:border-primary")}>
                    <span className="font-medium">{s.name}</span>
                    <span className="mt-1 block text-xs text-muted">{s.durationMin} min{s.priceCents != null ? ` · ${brl(s.priceCents)}` : ""}</span>
                  </button>
                ))}
              </div>
            </section>
          )}
          {data.professionals.length > 0 && (
            <section>
              <h2 className="text-sm font-semibold">Com quem?</h2>
              <div className="mt-2 flex flex-wrap gap-2">
                <button type="button" onClick={() => setProfessionalId("")} className={cx("rounded-full border px-3 py-1 text-sm", professionalId === "" ? "border-primary bg-primary-soft" : "border-border")}>Qualquer</button>
                {data.professionals.map((p) => (
                  <button key={p.id} type="button" onClick={() => setProfessionalId(p.id)} className={cx("rounded-full border px-3 py-1 text-sm", professionalId === p.id ? "border-primary bg-primary-soft" : "border-border")}>{p.name}</button>
                ))}
              </div>
            </section>
          )}
          {ready && (
            <section>
              <h2 className="text-sm font-semibold">{stepOffset + 1}. Horário{service ? ` (${service.durationMin} min)` : ""}</h2>
              {slotsQ.loading && !slotsQ.data ? (
                <Skeleton className="mt-2 h-24" />
              ) : slotsQ.error ? (
                <Alert tone="danger">{slotsQ.error}</Alert>
              ) : days.length === 0 ? (
                <Alert tone="info">Sem horários livres nos próximos 14 dias. Fale com a equipe pelo WhatsApp.</Alert>
              ) : (
                <>
                  <div className="mt-2 flex gap-2 overflow-x-auto pb-1">
                    {days.map((d) => (
                      <button key={d.date} type="button" onClick={() => { setDayPick(d.date); setStartPick(null); }} className={cx("shrink-0 rounded-lg border px-3 py-2 text-sm", day === d.date ? "border-primary bg-primary-soft" : "border-border bg-surface")}>
                        <span className="block text-xs capitalize text-muted">{d.weekday}</span>
                        <span className="font-medium tabular-nums">{d.date.slice(8, 10)}/{d.date.slice(5, 7)}</span>
                      </button>
                    ))}
                  </div>
                  <div className="mt-3 grid grid-cols-4 gap-2 sm:grid-cols-6">
                    {dayData?.slots.map((s) => (
                      <button key={s.start} type="button" onClick={() => setStartPick(s.start)} className={cx("rounded-lg border px-2 py-2 text-sm tabular-nums", start === s.start ? "border-primary bg-primary text-white" : "border-border bg-surface hover:border-primary")}>{s.label}</button>
                    ))}
                  </div>
                </>
              )}
            </section>
          )}
          {start && (
            <section className="rounded-xl border border-border bg-surface p-4">
              <h2 className="text-sm font-semibold">{stepOffset + 2}. Seus dados</h2>
              <div className="mt-3 space-y-3">
                <Field label="Nome" htmlFor="pb-name" required><Input id="pb-name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} autoComplete="name" /></Field>
                <Field label="WhatsApp" htmlFor="pb-phone" required hint="Usamos só para confirmar e lembrar do horário."><Input id="pb-phone" inputMode="tel" placeholder="(81) 99999-8888" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} autoComplete="tel" /></Field>
                {data.deposit && <p className="text-xs text-muted">{data.deposit}</p>}
                {error && <Alert tone="danger">{error}</Alert>}
                <Button className="w-full" onClick={submit} loading={busy} disabled={form.name.trim().length < 2 || form.phone.replace(/\D/g, "").length < 10}>Pedir horário</Button>
                <p className="text-xs text-muted">Ao pedir o horário, seus dados vão para {data.name}, que confirma e atende. Veja a <Link href="/privacidade" className="text-primary hover:underline">Política de Privacidade</Link>.</p>
              </div>
            </section>
          )}
        </div>
      )}
      <footer className="mt-10 text-center text-xs text-muted">Agendamento por <Link href="/" className="text-primary hover:underline">Secretar.ia</Link>. Você não precisa de cadastro.</footer>
    </main>
  );
}
