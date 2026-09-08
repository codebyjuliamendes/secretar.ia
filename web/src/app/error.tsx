"use client";

import { useEffect } from "react";
import { Button, LinkButton } from "@/components/ui/primitives";

export default function ErrorPage({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error("[ui-error]", error.digest ?? "", error.message);
  }, [error]);
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-4 p-6 text-center">
      <h1 className="text-2xl font-semibold">Algo deu errado</h1>
      <p className="max-w-md text-sm text-muted">
        Ocorreu um erro inesperado ao exibir esta página. Você pode tentar novamente ou voltar ao início.
        {error.digest && <span className="mt-2 block text-xs">Código: {error.digest}</span>}
      </p>
      <div className="flex gap-2">
        <Button onClick={reset}>Tentar novamente</Button>
        <LinkButton href="/app" variant="secondary">
          Ir para o painel
        </LinkButton>
      </div>
    </main>
  );
}
