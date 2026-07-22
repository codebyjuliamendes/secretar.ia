# Workflow: 01-recepcio (Multimídia Avançada)

**Descrição:** O Workflow principal foi atualizado para suportar pacientes que enviam Áudio ou Imagem no WhatsApp, convertendo esses formatos em texto rico antes de enviar para o Agente IA principal.

## Trigger
- **Webhook Evolution API**: Escuta mensagens recebidas (`messages.upsert`).

## Tratamento Multimídia (Switch Node)
Antes de enviar a mensagem para a IA, verificamos o `messageType`:

### Rota 1: `audioMessage`
1. **Download Media**: Baixa o áudio OGG da Evolution API.
2. **OpenAI Node (Whisper)**: 
   - Ação: Transcribe Audio.
   - Output: Texto transcrito da paciente.
3. Repassa o texto transcrito para o fluxo de classificação normal (como se a paciente tivesse digitado).

### Rota 2: `imageMessage`
1. **Download Media**: Baixa a imagem (foto do rosto/pele).
2. **Google Gemini (Vision)**:
   - Prompt: *"O paciente enviou esta foto para avaliação. Haja como recepcionista clínica e faça um elogio gentil seguido de um convite para marcar uma avaliação formal, lembrando que fotos não substituem diagnóstico médico."*
3. O fluxo responde o paciente diretamente e sugere agendamento.

### Rota 3: `conversation` / `extendedTextMessage`
Fluxo normal de classificação (Agendar, Cancelar, Info, Humano).

## Endpoint de Handoff (Humano)
Quando a intenção for `HUMANO`, o N8n fará um `POST` em:
- **URL**: `https://api.seusistema.com/api/n8n/alerts`
- **Body**: `{ "tenantId": "...", "phone": "...", "context": "O paciente perguntou sobre..." }`
- **Ação**: Isso apita no Painel SaaS do seu cliente em tempo real via WebSockets.
