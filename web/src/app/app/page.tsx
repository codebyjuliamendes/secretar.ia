"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { useSession } from "@/components/session";
import { Button, EmptyState, LinkButton } from "@/components/ui/primitives";

export default function AppIndex() {
  const { me, logout } = useSession();
  const router = useRouter();
  const first = me.memberships[0];

  useEffect(() => {
    if (first) router.replace(`/app/${first.tenantId}`);
  }, [first, router]);

  if (first) return null;
  return (
    <main className="mx-auto max-w-lg p-8">
      <EmptyState
        title="Você ainda não faz parte de nenhuma clínica"
        description={
          me.platformRole === "SUPER_ADMIN"
            ? "Sua conta é de administração da plataforma. Acesse o painel administrativo."
            : "Peça a um responsável da clínica para convidar seu e-mail, ou crie uma nova conta de clínica."
        }
        action={
          <div className="flex gap-2">
            {me.platformRole === "SUPER_ADMIN" && <LinkButton href="/admin">Painel administrativo</LinkButton>}
            <Button variant="secondary" onClick={logout}>
              Sair
            </Button>
          </div>
        }
      />
    </main>
  );
}
