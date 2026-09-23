# Bloco 2 — crescimento e retenção

Auditoria do código em `89b3c42ae6817f5839e3fc478b3e64ba2836cb25`.
Valores abaixo são defaults de `Settings`, não valores lidos da `.env`.
Não houve exclusão de dados de produção nem implementação de nova retenção.
O housekeeping roda a cada hora em `scheduler_loop`; `recent_messages` é
limpa no processamento de mensagens do Guardian. Retenção temporal não
estabelece um limite absoluto de bytes sob volume arbitrário.

| TABLE | GROWTH SOURCE | RETENTION | INDEX FOR PRUNE | AUDIT VALUE | SENSITIVE TEXT? | UNBOUNDED RISK? |
| --- | --- | --- | --- | --- | --- | --- |
| users | Novos pares chat/usuário, perfil e contador | Nenhuma | Nenhum por last_seen | Identidade/contexto de moderação | Sim: nome, username, idioma | Sim, usuários distintos permanecem |
| user_events | Entradas e eventos | 30 dias, housekeeping | Índices começam em chat/user/event_type; falta índice global created_at | Investigação de atividade/raid | metadata_json pode conter contexto | Janela temporal, sem limite de volume; limpeza faz scan |
| strikes | Advertências/flood/importação | expires_at desativa efeito; nenhuma exclusão | idx_strikes_active começa em chat/user | Histórico de penalidades | Motivo e metadata | Sim, strikes expirados ficam |
| containments | Restrição por chat/usuário | Expirada removida na consulta e no housekeeping | PK para consulta individual; falta blocked_until global | Estado operacional transitório | Motivo | Limitado temporalmente quando limpeza roda; scan global |
| recent_messages | IDs de mensagens | 300 segundos; limpeza ao receber mensagem | idx_recent_messages_created | Detecção/purge de flood | IDs apenas, não corpo | Sem crescimento sem tráfego; backlog parado até próxima mensagem |
| incidents | Alertas/relatos/moderação | Relatos user_report resolvidos/ignorados: redação após 90 dias; linhas permanecem | idx_incidents_retention(category,status,updated_at) | Auditoria central | Sim: evidence_json/note | Sim; outras categorias e relatos abertos sem redação temporal |
| actions | Todas as ações e entregas | Nenhuma | idx_actions_created disponível | Ledger de auditoria | reason/metadata_json podem conter texto | Sim |
| domains | Configuração administrativa | Upsert por domínio, sem remoção temporal | PK domain; nenhum índice temporal | Política vigente | Domínios, não mensagens | Cresce com domínios distintos configurados |
| settings | Estado/configuração/markers | Upsert por chave | PK key | Configuração operacional | Valores genéricos; não é cofre de segredos | Conjunto atual de chaves limitado pelo código; sem quota estrutural |
| schema_migrations | Versões de schema | Permanente, uma linha por versão | PK version | Necessário para compatibilidade e migração | Não | Apenas crescimento por releases |
| idempotency_keys | Claims de updates/eventos | TTL configurado, default 30 dias; prune expires_at | idx_idempotency_expires | Evita execução duplicada | Chaves/IDs, sem texto de mensagem | Janela temporal; depende do housekeeping |
| ai_events | Chamadas IA | 90 dias | idx_ai_events_created | Métricas/custo/diagnóstico | metadata e hash; campos permitem contexto | Janela temporal, sem quota de volume |
| knowledge_gaps | Perguntas distintas, upsert por hash | 30 dias desde last_seen | idx_knowledge_gaps_last_seen | Curadoria de conhecimento | Sim: sample_text até 500 caracteres | Perguntas recorrentes renovam prazo indefinidamente |
| scheduled_messages | Agendamentos | sent/failed/cancelled: 30 dias por COALESCE(sent_at,created_at); pending/sending/uncertain preservados | Índices status/send_at e status/next_attempt_at ajudam status; sem índice da expressão de corte | Entregas e recuperação manual | Sim: text | Sim para estados não finais; failed já é removido pela política existente |
| recurring_messages | Recorrências | Nenhuma, inclusive canceladas/pausadas | idx_recurring_due para scheduler; nenhum prune | Configuração recorrente e recuperação | Sim: text | Sim, inclusive finais |
| ama_sessions | Abertura de AMA | Fechadas há 30 dias e sem perguntas; housekeeping depois de limpar perguntas | idx_ama_sessions_chat começa em chat; falta status/closed_at global | Contexto das perguntas | Sim: title | AMAs abertos sem prazo; fechados limitados quando limpeza roda |
| ama_questions | Perguntas AMA | Removidas quando sessão fechada há 30 dias | idx_ama_questions_session cobre ama_id; seleção de sessões sem índice global de fechamento | Participação/contexto | Sim: question | AMAs abertos podem crescer indefinidamente |

## Propostas para revisão posterior

1. Separar a duração necessária do ledger da duração do texto em `actions` e
   `incidents`: preservar IDs, tipo, resultado e timestamps; definir prazo
   explícito de redação de texto/metadata por categoria. Não aplicar exclusão
   genérica de auditoria nesta etapa.
2. Definir arquivamento/redação de strikes expirados, perfis inativos,
   recorrências canceladas e AMAs abandonados, com critérios de recuperação
   manual. Não remover `uncertain` automaticamente: resultado externo desconhecido.
3. Considerar índices globais de limpeza em `user_events(created_at)`,
   `containments(blocked_until)` e `ama_sessions(status,closed_at)`, e um índice
   compatível com o corte dos agendamentos, após medir volume/plano/custo de escrita.
4. Definir orçamento de volume e política de arquivo para auditoria. Monitorar
   alarmes já existentes: DB 512 MiB e WAL 128 MiB por default. Os limites são
   alertas, não quotas. `journal_size_limit=16 MiB` limita WAL retido após reset,
   não impede crescimento enquanto um reader longo prende frames.

O DB real observado tem 159744 bytes, sem WAL pendente. Crescimento sem retenção
é um risco operacional de longo prazo registrado, não evidência de disco cheio
atual. Nenhuma política destrutiva nova foi aplicada.
