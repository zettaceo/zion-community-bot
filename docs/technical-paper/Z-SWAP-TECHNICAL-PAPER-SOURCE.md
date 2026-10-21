# Z-SWAP — Platform Architecture & Technical Paper — Canonical Source

## Final-artifact discovery addendum — 2026-10-19

This supersedes the historical claim below that only an editorial plan was
available. Prior-session Drive discovery identified the completed PT-BR v1.0:
[Z-SWAP — Guia Completo da Plataforma](https://drive.google.com/file/d/1baUgmKSH3kEwJaDZFddsqMVrgJ5wEagX/view),
modified 2026-10-18, 28,292,993 bytes, 83 pages.
SHA256: `e6a2f83905ce4f8ed633e41dbb1200c161b76cb5bd1645d0454bdb753fb1b27f`.
The copy was reacquired through the Drive connector on 2026-10-20 and its exact
SHA256 and 83-page count verified. A private copy is retained outside the repo
under the operator state directory, not indexed or sent to a model provider.

Recorded visual review of pages 2, 22, 77 and 78 found controlled-distribution
classification, conditional Solana fees, and explicit distinctions between
available, partial, disabled and unconfirmed functionality. These observations
are source-discovery evidence, not fresh production measurements. The raw paper
is not authorized for public indexing. Its classifications must be reconciled
with current public authority and implementation before any curated projection.
The old 67-section editorial classification below remains historical, not a
page-by-page certification of this newer 83-page PDF.

### Routing reconciliation — 2026-10-20

Fresh visual review of matrices 76–78 agrees with the exact application snapshot
`986ae759c1c76fe23967a8e61489d986b2bb9a51`: `src/lib/swap/fontes.ts` defines 0x for
same-chain EVM, Jupiter for same-chain Solana and LI.FI for cross-chain quoting.
`src/lib/limit/cow.ts` is the separate limit-order integration. CoW is not a
fourth quote source, and all sources do not compete on every pair. The three
existing knowledge sections containing the conflation were corrected together;
source classification/audience is unchanged. Network coverage is not guaranteed
pair/route availability. No provider URL, internal endpoint or contract address
was copied into knowledge.

Matrix 78 confirms the previously corrected conditional Solana fee policy and
the separation of platform and third-party costs. Matrix 77 distinguishes live,
partial, disabled, planned and unconfirmed scopes. Its unconfirmed Pro Terminal
status is not a replacement for a public beta label: a UI label and independent
execution evidence are different claims. Existing public status qualifiers remain.
The public application certification matrix was inspected at the exact source
snapshot; this is not a live production probe or proof of current deployments.

The PDF's text extraction omits many table cells and body labels. Only its page
structure can be inventoried from extracted text; a complete 83-page semantic
review cannot be certified from that extraction. Full visual reconciliation
remains open. The raw controlled paper remains outside every runtime corpus.

## Historical source identity

- Planned source path named in the mission: `technical-paper/01-PAGE-BY-PAGE-ROUTE.md`
- Verification result: that exact file is absent from the fetched Git history,
  current repository tree, local filesystem search and accessible Drive search.
- Verified replacement source: Drive project `Z-SWAP — Technical Paper — Master Plan`
- Verified project README: `00 — README — Z-SWAP Technical Paper`
  (Drive file `1r-r2sMsjYnJy9iLhkMdKDYLO4ljZi0TlwVo0Nq_URSs`)
- Verified content plan: `01 — Plano Completo de Conteúdo`
  (Drive file `1d0PpSLIkrxV6NPckXuT-rE9svxzQG4HN3bxGyKSpbGU`)
- Source date: 2026-10-14
- Reconciled on: 2026-10-16
- Reconciled against Z-SWAP `origin/main`: `166fd5be9c28fb2ffaaffd9413bf61c40f492698`
- Scope: 67 planned sections, estimated 60–80 landscape pages
- Overall classification: `MIXED`
- Status: `CURRENT_RECONCILIATION_SOURCE`

The verified Drive material is a plan for the Technical Paper, not a completed
public technical paper. It can identify topics and editorial intent, but it
cannot by itself prove runtime behavior. Only claims reconciled below and copied
into an approved knowledge projection may reach an agent.

## Retrieval rule

- `PUBLIC`: eligible only after reconciliation with current public truth/code.
- `CONTROLLED`: excluded from community retrieval unless a separate approved
  projection is created for an explicitly authorized agent/context.
- `INTERNAL`: never placed in public model context.
- `SECRET`: values and recovery material are never copied into this document
  or any knowledge source.
- The raw source documents are never indexed directly.
- MÍMIR receives only the curated public technical projection.
- EIR receives the smaller support/product projection already approved.
- ZION and FREYR do not receive internal architecture through cross-agent
  handoff or retrieval.

## Section classification and reconciliation

| # | Section | Classification | Retrieval decision |
|---:|---|---|---|
| 1 | Capa e identidade do documento | CONTROLLED | Editorial identity only. |
| 2 | Document Control | CONTROLLED | Editorial control metadata; never community retrieval. |
| 3 | Executive Summary | PUBLIC | Public only after reconciliation with current product status. |
| 4 | Why Z-SWAP Exists | PUBLIC | Institutional problem statement. |
| 5 | Platform Scope | PUBLIC | Public scope and explicit non-claims. |
| 6 | Platform Capability Map | PUBLIC | Public module map with current status qualifiers. |
| 7 | High-Level Architecture | PUBLIC | High-level public architecture only. |
| 8 | Technology Stack | PUBLIC | Named public technologies only; no operational configuration. |
| 9 | Deployment Architecture | CONTROLLED | Deployment topology is controlled; no hosts, regions, credentials or private routes. |
| 10 | Trust Boundaries | CONTROLLED | Trust-boundary explanation is controlled and must not expose internal threat detail. |
| 11 | User Control Model | PUBLIC | Public user-control model. |
| 12 | Wallet & Identity Architecture | PUBLIC | Public wallet/auth concepts without internal session details. |
| 13 | Supported Network Architecture | PUBLIC | Public network list; ZETTA Chain remains coming soon. |
| 14 | DEX Swap Architecture | PUBLIC | Public DEX lifecycle at conceptual level. |
| 15 | Routing Layer | PUBLIC | Public provider/routing concepts only. |
| 16 | Cross-Chain / Bridge Flow | PUBLIC | Public bridge flow at conceptual level. |
| 17 | Fee Architecture | PUBLIC | Public fee categories and current qualifiers. |
| 18 | Tier Architecture — The Hird | PUBLIC | Public Hird tiers and current limits. |
| 19 | CEX Architecture | PUBLIC | Public CEX concepts; never expose stored credential mechanics. |
| 20 | CEX Connection Lifecycle | CONTROLLED | Internal lifecycle/state detail. |
| 21 | CEX Order Execution Pipeline | CONTROLLED | Internal execution pipeline. |
| 22 | Execution State Machine | CONTROLLED | Internal state-machine detail. |
| 23 | Recovery Architecture | CONTROLLED | Internal recovery and cryptographic mechanism. |
| 24 | Idempotency & Concurrency Controls | CONTROLLED | Internal concurrency and lock detail. |
| 25 | Orders Architecture | PUBLIC | Public Orders scope; PARTIAL and no autonomous saved-plan execution. |
| 26 | DCA Architecture | CONTROLLED | Controlled DCA design; do not imply real availability. |
| 27 | DCA Safety Model | CONTROLLED | Controlled safety details. |
| 28 | Autopilot Architecture | CONTROLLED | Controlled; implemented/disabled is not public availability. |
| 29 | Autopilot Safety Controls | CONTROLLED | Controlled limits and guards. |
| 30 | Observer → Copilot → Pilot Model | CONTROLLED | Controlled future operating model. |
| 31 | ZION Architecture | PUBLIC | Public high-level ZION role. |
| 32 | ZION Safety Boundary | PUBLIC | Public principle: AI interprets, deterministic rules decide. |
| 33 | AI Provider Architecture | CONTROLLED | Controlled provider, fallback, cost and limit architecture. |
| 34 | Workbench / Laboratory Architecture | PUBLIC | Public Workbench capabilities. |
| 35 | Backtesting Model | PUBLIC | Public backtesting limits and risk qualifier. |
| 36 | Paper Trading Architecture | PUBLIC | Public simulated-capital explanation. |
| 37 | Strategy Intelligence | PUBLIC | Public analysis/learning boundary; no automatic real execution. |
| 38 | Portfolio Architecture | PUBLIC | Public Portfolio status remains PARTIAL. |
| 39 | Pools Discovery | PUBLIC | Public read-only Pools discovery. |
| 40 | Dashboard & Operational Views | PUBLIC | Public user-facing Dashboard only; admin view remains internal. |
| 41 | Data Architecture | INTERNAL | Internal data-domain map. |
| 42 | Database Security | INTERNAL | Internal database security and ACL detail. |
| 43 | Security Architecture | INTERNAL | Internal security mechanisms. |
| 44 | Financial Safety Model | PUBLIC | Public risk categories only. |
| 45 | Failure Modes & Recovery | INTERNAL | Internal failure and recovery detail. |
| 46 | Observability | INTERNAL | Internal telemetry and logs. |
| 47 | Release Engineering | INTERNAL | Internal release engineering. |
| 48 | Testing & Certification Model | INTERNAL | Internal certification process. |
| 49 | Migrations & Schema Governance | INTERNAL | Internal schema governance. |
| 50 | Production Maturity Matrix | INTERNAL | Internal maturity evidence; only approved public statuses may be projected. |
| 51 | Founder Pass Architecture | PUBLIC | Public Founder Pass terms. |
| 52 | Founder ≠ Financial Security Claim | PUBLIC | Public exclusions: no financial-security claims. |
| 53 | Commercial & Access Model | PUBLIC | Public distinction between Hird and Founder/Pantheon. |
| 54 | Current Production State | PUBLIC | Public snapshot only after exact dated reconciliation. |
| 55 | Known Limitations | PUBLIC | Public status vocabulary and limitations. |
| 56 | Open Engineering Items | INTERNAL | Internal debt/findings. |
| 57 | Roadmap | PUBLIC | Public roadmap without dates. |
| 58 | Scalability & Future Architecture | CONTROLLED | Controlled future architecture. |
| 59 | Integration Model | CONTROLLED | Controlled integration boundaries. |
| 60 | Risk Disclosure | PUBLIC | Public risk disclosure. |
| 61 | Glossary | PUBLIC | Public glossary. |
| 62 | Appendix A — Network Matrix | PUBLIC | Public network matrix after current-code reconciliation. |
| 63 | Appendix B — Feature Status Matrix | PUBLIC | Public feature statuses from approved certification only. |
| 64 | Appendix C — Fee Matrix | PUBLIC | Public fee matrix from executable/current source only. |
| 65 | Appendix D — State Machines | CONTROLLED | Controlled state machines. |
| 66 | Appendix E — Architecture Diagrams | CONTROLLED | Controlled diagrams until individually approved. |
| 67 | Appendix F — Document References | CONTROLLED | Controlled source map; repository paths are not community content. |

## Verified project README (archival transcription)

```text
Z-SWAP — TECHNICAL PAPER — MASTER PLAN
Nome do documento final
Z-SWAP — Platform Architecture & Technical Paper
Subtítulo: Multi-Chain Trading Infrastructure, Execution, Risk Controls & Intelligence
Nome em português: Z-SWAP — Arquitetura e Documento Técnico da Plataforma
Objetivo
Criar um documento técnico corporativo, autocontido, capaz de explicar a Z-SWAP em profundidade sem depender de uma apresentação oral. O material deve servir para parceiros, investidores, auditoria, due diligence e avaliação técnica.
Formato editorial
• Documento horizontal do início ao fim.
• Proporção recomendada: 16:9 landscape, pensada para PDF, notebook, monitor e reunião.
• Estimativa: 60–80 páginas.
• Alta densidade informacional, porém com muito espaço negativo e forte hierarquia visual.
• Um elemento visual técnico relevante a cada 1–2 páginas.
Princípio central
A apresentação de 21 slides comunica a visão. O Technical Paper prova e explica a plataforma.
Regra de verdade
Cada afirmação importante deve ser rastreável para arquitetura, código, produção ou documentação autoritativa. Estados devem ser marcados quando necessário como PRODUCTION, AVAILABLE, PARTIAL, DISABLED, ROADMAP ou COMING SOON.
Direção visual
• Fundo navy/preto baseado na própria plataforma.
• Cyan/azul = infraestrutura e execução.
• Violeta = inteligência/ZION.
• Gold = tiers/Founder e valor, usado de forma controlada.
• Nada de guerreiros, fantasia, cenas épicas ou estética cripto genérica.
• Identidade nórdica apenas em detalhes geométricos muito discretos.
• Prioridade absoluta para legibilidade.
Família de fundos
• Capa: versão mais rica, com grande Z estrutural, horizonte técnico e presença visual.
• Aberturas de seção: mesma linguagem, mais limpa.
• Páginas técnicas: navy/preto quase liso, linhas geométricas suaves nas bordas.
• Diagramas complexos: fundo ainda mais neutro para maximizar contraste.
• Destaques/conclusões: retorno controlado do horizonte/brilho da capa.
Estrutura desta pasta
01 — Planejamento: estratégia editorial, cronograma e regras de produção.
02 — Conteúdo Técnico: índice mestre e conteúdo de cada seção.
03 — Design System: sistema visual, grids, cores, tipografia e templates.
04 — Assets: brand oficial, backgrounds, diagramas, screenshots de UI e elementos gráficos.
Workflow recomendado
1. Consolidar conteúdo técnico autoritativo.
2. Validar estados reais e limitações.
3. Produzir diagramas e mapas.
4. Aprovar sistema visual.
5. Diagramar o documento completo.
6. Revisar técnica e editorialmente.
7. Exportar PDF final.
Regras permanentes
• Não inventar funcionalidades.
• Não transformar ROADMAP em AVAILABLE.
• Não apresentar Autopilot/DCA real como ativos se estiverem desabilitados.
• Não misturar Hird e Pantheon visualmente.
• Não usar claims de lucro, renda passiva, dividendos ou retorno garantido.
• Não expor secrets, credenciais, env vars sensíveis ou detalhes internos desnecessários.
• Quando usar screenshots, preferir telas reais da plataforma e apenas quando servirem como prova.
Estado inicial
Capa conceitual aprovada em linguagem visual, porém a versão final deve ser horizontal e usar a logo oficial. A página conceitual seguinte confirmou que o formato horizontal é superior para o miolo técnico.
Estrutura atualizada da pasta
• 01 — Planejamento
• 02 — Conteúdo Técnico
• 03 — Design System
• 04 — Assets
• 05 — Produção do Documento
• 06 — Exportações Finais
Documentos-chave
• 01 — Plano Completo de Conteúdo
• 02 — Design System e Direção Visual
• 03 — Plano de Produção, Evidência e QA
• 00 — Índice de Assets e Fontes Oficiais
• Referências Visuais — Conceitos Aprovados
Fonte oficial de assets
https://drive.google.com/drive/folders/1om2B5RjygN55xPGPY4Cr-UEW8UAf9-Eo
Pasta-mestra deste projeto
https://drive.google.com/drive/folders/10Wv-wZ3VYxnwZE3TuuOdMg2qG9y0A0bj
```

## Verified 67-section content plan (archival transcription)

```text
Z-SWAP — PLANO COMPLETO DE CONTEÚDO
Documento-alvo: Z-SWAP — Platform Architecture & Technical Paper
Escopo estimado: 60–80 páginas landscape.
ESTRUTURA MESTRA
1. Capa e identidade do documento
Título, subtítulo, versão, data, logo oficial e posicionamento técnico.
2. Document Control
Versão, data, classificação, fontes autoritativas e convenções AVAILABLE / PARTIAL / DISABLED / ROADMAP / COMING SOON.
3. Executive Summary
Resumo em uma página do que é a Z-SWAP, como opera e quais problemas resolve.
4. Why Z-SWAP Exists
Fragmentação atual entre wallets, DEXs, bridges, CEXs, scanners, dashboards e ferramentas de estratégia.
5. Platform Scope
O que a Z-SWAP é e o que não é: execução, análise, advisory, automação, custódia e infraestrutura.
6. Platform Capability Map
Mapa de módulos: Swap, Bridge, Orders, CEX Console, DCA, Portfolio, Pools Discovery, Dashboard, ZION, Workbench, Paper Simulation, Founder Pass e tiers.
7. High-Level Architecture
User/Wallet → Web App → Execution/Intelligence/Risk Layer → DEX/Bridge/CEX/Blockchain/Data Providers → Supabase/Observability.
8. Technology Stack
Next.js, TypeScript, Vercel, Supabase/Postgres, integrações blockchain, agregadores, CCXT e provedores de IA.
9. Deployment Architecture
GitHub → CI → Preview → Vercel Production → Supabase; explicar regiões e gru1 quando aplicável.
10. Trust Boundaries
Browser, wallet, backend, database, blockchain, CEX e terceiros.
11. User Control Model
Z-SWAP analisa/prepara/roteia; usuário decide/assina; rede/protocolo executa.
12. Wallet & Identity Architecture
EVM + Solana, sessão, autenticação e vínculo com execução.
13. Supported Network Architecture
Ethereum, Polygon, Arbitrum, Optimism, BNB Chain, Base, Avalanche e Solana; ZETTA Chain como coming soon.
14. DEX Swap Architecture
Quote → comparação → guards → confirmação da wallet → blockchain → receipt → registro.
15. Routing Layer
0x, LI.FI, Jupiter e demais provedores suportados; distinção entre Z-SWAP e agregadores.
16. Cross-Chain / Bridge Flow
Origem, destino, bridge, token, recipient e confirmação.
17. Fee Architecture
Separar platform fee, gas, DEX, bridge, exchange e third-party fees.
18. Tier Architecture — The Hird
Free/Thrall, Pro/Drengr, Trader/Berserkr, Pilot/Einherjar; capabilities, fee e limitações.
19. CEX Architecture
Conexão de exchange, backend, CCXT, credenciais protegidas e venues.
20. CEX Connection Lifecycle
CURRENT / RETIRED / REVOKED; identidade histórica da conexão.
21. CEX Order Execution Pipeline
Intent → validation → authorization → venue submission → reconciliation → fill/account state.
22. Execution State Machine
Estados, execução parcial, unknown honesto, cancelamento e reconciliação.
23. Recovery Architecture
Recovery por intent, fingerprint, HMAC e fail-closed sem expor segredo.
24. Idempotency & Concurrency Controls
Duplicação, reservas, locks, TOCTOU, race conditions e escrita concorrente.
25. Orders Architecture
Estado PARTIAL; planos condicionais e alertas sem vender autonomia total.
26. DCA Architecture
Plano → scheduler → queue → validation → cycle → settlement.
27. DCA Safety Model
Simulated vs real, capacity, balances, queue, retired connection protection e pause states.
28. Autopilot Architecture
IMPLEMENTED / DISABLED; arquitetura sem afirmar disponibilidade operacional.
29. Autopilot Safety Controls
Exposure limits, loss stop, pause, price guards, trusted checks, reserves e session scope.
30. Observer → Copilot → Pilot Model
Separar análise, assistência e eventual autonomia.
31. ZION Architecture
Contexto → providers/model → knowledge/analysis → advisory/cards/suggestions.
32. ZION Safety Boundary
IA interpreta; regras objetivas decidem.
33. AI Provider Architecture
Camada de provedores, fallback, custo, disponibilidade e limites.
34. Workbench / Laboratory Architecture
Strategies, runs, results, backtests, indicators e benchmarking.
35. Backtesting Model
Dados, janela, custos, execução simulada, slippage e limitações.
36. Paper Trading Architecture
Accounts → positions → simulation → PnL → analytics.
37. Strategy Intelligence
Relação entre estratégia, medição, resultados e aprendizado; sem ligar automaticamente lab a execução real.
38. Portfolio Architecture
Cobertura atual, fontes, agregação e limitações; estado PARTIAL.
39. Pools Discovery
Leitura e descoberta; separar discovery de liquidez automatizada.
40. Dashboard & Operational Views
Usuário e admin.
41. Data Architecture
Mapa por domínios: users, connections, operations, execution, DCA, paper, lab, ZION, tiers e audit.
42. Database Security
Supabase/Postgres, RLS, service-role boundary, migrations e ACL.
43. Security Architecture
Auth, authorization, secrets, server-side credentials, input validation, fail-closed, CSP, rate limiting e audit logs.
44. Financial Safety Model
Separar cybersecurity, execution integrity e market risk.
45. Failure Modes & Recovery
Provider down, timeout, stale state, partial execution, network error, CEX ambiguity, DB failure e failed deployment.
46. Observability
Logs, telemetry, runtime errors, audit trail, admin visibility e health checks.
47. Release Engineering
Branch → local gates → CI → preview → migration review → production → smoke → rollback.
48. Testing & Certification Model
Unit, integration, regression, deliberate-break, database, preview e production smoke.
49. Migrations & Schema Governance
Versionamento, ordem, forward migrations, read-before-write e rollback discipline.
50. Production Maturity Matrix
Component | State | Production | Real execution | Main limitation.
51. Founder Pass Architecture
Founder status, Premium 36 meses, início no fechamento oficial da venda e transferência sem reiniciar prazo.
52. Founder ≠ Financial Security Claim
Sem revenue share, dividend, passive income, guaranteed return ou treasury governance.
53. Commercial & Access Model
The Hird vs Founder/Pantheon sem misturar os dois sistemas.
54. Current Production State
Snapshot datado e versionado; SHA e estado operacional quando apropriado.
55. Known Limitations
AVAILABLE ≠ perfeito; PARTIAL ≠ quebrado; ROADMAP ≠ disponível.
56. Open Engineering Items
Debt, riscos conhecidos, findings não bloqueantes e controles não totalmente provados.
57. Roadmap
Advanced Automation, expansão de cobertura, ZETTA Chain e evolução de inteligência; sem datas inventadas.
58. Scalability & Future Architecture
Workers, queues, provider abstraction, mais chains e venues.
59. Integration Model
APIs, wallet integrations, provider integrations e webhook boundaries.
60. Risk Disclosure
Market, smart contract, bridge, CEX, provider, blockchain, software e human error.
61. Glossary
Intent, route, quote, fill, RLS, DCA, CEX, DEX, bridge, tier, Founder, ZION etc.
62. Appendix A — Network Matrix
Chain, VM, native asset, swap support e aggregator.
63. Appendix B — Feature Status Matrix
Estados por módulo.
64. Appendix C — Fee Matrix
Fees por tier e tipo.
65. Appendix D — State Machines
CEX, DCA e Autopilot.
66. Appendix E — Architecture Diagrams
Versões expandidas dos diagramas principais.
67. Appendix F — Document References
Documentos autoritativos do repositório e fontes de produção usados na redação.
REGRAS EDITORIAIS
• Toda seção técnica deve indicar o estado real quando houver risco de confusão.
• Diagramas devem explicar, não decorar.
• Screenshots reais somente quando servirem como evidência.
• Evitar linguagem promocional em capítulos técnicos.
• Limitações e riscos devem aparecer ao lado das capacidades correspondentes.
• O documento deve poder ser entendido sem narrador.
```
