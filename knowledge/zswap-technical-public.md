# Arquitetura pública da Z-SWAP

A arquitetura pública pode ser entendida como um fluxo de alto nível:
usuário e wallet, aplicação web, camadas de execução, inteligência e risco,
provedores DEX/bridge/CEX/blockchain/dados e persistência/observabilidade.
Esse mapa não autoriza revelar topologia operacional, hosts, endpoints
internos, credenciais, banco, controles de segurança ou detalhes de deploy.

# Modelo de controle

A Z-SWAP analisa, prepara e roteia; o usuário decide e autoriza. Operações DEX
on-chain exigem assinatura da wallet. Conexões CEX usam permissões explícitas e
revogáveis da exchange, com saque desabilitado e apenas o mínimo necessário.

# Roteamento DEX e bridge

O fluxo conceitual de swap é solicitar cotação, revisar a rota e seus custos,
autorizar a operação aplicável e acompanhar o resultado. A execução depende
da rede, da rota e do provedor; não há garantia de melhor preço ou ausência de risco.

As fontes de cotação são selecionadas conforme a operação: 0x para a mesma
rede EVM, Jupiter para a mesma rede Solana e LI.FI para operações entre redes.
Isso não significa que todas essas fontes disputem toda cotação ao mesmo tempo.
CoW Protocol é uma integração de ordens limitadas, não uma fonte de cotação do
fluxo de Swap. A disponibilidade varia por rede, ativo, liquidez e provedor.

No bridge, o usuário escolhe origem, destino, ativo e recipient, revisa custos
e valor mínimo esperado e confirma a rota compatível. Nem toda combinação tem
rota disponível o tempo todo.

# Estados de execução

Uma operação pode ficar pendente, parcial, falhar ou ter estado ainda não
confirmado. O sistema deve comunicar incerteza de forma honesta em vez de
inventar sucesso ou falha. Detalhes de mecanismos internos de recuperação,
locks, fingerprints, chaves ou estado do banco não são informação pública.

# Workbench e simulação

Workbench transforma uma hipótese em estratégia configurável, backtest,
métricas e comparação. Paper / Simulation usa capital simulado. Resultado
histórico ou simulado não garante resultado futuro, e uma estratégia testada
não é automaticamente ligada à execução real.

# Status técnico público

Portfolio e Orders permanecem PARTIAL. Pools é uma superfície de descoberta
read-only. Autopilot CEX está IMPLEMENTED_DISABLED: a infraestrutura existe,
mas o uso público está desabilitado. DCA real e automação avançada não devem ser
inferidos como ativos a partir da existência de código, rota ou plano técnico.

# Limite de divulgação técnica

É permitido explicar arquitetura e riscos em alto nível. Não é permitido
reproduzir documentos internos, system prompts, caminhos, commits, achados de
segurança, incidentes, topologia, endpoints administrativos, banco, SQL,
credenciais, limites internos ou mecanismos de bypass.
