/**
 * Datas no fuso da CLÍNICA, independentemente do fuso do computador de quem usa o painel.
 * Só Intl, sem biblioteca: o suficiente para posicionar uma agenda semanal e montar horários.
 */

export interface ZonedParts {
  year: number;
  month: number; // 1-12
  day: number;
  hour: number;
  minute: number;
  weekday: number; // 0 = segunda … 6 = domingo
  dateKey: string; // "2026-09-14"
}

const cache = new Map<string, Intl.DateTimeFormat>();
function formatter(tz: string) {
  let f = cache.get(tz);
  if (!f) {
    f = new Intl.DateTimeFormat("en-US", {
      timeZone: tz,
      hourCycle: "h23",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      weekday: "short",
    });
    cache.set(tz, f);
  }
  return f;
}

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

/** Componentes de um instante no fuso `tz`. */
export function zonedParts(date: Date, tz: string): ZonedParts {
  const parts = Object.fromEntries(formatter(tz).formatToParts(date).map((p) => [p.type, p.value]));
  const year = Number(parts.year);
  const month = Number(parts.month);
  const day = Number(parts.day);
  return {
    year,
    month,
    day,
    hour: Number(parts.hour) % 24,
    minute: Number(parts.minute),
    weekday: WEEKDAYS.indexOf(parts.weekday),
    dateKey: `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`,
  };
}

/** Deslocamento (ms) do fuso em relação ao UTC no instante dado. */
function offsetAt(date: Date, tz: string) {
  const p = zonedParts(date, tz);
  const asUtc = Date.UTC(p.year, p.month - 1, p.day, p.hour, p.minute, date.getUTCSeconds());
  return asUtc - Math.floor(date.getTime() / 1000) * 1000;
}

/** Instante UTC correspondente a um horário de parede no fuso `tz` (trata horário de verão). */
export function zonedToUtc(year: number, month: number, day: number, hour: number, minute: number, tz: string): Date {
  const guess = Date.UTC(year, month - 1, day, hour, minute);
  let utc = guess - offsetAt(new Date(guess), tz);
  utc = guess - offsetAt(new Date(utc), tz); // segunda passada: perto da virada do DST o primeiro chute erra 1 h
  return new Date(utc);
}

/** Minutos desde 00:00 do dia local (no fuso da clínica). */
export function minutesInZone(date: Date, tz: string) {
  const p = zonedParts(date, tz);
  return p.hour * 60 + p.minute;
}

/** Soma dias a um calendário (y-m-d) sem passar por fuso nenhum. */
export function addCalendarDays(dateKey: string, n: number): string {
  const [y, m, d] = dateKey.split("-").map(Number);
  const t = new Date(Date.UTC(y, m - 1, d + n));
  return `${t.getUTCFullYear()}-${String(t.getUTCMonth() + 1).padStart(2, "0")}-${String(t.getUTCDate()).padStart(2, "0")}`;
}

/** Chave da segunda-feira da semana (no fuso da clínica) que contém o instante. */
export function mondayKey(date: Date, tz: string): string {
  const p = zonedParts(date, tz);
  return addCalendarDays(p.dateKey, -p.weekday);
}

/** Meia-noite (início) de um dia-chave, como instante UTC, no fuso da clínica. */
export function dayStartUtc(dateKey: string, tz: string): Date {
  const [y, m, d] = dateKey.split("-").map(Number);
  return zonedToUtc(y, m, d, 0, 0, tz);
}

export function dayOfKey(dateKey: string) {
  return Number(dateKey.slice(8, 10));
}

/** "2026-09-14T11:30" (valor de um input datetime-local) no fuso da clínica → instante UTC. */
export function localInputToUtc(value: string, tz: string): Date {
  const [datePart, timePart = "00:00"] = value.split("T");
  const [y, m, d] = datePart.split("-").map(Number);
  const [h, mi] = timePart.split(":").map(Number);
  return zonedToUtc(y, m, d, h, mi, tz);
}

/** Instante UTC → valor de input datetime-local no fuso da clínica. */
export function utcToLocalInput(date: Date, tz: string): string {
  const p = zonedParts(date, tz);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${p.year}-${pad(p.month)}-${pad(p.day)}T${pad(p.hour)}:${pad(p.minute)}`;
}

/** Formata um instante como "dd/mm/aaaa, HH:MM" no fuso da clínica. */
export function formatInZone(date: Date, tz: string, opts: Intl.DateTimeFormatOptions = {}) {
  return new Intl.DateTimeFormat("pt-BR", { timeZone: tz, ...opts }).format(date);
}
