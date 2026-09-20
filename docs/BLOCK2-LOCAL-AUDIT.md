# Bloco 2 — SQLite e persistência: relatório final local

Data: 2026-09-19. Escopo executado exclusivamente em
`/home/zetta/zion-community-bot-v11`, branch `codex/block2-sqlite`.
**Bloco 2 concluído para auditoria local; sem integração ou deploy.**

A parada anterior confirmou a race de sobrescrita do backup. A autorização de
retomada permitiu corrigi-la, continuar os ensaios e manter a `.env` fora dos
backups comuns. Nenhum novo risco alto/crítico exigindo parada foi confirmado.

## A. Inventário e base auditada

| Caminho real | Branch | HEAD |
| --- | --- | --- |
| `/home/zetta/zion-community-bot` | zion-v1-prod | f8c704f16d05c5fba3b55957721b025c9abbaa23 |
| `/home/zetta/zion-community-bot-v1` | zion-v1-local | f8c704f16d05c5fba3b55957721b025c9abbaa23 |
| `/home/zetta/zion-community-bot-v11` | codex/block2-sqlite | Três commits de implementação abaixo, seguidos pelo commit deste relatório |
| `/home/zetta/zion-backups` | Não é repo Git | — |

`pwd` inicial era a produção; todos os comandos de edição/validação foram
executados explicitamente na nova worktree. Não foram encontrados AGENTS.md
nos ancestrais/repositórios inspecionados, excluindo venv e metadados Git.

Remote: `https://github.com/zettaceo/zion-community-bot.git`.
O fetch autorizado trouxe `origin/zion-v1.1-dev` em
`82f2471f3b112a93eb76aad267626a0ad1785634`, base exata da worktree.
Não foi forçado o SHA antigo `53e9708`.
`origin/zion-v1` permaneceu em `f8c704f16d05c5fba3b55957721b025c9abbaa23`;
produção tinha 0 commits à frente/atrás. `main` e `dev` locais não foram alteradas.
A worktree histórica já tinha `?? .venv`, preservado.

