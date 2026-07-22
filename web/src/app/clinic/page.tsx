export default function ClinicWorkspace() {
  return (
    <div className="flex h-screen bg-background">
      {/* Sidebar */}
      <aside className="w-64 border-r border-border glass flex flex-col">
        <div className="p-6 border-b border-border">
          <h2 className="text-xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-pink-400 to-purple-400 tracking-tight">Clínica Harmonize</h2>
        </div>
        <nav className="flex-1 p-4 space-y-2">
          <a href="#" className="block px-4 py-2 rounded-md bg-muted text-foreground font-medium">Analytics</a>
          <a href="#" className="block px-4 py-2 rounded-md hover:bg-muted/50 text-muted-foreground transition-colors">Configurações da IA</a>
          <a href="#" className="block px-4 py-2 rounded-md hover:bg-muted/50 text-muted-foreground transition-colors flex justify-between items-center">
            Inbox Humano
            <span className="bg-pink-600 text-white text-xs px-2 py-0.5 rounded-full">3</span>
          </a>
          <a href="#" className="block px-4 py-2 rounded-md hover:bg-muted/50 text-muted-foreground transition-colors">CRM de Pacientes</a>
        </nav>
      </aside>

      {/* Main Content */}
      <main className="flex-1 p-8 overflow-y-auto">
        <header className="mb-8">
          <h1 className="text-3xl font-bold">Seu Assistente de IA</h1>
          <p className="text-muted-foreground">Desempenho da recepcionista virtual nos últimos 30 dias.</p>
        </header>

        {/* Metric Cards */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
          <div className="glass p-5 rounded-xl border border-border">
            <h3 className="text-xs font-medium text-muted-foreground uppercase mb-1">Conversas Inciadas</h3>
            <p className="text-2xl font-bold">342</p>
          </div>
          <div className="glass p-5 rounded-xl border border-border">
            <h3 className="text-xs font-medium text-muted-foreground uppercase mb-1">Agendamentos Fechados</h3>
            <p className="text-2xl font-bold text-pink-400">84</p>
            <span className="text-xs text-muted-foreground mt-1 block">Conversão: 24.5%</span>
          </div>
          <div className="glass p-5 rounded-xl border border-border">
            <h3 className="text-xs font-medium text-muted-foreground uppercase mb-1">Resgatados da Fila</h3>
            <p className="text-2xl font-bold text-purple-400">12</p>
          </div>
          <div className="glass p-5 rounded-xl border border-border">
            <h3 className="text-xs font-medium text-muted-foreground uppercase mb-1">Transferidos (Humano)</h3>
            <p className="text-2xl font-bold text-amber-400">18</p>
            <span className="text-xs text-muted-foreground mt-1 block">Tópicos complexos</span>
          </div>
        </div>

        {/* Layout Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          
          {/* Recent Appointments */}
          <div className="lg:col-span-2 glass rounded-xl border border-border p-6">
            <div className="flex justify-between items-center mb-6">
              <h2 className="text-lg font-semibold">Agendamentos Recentes (via IA)</h2>
              <button className="text-sm text-pink-500 hover:underline">Ver Agenda Completa</button>
            </div>
            
            <div className="space-y-4">
              {[
                { nome: "Amanda Silva", proc: "Toxina Botulínica", data: "Hoje, 14:00", status: "Confirmado" },
                { nome: "Beatriz Costa", proc: "Preenchimento Labial", data: "Amanhã, 10:30", status: "Confirmado" },
                { nome: "Carla Nunes", proc: "Fios de PDO", data: "Quinta, 09:00", status: "Pendente Pagamento" }
              ].map((apt, i) => (
                <div key={i} className="flex justify-between items-center p-4 bg-muted/20 rounded-lg border border-border/50">
                  <div>
                    <p className="font-medium text-foreground">{apt.nome}</p>
                    <p className="text-sm text-muted-foreground">{apt.proc} • {apt.data}</p>
                  </div>
                  <span className={`px-3 py-1 rounded-full text-xs font-medium ${
                    apt.status === 'Confirmado' ? 'bg-emerald-500/10 text-emerald-400' : 'bg-amber-500/10 text-amber-400'
                  }`}>
                    {apt.status}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* AI Settings Preview */}
          <div className="glass rounded-xl border border-border p-6 flex flex-col">
            <h2 className="text-lg font-semibold mb-4">Ajuste Rápido (IA)</h2>
            <div className="flex-1 space-y-4">
              <div>
                <label className="text-sm font-medium text-muted-foreground block mb-1">Tom de Voz</label>
                <select className="w-full bg-muted border border-border rounded-md px-3 py-2 text-sm text-foreground focus:outline-none focus:border-pink-500">
                  <option>Elegante e Sofisticado</option>
                  <option>Amigável e Empático</option>
                  <option>Clínico e Direto</option>
                </select>
              </div>
              <div>
                <label className="text-sm font-medium text-muted-foreground block mb-1">Tempo Mínimo Agendamento</label>
                <input type="text" value="24 horas" className="w-full bg-muted border border-border rounded-md px-3 py-2 text-sm text-foreground focus:outline-none focus:border-pink-500" readOnly/>
              </div>
            </div>
            <button className="w-full mt-6 py-2 bg-pink-600 hover:bg-pink-700 text-white rounded-md font-medium transition-colors">
              Salvar Alterações
            </button>
          </div>
        </div>

      </main>
    </div>
  );
}
