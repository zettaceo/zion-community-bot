# Block 3 audit — reconciled

Authoritative base: `zion-v1.1-dev` at
`d4cda026e0b9099d18af73d73322d876b7dc8e57`.

Canonical review branch: `audit/block3-reconciled` (Draft PR #6).

This branch reconciles both parallel Block 3 audit lines:

- PR #4 / `zion-v1.1-block3-guardian`
- PR #5 / `audit/block3-guardian-telegram`

Neither source branch is authoritative by itself. The reconciled branch keeps the
current Block 2 merge base and ports only evidence-backed hardening from both
lines.

## Reconciled controls

- Community-only moderation stops at the private-chat boundary, while secret and
  credential protection remains universal.
- Positive cached Telegram admin privilege is revalidated before privileged
  chat-local commands; negative cache entries remain bounded anti-amplification
  protection.
- Runtime admin and rate-limit caches are TTL-pruned.
- Link handling uses IDNA2008/UTS46 non-transitional normalization, rejects
  invisible hostname obfuscation, records unsupported schemes separately, and
  fails closed on unparseable or excessive Telegram link entities.
- Hidden URLs from text links, captions, inline-keyboard URL buttons,
  `login_url`, and `web_app` participate in link and secret inspection.
- Percent-encoded hidden URL credentials are decoded for detection without
  persisting the raw credential.
- Unicode/NFKC-obfuscated credential labels, HTTP basic-auth credentials,
  labeled Base58/byte-array wallet keys, mnemonic-like material, and PEM/OpenSSH
  private-key blocks are covered by deterministic protection.
- Command secret protection executes before the persistent command
  idempotency claim. This keeps deletion retriable if the process crashes before
  the normal command pipeline, while functional command side effects remain
  at-most-once.
- Ordinary moderation updates and join-service updates have persistent
  idempotency keys, preventing duplicate punitive/onboarding side effects from
  Telegram redelivery.
- Flood deletion is limited to the triggering time window. Flood containment and
  the incident are persisted before Telegram enforcement; the external result is
  recorded afterward.
- Manual mute/ban/unban persist intent before the external Telegram call.
- Raid onboarding is batch-safe. Join persistence, raid counting, and the local
  ELEVATED transition are committed atomically before network notifications.
- Domain policy changes and other operator policy mutations keep audit records in
  the same SQLite transaction as the local mutation.
- Operator-facing user-controlled text is sanitized against control/newline/bidi
  display spoofing.
- A command privilege-matrix regression locks the intended public/admin/operator
  boundaries.

## Conflict resolutions

Two parallel implementations handled IDNA differently. The automated branch
rejected `faß.de` because Python's legacy built-in IDNA codec may collapse it to
`fass.de`. The reconciled branch instead uses the external `idna` package with
UTS46 and `transitional=False`, so `faß.de` becomes the distinct
`xn--fa-hia.de` and cannot alias an ASCII allowlist.

Unsupported or malformed clickable targets are represented in
`LinkDecision.unsupported_schemes` rather than as a synthetic domain string.
This keeps domain policy evidence separate from parser/scheme evidence while
remaining fail-closed.

The source PR #5 CI failure was not a product failure: its synthetic OpenSSH key
fixture contained a literal PEM begin marker and was correctly rejected by the
repository secret scanner. The fixture is now assembled at runtime; the scanner
itself was not weakened.

A post-reconciliation review found one additional crash-ordering gap: command
update IDs were claimed before universal secret deletion. A crash between those
steps could suppress Telegram redelivery while leaving a credential visible. The
secret preflight now runs before the durable claim; the regression test proves
the claim is not attempted for a secret-bearing command.

## Validation

The first fully reconciled candidate completed GitHub CI with:

- 262 tests
- failures=0
- errors=0
- secret scan: OK
- ZION validation: OK

Automated test-name comparison found no source-PR regressions missing from the
reconciled suite. Two old IDNA test names were intentionally replaced because the
non-transitional IDNA2008 implementation makes the old “reject sharp-s” behavior
obsolete while preserving the security invariant.

## Residual boundary

Telegram effects and SQLite commits are not a distributed transaction. No network
`await` is placed inside a SQLite transaction to pretend otherwise. Intent can
be persisted before an external effect and outcome can be recorded afterward,
but a crash in between remains an explicit unknown-outcome boundary.

Real Telegram verification is still required for supergroup permission semantics,
admin-role changes during cache TTL, actual media/entity/update shapes, concurrent
update delivery, and crash timing around external effects. Production, the Acer,
the live SQLite database, `.env`, systemd, network configuration, and deployment
are outside this GitHub-only Block 3 audit.

## Revisão independente final — 2026-09-20

Revisão local em clone novo `/tmp/zion-block3-final-Z3vt4rf8/repo`, com venv
próprio Python 3.12.3. Nenhum arquivo/venv/banco/configuração de produção foi
usado para os testes. Não foi iniciada instância de polling do bot. Objetos
Runtime nos testes usam DB, locks e serviços fake em diretórios descartáveis.

### Estado inicial verificado no GitHub

- Produção `zion-v1`: `f8c704f16d05c5fba3b55957721b025c9abbaa23`.
- Desenvolvimento: `d4cda026e0b9099d18af73d73322d876b7dc8e57`.
- PR #6 Draft, base `zion-v1.1-dev`, head `audit/block3-reconciled`:
  `f373ef483a44deba96a7daaea783b058fdce991f`.
- [CI #817 / run 35504298622](https://github.com/zettaceo/zion-community-bot/actions/runs/35504298622): SUCCESS nesse HEAD.
- PR #2 aberto e Draft; PRs #4/#5 fechados, `mergedAt=null`.
- Não houve divergência dos HEADs esperados.
- Produção local limpa em `zion-v1-prod`, mesmo commit estável; serviço
  active/running, PID 1610, NRestarts=0, início 2026-09-19 13:47:41 -03,
  WorkingDirectory `/home/zetta/zion-community-bot`. Somente consultas read-only
  ao Git e ao systemd; nenhum acesso ao DB ou à `.env` de produção nesta revisão.

### Descobertas reproduzidas e correções

| Severidade | Local | Reprodução anterior | Correção e regressão |
| --- | --- | --- | --- |
| HIGH | `_telegram_link_candidates` / `telegram_sensitive_surface` | 20 URLs benignas antes de uma URL com credencial; em privado ela escapava e um comando podia chegar ao claim | Inspeção universal usa todos os alvos completos; limites de 20/2048 ficam exclusivos da política de domínios. Teste cobre entities, caption, button, login_url e web_app, comando e mensagem comum |
| HIGH | Superfície sensível de URL | Rótulo duplamente percent-encoded ou depois de 2048 caracteres não era visto | Duas passagens limitadas de decode em conteúdo visível e URLs completas; testes falharam antes e passaram após a correção |
| HIGH | `BASIC_AUTH_URL_REGEX` | Userinfo `user:password@host` em ftp/custom escapava no privado, pois só HTTP(S) era reconhecido | Detectar e redigir userinfo com senha em esquemas sintaticamente válidos; não altera a allowlist de esquemas da política de links |
| MEDIUM | `ama_open_command` | Título com newline/bidi forjava campos na confirmação administrativa | `safe_display_text` na confirmação, preservando título armazenado; teste de saída |
| MEDIUM | `_enforce_flood` | Falha simulada de mute gerava aviso “silenciado” apesar de action.success=0 | Aviso explícito de falha e contenção local; regressão comprova ledger e resposta |

Commits de implementação:

- `a804e2f1f216dc8c1a3ac84b88adc9f545364547`: inspeção universal da superfície completa e userinfo.
- `1867b7ad9c420a55c5be4fbb4c8fe36888137216`: respostas de flood/AMA e matriz adicional de revisão.

Nenhuma descoberta HIGH/CRITICAL permaneceu aberta na revisão. As fixtures são
sintéticas; scanner e regras existentes não foram enfraquecidos. A regex de
userinfo foi ampliada com testes de detecção e redação, não relaxada para obter CI.

### Matriz da auditoria final

| Área | Verificação independente e evidência |
| --- | --- |
| Autoridade | Allowlist explícito em `is_operator`; `require_admin` revalida cache positivo e consulta membership real; privado sem allowlist retorna false. Cache negativo limita amplificação. Testes existentes de demotion durante TTL e matriz public/admin/operator preservados; teste novo cobre todos os comandos globais contra admin de grupo e falha de membership após cache positivo |
| Privado | Link/comando/mensagem normal ignora moderação comunitária. Teste novo mantém containment ativa e percorre NORMAL/ELEVATED/ATTACK/LOCKDOWN, fazendo falhar o teste se flood/containment/link-policy forem invocados. Nenhuma punição comunitária ou consulta de membership |
| Segredo em privado/admin | Preflight anterior às isenções; teste matricial de API key, Authorization/Bearer, password, access token, seed multiline, hex, Base58, bytes, OpenSSH, labels fullwidth/zero-width. Testes originais Telegram token/PEM/redação mantidos. Teste de superfícies escondidas verifica ausência de URL/valor no dump local |
| Links | IDNA2008 UTS46 transitional=False; `faß.de` → `xn--fa-hia.de`, distinto de `fass.de`; lookalikes/punycode, invisíveis e fullwidth cobertos. Targets extraídos de text_link, url parser, caption, buttons/login_url/web_app. Esquemas clicáveis desconhecidos, javascript/data/tg/ftp e URLs malformadas geram evidência de bloqueio; overflow/parser failure continuam fail-closed na política comunitária |
| Ordenação de comando | Revisados commits de859b3/09a0c6f/f373ef4: preflight de segredo antes do claim. Teste original garante claim não chamado; novos testes após 20 links e fault injection de audit após delete também garantem isso. Retry pode repetir delete, nunca o efeito funcional do comando |
| Idempotência/crash | Duplicatas de comando/moderação/join continuam suprimidas. Novo teste fecha e recria Runtime após claim e confirma supressão. Falha de ledger para comando normal fecha o gate. Claim não significa sucesso externo; uma queda após claim pode perder execução, deliberadamente at-most-once |
| Flood | Contagem e strike/containment/intent persistidos em transaction síncrona. Threshold ELEVATED/ATTACK nunca acima de NORMAL; expiração de strikes, reincidência objetiva, janela de deleção e distributed burst preservados. Novos testes verificam mute falho e fallback ban→mute; IA não participa da decisão |
| Raid/onboarding | `welcome_handler` agrupa claim, users, joins, contagem, estado/prazo e ledger antes de notificações; lote gera uma recepção, bots não contam. Fault injection de action reverte contadores/claim/estado e não notifica; retry funciona. Duplicata após commit não repete welcome |
| Efeitos externos | Manual mute/ban/unban tem intenção anterior; resultado depois. Falha de intenção impede chamada; falha de resultado mantém intenção e propaga erro (testes existentes). Delete de segredo precede ledger e é retriável. Welcome/alertas têm resultado externo incerto se houver crash após commit. Nenhuma promessa de exactly-once |
| Cache/memória | Admin e rate-limit têm prune por TTL; negativos não viram autoridade e positivos são revalidados nos comandos privilegiados. Rate-limit limita eventos por chave; quantidade de usuários/chats distintos dentro do TTL não possui quota absoluta. O custo da inspeção de segredos acompanha o tamanho do update recebido, sem truncamento silencioso da superfície |
| Output | `safe_display_text` normaliza whitespace/remove controles Unicode categoria C, incluindo bidi; aplicado em username/first_name, incident note/evidence, gaps e AMA. Regressões de campos administrativos preservadas; confirmação de abertura AMA agora também sanitizada |
| Transações | Varredura AST em todos os módulos `zion/*.py`: 24 scopes em telegram_app, 2 no Guardian e 14 no DB; zero Await dentro de transaction/_transaction_locked. Guardian segue síncrono. Teste permanente percorre todos os módulos |

### Preservação semântica dos PRs #4 e #5

Comparação realizada contra SHAs exatos, não apenas contagem de commits:

- PR #4: `5875e8f60e342b0af8cd0e1712f4e961e6a30eb1`, 226 testes de origem.
- PR #5: `d7cc22aa398967a3a003afb09e6401fe87d75de6`, 223 testes de origem.

[Comparação dos nomes dos testes](evidence/block3-source-tests.json).
Do PR #5 nenhum nome de teste falta. Do #4 faltam somente as duas expectativas
antigas que rejeitavam sharp-s, substituídas por três regressões de distinção
IDNA2008/allowlist. Métodos de teste alterados foram lidos no diff: threshold mais
restrito, fixtures Base58/bytes, classificação de esquema separada de domínio e
fixture OpenSSH montada em runtime preservam o propósito de segurança.

A revisão dos cinco módulos e testes associados confirmou:

- `guardian.py`: herda normalização/obfuscação, schemas recusados, seeds multiline,
  janela de flood e limites do #4; preserva IDNA2008, contenção para pending ban,
  incident_id e serializers de chave do #5. Helpers antigos foram consolidados,
  não removidos sem substituição funcional.
- `telegram_app.py`: conserva parsing fail-closed e ordering do #4, soma keyboard
  e URL credential inspection, revalidação de autoridade, sanitização e audit
  intent do #5. Onboarding reconciliado é atômico e por lote; preflight de segredo
  foi revalidado. A presente correção fecha os limites indevidamente compartilhados.
- `logging_safe.py`: mantém NFKC/zero-width e userinfo do #4 e blocos PEM/OpenSSH
  do #5; nova cobertura de userinfo fora de HTTP não retira nenhuma redação.
- `models.py`: mantém `unsupported_schemes` do #4 e `FloodDecision.incident_id` do #5.
- `config.py`: mantém normalização de allowlist do #5 com IDNA externo
  não-transicional; rejeitar sharp-s pela conversão legada não foi reintroduzido.
- Testes Guardian, moderação, raid, segurança, configuração e comandos
  comunitários foram executados na suíte completa, junto com atomicidade,
  concorrência, idempotência, crash e persistência do Bloco 2.

### Validação local final e gates

Baseline independente: **262 testes / 12.384 s**, verde.
Após correção de segredos: **268 / 13.665 s**, verde.
Final de implementação: **279 / 16.929 s**, failures=0/errors=0/skipped=0.
São **17 novos testes** (muitos com subcasos), sem exclusão de teste existente.
Compile, runtime/imports, unittest, sintaxe shell, sensitive tracked files,
SECRET SCAN e ZION VALIDATION: OK; `git diff --check`: OK.
[Resumo reproduzível](evidence/block3-final-validation.txt).

```bash
# Executar somente no clone isolado, com seu venv próprio.
bash scripts/validate.sh
.venv/bin/python -m unittest tests.test_block3_final tests.test_block3_review -v
git diff d4cda026e0b9099d18af73d73322d876b7dc8e57..HEAD --check
```

O merge-base permaneceu `d4cda026e0b9099d18af73d73322d876b7dc8e57`. Este commit
registra evidência **pré-merge**: o PR só poderá deixar Draft e ser integrado
com CI do seu HEAD remoto verde, produção remota/local intacta e PR #2 ainda
Draft. SHA do merge e run pós-merge serão informados na entrega final; nenhum
resultado futuro é presumido aqui.

### Limites operacionais antes de deploy

Não havia ambiente Telegram isolado explicitamente identificado nesta tarefa;
não foram usados tokens reais nem realizadas chamadas punitivas reais. Permanecem
pendentes antes de deploy: permissões reais de supergrupo, promoção/remoção de
admin, mídia/entities reais, concorrência de updates e crash ao redor de I/O
Telegram. Testes fake/unitários não substituem essas verificações.

A proteção é determinística, não um detector universal de toda ofuscação possível.
Decodificação de URL cobre até duas camadas percent-encoded, deliberadamente sem
loop ilimitado; não promete decodificar codificações arbitrárias. O overflow de
links ainda bloqueia política comunitária, mas sozinho não pune mensagem privada.
Caches têm expiração, não uma quota global de memória sob volume arbitrário.

SQLite não pode reverter Telegram. Ausência de action não prova ausência de
efeito externo; intenção registrada não prova resultado. Falha de delete por
permissões/rede pode deixar material visível, mesmo quando detectado; não se afirma
que o bot pode apagar sem direitos no chat. Produção permanece fora da integração
de desenvolvimento: PR #2 continua Draft, sem deploy/restart ou migração real.
