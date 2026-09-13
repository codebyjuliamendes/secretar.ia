import { Pricing } from "@/components/pricing";
import { LinkButton } from "@/components/ui/primitives";
import { getPublicConfig } from "@/lib/server/public-config";

const FEATURES = [
  {
    title: "Atendimento 24h no WhatsApp",
    text: "A secretária virtual responde dúvidas, informa preços e horários e registra pedidos de agendamento com base nas regras da sua clínica.",
  },
  {
    title: "Agenda e pacientes em um só lugar",
    text: "Cada conversa vira um paciente no CRM. Pedidos de agendamento chegam como pendentes para a equipe confirmar.",
  },
  {
    title: "Retenção automática",
    text: "Pacientes com procedimentos periódicos vencidos recebem um convite de retorno, sem duplicidade e respeitando seu plano.",
  },
  {
    title: "Transbordo humano",
    text: "Quando o paciente pede uma pessoa, a equipe é notificada na inbox e assume a conversa.",
  },
];

export default async function Home() {
  const config = await getPublicConfig();
  return (
    <main className="mx-auto flex min-h-screen max-w-5xl flex-col px-6 py-10">
      <header className="flex items-center justify-between">
        <span className="text-lg font-semibold tracking-tight">
          Secretar<span className="text-primary">.ia</span>
        </span>
        <nav className="flex gap-2">
          <LinkButton href="/login" variant="secondary" size="sm">
            Entrar
          </LinkButton>
          <LinkButton href="/register" size="sm">
            Criar conta
          </LinkButton>
        </nav>
      </header>

      <section className="my-auto py-16 text-center">
        <p className="mb-3 text-sm font-medium uppercase tracking-widest text-primary">Para clínicas de saúde e estética</p>
        <h1 className="mx-auto max-w-3xl text-4xl font-semibold tracking-tight sm:text-5xl">
          Sua secretária virtual no WhatsApp, com agenda, CRM e retenção.
        </h1>
        <p className="mx-auto mt-5 max-w-2xl text-lg text-muted">
          Cadastre a clínica, conecte o WhatsApp lendo um QR Code e deixe a IA cuidar do primeiro atendimento. Sua equipe
          confirma os agendamentos e assume quando o paciente pedir.
        </p>
        <div className="mt-8 flex justify-center gap-3">
          <LinkButton href="/register">Criar conta</LinkButton>
          <LinkButton href="/login" variant="secondary">
            Já tenho conta
          </LinkButton>
        </div>
      </section>

      <section className="grid gap-4 sm:grid-cols-2" aria-label="Funcionalidades">
        {FEATURES.map((f) => (
          <div key={f.title} className="rounded-xl border border-border bg-surface p-5">
            <h2 className="font-semibold">{f.title}</h2>
            <p className="mt-1 text-sm text-muted">{f.text}</p>
          </div>
        ))}
      </section>

      <Pricing config={config} people="pacientes" />

      <footer className="mt-12 text-center text-xs text-muted">© {new Date().getFullYear()} Secretar.ia</footer>
    </main>
  );
}
