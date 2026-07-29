'use client';

import { useState, useEffect } from 'react';

interface Tenant {
  id: string;
  name: string;
  whatsapp: string;
  status: string;
  appointmentCount: number;
  patientCount: number;
  createdAt: string;
}

export default function MasterAdminDashboard() {
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [loading, setLoading] = useState(true);
  const [isModalOpen, setIsModalOpen] = useState(false);
  
  // Form para nova clínica
  const [name, setName] = useState('');
  const [whatsapp, setWhatsapp] = useState('');
  const [prompt, setPrompt] = useState('Você é uma secretária de clínica de estética elegante...');
  const [prices, setPrices] = useState('Botox: R$ 990, Preenchimento: R$ 1200');
  const [businessHours, setBusinessHours] = useState('09:00 - 18:00');

  useEffect(() => {
    fetchTenants();
  }, []);

  const fetchTenants = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/admin/tenants');
      const data = await res.json();
      if (data.success) {
        setTenants(data.tenants);
      }
    } catch (err) {
      console.error("Falha ao buscar clínicas da API Python. Usando mocks offline.", err);
      // Fallback Mocks para o GitHub Showcase funcionar offline
      setTenants([
        {
          id: "1",
          name: "Clínica Harmonize",
          whatsapp: "5581999998888",
          status: "ACTIVE",
          appointmentCount: 84,
          patientCount: 142,
          createdAt: new Date().toISOString()
        },
        {
          id: "2",
          name: "Dra. Fernanda Estética",
          whatsapp: "5581988887777",
          status: "ACTIVE",
          appointmentCount: 32,
          patientCount: 64,
          createdAt: new Date().toISOString()
        },
        {
          id: "3",
          name: "Pele & Cia",
          whatsapp: "5581977776666",
          status: "PAST_DUE",
          appointmentCount: 0,
          patientCount: 12,
          createdAt: new Date().toISOString()
        }
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleCreateTenant = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const res = await fetch('http://localhost:8000/api/admin/tenants', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, whatsapp, prompt, prices, businessHours })
      });
      const data = await res.json();
      if (data.success) {
        alert("Clínica cadastrada com sucesso!");
        setIsModalOpen(false);
        fetchTenants();
      }
    } catch (err) {
      alert("Erro ao conectar com o backend em Python. Clínica criada localmente (mock).");
      const newMock: Tenant = {
        id: Math.random().toString(),
        name,
        whatsapp,
        status: "TRIAL",
        appointmentCount: 0,
        patientCount: 0,
        createdAt: new Date().toISOString()
      };
      setTenants([newMock, ...tenants]);
      setIsModalOpen(false);
    }
  };

  const activeCount = tenants.filter(t => t.status === 'ACTIVE').length;
  const trialCount = tenants.filter(t => t.status === 'TRIAL').length;
  const mrr = activeCount * 597; // R$ 597 por licença ativa

  return (
    <div className="flex h-screen bg-background text-foreground">
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
            <p className="text-muted-foreground">Monitoramento global da plataforma (Conectado ao Backend Python).</p>
          </div>
          <button 
            onClick={() => setIsModalOpen(true)}
            className="px-4 py-2 bg-pink-600 hover:bg-pink-700 text-white rounded-md font-medium transition-colors cursor-pointer"
          >
            + Nova Clínica
          </button>
        </header>

        {/* Metric Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          <div className="glass p-6 rounded-xl border border-border">
            <h3 className="text-sm font-medium text-muted-foreground mb-2">MRR (Receita Recorrente)</h3>
            <p className="text-3xl font-bold text-pink-400">R$ {mrr.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}</p>
            <span className="text-xs text-emerald-400 mt-2 block">+12% este mês</span>
          </div>
          <div className="glass p-6 rounded-xl border border-border">
            <h3 className="text-sm font-medium text-muted-foreground mb-2">Clínicas Ativas</h3>
            <p className="text-3xl font-bold">{activeCount}</p>
            <span className="text-xs text-muted-foreground mt-2 block">{trialCount} em período de testes (Trial)</span>
          </div>
          <div className="glass p-6 rounded-xl border border-border">
            <h3 className="text-sm font-medium text-muted-foreground mb-2">Total de Clientes Cadastrados</h3>
            <p className="text-3xl font-bold">{tenants.length}</p>
            <span className="text-xs text-emerald-400 mt-2 block">Saudável</span>
          </div>
        </div>

        {/* Table */}
        <div className="glass rounded-xl border border-border overflow-hidden">
          <div className="p-6 border-b border-border">
            <h2 className="text-lg font-semibold">Clínicas Recentes</h2>
          </div>
          <table className="w-full text-left">
            <thead className="bg-muted/30">
              <tr>
                <th className="p-4 font-medium text-muted-foreground">Nome</th>
                <th className="p-4 font-medium text-muted-foreground">WhatsApp</th>
                <th className="p-4 font-medium text-muted-foreground">Status</th>
                <th className="p-4 font-medium text-muted-foreground">Pacientes</th>
                <th className="p-4 font-medium text-muted-foreground">Consultas</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {loading ? (
                <tr>
                  <td colSpan={5} className="p-4 text-center text-muted-foreground">Carregando clínicas...</td>
                </tr>
              ) : tenants.length === 0 ? (
                <tr>
                  <td colSpan={5} className="p-4 text-center text-muted-foreground">Nenhuma clínica cadastrada.</td>
                </tr>
              ) : (
                tenants.map((t) => (
                  <tr key={t.id} className="hover:bg-muted/20 transition-colors">
                    <td className="p-4 font-medium">{t.name}</td>
                    <td className="p-4 text-sm text-muted-foreground">{t.whatsapp}</td>
                    <td className="p-4">
                      <span className={`px-2 py-1 rounded-full text-xs font-semibold ${
                        t.status === 'ACTIVE' 
                          ? 'bg-emerald-500/20 text-emerald-400' 
                          : t.status === 'TRIAL'
                          ? 'bg-blue-500/20 text-blue-400'
                          : 'bg-rose-500/20 text-rose-400'
                      }`}>
                        {t.status}
                      </span>
                    </td>
                    <td className="p-4">{t.patientCount}</td>
                    <td className="p-4">{t.appointmentCount}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Modal Nova Clínica */}
        {isModalOpen && (
          <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50">
            <div className="glass border border-border rounded-xl p-8 w-full max-w-lg shadow-2xl">
              <h2 className="text-2xl font-bold mb-6 text-pink-500">Cadastrar Nova Clínica</h2>
              <form onSubmit={handleCreateTenant} className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-muted-foreground mb-1">Nome da Clínica</label>
                  <input 
                    type="text" 
                    required 
                    value={name} 
                    onChange={e => setName(e.target.value)}
                    className="w-full bg-muted border border-border rounded-md px-3 py-2 text-foreground focus:outline-none focus:border-pink-500" 
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-muted-foreground mb-1">WhatsApp da Clínica (com DDI)</label>
                  <input 
                    type="text" 
                    placeholder="Ex: 5581999998888"
                    required 
                    value={whatsapp} 
                    onChange={e => setWhatsapp(e.target.value)}
                    className="w-full bg-muted border border-border rounded-md px-3 py-2 text-foreground focus:outline-none focus:border-pink-500" 
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-muted-foreground mb-1">Prompt Base da IA</label>
                  <textarea 
                    value={prompt} 
                    onChange={e => setPrompt(e.target.value)}
                    rows={3}
                    className="w-full bg-muted border border-border rounded-md px-3 py-2 text-foreground focus:outline-none focus:border-pink-500 text-sm" 
                  />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-muted-foreground mb-1">Preços e Serviços</label>
                    <input 
                      type="text" 
                      value={prices} 
                      onChange={e => setPrices(e.target.value)}
                      className="w-full bg-muted border border-border rounded-md px-3 py-2 text-foreground focus:outline-none focus:border-pink-500 text-sm" 
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-muted-foreground mb-1">Horário de Funcionamento</label>
                    <input 
                      type="text" 
                      value={businessHours} 
                      onChange={e => setBusinessHours(e.target.value)}
                      className="w-full bg-muted border border-border rounded-md px-3 py-2 text-foreground focus:outline-none focus:border-pink-500 text-sm" 
                    />
                  </div>
                </div>
                <div className="flex justify-end space-x-3 mt-8">
                  <button 
                    type="button"
                    onClick={() => setIsModalOpen(false)}
                    className="px-4 py-2 bg-muted hover:bg-muted/70 rounded-md font-medium transition-colors cursor-pointer"
                  >
                    Cancelar
                  </button>
                  <button 
                    type="submit"
                    className="px-4 py-2 bg-pink-600 hover:bg-pink-700 text-white rounded-md font-medium transition-colors cursor-pointer"
                  >
                    Salvar
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
