# Workflow: 05-info

**Nome no N8n:** `05-info`
**Descrição:** Agente focado exclusivamente em dúvidas gerais, preços (se configurado), endereço e políticas.

## Trigger
- **Tipo:** Execute Workflow Trigger (Acionado pela Recepção quando intent = INFO).

## Nós Ordenados

1. **Google Sheets - Buscar Configuração**
   - **Operação:** Read Rows (`ConfigClinica`).
   - Carrega todas as chaves (endereço, preços básicos se houver, políticas).

2. **Agent Node (LLM Info)**
   - **Modelo:** Google Gemini 2.0 Flash
   - **System Prompt:** 
     "Você é o assistente de informações da clínica {{NOME_CLINICA}}.
     Utilize o seguinte contexto para responder perguntas: {{Dados_Planilha_Config}}.
     Nunca agende horários. Apenas informe. Mantenha tom amigável."
   - **Input:** Mensagem do paciente.

3. **HTTP Request / Evolution API - Resposta**
   - Retorna a resposta gerada para o usuário.

## Tratamento de Erro
- Gravar Log. Se houver falha, Evolution API envia mensagem fallback: "Nossa recepção está com um pequeno atraso sistêmico. Já te respondemos com as informações!"
