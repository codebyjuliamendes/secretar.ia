import { LinkButton } from "@/components/ui/primitives";

export default function NotFound() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-4 p-6 text-center">
      <p className="text-sm font-medium uppercase tracking-widest text-primary">404</p>
      <h1 className="text-2xl font-semibold">Página não encontrada</h1>
      <p className="max-w-md text-sm text-muted">O endereço pode estar errado ou você não tem acesso a este recurso.</p>
      <LinkButton href="/app">Ir para o painel</LinkButton>
    </main>
  );
}
