# Checklist de Kickoff (Ativação de Novo Cliente)

Siga este procedimento estritamente após a assinatura da proposta e pagamento do setup/mês 1.

## Fase 1: Coleta de Dados (Onboarding)
- [ ] Solicitar preenchimento do `config-clinica-template.csv` com todos os dados da clínica (incluindo chaves de procedimentos e profissionais).
- [ ] Solicitar acesso ao Google Calendar da clínica (ou pedir que compartilhem o calendário oficial com o e-mail da nossa Service Account Google).
- [ ] Solicitar um chip/número de WhatsApp exclusivo ou escanear o QR Code no WhatsApp da clínica (apenas após garantir que humanos e bot não vão brigar por mensagens).

## Fase 2: Provisionamento de Infraestrutura
- [ ] Criar instância no Railway/Docker do Evolution API com o slug do cliente (ex: `clinica-fulana`).
- [ ] Escanear o QR Code do WhatsApp do cliente na instância do Evolution API.
- [ ] Criar planilha clone do Modelo de Dados no Google Sheets (Aba: ConfigClinica, Pacientes, Agendamentos, FilaEspera, Logs).
- [ ] Compartilhar a planilha com a conta Google do cliente (permissão de editor).
- [ ] Preencher a aba `ConfigClinica` com os dados coletados na Fase 1.

## Fase 3: Deploy dos Workflows
- [ ] Subir as specs do N8n em um novo workspace ou projeto focado no cliente.
- [ ] Configurar Credenciais N8n:
  - Evolution API (Base URL e Token)
  - Google Calendar (OAuth2 ou Service Account)
  - Google Sheets (OAuth2 ou Service Account)
  - Google Gemini API (Chave da API)
- [ ] Atualizar variáveis locais/globais (Webhook URL, Sheet ID, Calendar ID).
- [ ] Ativar workflows.

## Fase 4: Teste Homologação
- [ ] Mandar mensagem de saudação para o bot.
- [ ] Tentar marcar um procedimento real e verificar se cai no Calendar.
- [ ] Tentar desmarcar.
- [ ] Testar fluxo de Fila de Espera (disparo via webhook manual).

## Fase 5: Go-Live
- [ ] Comunicar clínica que o bot está operando.
- [ ] Enviar PDF / Resumo instruindo as recepcionistas humanas sobre como não interferir nas mensagens geridas pelo bot (marcar chats não lidos/lidos).
- [ ] Monitorar a aba `Logs` de hora em hora no primeiro dia.
