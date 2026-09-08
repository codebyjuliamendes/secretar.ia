"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState, type FormEvent } from "react";
import { api, errorMessage } from "@/lib/api";
import { Alert, Button, Field, Input } from "@/components/ui/primitives";

function ResetForm() {
  const params = useSearchParams();
  const router = useRouter();
  const token = params.get("token") ?? "";
  const welcome = params.get("welcome") === "1";
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (password !== confirm) return setError("As senhas não coincidem.");
    setError(null);
    setLoading(true);
    try {
      await api.post("auth/reset-password", { token, password });
      router.replace("/login?reset=1");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  if (!token) {
    return (
      <Alert tone="danger" title="Link inválido">
        Este link de redefinição está incompleto.{" "}
        <Link href="/forgot-password" className="underline">
          Solicite um novo.
        </Link>
      </Alert>
    );
  }

  return (
    <>
      <h1 className="text-xl font-semibold">{welcome ? "Bem-vindo(a)! Defina sua senha" : "Nova senha"}</h1>
      <p className="mt-1 text-sm text-muted">
        {welcome ? "Você foi convidado(a) para uma clínica. Crie sua senha para acessar." : "Escolha uma nova senha para sua conta."}
      </p>
      <form onSubmit={onSubmit} className="mt-6 space-y-4" noValidate>
        <Field label="Nova senha" htmlFor="password" required hint="Mínimo de 8 caracteres com letras e números.">
          <Input id="password" type="password" autoComplete="new-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
        </Field>
        <Field label="Confirmar senha" htmlFor="confirm" required>
          <Input id="confirm" type="password" autoComplete="new-password" required value={confirm} onChange={(e) => setConfirm(e.target.value)} />
        </Field>
        {error && <Alert tone="danger">{error}</Alert>}
        <Button type="submit" className="w-full" loading={loading}>
          Salvar senha
        </Button>
      </form>
    </>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={null}>
      <ResetForm />
    </Suspense>
  );
}
