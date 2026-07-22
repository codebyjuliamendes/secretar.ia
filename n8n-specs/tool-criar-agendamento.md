# Workflow: tool-criar-agendamento

**Nome no N8n:** `tool-criar-agendamento`
**Descrição:** Sub-workflow (Tool) que escreve no banco de dados SaaS (PostgreSQL) e no Calendar.

## Trigger
- **Tipo:** Execute Workflow Trigger (Tool)
- **Descrição da Tool:** "Cria o evento de agendamento no sistema. USE APENAS APÓS CONFIRMAÇÃO DO PACIENTE."
- **Inputs:**
  - `nome_paciente`: String
  - `telefone_paciente`: String
  - `procedimento`: String
  - `profissional`: String
  - `data_hora_inicio`: String (ISO 8601)
  - `data_hora_fim`: String (ISO 8601)

## Nós Ordenados

1. **HTTP Request (Aesthetics SaaS API)**
   - **Method:** POST
   - **URL:** `https://api.seusistema.com/api/n8n/appointments`
   - **Headers:** `x-api-key: {{ $env.SAAS_API_KEY }}`
   - **Body JSON:**
     ```json
     {
       "tenantId": "{{ $env.TENANT_ID }}",
       "phone": "{{ $json.telefone_paciente }}",
       "service": "{{ $json.procedimento }}",
       "date": "{{ $json.data_hora_inicio }}"
     }
     ```

2. **Google Calendar (Sincronização Visual)**
   - **Operação:** Create Event
   - **Calendário:** `CLIENT_CALENDAR_ID`
   - **Title:** `{{ $json.nome_paciente }} - {{ $json.procedimento }}`
   - **Start:** `{{ $json.data_hora_inicio }}`
   - **End:** `{{ $json.data_hora_fim }}`

3. **Return Node**
   - **Output:** Status "Agendamento criado com sucesso no banco de dados."

## Tratamento de Erro
- Se a API retornar erro, alertar a Clínica pelo painel Admin.
