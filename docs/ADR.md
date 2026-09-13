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

## ADR-012 — Base de conhecimento com pgvector e fallback para busca textual

**Contexto.** A IA só conhecia prompt, catálogo e horários; dúvidas sobre preparo, políticas e pagamento
viravam "vou confirmar com a equipe" ou, pior, invenção. ADR-005 deixou RAG como evolução explícita.
**Decisão.** Documentos livres por clínica (`KnowledgeDocument`, até 50 por tenant e 30 mil caracteres cada)
são partidos em trechos de ~800 caracteres por parágrafo (`KnowledgeChunk`) com embedding Gemini
(`gemini-embedding-001`, 768 dims) em coluna `vector(768)` do pgvector, no mesmo Postgres (sem serviço de
busca à parte). A cada mensagem, os 4 trechos mais próximos (cosseno) entram no prompt em um bloco próprio,
com instrução de usá-los como única fonte para dúvidas e de encaminhar à equipe o que não estiver ali. Sem
chave de IA ou em falha de embedding, os trechos ficam sem vetor e a recuperação usa `to_tsvector('portuguese')`
com termos em OR ranqueados por `ts_rank`; a resposta por regras também cita o melhor trecho. A coluna é
`Unsupported` no Prisma: escrita e busca via SQL bruto em `services/knowledge.py`.
**Adendo (12/set/2026) — índice HNSW.** A migration `20260912100000_knowledge_hnsw` cria
`KnowledgeChunk_embedding_idx` como `USING hnsw (embedding vector_cosine_ops)`. O schema declara o mesmo
índice como `@@index([embedding])`: o Prisma não expressa HNSW, mas não compara o algoritmo no diff, então a
verificação de drift do CI fecha (verificado localmente). Como o filtro por `tenantId` é aplicado depois da
vizinhança aproximada, a busca roda com `SET LOCAL hnsw.iterative_scan = relaxed_order` (pgvector ≥ 0.8)
dentro de uma transação, para que clínicas pequenas em uma tabela grande não recebam resultado vazio; se o
servidor não conhecer o parâmetro, a consulta simples é usada. Nunca recriar o índice via `migrate dev`
(sairia btree e falharia: 768 dims excedem a entrada máxima do btree).
**Consequências.** Postgres precisa da extensão `vector` (imagem `pgvector/pgvector:pg16` no compose e no CI;
Neon/Supabase já oferecem). Reindexação manual disponível para quando a chave de IA for configurada depois.
Ingestão de PDF/URL e sugestão automática de documentos ficam como evolução.

## ADR-013 — Leitura de mídia e base de conhecimento como recursos de plano (PRO no trial)

**Contexto.** ADR-010 e ADR-012 deixaram explícito que o gating de áudio/imagem e RAG por plano era decisão de
produto pendente. Sem ele, o FREE consumia Gemini multimodal e embeddings sem nenhuma receita associada.
**Decisão.** `PlanLimits` ganha `media_understanding`, `knowledge_base` e `max_knowledge_documents`: FREE não
tem nenhum dos dois; BASIC tem ambos com 10 documentos; PRO 50; ENTERPRISE ilimitado. Durante o **trial** a
clínica usa os recursos do PRO (`TRIAL_FEATURE_PLAN`), mantendo os limites de volume (mensagens, pacientes,
membros) do plano contratado — recurso é o que se experimenta, volume é o que se paga. A resolução fica em
`domain/plans.py::feature_plan/feature_enabled` e é aplicada no backend: mídia fora do plano responde ao
paciente pedindo texto sem acionar o provedor, registra `error=media_not_in_plan` e avisa a clínica na inbox
(BILLING, dedupe 24 h); base de conhecimento fora do plano devolve 402 `plan_feature_locked` em criar/reindexar,
a IA não recupera trechos e a busca de teste responde `locked`. Documentos existentes de uma clínica que caiu
para o FREE são preservados e voltam a valer ao subir de plano. O frontend só reflete (`featureAccess` nas
configurações, `knowledgeDocuments` no uso, recursos nos cards de plano).
**Consequências.** Custo de IA alinhado à receita; conversão do trial pela experiência completa. Mudar a
política é alterar `PLAN_LIMITS`/`TRIAL_FEATURE_PLAN`, sem tocar em rotas. O campo `Tenant.features` (Json)
continua livre e **não** sobrepõe o plano: um OWNER poderia editá-lo pela API de configurações.

## ADR-014 — Ingestão de PDF e URL na base de conhecimento, sem OCR e com proteção contra SSRF

