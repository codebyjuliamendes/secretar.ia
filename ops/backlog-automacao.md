# Backlog de Automação (Template)

Este documento centraliza as ideias e demandas de novas features solicitadas pelas clínicas.

| Status | Prioridade | Épico | Descrição da Feature | Critério de Aceite |
|--------|------------|-------|----------------------|-------------------|
| [BACKLOG] | Alta | Vendas | Disparo ativo para pacientes que não vêm há 6 meses oferecendo botox. | Workflow agendado consulta base de pacientes, cruza datas de última visita e manda mensagem promocional via Evolution API. |
| [BACKLOG] | Média | Pagamentos | Integração com Asaas para gerar Link de Pagamento (Sinal de 50%). | Bot de agendamento aciona tool do Asaas, gera link, paciente paga, Webhook do Asaas confirma no N8n e efetiva a agenda. |
| [BACKLOG] | Baixa | Ops | Integração com sistema de prontuário eletrônico legado. | Bot pesquisa paciente no sistema legado via API antes de criar o agendamento no Sheets. |
| [DOING] | Alta | Infra | Migrar Evolution API para container AWS ECS. | Evolução da versão atual no Railway para AWS sem downtime. |
| [DONE] | Alta | MVP | Pipeline de 10 workflows de Recepção e Agendamento. | Entregue no Kickoff inicial. |
