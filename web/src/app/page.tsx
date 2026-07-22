import Link from "next/link";

export default function Home() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center p-24 relative overflow-hidden">
      {/* Background decoration */}
      <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-pink-500/10 rounded-full blur-3xl -z-10"></div>
      <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-purple-500/10 rounded-full blur-3xl -z-10"></div>
      
      <div className="z-10 text-center max-w-2xl glass p-12 rounded-3xl shadow-2xl">
        <h1 className="text-4xl font-extrabold tracking-tight mb-4 text-transparent bg-clip-text bg-gradient-to-r from-pink-400 to-purple-400">
          Aesthetics AI Platform
        </h1>
        <p className="text-muted-foreground text-lg mb-8">
          Escolha o painel para realizar o login no sistema. Em produção, isso seria redirecionado via autenticação.
        </p>
        
        <div className="flex gap-6 justify-center">
          <Link href="/admin" className="px-6 py-3 rounded-lg bg-card border border-border hover:border-pink-500 transition-colors shadow-sm font-semibold">
            Login Master Admin
          </Link>
          <Link href="/clinic" className="px-6 py-3 rounded-lg bg-pink-600 hover:bg-pink-700 transition-colors shadow-sm font-semibold text-white">
            Login Clínica (Tenant)
          </Link>
        </div>
      </div>
    </div>
  );
}
