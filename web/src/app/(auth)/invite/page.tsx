"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState, type FormEvent } from "react";
import { Alert, Button, Field, Input, Skeleton } from "@/components/ui/primitives";
import { ApiError, api, errorMessage } from "@/lib/api";
import { ROLE_LABEL } from "@/lib/format";
import type { InviteInfo, Me } from "@/lib/types";

function InviteForm() {
  const params = useSearchParams();
  const router = useRouter();
  const token = params.get("token") ?? "";
  const [info, setInfo] = useState<InviteInfo | null>(null);
  const [me, setMe] = useState<Me | null | undefined>(undefined); // undefined = ainda não sabemos
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!token) return;
    let alive = true;
    (async () => {
      try {
        const i = await api.get<InviteInfo>(`auth/invites/${encodeURIComponent(token)}`);
        if (!alive) return;
        setInfo(i);
        setName(i.name);
      } catch (err) {
        if (alive) setError(errorMessage(err));
      }
      try {
        const m = await api.get<Me>("auth/me");
        if (alive) setMe(m);
      } catch {
        if (alive) setMe(null);
      }
    })();
    return () => {
      alive = false;
    };
  }, [token]);

  async function accept(e?: FormEvent) {
    e?.preventDefault();
    if (info && !info.userExists && password !== confirm) return setError("As senhas não coincidem.");
    setError(null);
    setLoading(true);
    try {
      const body = info?.userExists ? { token } : { token, name, password };
      const r = await api.post<{ tenantId: string }>("auth/invites/accept", body);
      router.replace(`/app/${r.tenantId}`);
    } catch (err) {
      if (err instanceof ApiError && err.code === "invite_login_required") {
        setError(`Entre com a conta ${info?.email} para aceitar este convite.`);
      } else {
        setError(errorMessage(err));
      }
    } finally {
      setLoading(false);
    }
  }

  if (!token) {
    return <Alert tone="danger" title="Link inválido">Este link de convite está incompleto. Peça um novo à clínica.</Alert>;
  }
  if (error && !info) {
    return (
      <>
        <Alert tone="danger" title="Convite indisponível">{error}</Alert>
        <p className="mt-4 text-sm text-muted"><Link href="/login" className="text-primary hover:underline">Ir para o login</Link></p>
      </>
    );
  }
  if (!info || me === undefined) return <Skeleton className="h-40" />;

  const loggedAsInvitee = me?.email.toLowerCase() === info.email.toLowerCase();
  const nextUrl = `/login?next=${encodeURIComponent(`/invite?token=${token}`)}`;

  return (
    <>
      <h1 className="text-xl font-semibold">Convite para {info.clinicName}</h1>
      <p className="mt-1 text-sm text-muted">
        Você foi convidado(a) como <span className="font-medium text-foreground">{ROLE_LABEL[info.role]}</span> usando o e-mail{" "}
        <span className="font-medium text-foreground">{info.email}</span>.
      </p>

      {info.userExists ? (
        <div className="mt-6 space-y-4">
          {loggedAsInvitee ? (
            <>
              <p className="text-sm text-muted">Você já está conectado(a) com este e-mail. Confirme para entrar na equipe.</p>
              {error && <Alert tone="danger">{error}</Alert>}
              <Button className="w-full" loading={loading} onClick={() => accept()}>Aceitar convite</Button>
            </>
          ) : (
            <>
              <Alert tone="info">
                Este e-mail já tem uma conta na Secretar.ia. Entre com ela para aceitar o convite
                {me ? ` (você está conectado(a) como ${me.email})` : ""}.
              </Alert>
              <Button className="w-full" onClick={() => router.push(nextUrl)}>Entrar com {info.email}</Button>
            </>
          )}
        </div>
      ) : (
        <form onSubmit={accept} className="mt-6 space-y-4" noValidate>
          <Field label="Seu nome" htmlFor="name" required>
            <Input id="name" autoComplete="name" required value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
          <Field label="Crie uma senha" htmlFor="password" required hint="Mínimo de 8 caracteres com letras e números.">
            <Input id="password" type="password" autoComplete="new-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
          </Field>
          <Field label="Confirmar senha" htmlFor="confirm" required>
            <Input id="confirm" type="password" autoComplete="new-password" required value={confirm} onChange={(e) => setConfirm(e.target.value)} />
          </Field>
          {error && <Alert tone="danger">{error}</Alert>}
          <Button type="submit" className="w-full" loading={loading}>Criar conta e entrar na equipe</Button>
        </form>
      )}
    </>
  );
}

export default function InvitePage() {
  return (
    <Suspense fallback={null}>
      <InviteForm />
    </Suspense>
  );
}
