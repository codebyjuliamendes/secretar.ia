# Decisões arquiteturais (ADRs)

Formato curto: contexto → decisão → consequências. Data de referência: setembro/2026.

## ADR-001 — Autenticação própria (JWT + refresh opaco) em vez de provedor externo

**Contexto.** O MVP não tinha autenticação; a stack é FastAPI + Prisma + Postgres (não Supabase).
**Decisão.** Implementar e-mail/senha com bcrypt, access token JWT curto (15 min) e refresh token opaco
armazenado como hash, com rotação e detecção de reuso. Verificação de e-mail e reset por tokens de uso único.
**Consequências.** Sem dependência de terceiros e sem custo por MAU; exige cuidado com SMTP em produção.
Login social (Google) pode ser adicionado como provedor adicional sem mudar o modelo.

## ADR-002 — Isolamento de tenant pela URL + membership, respondendo 404

**Contexto.** O MVP aceitava `tenantId` em query string sem autenticação (IDOR total).
**Decisão.** Todas as rotas de clínica vivem em `/api/clinic/{tenantId}/...`; uma dependência única carrega
a membership do usuário para aquele tenant e injeta o papel. Ausência de membership responde **404**, não 403,
para não revelar a existência de tenants. `SUPER_ADMIN` não é membro implícito.
**Consequências.** Impossível esquecer o filtro por tenant em um handler: o `tenant_id` vem do contexto
validado. RLS no Postgres não foi adotado porque o acesso é exclusivamente pelo backend com um único papel de
banco; se surgir acesso direto ao banco por clientes, RLS deve ser adicionado.

## ADR-003 — Fila persistida no Postgres com `FOR UPDATE SKIP LOCKED`

**Contexto.** A fila do MVP fazia `find_first` + `update` (race entre workers) e nunca recuperava jobs presos.
**Decisão.** Claim atômico via `UPDATE ... WHERE id = (SELECT ... FOR UPDATE SKIP LOCKED) RETURNING`,
backoff exponencial com jitter, `PermanentJobError` para falhas não retentáveis e recuperação de jobs
`RUNNING` há mais de N minutos. Sem Redis/Celery para manter uma única dependência de infraestrutura.
**Consequências.** Suporta múltiplas réplicas. Throughput limitado pelo Postgres (adequado para o volume de
mensagens de clínicas). Migração para uma fila dedicada é local a `app/jobs/queue.py`.

## ADR-004 — BFF no Next.js com cookies httpOnly

**Contexto.** O frontend chamava `localhost:8000` hard-coded e não havia sessão.
**Decisão.** Toda chamada do navegador passa por `/api/backend/*` (route handler), que anexa o access token
guardado em cookie `httpOnly`, renova via refresh em 401 e nunca entrega tokens ao JavaScript.
**Consequências.** Mitiga roubo de token por XSS; `API_URL` não precisa ser público; o CORS do backend pode
ficar restrito ao domínio do BFF. Custo: um hop extra por requisição.

## ADR-005 — IA com saída estruturada, reconciliação por regras e fallback determinístico

**Contexto.** O MVP simulava a IA com `if/else` e prometia recursos (RAG, Whisper, Vision, prompt caching)
inexistentes.
**Decisão.** Gemini via REST com `responseSchema` JSON, instruções de sistema separadas do texto do
paciente, limite de tokens/timeout e reconciliação da intenção com um classificador por regras (pedido
explícito de humano sempre prevalece). Sem chave ou em falha, responde por regras com os dados da clínica e
registra o modo degradado. Quotas mensais por plano são verificadas antes de chamar o modelo.
**Consequências.** Nenhuma funcionalidade fake em produção; custo controlado; recursos multimodais e RAG
ficam como evolução explícita (ver pendências no relatório de entrega).

## ADR-006 — Planos e quotas aplicados no backend

**Decisão.** `Plan` no tenant, limites em `app/domain/plans.py`, contadores mensais em `UsageCounter` com
`INSERT ... ON CONFLICT` atômico. Webhooks do Stripe atualizam status e plano via `metadata`.
**Consequências.** O frontend apenas exibe; nenhuma verificação de limite depende dele.

## ADR-007 — Integrações encapsuladas com modo explícito por ambiente

**Decisão.** WhatsApp, e-mail e IA têm um único ponto de acesso em `app/integrations/`. Em desenvolvimento,
sem credenciais, usam providers `console` (logam); em `staging`/`production` a ausência de credenciais é erro.
**Consequências.** Testes rodam sem rede; produção nunca "finge" sucesso.

## ADR-008 — Rate limit persistido no Postgres

