# Workflow: tool-consultar-disponibilidade

**Nome no N8n:** `tool-consultar-disponibilidade`
**Descrição:** Sub-workflow (Tool) que consulta o Google Calendar para verificar slots livres.

## Trigger
- **Tipo:** Execute Workflow Trigger (Tool)
- **Descrição da Tool:** "Verifica a disponibilidade de horários no calendário."
- **Inputs (JSON Schema):**
  - `data_inicio`: String (ISO 8601)
  - `data_fim`: String (ISO 8601)

## Nós Ordenados

1. **Google Calendar**
   - **Operação:** Get Free/Busy
   - **Calendário:** `CLIENT_CALENDAR_ID`
   - **Time Min:** `{{ $json.data_inicio }}`
   - **Time Max:** `{{ $json.data_fim }}`

2. **Code (JS)**
   - **Script:** Inverter a lógica de "Busy" para "Free", gerando slots de 1 hora dentro do horário de funcionamento configurado na clínica. Ignorar slots passados.

3. **Return Node**
   - **Output:** Array de objetos com horários disponíveis (ex: `[{"hora": "09:00", "data": "2026-10-15"}, ...]`).

## Tratamento de Erro
- Retornar mensagem clara ao Agente: "Falha técnica ao acessar agenda. Peça para o paciente aguardar atendimento humano."