CI remoto do SHA-base:
[push SUCCESS](https://github.com/zettaceo/zion-community-bot/actions/runs/35465181297)
e [PR SUCCESS](https://github.com/zettaceo/zion-community-bot/actions/runs/35465183489).
Esses resultados são da base, não dos commits locais sem push.

## B. Produção real

| Campo | Antes e após a retomada |
| --- | --- |
| Serviço | zion.service, active/running |
| MainPID | 1610 |
| NRestarts | 0 |
| Início | Sat 2026-09-19 13:47:41 -03 |
| WorkingDirectory e /proc/1610/cwd | /home/zetta/zion-community-bot |
| ExecStart | /home/zetta/zion-community-bot/.venv/bin/python /home/zetta/zion-community-bot/bot.py |
| Executável resolvido | /usr/bin/python3.12 |
| Branch/commit | zion-v1-prod / f8c704f16d05c5fba3b55957721b025c9abbaa23 |

Na inspeção inicial, a varredura dos processos Python legíveis encontrou apenas
PID 1610 como candidato ZION/bot.py. Não houve leitura de environment do processo.
`systemctl status` foi consultado com `--lines=0`, evitando conteúdo do journal.
Produção permaneceu limpa. O fetch inicial e a criação da worktree alteraram
somente metadados Git compartilhados, sem checkout/pull da produção.

## C. SQLite produção — somente leitura

Origem aberta por URI `file:/home/zetta/zion-community-bot/zion.db?mode=ro`.
Somente metadados/contagens foram extraídos; nenhum conteúdo de linha foi impresso.

| Campo | Valor |
| --- | --- |
| DB/WAL/SHM | 159744 / 0 / 32768 bytes |
| quick_check / integrity_check | ok / ok, inclusive nas cópias finais |
| journal_mode | wal |
| foreign_keys na conexão de inspeção inicial | 0 |
| busy_timeout na conexão de inspeção | 5000 ms |
| page_size / page_count / freelist_count | 4096 / 39 / 0 |
| user_version | 0 |
| page_count × page_size / freelist ratio | 159744 bytes / 0 |

`foreign_keys` e `busy_timeout` pertencem à conexão; isso não mede a conexão do
serviço. O candidato habilita foreign_keys=1. O versionamento do candidato usa
`schema_migrations`, não `user_version`.

| Tabela original | Origem | Cópia antes | Após migração/restauração |
| --- | ---: | ---: | ---: |
| actions | 0 | 0 | 0 |
| ai_events | 0 | 0 | 0 |
| containments | 0 | 0 | 0 |
| domains | 0 | 0 | 0 |
| incidents | 0 | 0 | 0 |
| knowledge_gaps | 0 | 0 | 0 |
| recent_messages | 0 | 0 | 0 |
| scheduled_messages | 0 | 0 | 0 |
| settings | 2 | 2 | 2 |
| strikes | 3 | 3 | 3 |
| user_events | 0 | 0 | 0 |
| users | 1 | 1 | 1 |

Índices explícitos originais: idx_actions_created, idx_ai_events_created,
idx_incidents_created, idx_incidents_retention, idx_knowledge_gaps_last_seen,
idx_knowledge_gaps_open, idx_recent_messages_created, idx_recent_messages_user,
idx_scheduled_pending, idx_strikes_active, idx_user_events_type_window,
idx_user_events_user; mais um sqlite_autoindex de PK em cada tabela.

Permissões observadas, uid/gid 1000:
DB, WAL, SHM, zion.log e `.env`: **0600**; `backups/` e
`/home/zetta/zion-backups`: **0700**.
`~/.local/state/zion-community-bot/` estava ausente; não foi criado.
Log: 6632309 bytes; `.env`: 320 bytes, apenas stat.
DB/WAL/.env conservaram respectivamente mtime_ns
1789832780783347345 / 1789836462048975655 / 1789812807633369062,
além dos tamanhos/modos originais, na conferência final.

## D. Cópia consistente e evidência reproduzível

Ensaio final sobre o código em `89b3c42ae6817f5839e3fc478b3e64ba2836cb25`:

```bash
cd /home/zetta/zion-community-bot-v11
/home/zetta/zion-community-bot/.venv/bin/python \
  scripts/rehearse-sqlite-copy.py /home/zetta/zion-community-bot/zion.db
```

O script abre a origem read-only, fixa um snapshot de leitura e usa
`sqlite3.Connection.backup()`. Nunca inicializa/chmod a origem.
Destino da execução final:
`/tmp/zion-block2-20260919T225946Z-1d18wi8f/zion.db`.
Diretório 0700, banco 0600, 159744 bytes antes da migração.
SHA256 **antes de migrar**:
`06d3a6a86dbec6a5447876a795fd943fc39b8dc02e31570c4fd1d99d82f8d7b1`.
O arquivo nesse caminho depois foi migrado e usado no ensaio WAL; o hash acima
é o snapshot pré-migração, não o hash atual do arquivo.

[Metadados completos, sem conteúdo pessoal](evidence/block2-copy-rehearsal.json)
e evidência privada original em `evidence.json` no diretório temporário.
Cópias anteriores, igualmente privadas, permaneceram em
`/tmp/zion-block2-20260919T224936Z-i_g53ndx` e
`/tmp/zion-block2-20260919T225625Z-n_zk_i2i`. São artefatos descartáveis locais,
sem versionamento do DB; nenhum backup de produção foi removido.

## E. Migração e restauração

- Schema antes: 0, sem schema_migrations; depois: **2**.
- Markers: 1 scheduler_delivery_reliability; 2 scheduler_claim_tracking.
- 12 tabelas originais preservadas; cinco adicionais: schema_migrations (2
  linhas), idempotency_keys, recurring_messages, ama_sessions e ama_questions
  (0 linhas cada).
- Todas as contagens e **todos os valores das colunas originais** comparados em
  memória na cópia: preservados. Nenhum valor pessoal foi exibido.
- Segunda initialize: dump de schema/dados idêntico em memória, inclusive markers
  e timestamps; nenhum estado foi reescrito.
- quick_check/integrity_check: ok; foreign_keys=1; journal_mode=wal;
  busy_timeout=5000; synchronous=FULL (2); trusted_schema=0;
  wal_autocheckpoint=1000; journal_size_limit=16777216;
  application_id=1514753870.
- Backup migrado: `migrated-backup.db` no diretório final, 221184 bytes, 0600.
  Fonte fechada antes da abertura independente do backup. Schema, contagens e
  conteúdo lógico idênticos; checks OK. SHA do backup consta na evidência JSON.

Falha injetada durante initialize agora reverte DDL, application_id, colunas,
markers e defaults juntos. PRAGMAs de conexão/journal são configurados antes de
BEGIN, por exigência SQLite; não se promete rollback do modo de journal.
Dois inicializadores concorrentes terminam com uma única linha por versão.
Banco com schema futuro é recusado antes de adotar application_id.

## F. Falhas, concorrência e limites

| Ensaio | Evidência/resultado |
| --- | --- |
| BUSY real na cópia | A mantém BEGIN IMMEDIATE; B espera 5.011877 s, lança SQLITE_BUSY, in_transaction=false, chave de teste ausente; novas escritas funcionam após liberar A |
| Crash antes do commit | Subprocesso separado, handshake com timeout, SIGKILL: mudança ausente; quick/integrity OK |
| Crash após commit | Segundo subprocesso, synchronous=FULL, commit retornado antes do handshake/SIGKILL: mudança presente; quick/integrity OK |
| WAL na cópia real | Reader conta 0 antes/durante; writer confirma 20; reader conta 20 após encerrar snapshot; WAL 0 → 329632 bytes |
| PASSIVE com reader preso | 80 frames no log, 0 checkpointed; operação não força desbloqueio do leitor |
| PASSIVE após reader liberar | 80/80 frames; 20 registros preservados; checks OK |
| SQLITE_FULL multi-write | max_page_count em DB sintético, primeira escrita pequena seguida de 2 MiB na mesma transação/savepoint; código SQLITE_FULL preservado, primeira escrita revertida, in_transaction=false, checks OK |
| Corrupção fora do header | Cópia sintética independente: byte de tipo da página b-tree de users alterado para 0xff; quick/integrity detectam; HealthService db_ok=false |
| Health com cache saudável | Erro real de leitura de estado invalida cache; db_ok=false e SAFE_MODE, mesmo que SELECT 1 ainda funcione |
| Race de backup injetada | Destino criado durante a janela; FileExistsError, bytes concorrentes preservados, temporários limpos, origem íntegra |
| Race de backup real | Dois processos spawn, barreira imediatamente antes do os.link real: exatamente um sucesso e um FileExistsError; arquivo final íntegro/0600 |
| Backup/restore | Banco real copiado/migrado/backupeado; origem fechada; backup aberto independentemente, conteúdo/schema/counts idênticos |
| Permissões | DB/WAL/SHM 0600; scratch 0700; backup privado desde criação, antes de publicar |
| Stale sending | Testes existentes mantêm quarentena uncertain/paused, sem replay automático |

Testes relevantes: `test_backup_publication.py`, `test_transaction_atomicity.py`,
`test_block2_failures.py` e `test_persistence_v11.py`. A corrupção e SQLITE_FULL
nunca atingiram arquivos de produção. SIGKILL prova crash de processo; não é
simulação física de perda de energia/controlador de disco.

## G. Bugs confirmados/corrigidos

| Severidade | Arquivo/função | Reprodução / risco | Correção / regressão |
| --- | --- | --- | --- |
| Alta, previamente autorizada | zion/db.py: backup_to | Criar destino após exists e antes de replace; backup concorrente perdido silenciosamente | os.link atômico no-clobber, tmp 0600, quick/integrity/FK checks, fsync arquivo/diretório, unlink tmp; dois testes de race |
| Média | db.transaction; Guardian.record_message/evaluate_chat_burst; comandos Telegram | Falhar INSERT de ação/expiração/contenção após primeira escrita; estado parcial persistente | Transação síncrona única e remoção de commits redundantes de métodos autocommit; testes de incident/action, estado/prazo, flood, AMA e scheduler |
| Média | db.mark_scheduled_message/advance_recurring_message e operações de recuperação | Instâncias concorrentes leem sending e disputam transição; retorno pode não representar estado persistido | BEGIN IMMEDIATE protege leitura/transição; dois resultados concorrentes concordam com estado final |
| Média | db.initialize/_apply_schema_migrations_locked | Falha após DDL/antes do marker deixava schema parcial; inicializadores disputavam markers lidos antes do lock | DDL/defaults/identity/markers na mesma transação; teste falha após DDL, falha de marker e dois inicializadores |
| Média | db._transaction_locked | SQLITE_FULL reverte transação SQLite inteira, inclusive savepoint; rollback do savepoint ausente mascara erro original | Só tenta ROLLBACK TO se transação ainda ativa; código SQLITE_FULL e rollback verificados |
| Média | health.HealthService.snapshot | Leitura de estado falha com cache de integridade ainda positivo; ping SELECT 1 não prova leitura válida | Estado de leitura participa de db_ok; invalida cache e força nova checagem; teste específico |
| Baixa | db.initialize | SCHEMA fixava timeout 5000 apesar de parâmetro menor | Restaura busy_timeout configurado; teste 75 ms |
| Baixa | db.initialize / backup_to | Inicializar dentro de transação pode commitá-la via executescript; backup da mesma conexão em escrita pode aguardar indefinidamente | Recusa explícita dessas chamadas em transação ativa; teste sem commit acidental |
| Baixa | backup_to, metadados/durabilidade | Versão lida da origem após backup podia não corresponder ao snapshot; erros de fsync de diretório eram ignorados | Versão vem do backup validado; erros propagados; falha fsync mantém final completo e limpa tmp |

Um erro de fsync depois de os.link pode deixar um **backup final completo** e
retornar erro. Ele é preservado, não apagado nem sobrescrito em nova tentativa.
O chamador deve inspecionar esse arquivo e escolher outro destino, sem tratar o
erro como sucesso de durabilidade.

### Auditoria explícita de operações relacionadas

| Sequência | Decisão final |
| --- | --- |
| Incidente + ação local consecutiva; warn + strike + incidente + ação | Uma transaction agrupa as escritas SQLite relacionadas; falha de persistência da ação reverte as escritas locais anteriores, não efeitos Telegram |
| Estado + expiração + ação; expiração automática | Uma transaction, inclusive leitura do estado anterior no comando state; nenhuma confirmação ao usuário antes do commit |
| Flood: mensagens + strike + containment | Uma transaction síncrona no Guardian; falha de containment preserva mensagens anteriores e não deixa strike parcial |
| AMA open/close e perguntas | Locks/transactions existentes preservados; audit action do comando participa da mesma transação; falha do segundo update/ação reverte |
| Scheduler claim e transition | Claim condicional; leitura/modificação serializada; transition + action no loop agrupadas; estado sending remanescente vai à quarentena se houver falha |
| Idempotency | Claim usa um UPSERT condicional atômico; participa de transaction quando agrupado; claim de update antes de I/O conserva semântica at-most-once existente |
| Migrações SQL | DDL e markers/defaults em uma transação, markers verificados sob lock; replay idempotente |
| Importação JSON legada | BEGIN IMMEDIATE já existente cobre mensagens/contenções/strikes/marker; testes de migração existentes preservados |
| Backup e metadados | Snapshot via API; metadata retirada da cópia; publicação atômica; filesystem não é transação SQL |
| Ação externa e persistência local | A ordem depende do fluxo: mute, ban, unban e alguns deletes/moderações podem chamar Telegram antes de persistir incident + action. Falha entre esses eventos pode deixar o efeito externo sem registro local completo; é risco residual conhecido |

Nenhuma transaction introduzida contém `await`, comprovado por teste estrutural.
A maior parte do diff em Guardian/telegram_app é indentação das sequências dentro
dessas transações, sem reformatação geral. A atomicidade garantida cobre operações
puramente SQLite relacionadas. Telegram e SQLite não formam uma transação
distribuída: a transação local não torna atômico nem reverte um efeito externo.
Não há promessa de exactly-once entre Telegram e SQLite. O scheduler mantém
claim/quarentena porque um resultado externo desconhecido não pode ser inferido
com segurança a partir do estado local.

## H. Retenção, backup de deploy e arquivos alterados

[Matriz completa das 17 tabelas e propostas de política](BLOCK2-RETENTION.md).
Crescimento sem retenção persiste em actions, incidents, strikes e recorrências,
entre outros casos documentados. Não se afirma crescimento global limitado.
A auditoria foi entregue conforme a autorização; nenhuma retenção destrutiva nova.

`scripts/apply-zion-v1.sh` foi somente auditado: backup via API antes do stop,
registro de HEAD/status, unit instalada, `.env` apenas stat/hash. **Não copiar a
`.env` é agora requisito**, coberto por teste; o script foi preservado e não
executado. Nenhum segredo real foi lido para testar o script. Destino de deploy
usa timestamp; uma colisão de DB agora falha em vez de sobrescrever.

Arquivos de código/testes alterados:

- `zion/db.py`: publicação no-clobber, transações, migração atômica, timeout.
- `zion/guardian.py`: grupos de persistência atômicos de flood/burst.
- `zion/telegram_app.py`: transações em mudanças relacionadas, sem await interno.
- `zion/health.py`: erro de leitura impede DB saudável e invalida cache.
- `tests/test_backup_publication.py`: cinco testes de backup/política de segredo.
- `tests/test_transaction_atomicity.py`: quinze testes de rollback/concorrência.
- `tests/test_block2_failures.py`: dez testes de falhas/health/permissões/restore.
- `tests/test_persistence_v11.py`: expectativa de rollback integral de initialize;
  subprocesso com timeout de readiness, signal.pause e fechamento de pipes.
- `scripts/rehearse-sqlite-copy.py`: ensaio reproduzível origem read-only → scratch.
- `docs/BLOCK2-LOCAL-AUDIT.md`, `docs/BLOCK2-RETENTION.md`,
  `docs/evidence/block2-copy-rehearsal.json`, `docs/evidence/block2-validation.txt`.

Commits locais de implementação:

1. `75accf8dbc99cf96f026f15374c53a3c1c489e76` — backup publication race + testes.
2. `cc1b3fefe04b7ba85266c5924799c1dbb43cd30f` — atomicidade + testes.
3. `89b3c42ae6817f5839e3fc478b3e64ba2836cb25` — migração/falhas/health + testes/ensaio.
4. Commit de documentação que contém este relatório; seu SHA é informado na
   entrega e pode ser obtido com `git log -1 --format=%H` após a conclusão.

## I. Validação final

Base: 154 testes em 12.174 s. Após backup: 159 em 17.039 s.
Após atomicidade: 173 em 17.829 s.
Árvore final de implementação: **184 testes em 10.193 s**,
**failures=0, errors=0, skipped=0**.
Compile, runtime compatibility, imports, sintaxe shell, arquivos sensíveis
versionados, secret scan e `ZION VALIDATION: OK`.
[Resumo da execução](evidence/block2-validation.txt).

```bash
cd /home/zetta/zion-community-bot-v11
PATH=/home/zetta/zion-community-bot/.venv/bin:$PATH bash scripts/validate.sh
git diff --check
git status --short --branch
```

`git diff --check` aprovado; estado entregue limpo, branch local quatro commits
à frente da base. Nenhum push; os commits locais não possuem novo resultado CI
remoto. O venv foi usado sem instalar/remover/atualizar dependências.

Falhas intermediárias de testes foram investigadas: uma conexão SQLite de
inspeção precisava close explícito; WAL já alocado podia ser reutilizado sem
crescer, então o ensaio passou a exceder o espaço prealocado; a fixture usava
severidade em caixa inválida. Não foram alteradas expectativas para esconder
falhas de implementação. O teste de migração foi fortalecido para o novo
contrato explícito de rollback integral.

## J. Garantia de não impacto e limites

- Produção não reiniciada nem parada; PID, início e NRestarts inalterados.
- Banco real não modificado por escritas SQL, migração, VACUUM, REINDEX ou
  checkpoint; somente conexão read-only e backup API da origem.
- DB/WAL/.env mantiveram tamanho/mtime/modo observados. Leituras WAL podem usar
  locks/metadados do SHM; não se promete imutabilidade física desse coordenador.
- `.env` não lida, copiada ou modificada; nenhum segredo real impresso.
- Wi-Fi/NetworkManager/USB/Tailscale/SSH/systemd não modificados.
- Nenhuma branch de produção alterada, nenhum pull/checkout nela.
- Nenhum push, merge, rebase de produção ou deploy.
- Nenhuma alteração de dependência ou symlink no venv de produção.

Health verifica integridade com cache de até 300 s. Uma nova falha de leitura
invalida o cache imediatamente; corrupção em página ainda não acessada pode
aguardar a próxima varredura. Os ensaios não prometem detecção instantânea de
qualquer dano nem atomicidade entre Telegram e SQLite.
