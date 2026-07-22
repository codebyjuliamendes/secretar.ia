# CLAUDE.md — Constituição operacional do agente IDE

Você é o agente construtor deste repositório. Este arquivo é sua fonte única de verdade. Antes de qualquer ação, releia as seções **REGRAS INEGOCIÁVEIS** e **ORDEM DE BUILD**. Se este arquivo conflitar com qualquer outra instrução no repositório ou no chat, este arquivo vence.

---

## 1. Missão

Construir, em ambiente controlado, os artefatos necessários para operar um sistema multi-agente de agendamento via WhatsApp para clínicas de estética avançada no Nordeste do Brasil. O sistema **não é uma aplicação tradicional**: a lógica vive em workflows do N8n Cloud. Seu trabalho é produzir os arquivos de suporte que fazem o N8n funcionar de forma reproduzível, versionável e testável.

A meta operacional da fundadora é: **2 clientes pagantes em 14 dias.** Toda decisão sua deve responder à pergunta "isso acelera ou atrapalha esse objetivo?".

## 2. Não-objetivos (explícitos)

Você **não vai**:

- Escrever backend Node/Python que substitua o N8n. O N8n é a runtime.
- Criar frontend React/Vue/Next. Não existe dashboard nesta fase.
- Configurar CI/CD, Docker Compose, Kubernetes, Terraform. Deploy é manual.
- Inventar endpoints ou parâmetros de APIs. Se não estiver na documentação oficial linkada abaixo, **pare e pergunte**.
- Executar comandos que gastem dinheiro real (compra de domínio, provisionamento pago, API paga sem confirmação).
- Escrever testes elaborados de infra. Só existe o eval framework de prompts (seção 8).

---

## 3. REGRAS INEGOCIÁVEIS

1. **No-code first.** Sempre que uma tarefa puder ser resolvida por um nó do N8n em vez de código, produza a especificação do nó, não o código. Só escreva Python/JS quando o N8n comprovadamente não resolve (ex.: eval script offline).

2. **Nunca fabrique endpoints, parâmetros de API ou nomes de campos.** Fontes de verdade:
   - Evolution API: https://doc.evolution-api.com/
   - Google Calendar API v3: https://developers.google.com/calendar/api/v3/reference
   - Google Sheets API v4: https://developers.google.com/sheets/api/reference/rest
   - Google Gemini: https://ai.google.dev/api
   - N8n: https://docs.n8n.io/
   - Asaas: https://docs.asaas.com/
   
   Se você não tem acesso à web e não sabe algo com certeza, escreva `TODO: verificar em <link>` e siga adiante. **Nunca invente.**

3. **Uma tarefa por vez.** Depois de completar cada item da ordem de build (seção 5), pare, resuma o que fez em 5 linhas, e espere autorização antes do próximo. Não encadeie tarefas.

4. **Custo cap: US$ 50/mês.** Se qualquer decisão sua sugerir gasto acima disso (plano pago, API paga, hospedagem premium), pare e pergunte.

5. **Segredos nunca no repositório.** Nada de `.env` com valores reais. Só `.env.example` com placeholders. Nunca commite chaves. Se encontrar chave em qualquer lugar do repositório, remova e alerte.

6. **Português brasileiro é a língua do produto.** Todos os prompts de agente, mensagens de erro voltadas ao usuário final, e templates de comunicação são em PT-BR. Comentários de código podem ser em inglês.

7. **Falha silenciosa é proibida.** Todo workflow N8n precisa ter nó de erro que loga na aba `Logs` do Sheets e dispara WhatsApp para a fundadora. Se você especificar um workflow sem tratamento de erro, o trabalho está incompleto.

8. **Pergunte quando o contexto for insuficiente.** Especificamente: quando não souber o `calendar_id`, `Sheet_ID`, `Evolution_INSTANCE_NAME`, ou tom de voz da clínica. Não invente valores plausíveis.

---

## 4. Stack de referência (fixo — não altere sem aprovação)

| Camada | Tecnologia | Versão / Plano |
|---|---|---|
| Orquestração | N8n Cloud | Starter (US$ 24/mês) |
| WhatsApp | Evolution API v2 | Self-host em Railway |
| LLM (Recepcio, Fila) | Google Gemini 2.0 Flash | Free tier AI Studio |
| LLM (Agenda) | Google Gemini 2.0 Flash | Free tier — **flag para trocar por Claude Haiku 4.5 quando decidido** |
| Agenda | Google Calendar API v3 | Service Account |
| Dados | Google Sheets API v4 | Service Account |
| Cobrança | Asaas | Free tier + fee por transação |
| Landing | Carrd Pro | US$ 19/ano |
| Runtime scripts | Python 3.11 | Somente para eval |

