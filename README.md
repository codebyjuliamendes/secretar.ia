# 🤖 Secretar.ia — AI-Powered Multi-Tenant SaaS for High-Ticket Clinics

**Secretar.ia** é uma solução de inteligência artificial de nível corporativo e arquitetura multi-tenant, projetada especificamente para automatizar a recepção, agendamento, atendimento e retenção de pacientes em clínicas de estética e saúde de alto padrão (*high-ticket*). 

A plataforma resolve o acoplamento entre "crescimento de receita" e "trabalho operacional", permitindo que as clínicas escalem seus atendimentos via WhatsApp com zero intervenção humana inicial.

---

## 📐 Visão Arquitetural da Plataforma

O sistema foi desenhado seguindo padrões modernos de microsserviços e divisão de responsabilidades, garantindo segurança de dados, isolamento entre clínicas e altíssima performance para processamento de inteligência artificial.

```mermaid
graph TD
    Patient([Paciente no WhatsApp]) -->|WhatsApp Integration| Evolution[Evolution API Gateway]
    Evolution -->|Webhook Events| N8n[n8n Automation Engine]
    
    subgraph IA & Camada Cognitiva
        N8n -->|Whisper API| Transcription[Transcrição e Análise de Áudio]
        N8n -->|Gemini 1.5 Pro| Vision[Visão Computacional e Skin Assessment]
    end

    N8n -->|Processamento de Regra de Negócio| Python[FastAPI Backend - Python 3.12]
    Python -->|Queries Seguras| Postgres[(PostgreSQL / Multi-Tenant DB)]
    
    subgraph Interface do Usuário (Next.js)
        Next[Next.js App Router] -->|Consumo REST API| Python
        Admin[SuperAdmin Panel]
        Clinic[Clinic Workspace & Realtime Inbox]
    end
```

---

## 💎 Pilares de Valor & Engenharia do SaaS

### 1. Arquitetura Multi-Tenant & Isolamento
*   **Isolamento Logístico**: Banco de dados relacional com políticas de isolamento estritas por ID da clínica (`tenantId`), permitindo escalar para centenas de clientes sob o mesmo banco sem vazamento de dados.
*   **Conexões Independentes**: Arquitetura pronta para integração do próprio calendário do médico (Google Calendar via OAuth2) e número de WhatsApp independente por clínica.

### 2. Camada de Agentes de IA Inteligentes
*   **Recepção Multimodal Ativa**:
    *   *Transcrição de Áudio (Whisper)*: O assistente de IA lê, transcreve e entende as intenções enviadas por mensagens de voz.
    *   *Visão Computacional (Gemini)*: Reconhece fotos de rosto enviadas por pacientes para pré-avaliar a pele e sugerir os procedimentos mais adequados com tato comercial.
*   **Agente de Upsell & Retenção (Autônomo)**:
    *   Processador em lote (CRON) que identifica procedimentos que perdem o efeito (como a Toxina Botulínica após 5 meses) e reengaja ativamente a paciente via WhatsApp para agendar o retoque.

### 3. Painel Administrativo Self-Service
*   **Visão de Negócios**: Gráficos de faturamento recuperado pela IA, taxas de conversão de agendamentos e métricas críticas de no-show.
*   **Inbox de Transbordo Realtime**: Painel com alertas automatizados de handoff. Quando a IA encontra uma dúvida complexa (intenção `HUMANO`), o sistema notifica a recepcionista física instantaneamente para assumir a conversa pelo chat integrado.

---

## 💻 Stack Tecnológica de Destaque

*   **Frontend**: Next.js 15 (App Router), React 19, Tailwind CSS 4, Shadcn/UI (Design System premium baseado em Glassmorphism e Dark Mode).
*   **Backend**: Python 3.12, FastAPI (Assíncrono com Uvicorn).
*   **Persistência**: Prisma Client Python (`prisma-client-py`) com suporte nativo a migrações e modelagem em PostgreSQL e MySQL.
*   **Orquestração**: N8n Workflow Engine.
*   **Infraestrutura**: Docker Compose para orquestração de serviços de banco de dados e pipelines locais.

---

## 🛡️ Propósitos de Negócio

O **Secretar.ia** foi concebido para operar como um produto comercial escalável (SaaS). O objetivo principal é remover a necessidade de intervenção do administrador durante o onboarding de novos consultórios, automatizando o faturamento mensal recorrente (MRR) via Stripe/Asaas e integrando fluxos de provisionamento que cortam o acesso da IA em caso de atraso no pagamento.
