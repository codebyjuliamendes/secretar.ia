# Workflow: 04-fila

**Nome no N8n:** `04-fila`
**Descrição:** Acionado quando há um cancelamento ou rodado em lote para oferecer vagas abertas para pacientes aguardando.

## Trigger
- **Tipo:** Webhook (POST) interno ou chamado ao final de `06-cancelamento`.
- **Payload esperado:** `procedimento`, `profissional`, `data`, `hora`.

## Nós Ordenados

1. **Google Sheets - Buscar Fila**
   - **Operação:** Read Rows
   - **Sheet:** `FilaEspera`
   - **Filtro:** Status = `AGUARDANDO` E Procedimento bate com a vaga. Ordenar por Data_Entrada (FIFO). Limite de 1 a 3 pacientes (conforme configuração).

2. **IF - Tem paciente na fila?**
   - **False:** Encerra.
   - **True:** Loop nos pacientes.

3. **Agent Node (LLM Fila)**
   - **Modelo:** Google Gemini 2.0 Flash
   - **System Prompt:** Conteúdo de `prompts/fila-system.md`
   - **Input:** Contexto da vaga injetado artificialmente ("Surgiu uma vaga dia X hora Y, ofereça ao paciente").
   - *Nota: Na verdade, o Agent atuará quando o paciente responder. O envio inicial é apenas texto fixo!*

   **Correção de Arquitetura no Workflow:**
   - 3a. Disparo Ativo (Sem LLM): "Olá! Surgiu uma vaga... deseja agendar?"
   - 3b. Atualizar Status `FilaEspera` para `NOTIFICADO`.
   - Quando o paciente responder, a *Recepção* verá que o status na Fila é NOTIFICADO e roteará para um Sub-workflow com o Agent `Fila`, que analisará a resposta (Sim/Não) e consumará o agendamento trocando status.

## Tratamento de Erro
- Gravar Log.