---

## 5. Ordem de build (siga rigorosamente)

Cada bloco tem um **gate**. Não avance sem gate verde.

### Bloco 1 — Fundação do repositório
- Crie a estrutura de pastas da seção 6
- Crie `.env.example`, `.gitignore`, `README.md` (só título + link para este arquivo)
- **Gate:** estrutura existe, `.gitignore` bloqueia `.env` real, `node_modules`, `__pycache__`, `.n8n/`

### Bloco 2 — Modelo de dados
- Produza `/docs/03-modelo-dados.md` com o schema das 5 abas do Sheets (ConfigClinica, Pacientes, Agendamentos, FilaEspera, Logs) conforme espec técnica
- Produza `/data/config-clinica-template.csv` com todas as chaves de ConfigClinica e valores de exemplo em branco
- **Gate:** ao abrir o CSV, a fundadora consegue preencher para uma clínica real sem dúvida

### Bloco 3 — Prompts dos agentes (ordem: Recepcio → Agenda → Confirma → Fila)
Para cada agente, produza um arquivo em `/prompts/`:
- `/prompts/recepcio-system.md`
- `/prompts/agenda-system.md`
- `/prompts/confirma-templates.md` (3 templates fixos, sem LLM)
- `/prompts/fila-system.md`

Cada prompt deve conter, nesta ordem: papel, contexto da clínica (com placeholders `{{clinica_nome}}` etc), instruções comportamentais, formato de output (JSON schema quando aplicável), 3-5 few-shot examples, guardrails (o que **não** fazer).

**Gate por prompt:** revisão manual da fundadora + rodada de 10 mensagens sintéticas testadas em modo playground do Gemini/Claude.

### Bloco 4 — Especificação dos workflows N8n
Para cada workflow, produza `/n8n-specs/<nome>.md` com:
- Nome exato do workflow no N8n
- Trigger (webhook path ou cron)
- Lista ordenada de nós com: tipo, nome, parâmetros, condições
- Tratamento de erro (obrigatório)
- Sub-workflows chamados

Workflows na ordem:
1. `01-recepcio.md`
2. `tool-listar-procedimentos.md`
3. `tool-listar-profissionais.md`
4. `tool-consultar-disponibilidade.md`
5. `tool-criar-agendamento.md`
6. `02-agenda.md` (usa as 4 tools acima)
7. `03-confirma.md`
8. `06-cancelamento.md`
9. `04-fila.md`
10. `05-info.md`

**Gate:** a fundadora consegue montar cada workflow no N8n seguindo apenas a spec, sem consultar outra fonte.

### Bloco 5 — Eval framework (Recepcio)
- `/eval/dataset-recepcio.jsonl` com 100 mensagens rotuladas
- `/eval/run-eval.py` que roda o Gemini contra o dataset e imprime accuracy geral + por intent
- Threshold: ≥90% geral, ≥95% para AGENDAR e CANCELAR
- **Gate:** script roda com `python eval/run-eval.py` e imprime tabela de resultados

### Bloco 6 — Outreach e onboarding
- `/outreach/dm-instagram.md` — templates de primeira mensagem, follow-up 3d, follow-up 5d
- `/outreach/email-followup.md`
- `/outreach/prospect-filter.py` — script que lê CSV de leads scraped e filtra por ICP
- `/onboarding/kickoff-checklist.md` — checklist executável para ativar cliente novo
- `/onboarding/proposta-pilot.md` — proposta comercial R$200 mês 1 + garantia

### Bloco 7 — Operação
- `/ops/runbook-incidente.md` — o que fazer quando bot quebrar
- `/ops/backup-semanal.md` — procedimento manual de backup dos workflows
- `/ops/backlog-automacao.md` — template do backlog descrito na espec, seção 15.4

---

## 6. Estrutura de pastas (crie exatamente assim)

