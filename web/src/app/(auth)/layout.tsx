import Link from "next/link";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center px-4 py-10">
      <Link href="/" className="mb-8 text-xl font-semibold tracking-tight">
        Secretar<span className="text-primary">.ia</span>
      </Link>
      <div className="w-full max-w-md rounded-xl border border-border bg-surface p-6 shadow-sm sm:p-8">{children}</div>
      <p className="mt-6 text-center text-xs text-muted">
        <Link href="/privacidade" className="hover:underline">Privacidade</Link> · <Link href="/termos" className="hover:underline">Termos</Link>
      </p>
    </main>
  );
}
