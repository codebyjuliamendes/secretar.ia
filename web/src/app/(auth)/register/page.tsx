"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { ApiError, api, errorMessage } from "@/lib/api";
import { Alert, Button, Field, Input } from "@/components/ui/primitives";

const initial = { name: "", email: "", password: "", clinicName: "", whatsapp: "" };

export default function RegisterPage() {
  const router = useRouter();
  const [form, setForm] = useState(initial);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const set = (k: keyof typeof initial) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.target.value });

  function validate() {
    const errs: Record<string, string> = {};
    if (form.name.trim().length < 2) errs.name = "Informe seu nome.";
    if (!/^\S+@\S+\.\S+$/.test(form.email)) errs.email = "Informe um e-mail válido.";
    if (form.password.length < 8 || /^\d+$/.test(form.password) || /^[a-zA-Z]+$/.test(form.password))
      errs.password = "Mínimo de 8 caracteres, combinando letras e números.";
    if (form.clinicName.trim().length < 2) errs.clinicName = "Informe o nome da clínica.";
    if (form.whatsapp.replace(/\D/g, "").length < 10) errs.whatsapp = "Informe o WhatsApp com DDD.";
    setFieldErrors(errs);
    return Object.keys(errs).length === 0;
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!validate()) return;
    setLoading(true);
    try {
      await api.post("auth/register", form);
      router.replace("/app?welcome=1");
    } catch (err) {
      if (err instanceof ApiError && err.details?.length) {
        setFieldErrors(Object.fromEntries(err.details.map((d) => [d.field, d.message])));
      }
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <h1 className="text-xl font-semibold">Criar conta</h1>
      <p className="mt-1 text-sm text-muted">Comece no plano gratuito, sem cartão de crédito. Planos pagos são liberados pela equipe Secretar.ia.</p>
      <form onSubmit={onSubmit} className="mt-6 space-y-4" noValidate>
        <Field label="Seu nome" htmlFor="name" required error={fieldErrors.name}>
          <Input id="name" autoComplete="name" value={form.name} onChange={set("name")} />
        </Field>
        <Field label="E-mail" htmlFor="email" required error={fieldErrors.email}>
          <Input id="email" type="email" autoComplete="email" value={form.email} onChange={set("email")} />
        </Field>
        <Field label="Senha" htmlFor="password" required error={fieldErrors.password} hint="Mínimo de 8 caracteres com letras e números.">
          <Input id="password" type="password" autoComplete="new-password" value={form.password} onChange={set("password")} />
        </Field>
        <Field label="Nome da clínica" htmlFor="clinicName" required error={fieldErrors.clinicName}>
          <Input id="clinicName" autoComplete="organization" value={form.clinicName} onChange={set("clinicName")} />
        </Field>
        <Field label="WhatsApp da clínica" htmlFor="whatsapp" required error={fieldErrors.whatsapp} hint="Número que os pacientes usam para falar com a clínica.">
          <Input id="whatsapp" inputMode="tel" placeholder="(81) 99999-8888" value={form.whatsapp} onChange={set("whatsapp")} />
        </Field>
        {error && <Alert tone="danger">{error}</Alert>}
        <Button type="submit" className="w-full" loading={loading}>
          Criar conta
        </Button>
      </form>
      <p className="mt-4 text-center text-sm text-muted">
        Já tem conta?{" "}
        <Link href="/login" className="text-primary hover:underline">
          Entrar
        </Link>
      </p>
    </>
  );
}
