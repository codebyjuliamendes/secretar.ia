# Workflow: 02-agenda

**Nome no N8n:** `02-agenda`
**Descrição:** Sub-workflow chamado pela recepção. Trata toda a conversação para agendar consultas, usando as tools definidas.

## Trigger
- **Tipo:** Execute Workflow Trigger
- **Inputs:**
  - `phone_number`: String (Telefone do paciente)
  - `message`: String (Mensagem do paciente)

## Nós Ordenados

1. **Agent (Advanced AI Node)**
   - **Modelo:** Google Gemini 2.0 Flash (ou Claude Haiku 4.5 via flag)
   - **System Prompt:** Conteúdo de `prompts/agenda-system.md`
   - **Memory:** Window Buffer Memory (Session ID = `phone_number`).
   - **Tools associadas:**
     - `tool-listar-procedimentos`
     - `tool-listar-profissionais`
     - `tool-consultar-disponibilidade`
     - `tool-criar-agendamento`

2. **HTTP Request / Evolution API - Enviar Resposta**
   - **POST** `/message/sendText/{{EVOLUTION_INSTANCE_NAME}}`
   - **Body:** `number`: `{{ $json.phone_number }}`, `text`: `{{ $json.output_do_agent }}`

## Tratamento de Erro
- **Error Trigger Node:** Se o agente falhar por limite de tokens, timeout ou falha na Evolution API.
- Gravar no Sheets (`Logs`) e alertar Fundadora no WhatsApp.
