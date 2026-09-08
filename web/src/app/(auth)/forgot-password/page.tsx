"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { api, errorMessage } from "@/lib/api";
import { Alert, Button, Field, Input } from "@/components/ui/primitives";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await api.post("auth/forgot-password", { email });
      setSent(true);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <h1 className="text-xl font-semibold">Recuperar senha</h1>
      <p className="mt-1 text-sm text-muted">Enviaremos um link para redefinir sua senha.</p>
      {sent ? (
        <div className="mt-6 space-y-4">
          <Alert tone="success" title="Verifique seu e-mail">
            Se existir uma conta para {email}, você receberá um link válido por 1 hora.
          </Alert>
          <Link href="/login" className="block text-center text-sm text-primary hover:underline">
            Voltar ao login
          </Link>
        </div>
      ) : (
        <form onSubmit={onSubmit} className="mt-6 space-y-4" noValidate>
          <Field label="E-mail" htmlFor="email" required>
            <Input id="email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
          </Field>
          {error && <Alert tone="danger">{error}</Alert>}
          <Button type="submit" className="w-full" loading={loading}>
            Enviar link
          </Button>
          <Link href="/login" className="block text-center text-sm text-primary hover:underline">
            Voltar ao login
          </Link>
        </form>
      )}
    </>
  );
}