**Contexto.** ADR-012 deixou a ingestão de PDF/URL como evolução: as clínicas já têm o conteúdo em manuais
PDF e no site, e colar texto à mão limita a adoção da base de conhecimento.
**Decisão.** `services/knowledge_sources.py` transforma fontes em texto e reaproveita `add_document`:
- **PDF** (`POST /knowledge/upload`, multipart, até 10 MB; também `.txt`/`.md`) com `pypdf`. Sem OCR: um PDF
  digitalizado sem camada de texto é recusado (`pdf_no_text`) em vez de virar documento vazio. Linhas quebradas
  pelo layout viram um parágrafo; linhas em branco separam parágrafos, que é o que o chunker entende.
- **URL** (`POST /knowledge/import-url`): só `http/https`, sem credenciais na URL; o host é resolvido e recusado
  se qualquer IP for privado, loopback, link-local, multicast, reservado, NAT compartilhado ou IPv4 mapeado em
  IPv6 (cobre `127.0.0.1`, `localhost`, `169.254.169.254`, `[::1]`). Redirecionamentos são seguidos à mão
  (máx. 3) revalidando cada destino, o corpo é lido em streaming com teto de 2 MB, e só HTML, PDF e texto são
  aceitos. HTML vira texto por parágrafos com o `HTMLParser` da biblioteca padrão (sem `script/style/nav`),
  e o `<title>` vira o título do documento.
- Conteúdo maior que um documento (30 mil caracteres) é dividido em partes "Título (i/n)" em limites de
  parágrafo, e a cota de documentos do plano (ADR-013) é verificada **antes** de gravar qualquer parte:
  importação é tudo-ou-nada. `KnowledgeDocument.source/sourceRef` registram a origem (`text|pdf|url|file`).
- Testes rodam sem rede: `httpx.MockTransport` e resolução de DNS injetados; o PDF de teste é gerado em memória
  com xref válido.
**Consequências.** Dependências novas: `pypdf` e `python-multipart`. A verificação de IP acontece antes da
requisição e o httpx resolve o nome de novo ao conectar (janela teórica de DNS rebinding); para fechar isso
seria preciso conectar ao IP validado com SNI manual, o que fica como evolução se o produto ganhar exposição.
Páginas que exigem JavaScript para renderizar o conteúdo não são suportadas (só o HTML servido). OCR de PDFs
digitalizados fica como evolução (Gemini multimodal já lê imagens; um caminho é rasterizar as páginas).

## ADR-015 — Leitura do Google Calendar por polling incremental (syncToken), não por push

**Contexto.** ADR-011 deixou a agenda em sentido único: um compromisso criado direto no Google não bloqueava
horários e a IA podia oferecer um slot já ocupado. A evolução prevista falava em watch/push do Google.
**Decisão.** Polling incremental em vez de push, por enquanto: o job `pull-calendar` roda a cada 10 minutos
por conexão ativa (scheduler interno com advisory lock; também `POST /internal/cron/pull-calendar`), logo
após conectar e ao ressincronizar. Usa `events.list` com `singleEvents=true`, `showDeleted=true` e o
`nextSyncToken` guardado em `CalendarConnection.syncToken`; `410 Gone` ou uma leitura completa a cada 24 h
(`lastFullPullAt`, porque a janela de tempo fica presa ao token) refazem a janela (−24 h, +60 dias) e removem
o que não voltou. Os eventos são espelhados em `ExternalBusy` (único por tenant+`externalId`), ignorando os
da própria Secretar.ia (`extendedProperties.private.secretariaAppointmentId` ou `externalEventId` conhecido),
cancelados, `transparency=transparent` e os recusados pelo dono da agenda; evento de dia inteiro ocupa o dia no
fuso da clínica. `scheduling.busy_between` passa a somar `ExternalBusy`, então `free_slots` (o que a IA
oferece), `check_availability` (criação manual, salvo `force`) e o calendário semanal (`external`) enxergam os
bloqueios. Desconectar apaga o espelho; a manutenção diária descarta bloqueios com mais de dois dias passados.
**Por que não push agora.** `events.watch` exige endpoint público em HTTPS, canais que expiram e precisam de
renovação, e a notificação não traz o evento — só dispara um `events.list` incremental, exatamente o que o
polling já faz. Quando a latência de até 10 minutos incomodar, o watch entra como gatilho do mesmo job
(`enqueue(PULL_CALENDAR)`), sem mudar o modelo.
**Consequências.** Uma leitura por conexão a cada 10 min (barata: incremental, quase sempre vazia). Escopo
OAuth `calendar.events` já cobre leitura; conexões existentes não precisam reconectar. Compromissos em outros
calendários da mesma conta (só `calendarId=primary` é lido) e recorrências com exceções muito distantes ficam
fora da janela até a próxima leitura completa. Provider console ganha `external_events` e simulação de token
expirado para testar tudo sem rede.
