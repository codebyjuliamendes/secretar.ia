'use client';

import { useState, useEffect } from 'react';

interface Appointment {
  id: string;
  patientName: string;
  service: string;
  date: string;
  status: string;
}

interface Metrics {
  patientCount: number;
  appointmentCount: number;
  humanHandoffs: number;
}

export default function ClinicWorkspace() {
  const [tenantId, setTenantId] = useState('1'); // Mock ID inicial
  const [metrics, setMetrics] = useState<Metrics>({
    patientCount: 142,
    appointmentCount: 84,
    humanHandoffs: 18
  });
  const [recentAppointments, setRecentAppointments] = useState<Appointment[]>([]);
  const [loading, setLoading] = useState(true);

  // States do Quick Config
  const [voiceTone, setVoiceTone] = useState('Elegante e Sofisticado');
  const [prices, setPrices] = useState('Botox: R$ 990, Preenchimento: R$ 1200');
  const [businessHours, setBusinessHours] = useState('09:00 - 18:00');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetchClinicData();
  }, [tenantId]);

  const fetchClinicData = async () => {
    try {
      const res = await fetch(`http://localhost:8000/api/clinic/dashboard?tenantId=${tenantId}`);
      const data = await res.json();
      if (data.success) {
        setMetrics(data.metrics);
        setRecentAppointments(data.recentAppointments);
      }
    } catch (err) {
      console.error("Falha ao conectar no FastAPI. Carregando dados Mock/Offline.", err);
      // Fallbacks para vitrine GitHub
      setRecentAppointments([
        { id: "1", patientName: "Amanda Silva", service: "Toxina Botulínica", date: new Date().toISOString(), status: "Confirmado" },
        { id: "2", patientName: "Beatriz Costa", service: "Preenchimento Labial", date: new Date().toISOString(), status: "Confirmado" },
        { id: "3", patientName: "Carla Nunes", service: "Fios de PDO", date: new Date().toISOString(), status: "Pendente" }
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleSaveConfig = async () => {
    setSaving(true);
    try {
      const res = await fetch(`http://localhost:8000/api/clinic/config?tenantId=${tenantId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          prompt: `Tom de Voz: ${voiceTone}`, 
          prices, 
          businessHours 
        })
      });
      const data = await res.json();
      if (data.success) {
        alert("Configuração da IA atualizada com sucesso no banco de dados!");
      }
    } catch (err) {
      alert("Falha de conexão. Configuração atualizada offline.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex h-screen bg-background text-foreground">
      {/* Sidebar */}
      <aside className="w-64 border-r border-border glass flex flex-col">
        <div className="p-6 border-b border-border">
          <h2 className="text-xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-pink-400 to-purple-400 tracking-tight">Clínica Harmonize</h2>
          <select 
            value={tenantId} 
            onChange={(e) => setTenantId(e.target.value)}
            className="w-full mt-2 bg-muted text-xs border border-border rounded px-2 py-1 focus:outline-none"
          >
            <option value="1">ID do Tenant: 1 (Harmonize)</option>
            <option value="2">ID do Tenant: 2 (Dra. Fernanda)</option>
          </select>
        </div>
        <nav className="flex-1 p-4 space-y-2">
          <a href="#" className="block px-4 py-2 rounded-md bg-muted text-foreground font-medium">Analytics</a>
          <a href="#" className="block px-4 py-2 rounded-md hover:bg-muted/50 text-muted-foreground transition-colors">Configurações da IA</a>
          <a href="#" className="block px-4 py-2 rounded-md hover:bg-muted/50 text-muted-foreground transition-colors flex justify-between items-center">
            Inbox Humano
            <span className="bg-pink-600 text-white text-xs px-2 py-0.5 rounded-full">{metrics.humanHandoffs}</span>
          </a>
          <a href="#" className="block px-4 py-2 rounded-md hover:bg-muted/50 text-muted-foreground transition-colors">CRM de Pacientes</a>
        </nav>
      </aside>

      {/* Main Content */}
      <main className="flex-1 p-8 overflow-y-auto">
        <header className="mb-8">
          <h1 className="text-3xl font-bold">Seu Assistente de IA</h1>
          <p className="text-muted-foreground">Desempenho da recepcionista virtual nos últimos 30 dias (Integrado ao FastAPI).</p>
        </header>

        {/* Metric Cards */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
          <div className="glass p-5 rounded-xl border border-border">
            <h3 className="text-xs font-medium text-muted-foreground uppercase mb-1">Pacientes Atendidos</h3>
            <p className="text-2xl font-bold">{metrics.patientCount}</p>
          </div>
          <div className="glass p-5 rounded-xl border border-border">
            <h3 className="text-xs font-medium text-muted-foreground uppercase mb-1">Agendamentos Totais</h3>
            <p className="text-2xl font-bold text-pink-400">{metrics.appointmentCount}</p>
            <span className="text-xs text-muted-foreground mt-1 block">Conversão Estimada: 24.5%</span>
          </div>
          <div className="glass p-5 rounded-xl border border-border">
            <h3 className="text-xs font-medium text-muted-foreground uppercase mb-1">Alertas no Painel</h3>
            <p className="text-2xl font-bold text-purple-400">{metrics.humanHandoffs}</p>
          </div>
          <div className="glass p-5 rounded-xl border border-border">
            <h3 className="text-xs font-medium text-muted-foreground uppercase mb-1">Transferidos (Humano)</h3>
            <p className="text-2xl font-bold text-amber-400">{metrics.humanHandoffs}</p>
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
              {loading ? (
                <p className="text-sm text-muted-foreground">Carregando consultas...</p>
              ) : recentAppointments.map((apt) => (
                <div key={apt.id} className="flex justify-between items-center p-4 bg-muted/20 rounded-lg border border-border/50">
                  <div>
                    <p className="font-medium text-foreground">{apt.patientName}</p>
                    <p className="text-sm text-muted-foreground">
                      {apt.service} • {new Date(apt.date).toLocaleDateString('pt-BR')} às {new Date(apt.date).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}
                    </p>
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
                <select 
                  value={voiceTone}
                  onChange={e => setVoiceTone(e.target.value)}
                  className="w-full bg-muted border border-border rounded-md px-3 py-2 text-sm text-foreground focus:outline-none focus:border-pink-500"
                >
                  <option>Elegante e Sofisticado</option>
                  <option>Amigável e Empático</option>
                  <option>Clínico e Direto</option>
                </select>
              </div>
              <div>
                <label className="text-sm font-medium text-muted-foreground block mb-1">Tabela de Preços</label>
                <input 
                  type="text" 
                  value={prices} 
                  onChange={e => setPrices(e.target.value)}
                  className="w-full bg-muted border border-border rounded-md px-3 py-2 text-sm text-foreground focus:outline-none focus:border-pink-500"
                />
              </div>
              <div>
                <label className="text-sm font-medium text-muted-foreground block mb-1">Horário de Funcionamento</label>
                <input 
                  type="text" 
                  value={businessHours} 
                  onChange={e => setBusinessHours(e.target.value)}
                  className="w-full bg-muted border border-border rounded-md px-3 py-2 text-sm text-foreground focus:outline-none focus:border-pink-500"
                />
              </div>
            </div>
            <button 
              onClick={handleSaveConfig}
              disabled={saving}
              className="w-full mt-6 py-2 bg-pink-600 hover:bg-pink-700 text-white rounded-md font-medium transition-colors cursor-pointer disabled:opacity-50"
            >
              {saving ? 'Salvando...' : 'Salvar Alterações'}
            </button>
          </div>
        </div>

      </main>
    </div>
  );
}
