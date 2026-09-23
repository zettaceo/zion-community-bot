# ZION — Community FAQ

# O que é o ZION? / What is ZION?

PT-BR: ZION é o assistente oficial da comunidade Z-SWAP. Ele ajuda a entender o produto, encontrar orientações confiáveis, receber novos membros e manter a comunidade mais segura. Nos bastidores, o Guardian aplica regras claras de proteção e moderação.

EN: ZION is the official assistant for the Z-SWAP community. It helps people understand the product, find reliable guidance, welcome new members and keep the community safer. Behind the conversation, the Guardian applies clear protection and moderation rules.

# A IA pode banir alguém? / Can AI ban someone?

Não. A classificação por IA é observe-only por padrão e não recebe autoridade direta para apagar, silenciar ou banir. Ações punitivas automáticas dependem de regras determinísticas, e casos ambíguos devem ser revisados por humanos autorizados.

No. AI classification is observe-only by default and has no direct authority to delete, mute or ban. Automatic punitive actions require deterministic rules, and ambiguous cases should be reviewed by authorized humans.

# O que acontece se a Mistral ficar fora do ar? / What if Mistral is unavailable?

O Guardian determinístico continua funcionando mesmo quando a camada de IA está indisponível. Falhas consecutivas da Mistral podem abrir um circuit breaker temporário para interromper novas chamadas ao provedor sem desligar a moderação determinística.

The deterministic Guardian remains operational when the AI layer is unavailable. Consecutive Mistral failures can open a temporary circuit breaker that pauses provider calls without disabling deterministic moderation.

# Quais dados são armazenados? / What data is stored?

Mensagens comuns não são armazenadas integralmente. ZION mantém metadados operacionais necessários para moderação, auditoria e estado. Perguntas dirigidas ao ZION, com ou sem /ask, podem ser enviadas de forma sanitizada à Mistral. Quando não há correspondência oficial, elas podem ser mantidas como lacunas sanitizadas por retenção limitada. Perguntas enviadas explicitamente a um AMA são mantidas temporariamente para organizar a sessão e depois são removidas conforme a retenção configurada.

Ordinary message bodies are not stored in full. ZION keeps operational metadata needed for moderation, audit and state. Questions addressed to ZION, with or without /ask, may be sent to Mistral after sanitization. When no official knowledge matches, they may be retained as sanitized knowledge gaps for a limited period. Questions explicitly submitted to an AMA are retained temporarily to organize the session and later removed according to configured retention.

# Como denunciar uma mensagem? / How do I report a message?

Responda à mensagem usando /report e, opcionalmente, informe um motivo. O ZION registra um incidente para revisão administrativa.

Reply to the message with /report and optionally add a reason. ZION records an incident for administrative review.

# Como participar de um AMA? / How do I join an AMA?

Quando um administrador abrir um AMA no chat, use /ama seguido da sua pergunta. Se não houver AMA ativo, ZION informará que não há sessão aberta.

When an administrator opens an AMA in the chat, use /ama followed by your question. If no AMA is active, ZION will say that no session is open.

# O que significa ELEVATED?

ELEVATED é um estado operacional temporário usado quando sinais objetivos, como entrada em massa ou pico distribuído de mensagens, justificam controles de flood mais rígidos. Entrar em ELEVATED não pune automaticamente um indivíduo.

ELEVATED is a temporary operating state used when objective signals such as mass joins or a distributed message burst justify tighter flood controls. Entering ELEVATED does not automatically punish an individual.

# Segurança de carteira / Wallet security

Nunca publique seed phrase, recovery phrase ou chave privada. Administradores da Z-SWAP e o ZION não devem pedir esses segredos. Quando o Guardian identifica uma possível exposição com alta confiança, ele pode remover a mensagem para reduzir a exposição.

Never publish a seed phrase, recovery phrase or private key. Z-SWAP administrators and ZION should not ask for those secrets. When the Guardian detects a likely exposure with high confidence, it may remove the message to reduce exposure.

# Respostas sobre produto / Product answers

ZION deve usar somente conhecimento oficial aprovado para afirmar fatos sobre a Z-SWAP. Se a base não sustentar uma resposta, ele deve dizer que não há informação oficial suficiente em vez de inventar recursos, prazos, taxas, retornos ou políticas.

ZION must use only approved official knowledge for factual Z-SWAP claims. If the knowledge base does not support an answer, it should say there is not enough official information rather than inventing features, deadlines, fees, returns or policies.
