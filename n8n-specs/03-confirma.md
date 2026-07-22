# Workflow: 03-confirma

**Nome no N8n:** `03-confirma`
**Descrição:** Disparo ativo (sem requisição do usuário) para confirmar agendamentos do dia seguinte.

## Trigger
- **Tipo:** Schedule (Cron)
- **Regra:** Rodar todos os dias às 18:00 (ou horário definido na configuração).

## Nós Ordenados

1. **Google Sheets - Buscar Agendamentos de Amanhã**
   - **Operação:** Read Rows
   - **Sheet:** `Agendamentos`
   - **Filtro:** Data igual a `AMANHÃ` e Status igual a `CONFIRMADO`.

2. **IF - Existem Agendamentos?**
   - Se Vazio, encerra.
   - Se Existir, passa para um Loop (Item Lists / Split In Batches).

3. **Loop (Para cada Paciente)**
   - **Set / Expression:** Escolhe o template rodando `hash(data_atual + telefone) % 3` entre os 3 templates do `prompts/confirma-templates.md`.
   - **Substituição:** Substitui `{{nome_paciente}}`, `{{hora}}`, `{{procedimento}}`, `{{profissional}}`.
   
4. **HTTP Request / Evolution API - Disparo**
   - **POST** `/message/sendText/{{EVOLUTION_INSTANCE_NAME}}`
   - **Body:** Telefone e o Template gerado.

5. **Google Sheets - Atualizar Status**
   - **Operação:** Update Row
   - **Sheet:** `Agendamentos`
   - **Filtro:** `ID_Agendamento`
   - **Update:** Mudar campo "Status" para `NOTIFICADO_CONFIRMACAO`. (O paciente deve responder SIM ou NÃO, que voltará pela Recepção).

## Tratamento de Erro
- Gravar no Sheets (`Logs`) caso a Evolution API falhe em um disparo, mas continuar o loop para os próximos pacientes.