**Contexto.** O limitador de login/cadastro/recuperação de senha era em memória: cada réplica tinha seu
próprio contador, o que multiplicava o limite efetivo e o zerava a cada deploy.
**Decisão.** Contadores por `(escopo, chave, janela fixa)` na tabela `RateLimitBucket`, incrementados com
`INSERT ... ON CONFLICT` atômico. Sem Redis, mantendo o Postgres como única dependência (coerente com
ADR-003). Se o banco falhar, o limitador abre (fail-open) e registra erro: indisponibilidade do banco já
impede o login e nunca deve virar bloqueio silencioso. Buckets antigos são apagados na manutenção diária.
**Consequências.** Limite consistente entre réplicas e entre deploys; uma escrita extra por tentativa de
login (irrelevante para o volume). Janela fixa em vez de deslizante: no pior caso permite até 2× o limite
na virada da janela, aceitável para proteção de força bruta.

## ADR-009 — Checkout e portal do Stripe via REST, plano só muda pelo webhook

**Contexto.** O billing só reagia a webhooks; contratar ou trocar de plano exigia contato manual.
**Decisão.** `integrations/stripe.py` cria Checkout Sessions (assinatura, `client_reference_id` = tenant,
metadata `tenantId`/`plan` na sessão e na assinatura) e sessões do Customer Portal, por REST com httpx (sem
SDK, como as demais integrações). O plano do tenant **nunca** muda na resposta do checkout: só quando o
webhook assinado confirmar (`checkout.session.completed`, `invoice.paid`, ...). Com assinatura ativa,
mudanças de plano e pagamento pendente vão para o portal, evitando duas assinaturas para o mesmo tenant.
Apenas `OWNER` (BILLING_MANAGE) pode iniciar checkout/portal. Sem chave em development, o provider console
devolve a URL de retorno marcada `checkout=console`; em produção a ausência de chave é erro.
**Consequências.** Fluxo self-service completo; a fonte de verdade continua sendo o webhook idempotente.
Os price ids ficam em variáveis de ambiente (um por plano contratável: BASIC e PRO); ENTERPRISE segue
negociado manualmente.

## ADR-010 — Áudio e imagem via Gemini multimodal (sem Whisper/Vision separados)

**Contexto.** Pacientes mandam áudio e foto com frequência; o webhook respondia `unsupported_message_type`
e a mensagem morria em silêncio. A pendência falava em "Whisper" e "Vision" como serviços à parte.
**Decisão.** Usar o próprio Gemini com entrada inline (`inlineData`): áudio → transcrição literal em
pt-BR; imagem → descrição objetiva em até 3 frases, com transcrição de textos legíveis e proibição explícita
de diagnóstico. O texto derivado entra no pipeline normal como mensagem do paciente, prefixado
(`[Áudio do paciente, transcrito] ...`), e os tokens são somados no `ExecutionLog`. Mídia da Evolution é
baixada via `getBase64FromMediaMessage`; o webhook normalizado aceita `mediaKind/mediaBase64/mediaMimeType`.
Sem IA configurada, arquivo acima do limite ou falha do provedor, a resposta é honesta ("só consigo ler
texto, pode escrever?") e registrada com `error=media_unreadable`; nunca fingimos ter entendido.
**Consequências.** Um único provedor e uma única chave; sem custo fixo de serviços adicionais. Limites de
16 MB (áudio) e 8 MB (imagem) por mensagem. Se for preciso trocar o provedor de transcrição, o ponto é
`services/media.py::client_for`.

## ADR-011 — Google Calendar por clínica com OAuth próprio e sincronização pela fila

**Contexto.** As equipes já vivem no Google Calendar; a agenda da Secretar.ia ficava isolada.
**Decisão.** OAuth 2.0 (código + refresh, `access_type=offline`) por tenant, iniciado por OWNER/MANAGER. O
`state` é um JWT assinado com tenant, usuário e validade de 15 min; o callback público revalida a membership
antes de gravar. Refresh e access tokens ficam cifrados (Fernet, `TOKEN_ENCRYPTION_KEY`) em
`CalendarConnection`. A sincronização é assíncrona: cada mudança de agendamento enfileira `sync-calendar`
(ADR-003), que faz upsert/delete do evento e guarda `externalEventId`; agendamentos pendentes viram eventos
`tentative` com prefixo "[Pendente]". Falha de credencial (`invalid_grant`) desliga a sincronização, registra
`lastError` e notifica a inbox; a UI oferece "Reconectar". Sem credenciais em development, um provider console
em memória permite testar o fluxo inteiro sem rede.
**Consequências.** Sentido único (Secretar.ia → Google): eventos criados diretamente no Google não bloqueiam
horários na IA. Leitura bidirecional (watch/push do Google) fica como evolução, reaproveitando a conexão.
Dependência nova: `cryptography` (Fernet).
