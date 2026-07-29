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
  recoveredRevenue: number; // Faturamento Recuperado pela IA
}

export default function ClinicWorkspace() {
  const [tenantId, setTenantId] = useState('1'); // Mock ID inicial
  const [metrics, setMetrics] = useState<Metrics>({
    patientCount: 142,
    appointmentCount: 84,
    humanHandoffs: 18,
    recoveredRevenue: 12450.00
  });
  const [recentAppointments, setRecentAppointments] = useState<Appointment[]>([]);
  const [loading, setLoading] = useState(true);

  // States do Quick Config da IA
  const [voiceTone, setVoiceTone] = useState('Elegante e Sofisticado');
  const [proceduresText, setProceduresText] = useState(
    "Botox (Toxina Botulínica): R$ 990 - Suaviza linhas de expressão, retoque em 5 meses.\nPreenchimento Labial: R$ 1.200 - Volume e contorno labial com ácido hialurônico.\nPeeling de Diamante: R$ 250 - Microesfoliação para renovação celular."
  );
  const [businessHours, setBusinessHours] = useState('09:00 - 18:00');
  const [isUpsellActive, setIsUpsellActive] = useState(true);
  const [upsellMessage, setUpsellMessage] = useState(
    "Olá {nome}! Percebemos que sua última aplicação de Botox completou 5 meses. Gostaria de garantir seu horário de retorno para manter os resultados ideais?"
  );
  const [saving, setSaving] = useState(false);

  // States do Onboarding Self-Service
  const [isCalendarConnected, setIsCalendarConnected] = useState(true);
  const [isWhatsappConnected, setIsWhatsappConnected] = useState(true);
  const [showQR, setShowQR] = useState(false);

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
          prompt: `Tom de Voz: ${voiceTone} | Upsell: ${isUpsellActive ? 'Ativo' : 'Inativo'} | Mensagem: ${upsellMessage}`, 
          prices: proceduresText, 
          businessHours 
        })
      });
      const data = await res.json();
      if (data.success) {
        alert("Configurações salvas e indexadas com pgvector no banco de dados!");
      }
    } catch (err) {
      alert("Falha de conexão com a API Python. Dados atualizados localmente no painel.");
    } finally {
      setSaving(false);
    }
  };

  const toggleCalendar = () => setIsCalendarConnected(!isCalendarConnected);
  
  const connectWhatsapp = () => {
    if (isWhatsappConnected) {
      setIsWhatsappConnected(false);
    } else {
      setShowQR(true);
    }
  };

  const confirmQRScan = () => {
    setShowQR(false);
    setIsWhatsappConnected(true);
  };

  // Cálculo de ROI comercial (SaaS custa R$ 497)
  const saasCost = 497.00;
  const roi = ((metrics.recoveredRevenue - saasCost) / saasCost) * 100;

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
          <a href="#" className="block px-4 py-2 rounded-md bg-muted text-foreground font-medium">Analytics & ROI</a>
          <a href="#" className="block px-4 py-2 rounded-md hover:bg-muted/50 text-muted-foreground transition-colors">Configurações da IA</a>
          <a href="#" className="block px-4 py-2 rounded-md hover:bg-muted/50 text-muted-foreground transition-colors flex justify-between items-center">
            Inbox Humano
            <span className="bg-pink-600 text-white text-xs px-2 py-0.5 rounded-full">{metrics.humanHandoffs}</span>
          </a>
          <a href="#" className="block px-4 py-2 rounded-md hover:bg-muted/50 text-muted-foreground transition-colors">CRM de Pacientes</a>
        </nav>
        
        {/* Token Caching Status indicator */}
        <div className="p-4 m-4 bg-emerald-500/10 border border-emerald-500/30 rounded-lg">
          <p className="text-xs text-emerald-400 font-semibold flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse"></span>
            Prompt Caching: Ativo
          </p>
          <p className="text-[10px] text-muted-foreground mt-1">Economia de 82% de tokens em tempo real.</p>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 p-8 overflow-y-auto">
        <header className="mb-8 flex justify-between items-start">
          <div>
            <h1 className="text-3xl font-bold">Painel de Controle da Clínica</h1>
            <p className="text-muted-foreground">Monitoramento de ROI e parametrização do Assistente de IA.</p>
          </div>
          
          {/* Status de Onboarding Self-Service */}
          <div className="flex gap-3">
            <button 
              onClick={toggleCalendar}
              className={`px-3 py-1.5 rounded-md text-xs font-semibold border transition-all cursor-pointer flex items-center gap-2 ${
                isCalendarConnected 
                  ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' 
                  : 'bg-rose-500/10 text-rose-400 border-rose-500/20'
              }`}
            >
              {isCalendarConnected ? '📅 Calendar Conectado' : '📅 Conectar Calendar'}
            </button>
            
            <button 
              onClick={connectWhatsapp}
              className={`px-3 py-1.5 rounded-md text-xs font-semibold border transition-all cursor-pointer flex items-center gap-2 ${
                isWhatsappConnected 
                  ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' 
                  : 'bg-rose-500/10 text-rose-400 border-rose-500/20'
              }`}
            >
              {isWhatsappConnected ? '💬 WhatsApp Conectado' : '💬 Conectar WhatsApp'}
            </button>
          </div>
        </header>

        {/* Metric Cards com foco em ROI Comercial */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
          <div className="glass p-5 rounded-xl border border-border">
            <h3 className="text-xs font-medium text-muted-foreground uppercase mb-1">Métricas de Atendimento</h3>
            <p className="text-2xl font-bold">{metrics.patientCount} Pacientes</p>
            <span className="text-xs text-muted-foreground mt-1 block">{metrics.appointmentCount} agendamentos fechados</span>
          </div>
          <div className="glass p-5 rounded-xl border border-border">
            <h3 className="text-xs font-medium text-muted-foreground uppercase mb-1">Faturamento Recuperado (IA)</h3>
            <p className="text-2xl font-bold text-pink-400">R$ {metrics.recoveredRevenue.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}</p>
            <span className="text-xs text-emerald-400 mt-1 block">Recuperação ativa de faltas e leads</span>
          </div>
          <div className="glass p-5 rounded-xl border border-border">
            <h3 className="text-xs font-medium text-muted-foreground uppercase mb-1">Custo do SaaS</h3>
            <p className="text-2xl font-bold text-muted-foreground">R$ {saasCost.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}</p>
            <span className="text-xs text-muted-foreground mt-1 block">Assinatura mensal fixa</span>
          </div>
          <div className="glass p-5 rounded-xl border border-border bg-gradient-to-br from-pink-500/10 to-transparent">
            <h3 className="text-xs font-medium text-muted-foreground uppercase mb-1">Retorno Líquido (ROI)</h3>
            <p className="text-2xl font-bold text-emerald-400">+{roi.toFixed(0)}%</p>
            <span className="text-xs text-emerald-400 mt-1 block">Lucro limpo gerado pela IA</span>
          </div>
        </div>

        {/* Layout Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          
          {/* Coluna Esquerda: Agendamentos e Vector RAG */}
          <div className="lg:col-span-2 space-y-8">
            {/* Recent Appointments */}
            <div className="glass rounded-xl border border-border p-6">
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

            {/* Vector RAG Procedure input */}
            <div className="glass rounded-xl border border-border p-6">
              <h2 className="text-lg font-semibold mb-2">Procedimentos & Tabela de Preços (pgvector RAG)</h2>
              <p className="text-xs text-muted-foreground mb-4">
                Digite os detalhes dos tratamentos e preços abaixo. A IA irá indexar semanticamente essas informações no banco de dados para responder aos pacientes com precisão.
              </p>
              <textarea 
                value={proceduresText}
                onChange={e => setProceduresText(e.target.value)}
                rows={5}
                className="w-full bg-muted border border-border rounded-md px-3 py-2 text-sm text-foreground focus:outline-none focus:border-pink-500 font-mono"
              />
              <p className="text-[10px] text-pink-400/80 mt-2 font-semibold">✔ Indexação Vetorial ativada automaticamente ao salvar.</p>
            </div>
          </div>

          {/* Coluna Direita: AI Voice Settings & Upsell Campaigns */}
          <div className="space-y-8">
            {/* AI Settings Preview */}
            <div className="glass rounded-xl border border-border p-6 flex flex-col">
              <h2 className="text-lg font-semibold mb-4">Ajuste de Personalidade da IA</h2>
              <div className="space-y-4">
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
                  <label className="text-sm font-medium text-muted-foreground block mb-1">Horário de Funcionamento</label>
                  <input 
                    type="text" 
                    value={businessHours} 
                    onChange={e => setBusinessHours(e.target.value)}
                    className="w-full bg-muted border border-border rounded-md px-3 py-2 text-sm text-foreground focus:outline-none focus:border-pink-500"
                  />
                </div>
              </div>
            </div>

            {/* Campaign Upsell Panel */}
            <div className="glass rounded-xl border border-border p-6 flex flex-col">
              <div className="flex justify-between items-center mb-4">
                <h2 className="text-lg font-semibold">Campanha de Upsell (Retenção)</h2>
                <label className="relative inline-flex items-center cursor-pointer">
                  <input 
                    type="checkbox" 
                    checked={isUpsellActive} 
                    onChange={() => setIsUpsellActive(!isUpsellActive)}
                    className="sr-only peer" 
                  />
                  <div className="w-9 h-5 bg-muted peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-foreground after:border-border after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-pink-600"></div>
                </label>
              </div>
              <p className="text-xs text-muted-foreground mb-4">
                O sistema monitora automaticamente o banco de dados e envia uma mensagem ativa para pacientes cujo Botox (Toxina) completou 5 meses.
              </p>
              <div>
                <label className="text-sm font-medium text-muted-foreground block mb-1">Mensagem Ativa</label>
                <textarea 
                  value={upsellMessage} 
                  onChange={e => setUpsellMessage(e.target.value)}
                  disabled={!isUpsellActive}
                  rows={4}
                  className="w-full bg-muted border border-border rounded-md px-3 py-2 text-xs text-foreground focus:outline-none focus:border-pink-500 disabled:opacity-50"
                />
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

        </div>

        {/* Modal Simulação QR Code Whatsapp (Self-service onboarding) */}
        {showQR && (
          <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50">
            <div className="glass border border-border rounded-xl p-8 w-full max-w-sm text-center shadow-2xl">
              <h3 className="text-xl font-bold mb-4 text-pink-500">Conectar WhatsApp</h3>
              <p className="text-xs text-muted-foreground mb-6">Abra o WhatsApp no seu celular, vá em Aparelhos Conectados e escaneie o código abaixo:</p>
              
              {/* QR Code Mock */}
              <div className="bg-white p-4 inline-block rounded-lg mb-6 border border-border shadow-inner">
                <div className="w-48 h-48 bg-[radial-gradient(ellipse_at_center,_var(--tw-gradient-stops))] from-slate-900 to-slate-700 flex flex-wrap items-center justify-center p-2 rounded">
                  <div className="w-10 h-10 bg-white m-1"></div>
                  <div className="w-10 h-10 bg-white m-1"></div>
                  <div className="w-10 h-10 bg-white m-1"></div>
                  <div className="w-10 h-10 bg-white m-1"></div>
                  <div className="w-10 h-10 bg-white m-1"></div>
                  <div className="w-10 h-10 bg-white m-1"></div>
                  <div className="w-10 h-10 bg-white m-1"></div>
                  <div className="w-10 h-10 bg-white m-1"></div>
                  <p className="text-[10px] text-white font-bold font-mono">EVOLUTION API QR_CODE</p>
                </div>
              </div>
              
              <div className="flex justify-center gap-3">
                <button 
                  onClick={() => setShowQR(false)}
                  className="px-4 py-2 bg-muted hover:bg-muted/70 rounded-md font-medium text-xs transition-colors cursor-pointer"
                >
                  Cancelar
                </button>
                <button 
                  onClick={confirmQRScan}
                  className="px-4 py-2 bg-pink-600 hover:bg-pink-700 text-white rounded-md font-medium text-xs transition-colors cursor-pointer"
                >
                  Confirmar Escaneamento
                </button>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