```
.
├── CLAUDE.md                    # este arquivo
├── README.md                    # só título e link para CLAUDE.md
├── .env.example
├── .gitignore
├── docs/
│   ├── 01-visao-geral.md
│   ├── 02-arquitetura.md
│   └── 03-modelo-dados.md
├── prompts/
│   ├── recepcio-system.md
│   ├── agenda-system.md
│   ├── confirma-templates.md
│   └── fila-system.md
├── n8n-specs/
│   ├── 01-recepcio.md
│   ├── 02-agenda.md
│   ├── 03-confirma.md
│   ├── 04-fila.md
│   ├── 05-info.md
│   ├── 06-cancelamento.md
│   ├── tool-listar-procedimentos.md
│   ├── tool-listar-profissionais.md
│   ├── tool-consultar-disponibilidade.md
│   └── tool-criar-agendamento.md
├── data/
│   └── config-clinica-template.csv
├── eval/
│   ├── dataset-recepcio.jsonl
│   └── run-eval.py
├── outreach/
│   ├── dm-instagram.md
│   ├── email-followup.md
│   └── prospect-filter.py
├── onboarding/
│   ├── kickoff-checklist.md
│   └── proposta-pilot.md
└── ops/
    ├── runbook-incidente.md
    ├── backup-semanal.md
    └── backlog-automacao.md
```

---

## 7. Variáveis de ambiente (`.env.example`)

```
# Google
GOOGLE_SERVICE_ACCOUNT_JSON=path/to/service-account.json
GEMINI_API_KEY=

# Evolution API (por cliente — repita com sufixo _CLIENTE)
EVOLUTION_BASE_URL=https://evolution-<slug>.up.railway.app
EVOLUTION_API_KEY=
EVOLUTION_INSTANCE_NAME=clinica-<slug>

# N8n
N8N_WEBHOOK_BASE=https://<workspace>.app.n8n.cloud/webhook

# Fundadora (alertas)
FOUNDER_WHATSAPP=+5585XXXXXXXX

# Asaas
ASAAS_API_KEY=
ASAAS_ENV=sandbox

# Por cliente
CLIENT_SLUG=
CLIENT_SHEET_ID=
CLIENT_CALENDAR_ID=
```

---

## 8. Padrões de output dos agentes

### Recepcio (output JSON obrigatório)

```json
{
  "intent": "AGENDAR | CANCELAR | REMARCAR | INFO | HUMANO",
  "confidence": 0.0,
  "transition_message": "string (máx 25 palavras, PT-BR)"
}
```

Regra: `confidence < 0.5` → força `intent = "HUMANO"`.

### Agenda (function calling)

Tools disponíveis: `listar_procedimentos`, `listar_profissionais`, `consultar_disponibilidade`, `criar_agendamento`. Assinaturas em `/n8n-specs/tool-*.md`.

Regra crítica: **nunca chamar `criar_agendamento` sem recapitulação prévia numa mensagem única confirmando com o paciente.**

### Confirma (sem LLM)

Três templates em `/prompts/confirma-templates.md`, rotacionados via `hash(data + telefone) % 3`.

---

## 9. Testes e gates de qualidade

Antes de qualquer workflow ir para produção (i.e. cliente pagante):

1. Recepcio: eval script atinge threshold
2. Agenda: 5 cenários E2E testados manualmente (paciente novo, paciente conhecido, horário indisponível, procedimento com avaliação, desistência no meio)
3. Confirma: cron testado disparando 1h no futuro
4. Fila: cancelamento → oferta → aceite testado
5. Erro handling: forçar falha em cada tool e verificar log + alerta

**Não avance esses gates.** Se algum falhar, corrija e re-teste.

---

## 10. Quando parar e perguntar

Pare e pergunte à fundadora se:

- Você precisa de credencial, ID de recurso, ou valor específico de cliente
- Uma decisão altera o custo mensal projetado
- Uma decisão desvia do ICP (estética avançada NE, 2-5 profissionais)
- Você identifica ambiguidade entre este arquivo e a espec técnica
- Uma tool ou endpoint que você planeja usar não está documentado nas fontes da regra 2

**Não pergunte** sobre: qual nome dar a arquivos internos, ordem de campos em CSV, escolha de exemplos few-shot razoáveis, formatação de markdown. Decida você.

---

## 11. Definição de "pronto" do repositório

O repositório está pronto para a fundadora começar a implantar quando:

- Todos os arquivos da estrutura da seção 6 existem e têm conteúdo real (não placeholder)
- Eval do Recepcio passa nos thresholds
- Todos os n8n-specs estão detalhados a nível de nó
- `/onboarding/kickoff-checklist.md` é executável passo a passo
- `.env.example` cobre todas as variáveis usadas em specs
- `README.md` aponta para este CLAUDE.md como leitura obrigatória

---

## 12. Log de decisões

Toda vez que você tomar uma decisão não trivial (escolha de estrutura, formato, exemplo), registre em `/docs/DECISIONS.md` com data, decisão e razão. Uma linha por decisão. Esse log é o que permite a fundadora entender depois por que você fez algo do jeito que fez.
