import type { AppointmentStatus, Plan, TenantRole, TenantStatus } from "./types";

export const brl = (cents: number) =>
  (cents / 100).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });

export const formatDate = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric" }) : "—";

export const formatDateTime = (iso: string | null | undefined) =>
  iso
    ? new Date(iso).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" })
    : "—";

export const formatRelative = (iso: string) => {
  const diff = Date.now() - new Date(iso).getTime();
  const min = Math.round(diff / 60000);
  if (min < 1) return "agora";
  if (min < 60) return `${min} min atrás`;
  const h = Math.round(min / 60);
  if (h < 24) return `${h} h atrás`;
  const d = Math.round(h / 24);
  return d === 1 ? "ontem" : `${d} dias atrás`;
};

export const formatPhone = (digits: string) => {
  const m = digits.match(/^55(\d{2})(\d{4,5})(\d{4})$/);
  return m ? `+55 (${m[1]}) ${m[2]}-${m[3]}` : `+${digits}`;
};

export const STATUS_LABEL: Record<TenantStatus, string> = {
  TRIAL: "Em teste",
  ACTIVE: "Ativa",
  PAST_DUE: "Pagamento pendente",
  CANCELED: "Cancelada",
  SUSPENDED: "Suspensa",
};

export const STATUS_TONE: Record<TenantStatus, "success" | "info" | "warning" | "danger" | "neutral"> = {
  TRIAL: "info",
  ACTIVE: "success",
  PAST_DUE: "warning",
  CANCELED: "neutral",
  SUSPENDED: "danger",
};

export const APPT_LABEL: Record<AppointmentStatus, string> = {
  PENDING: "Pendente",
  CONFIRMED: "Confirmado",
  COMPLETED: "Realizado",
  CANCELED: "Cancelado",
  NO_SHOW: "Faltou",
};

export const APPT_TONE: Record<AppointmentStatus, "success" | "info" | "warning" | "danger" | "neutral"> = {
  PENDING: "warning",
  CONFIRMED: "info",
  COMPLETED: "success",
  CANCELED: "neutral",
  NO_SHOW: "danger",
};

export const ROLE_LABEL: Record<TenantRole, string> = {
  OWNER: "Proprietário(a)",
  MANAGER: "Gerente",
  STAFF: "Recepção",
};

export const PLAN_LABEL: Record<Plan, string> = {
  FREE: "Gratuito",
  BASIC: "Básico",
  PRO: "Pro",
  ENTERPRISE: "Enterprise",
};

export const INTENT_LABEL: Record<string, string> = {
  AGENDAR: "Agendar",
  CANCELAR: "Cancelar",
  INFO: "Informações",
  HUMANO: "Pediu humano",
  SAUDACAO: "Saudação",
};

export const limitLabel = (n: number) => (n < 0 ? "ilimitado" : n.toLocaleString("pt-BR"));

export function toLocalInputValue(iso?: string) {
  const d = iso ? new Date(iso) : new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
