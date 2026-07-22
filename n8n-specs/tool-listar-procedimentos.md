# Workflow: tool-listar-procedimentos

**Nome no N8n:** `tool-listar-procedimentos`
**Descrição:** Sub-workflow (Tool) acionado pelo agente de Agendamento.

## Trigger
- **Tipo:** Execute Workflow Trigger (Tool)
- **Descrição da Tool:** "Retorna a lista de procedimentos estéticos oferecidos pela clínica."

## Nós Ordenados

1. **Google Sheets - Buscar Procedimentos**
   - **Operação:** Read Rows
   - **Sheet:** `ConfigClinica`
   - **Filtro:** Chave igual a `LISTA_PROCEDIMENTOS` (certifique-se que essa chave seja criada no Sheets e contenha valores separados por vírgula, ex: "Botox, Preenchimento, Peeling").
   
2. **Set (Formatação)**
   - Transformar o valor retornado em um array legível para o Agente.

## Output
- Retorna (Return Node) o array de procedimentos.

## Tratamento de Erro
- Se Sheets falhar, retorna `["Erro ao carregar procedimentos. Peça para o paciente aguardar um humano."]`. O workflow principal trata erros silenciosos no Error Trigger.
