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
