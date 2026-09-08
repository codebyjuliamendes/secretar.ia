"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { api, errorMessage } from "@/lib/api";
import { Alert, LinkButton, Spinner } from "@/components/ui/primitives";

function Verify() {
  const token = useSearchParams().get("token");
  const [state, setState] = useState<"loading" | "ok" | "error">(token ? "loading" : "error");
  const [message, setMessage] = useState(token ? "" : "Link de verificação incompleto.");

  useEffect(() => {
    if (!token) return;
    api
      .post("auth/verify-email", { token })
      .then(() => setState("ok"))
      .catch((err) => {
        setState("error");
        setMessage(errorMessage(err));
      });
  }, [token]);

  return (
    <div className="space-y-4 text-center">
      <h1 className="text-xl font-semibold">Verificação de e-mail</h1>
      {state === "loading" && (
        <div className="flex justify-center py-6" role="status" aria-label="Verificando">
          <Spinner className="h-6 w-6 text-primary" />
        </div>
      )}
      {state === "ok" && <Alert tone="success">E-mail confirmado com sucesso.</Alert>}
      {state === "error" && <Alert tone="danger">{message}</Alert>}
      <LinkButton href="/app">Ir para o painel</LinkButton>
    </div>
  );
}

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={null}>
      <Verify />
    </Suspense>
  );
}
