export type PlatformRole = "USER" | "SUPER_ADMIN";
export type TenantRole = "OWNER" | "MANAGER" | "STAFF";
export type TenantStatus = "PENDING" | "ACTIVE" | "PAST_DUE" | "CANCELED" | "SUSPENDED";
export type Plan = "BASIC" | "PRO" | "PREMIUM" | "ENTERPRISE";
export type Tone = "acolhedor" | "objetivo" | "formal";
export type AppointmentStatus = "PENDING" | "CONFIRMED" | "COMPLETED" | "CANCELED" | "NO_SHOW";

export interface MembershipSummary {
  tenantId: string;
  role: TenantRole;
  tenant: {
    id: string;
    name: string;
    status: TenantStatus;
    plan: Plan;
    whatsappConnected: boolean;
  };
}

export interface Me {
  id: string;
  email: string;
  name: string;
  platformRole: PlatformRole;
  emailVerified: boolean;
  memberships: MembershipSummary[];
}

export interface TenantSummary {
  id: string;
  name: string;
  whatsapp: string;
  whatsappConnected: boolean;
  status: TenantStatus;
  plan: Plan;
  timezone: string;
  niche: NicheInfo;
  createdAt: string;
  role: TenantRole;
  unreadNotifications: number;
}

/** Vocabulário do nicho escolhido pelo admin (paciente/cliente/tutor…). */
export interface NicheInfo {
  key: string;
  label: string;
  person: string;
  people: string;
  appointment: string;
}

export interface PlanLimits {
  plan: Plan;
  label: string;
  priceFrom: boolean;
  aiMessagesPerMonth: number;
  maxPatients: number;
  maxMembers: number;
  upsellCampaigns: boolean;
  mediaUnderstanding: boolean;
  knowledgeBase: boolean;
  maxKnowledgeDocuments: number; // -1 = ilimitado
  priceCentsMonth: number;
}

/** O que a clínica pode usar agora (recursos do plano contratado). */
export interface FeatureAccess {
  featurePlan: Plan;
  media: boolean;
  knowledge: boolean;
  maxKnowledgeDocuments: number;
}

export interface TenantSettings extends Omit<TenantSummary, "role" | "unreadNotifications"> {
  prompt: string;
  tone: Tone;
  prices: string | null;
  businessHours: string | null;
  upsellEnabled: boolean;
  upsellMessage: string | null;
  upsellDays: number;
  slotMinutes: number;
  features: Record<string, boolean>;
  featureAccess: FeatureAccess;
  planLimits: PlanLimits;
}

export interface Usage {
  period: string;
  aiMessages: { used: number; limit: number };
  patients: { used: number; limit: number };
  members: { used: number; limit: number };
  knowledgeDocuments: { used: number; limit: number };
}

export interface Dashboard {
  periodDays: number;
  kpis: {
    patientsTotal: number;
    patientsNew: number;
    patientsNewPrev: number;
    appointmentsCreated: number;
    appointmentsCreatedPrev: number;
    appointmentsPending: number;
    appointmentsUpcoming: number;
    appointmentsByAI: number;
    revenueCompletedCents: number;
    revenueFromAICents: number;
    humanHandoffs: number;
    unreadNotifications: number;
    aiMessages: number;
    aiDegraded: number;
    aiAvgResponseMs: number;
  };
  series: { day: string; appointments: number; messages: number }[];
  intents: { intent: string; count: number }[];
  recentAppointments: {
    id: string;
    patientName: string;
    service: string;
    date: string;
    status: AppointmentStatus;
    source: string;
  }[];
  usage: Usage;
}

export interface Service {
  id: string;
  name: string;
  durationMin: number;
  priceCents: number | null;
  description: string | null;
  active: boolean;
  sortOrder: number;
}

export interface AvailabilityRule {
  weekday: number; // 0 = segunda ... 6 = domingo
  start: string; // HH:MM
  end: string; // HH:MM
}

export interface ExternalBusy {
  id: string;
  summary: string | null;
  start: string;
  end: string;
  allDay: boolean;
}

