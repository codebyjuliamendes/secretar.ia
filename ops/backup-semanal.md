# Procedimento de Backup Semanal

Como não estamos utilizando infraestrutura Git nativa conectada ao N8n Cloud Starter, o backup dos workflows é uma tarefa manual crítica que deve ser executada **toda sexta-feira**.

## Passo a Passo

1. **Acessar o N8n Cloud**
   - Acesse a interface do N8n e abra a lista de Workflows (pasta do cliente).

2. **Download das Definições**
   - Para **cada um dos 10 workflows**:
     1. Abra o workflow.
     2. Clique nas configurações do workflow (engrenagem no canto superior direito) ou no menu `...`.
     3. Selecione **Download** (isso baixará um arquivo `.json`).

3. **Versionamento Seguro**
   - Mova os arquivos `.json` baixados para a pasta local da sua máquina.
   - (Opcional) Faça o commit num repositório Git privado de infraestrutura:
     ```bash
     git add backups/
     git commit -m "Backup semanal cliente X - YYYY-MM-DD"
     git push
     ```

4. **Backup do Google Sheets (Opcional, porém recomendado)**
   - Acesse a planilha de Modelo de Dados do cliente.
   - Vá em `Arquivo -> Fazer o download -> Microsoft Excel (.xlsx)`.
   - Guarde na mesma pasta de backup.

## Restauração (Se necessário)
Para subir um backup:
- No N8n, crie um workflow em branco.
- Clique no menu `...` e depois em **Import from File**.
- Selecione o `.json` correspondente. As credenciais precisarão ser religadas se for em um novo workspace.
