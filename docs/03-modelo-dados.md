# Modelo de Dados (Google Sheets)

O banco de dados da operação é mantido no Google Sheets para fácil acesso e manutenção pela clínica. Ele é composto por 5 abas principais.

## Aba 1: ConfigClinica
Armazena configurações globais da clínica, injetadas no contexto dos agentes.

| Coluna | Tipo | Descrição |
|---|---|---|
| Chave | String | Identificador da configuração (ex: `NOME_CLINICA`) |
| Valor | String | Valor configurado pela clínica |
| Descricao | String | Orientação sobre como preencher o valor |

## Aba 2: Pacientes
Registro central de pacientes que interagem com o bot.

| Coluna | Tipo | Descrição |
|---|---|---|
| ID_Paciente | String | Número de telefone com DDI (ex: 5585999999999) - Chave Primária |
| Nome | String | Nome do paciente |
| CPF | String | CPF (se aplicável/necessário para o Asaas) |
| Data_Nascimento | Date | Data de nascimento (opcional) |
| Notas | Text | Preferências ou alertas médicos importantes |
| Data_Cadastro | DateTime | Timestamp do primeiro contato |

## Aba 3: Agendamentos
Espelho do Google Calendar, centraliza o status interno e logs de cada consulta.

| Coluna | Tipo | Descrição |
|---|---|---|
| ID_Agendamento | String | ID único gerado pelo N8n ou ID do Calendar |
| ID_Paciente | String | FK para Pacientes |
| Nome_Paciente | String | Nome para visualização rápida |
| Data_Hora_Inicio | DateTime | Formato ISO 8601 |
| Data_Hora_Fim | DateTime | Formato ISO 8601 |
| Profissional | String | Nome do profissional |
| Procedimento | String | Nome do procedimento agendado |
| Status | String | PENDENTE, CONFIRMADO, CANCELADO, REALIZADO |
| Calendar_Event_ID | String | ID do evento no Google Calendar |

## Aba 4: FilaEspera
Gerencia pacientes que desejam antecipar consultas caso haja desistência.

| Coluna | Tipo | Descrição |
|---|---|---|
| ID_Fila | String | UUID único para a entrada |
| ID_Paciente | String | FK para Pacientes |
| Profissional | String | Profissional de interesse (ou "Qualquer") |
| Procedimento | String | Procedimento de interesse |
| Preferencia_Dias | String | Ex: "Segundas e Terças" ou "Qualquer" |
| Preferencia_Horario | String | Ex: "Manhã", "Tarde", "Qualquer" |
| Status | String | AGUARDANDO, NOTIFICADO, AGENDADO, EXPIRADO |
| Data_Entrada | DateTime | Quando entrou na fila |

## Aba 5: Logs
Registro de erros e auditoria de sistema (Regra Inegociável #7).

| Coluna | Tipo | Descrição |
|---|---|---|
| Timestamp | DateTime | Momento do evento |
| Workflow | String | Nome do workflow N8n de origem |
| Nivel | String | INFO, WARN, ERROR |
| Mensagem | String | Descrição legível do erro ou evento |
| Dados_Contexto | JSON | Variáveis de execução no momento do erro |
