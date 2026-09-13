# Colocar no ar

Roteiro para subir a Secretar.ia em um servidor só (VPS), do zero ao primeiro cliente atendendo. Leva cerca de
uma tarde. O que exige cartão ou conta em terceiro está marcado com **[contratar]**.

## 1. O que contratar antes

| Item | Para quê | Observação |
|---|---|---|
| **[contratar]** Servidor (VPS) | roda tudo | 4 GB de memória e 2 vCPUs atendem as primeiras dezenas de clientes. Ubuntu 24.04. |
| **[contratar]** Domínio | endereço do painel | três subdomínios: `app.`, `api.` e `wa.` |
| **[contratar]** Chave do Gemini | a inteligência da assistente | Google AI Studio, com faturamento ativo |
| **[contratar]** E-mail de envio (SMTP) | confirmações, convites, relatórios | qualquer provedor transacional; configure SPF e DKIM no domínio |
| **[contratar]** Chip de WhatsApp | número que atende | um por negócio; a conta demo pode usar um seu |
| Stripe | cartão recorrente | opcional: Pix e boleto já funcionam pelo admin |

O WhatsApp roda no próprio servidor pela Evolution API, que já vem no compose de produção. Ela precisa ficar
ligada sem parar, porque mantém a sessão do QR Code viva.

## 2. Apontar os domínios

Crie três registros A apontando para o IP do servidor:

```
app.seudominio.com.br   → IP
api.seudominio.com.br   → IP
wa.seudominio.com.br    → IP
```

Espere propagar antes de subir, senão o certificado falha.

## 3. Preparar o servidor

```sh
ssh root@IP
apt update && apt install -y docker.io docker-compose-plugin git
git clone <url-do-repo> /opt/secretaria && cd /opt/secretaria
```

## 4. Preencher os segredos

```sh
cp .env.prod.example .env                # domínios, senha do banco, chave da Evolution
cp backend/.env.example backend/.env     # o resto
docker run --rm python:3.12 python -c "import secrets;print(secrets.token_urlsafe(48))"   # para cada segredo
```

Em `backend/.env`, o mínimo para o backend aceitar subir em produção:

```
APP_ENV=production
JWT_SECRET=...            # 32+ caracteres
WHATSAPP_APP_SECRET=...   # mesma string usada no webhook
CRON_SECRET=...
EVOLUTION_API_KEY=...     # a mesma do .env da raiz
EVOLUTION_WEBHOOK_TOKEN=...
GEMINI_API_KEY=...
SMTP_HOST=... SMTP_USER=... SMTP_PASSWORD=... SMTP_FROM="Secretar.ia <no-reply@seudominio.com.br>"
SUPER_ADMIN_EMAIL=voce@seudominio.com.br
TOKEN_ENCRYPTION_KEY=...  # uv run python -m app.cli gen-key (só se for usar Google Calendar)
```

E o que deixa o produto com a sua cara:

```
SALES_WHATSAPP=5581999998888      # botão "Falar com a Júlia"
SALES_CONTACT_NAME=Júlia
DEMO_WHATSAPP=5581988887777       # "Converse com a assistente agora" na landing
ALERTS_EMAIL=voce@seudominio.com.br
LEGAL_ENTITY="Sua Empresa LTDA"   # aparece nas páginas de Privacidade e Termos
LEGAL_DOC="00.000.000/0001-00"
PRIVACY_EMAIL=privacidade@seudominio.com.br
```

## 5. Subir

```sh
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml logs -f backend   # migrations aplicam sozinhas no start
```

Confira:

```sh
curl https://api.seudominio.com.br/health   # {"status":"ok"}
curl https://api.seudominio.com.br/ready    # banco respondendo
```

Crie o primeiro administrador:

```sh
docker compose -f docker-compose.prod.yml exec backend uv run python -m app.cli create-superadmin \
  --email voce@seudominio.com.br --name "Seu Nome" --password "senha-forte"
```

## 6. Conectar o primeiro WhatsApp

1. Entre em `https://app.seudominio.com.br`, crie a conta de teste e libere o plano pelo admin.
2. Em Assistente & WhatsApp, clique em Conectar e leia o QR Code com o celular do número.
3. Mande uma mensagem de outro telefone e veja a resposta chegar.
4. Confira no Inbox e na Agenda que a conversa e o pedido apareceram.

## 7. Backup

```sh
sh deploy/backup.sh                                   # roda uma vez para testar
crontab -e
0 3 * * * cd /opt/secretaria && sh deploy/backup.sh >> /var/log/secretaria-backup.log 2>&1
```

Copie os arquivos de `backups/` para fora do servidor e **restaure um deles em um banco de teste pelo menos uma
vez**. Backup nunca testado não é backup.

## 8. Checklist de véspera

- [ ] `https://app...`, `https://api...` e `https://wa...` abrem com cadeado
- [ ] `/health` e `/ready` respondem
- [ ] Cadastro, liberação pelo admin e conexão do WhatsApp funcionaram de ponta a ponta
- [ ] Chegou e-mail de verificação na caixa de entrada, não no spam
- [ ] Páginas `/privacidade` e `/termos` abrem com a razão social e o CNPJ preenchidos
- [ ] `LEGAL_ENTITY`, `LEGAL_DOC` e `PRIVACY_EMAIL` definidos
- [ ] Backup rodou e a restauração foi testada
- [ ] Um relatório mensal e um lembrete de véspera foram disparados à mão para conferir o texto:
      `curl -X POST -H "Authorization: Bearer $CRON_SECRET" https://api.../api/internal/cron/reminders`
- [ ] Alguém é avisado quando o servidor cai (qualquer serviço de uptime aponta para `/health`)

## 9. Atualizar depois

```sh
cd /opt/secretaria && git pull
docker compose -f docker-compose.prod.yml up -d --build
```

As migrations aplicam no start. Para janelas com mudança grande de banco, faça o backup antes do `git pull`.

## Se algo der errado

| Sintoma | Onde olhar |
|---|---|
| Backend não sobe | `docker compose logs backend`: em produção ele recusa iniciar sem `JWT_SECRET`, `WHATSAPP_APP_SECRET` e `CRON_SECRET`, e exige https em `PUBLIC_API_URL` e `FRONTEND_URL` |
| Assistente não responde | conta liberada? WhatsApp conectado? veja Fila de tarefas no admin e `docker compose logs backend` |
| QR Code não aparece | `docker compose logs evolution`; confira `EVOLUTION_API_KEY` igual nos dois arquivos |
| E-mail no spam | falta SPF e DKIM no domínio do `SMTP_FROM` |
| Certificado não sai | DNS ainda propagando, ou as portas 80 e 443 estão ocupadas |