export interface CalendarData {
  timezone: string;
  slotMinutes: number;
  rules: AvailabilityRule[];
  /** Compromissos criados direto no Google Calendar da clínica (bloqueiam horários da IA). */
  external: ExternalBusy[];
  appointments: {
    id: string;
    service: string;
    start: string;
    end: string;
    status: AppointmentStatus;
    source: string;
    patient: { id: string; name: string | null; phone: string } | null;
  }[];
}

export interface Appointment {
  id: string;
  service: string;
  serviceId: string | null;
  date: string;
  durationMin: number;
  end: string;
  status: AppointmentStatus;
  priceCents: number | null;
  notes: string | null;
  source: string;
  externalEventId?: string | null;
  createdAt: string;
  patient: { id: string; name: string | null; phone: string } | null;
}

export interface Patient {
  id: string;
  name: string | null;
  phone: string;
  notes: string | null;
  marketingOptOut: boolean;
  createdAt: string;
  appointmentCount?: number;
  lastAppointmentAt?: string | null;
}

export interface PatientDetail extends Patient {
  appointments: { id: string; service: string; date: string; status: AppointmentStatus }[];
  conversation: { role: "USER" | "ASSISTANT"; content: string; createdAt: string }[];
}

export interface Paginated<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface Notification {
  id: string;
  type: "HUMAN_HANDOFF" | "APPOINTMENT_REQUESTED" | "APPOINTMENT_CANCELED" | "BILLING" | "SYSTEM";
  title: string;
  body: string;
  phone: string | null;
  readAt: string | null;
  createdAt: string;
}

export interface Member {
  id: string;
  role: TenantRole;
  createdAt: string;
  user: { id: string; name: string; email: string; emailVerified: boolean } | null;
}

export interface TeamInvite {
  id: string;
  email: string;
  name: string;
  role: TenantRole;
  expiresAt: string;
  createdAt: string;
}

export interface InviteInfo {
  clinicName: string;
  email: string;
  name: string;
  role: TenantRole;
  userExists: boolean;
  expiresAt: string;
}

export interface AuditEntry {
  id: string;
  action: string;
  resourceType: string;
  resourceId: string | null;
  actor: { id: string; name: string; email: string } | null;
  metadata: Record<string, unknown> | null;
  createdAt: string;
}

export interface Billing {
  status: TenantStatus;
  plan: Plan;
  subscriptionId: string | null;
  hasCustomer: boolean;
  checkoutEnabled: boolean;
  purchasablePlans: Plan[];
  usage: Usage;
  plans: PlanLimits[];
  sales: SalesContact;
}

export interface SalesContact {
  whatsapp: string; // só dígitos com DDI; vazio = não configurado
  name: string;
}

export interface PublicConfig {
  plans: PlanLimits[];
  niches: { key: string; label: string }[];
  sales: SalesContact;
}

export type KnowledgeSource = "text" | "pdf" | "url" | "file";

export interface KnowledgeDocument {
  id: string;
  title: string;
  chars: number;
  chunkCount: number;
  embedded: boolean;
  source: KnowledgeSource;
  sourceRef: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface GoogleCalendarStatus {
  available: boolean;
  connected: boolean;
  accountEmail: string | null;
  calendarId: string | null;
  syncEnabled: boolean;
  lastSyncAt: string | null;
  lastError: string | null;
  lastPullAt: string | null;
  pushActive: boolean;
  externalEvents: number;
}

export interface WhatsAppStatus {
  instance: string | null;
  connected: boolean;
  state: string;
  qrCode: string | null;
}

export interface AdminTenant {
  id: string;
  name: string;
  whatsapp: string;
  status: TenantStatus;
  plan: Plan;
  niche: string;
  whatsappConnected: boolean;
  createdAt: string;
  appointmentCount: number;
  patientCount: number;
  memberCount: number;
}

export interface AdminOverview {
  tenants: { total: number; active: number; pending: number; pastDue: number; inactive: number };
  mrrCents: number;
  aiMessagesThisMonth: number;
  failedJobs: number;
}

export interface AdminJob {
  id: string;
  name: string;
  status: "PENDING" | "RUNNING" | "COMPLETED" | "FAILED";
  retries: number;
  maxRetries: number;
  runAt: string;
  error: string | null;
  updatedAt: string;
}
