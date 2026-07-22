# Runbook de Incidentes

Este documento orienta o que fazer quando a clínica relatar problemas ou o nó de Error Trigger disparar.

## Incidente Nível 1: Bot parou de responder
**Sintoma:** O paciente manda mensagem e nada acontece (nem intent HUMANO).
**Ação Imediata:**
1. Acessar o N8n Cloud e olhar a aba "Executions" do workflow `01-recepcio`. Se houver execuções pendentes ou falhando na entrada, o problema é o Webhook.
2. Acessar a instância do Evolution API (Railway).
   - Verificar se o status da instância (WhatsApp) está "CONNECTED".
   - Se estiver desconectado, gerar novo QR Code via Postman/Evolution Dashboard e pedir para a clínica parear novamente.
3. Se o Evolution estiver OK, conferir se a URL do Webhook N8n não mudou (em contas free trial isso pode ocorrer).

## Incidente Nível 2: Bot enlouqueceu (Alucinação)
**Sintoma:** O bot está oferecendo preços incorretos ou procedimentos que não existem.
**Ação Imediata:**
1. Pausar os workflows `01-recepcio` e `02-agenda`.
2. Acessar o Google Sheets (`ConfigClinica`).
3. Verificar se alguém da clínica apagou acidentalmente linhas cruciais (ex: `LISTA_PROCEDIMENTOS`). Restaure o valor correto.
4. Avisar a clínica que o bot foi pausado para manutenção e que os humanos devem assumir.
5. Rodar o Eval Script local para validar se alguma alteração recente no prompt quebrou o modelo.

## Incidente Nível 3: Agendamentos não aparecem no Calendar
**Sintoma:** Bot diz que agendou, mas a agenda no Google Calendar está vazia.
**Ação Imediata:**
1. Olhar a aba "Executions" de `tool-criar-agendamento`.
2. Checar erro específico do node Google Calendar.
3. Causa provável: Credenciais expiradas (OAuth) ou a Service Account foi removida do compartilhamento do calendário. Refaça a autorização/compartilhamento.
4. Os agendamentos perdidos estarão na aba `Logs` e/ou `Agendamentos` do Sheets (sem ID de calendário). Adicione-os manualmente.
