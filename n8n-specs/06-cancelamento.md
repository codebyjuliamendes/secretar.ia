# Workflow: 06-cancelamento

**Nome no N8n:** `06-cancelamento`
**Descrição:** Cancela evento no Google Calendar e atualiza status no Sheets, seja por desistência ou pelo processo de confirmação.

## Trigger
- **Tipo:** Execute Workflow Trigger (Acionado pela Recepção quando intent = CANCELAR).

## Nós Ordenados

1. **Google Sheets - Buscar Último Agendamento Ativo**
   - **Operação:** Read Rows
   - **Sheet:** `Agendamentos`
   - **Filtro:** Telefone igual ao do usuário E Status não cancelado/realizado E data no futuro.

2. **IF - Agendamento Encontrado?**
   - **False:** Responde (Evolution API) "Não localizei nenhum agendamento futuro no seu número. Quer falar com um atendente?".
   - **True:** Continua para cancelamento.

3. **Google Calendar**
   - **Operação:** Delete Event
   - **Calendário:** `CLIENT_CALENDAR_ID`
   - **Event ID:** ID resgatado do Sheets.

4. **Google Sheets - Atualizar Status**
   - **Operação:** Update Row
   - **Sheet:** `Agendamentos`
   - **Status:** Mudar para `CANCELADO`.

5. **HTTP Request / Evolution API - Resposta**
   - Avisar o paciente que foi cancelado.

6. **Acionar Fila de Espera (Opcional/Webhook interno)**
   - **Operação:** HTTP Request chamando o trigger do workflow `04-fila` passando a vaga recém aberta.

## Tratamento de Erro
- Se erro, alerta no Sheets `Logs`.
