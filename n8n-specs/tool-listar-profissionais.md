# Workflow: tool-listar-profissionais

**Nome no N8n:** `tool-listar-profissionais`
**Descrição:** Sub-workflow (Tool) acionado pelo agente de Agendamento para descobrir o corpo clínico.

## Trigger
- **Tipo:** Execute Workflow Trigger (Tool)
- **Descrição da Tool:** "Retorna a lista de médicos e especialistas disponíveis."

## Nós Ordenados

1. **Google Sheets - Buscar Profissionais**
   - **Operação:** Read Rows
   - **Sheet:** `ConfigClinica`
   - **Filtro:** Chave igual a `LISTA_PROFISSIONAIS` (ex: "Dra. Ana, Dra. Carla").
   
2. **Set (Formatação)**
   - Transformar a string em um formato claro para o LLM.

## Output
- Retorna (Return Node) a lista textual de profissionais.

## Tratamento de Erro
- Se falhar, retornar array vazio e notificar log.
