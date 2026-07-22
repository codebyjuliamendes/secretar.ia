export default function MasterAdminDashboard() {
  return (
    <div className="flex h-screen bg-background">
      {/* Sidebar */}
      <aside className="w-64 border-r border-border glass flex flex-col">
        <div className="p-6 border-b border-border">
          <h2 className="text-xl font-bold text-pink-500 tracking-tight">SuperAdmin</h2>
        </div>
        <nav className="flex-1 p-4 space-y-2">
          <a href="#" className="block px-4 py-2 rounded-md bg-muted text-foreground font-medium">Dashboard Global</a>
          <a href="#" className="block px-4 py-2 rounded-md hover:bg-muted/50 text-muted-foreground transition-colors">Clínicas (Tenants)</a>
          <a href="#" className="block px-4 py-2 rounded-md hover:bg-muted/50 text-muted-foreground transition-colors">Faturamento (Asaas)</a>
          <a href="#" className="block px-4 py-2 rounded-md hover:bg-muted/50 text-muted-foreground transition-colors">Infra & N8n</a>
        </nav>
      </aside>

      {/* Main Content */}
      <main className="flex-1 p-8 overflow-y-auto">
        <header className="flex justify-between items-center mb-8">
          <div>
            <h1 className="text-3xl font-bold">Visão Geral</h1>
            <p className="text-muted-foreground">Monitoramento global da plataforma.</p>
          </div>
          <button className="px-4 py-2 bg-pink-600 hover:bg-pink-700 text-white rounded-md font-medium transition-colors">
            + Nova Clínica
          </button>
        </header>

        {/* Metric Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          <div className="glass p-6 rounded-xl border border-border">
            <h3 className="text-sm font-medium text-muted-foreground mb-2">MRR (Receita Recorrente)</h3>
            <p className="text-3xl font-bold">R$ 14.590,00</p>
            <span className="text-xs text-emerald-400 mt-2 block">+12% este mês</span>
          </div>
          <div className="glass p-6 rounded-xl border border-border">
            <h3 className="text-sm font-medium text-muted-foreground mb-2">Clínicas Ativas</h3>
            <p className="text-3xl font-bold">24</p>
            <span className="text-xs text-emerald-400 mt-2 block">+2 novos pilotos</span>
          </div>
          <div className="glass p-6 rounded-xl border border-border">
            <h3 className="text-sm font-medium text-muted-foreground mb-2">Requisições IA (30d)</h3>
            <p className="text-3xl font-bold">142.304</p>
            <span className="text-xs text-emerald-400 mt-2 block">Saudável</span>
          </div>
        </div>

        {/* Table Mockup */}
        <div className="glass rounded-xl border border-border overflow-hidden">
          <div className="p-6 border-b border-border">
            <h2 className="text-lg font-semibold">Clínicas Recentes</h2>
          </div>
          <table className="w-full text-left">
            <thead className="bg-muted/30">
              <tr>
                <th className="p-4 font-medium text-muted-foreground">Nome</th>
                <th className="p-4 font-medium text-muted-foreground">Status N8n</th>
                <th className="p-4 font-medium text-muted-foreground">Plano</th>
                <th className="p-4 font-medium text-muted-foreground">Agendamentos (30d)</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              <tr className="hover:bg-muted/20 transition-colors">
                <td className="p-4 font-medium">Clínica Harmonize</td>
                <td className="p-4"><span className="px-2 py-1 bg-emerald-500/20 text-emerald-400 rounded-full text-xs">Online</span></td>
                <td className="p-4">Piloto (Dia 4)</td>
                <td className="p-4">12</td>
              </tr>
              <tr className="hover:bg-muted/20 transition-colors">
                <td className="p-4 font-medium">Dra. Fernanda Estética</td>
                <td className="p-4"><span className="px-2 py-1 bg-emerald-500/20 text-emerald-400 rounded-full text-xs">Online</span></td>
                <td className="p-4">Pro (R$ 597)</td>
                <td className="p-4">84</td>
              </tr>
              <tr className="hover:bg-muted/20 transition-colors">
                <td className="p-4 font-medium">Pele & Cia</td>
                <td className="p-4"><span className="px-2 py-1 bg-rose-500/20 text-rose-400 rounded-full text-xs">Desconectado</span></td>
                <td className="p-4">Pro (R$ 597)</td>
                <td className="p-4">0</td>
              </tr>
            </tbody>
          </table>
        </div>
      </main>
    </div>
  );
}
