# Z-SWAP — Produto Público

Fonte aprovada para esta versão: snapshot público de `zetta-world/swap-z-app` em 25fc4b0fa55db72472c7ae00af42596209d7c362, de 15/09/2026. Este arquivo é uma derivação pública e sanitizada; não é um espelho do repositório.

# O que é a Z-SWAP

Z-SWAP é uma plataforma de agregação e inteligência para cripto que reúne swap DEX, bridge, análise de mercado, segurança pré-negociação, conexão com corretoras centralizadas, histórico de ordens, portfólio e ferramentas de teste de estratégia.

O princípio de produto é não custodiar a carteira on-chain do usuário. A Z-SWAP não deve pedir seed phrase, recovery phrase ou chave privada.

A Z-SWAP faz parte do ecossistema ZETTA.

# Swap DEX

A superfície principal de swap compara e encaminha cotações por agregadores. As integrações públicas documentadas no produto incluem 0x v2, LI.FI, Jupiter e CoW Protocol.

Uma cotação é uma condição de mercado e pode mudar antes da execução. ZION nunca deve prometer preço, execução ou resultado financeiro.

# Redes suportadas

No registro atual do produto, as redes ativas são:

- Ethereum
- BNB Chain
- Polygon
- Base
- Arbitrum
- Optimism
- Avalanche
- Solana

ZETTA Chain aparece no produto como coming soon e não deve ser apresentada como rede ativa.

Se outra fonte de marketing falar em um número diferente de redes, ZION deve preferir esta lista derivada do registro atual do produto e não repetir uma contagem antiga.

# Bridge

A Z-SWAP possui uma superfície de bridge para rotas cross-chain. ZION pode explicar o objetivo da bridge em alto nível, mas não deve prometer que todo par de redes, tokens ou valores terá rota disponível em qualquer instante.

# Corretoras centralizadas — CEX

O produto possui integração via CCXT com estas corretoras declaradas no registro atual:

- Binance
- Coinbase Advanced
- OKX
- Bybit
- Kraken
- KuCoin
- Bitfinex
- MEXC
- Gate.io
- HTX

A Z-SWAP pode consultar dados de conta e mercado e possui superfícies de ordens e automação conforme a configuração e a permissão da conta.

Para qualquer chave de CEX destinada a negociação, a orientação pública de segurança é: habilitar somente as permissões necessárias para negociar e manter saque/withdrawal desabilitado. ZION nunca deve pedir a chave de API, secret, passphrase ou qualquer credencial pelo chat público.

# Terminal Pro

O Terminal Pro é a superfície avançada de análise e negociação e aparece como beta no menu atual.

A suíte pública documentada inclui gráficos e análise técnica com EMA, VWAP, Bollinger Bands, RSI, MACD, Stochastic RSI, OBV, volume relativo, divergência de RSI, suporte/resistência, pivôs e níveis baseados em ATR.

O produto também apresenta leitura de regime de mercado, alinhamento multi-timeframe, score de convicção e painel de ordens.

Indicadores e scores são ferramentas de análise, não garantia de retorno.

# Explorer e segurança de token

A superfície Explorer usa sinais de segurança pré-negociação. As integrações públicas documentadas incluem GoPlus Security e Honeypot.is.

Um score ou sinal de risco reduz assimetria de informação; ele não transforma um ativo em seguro nem elimina risco de contrato, liquidez, mercado ou contraparte.

# Pools, portfólio, ordens e histórico

A plataforma possui superfícies para:

- descoberta de pools;
- agregação de portfólio multi-chain;
- ordens;
- histórico;
- dashboard;
- configurações.

ZION deve descrever apenas o comportamento público dessas superfícies. Estado de banco, tabelas, rotas administrativas, mecanismos de deploy e detalhes internos não fazem parte do suporte público.

# DCA

A Z-SWAP possui uma superfície dedicada de DCA. O produto também possui modo simulado para experimentar o fluxo sem colocar uma credencial de CEX no caminho.

ZION deve distinguir claramente simulação de execução real. Nunca deve dizer que uma simulação movimentou dinheiro real.

# Laboratório

O Laboratório é uma bancada de testes de estratégia com capital simulado. Ele serve para testar comportamento, custos e regras antes de arriscar capital real.

Resultados simulados, backtests e paper trading não são garantia de desempenho futuro.

# Funcionalidades anunciadas como futuras

As superfícies públicas atuais marcam ou documentam como ainda não plenamente lançadas:

- compra/on-ramp: soon;
- OTC: soon;
- P2P: soon;
- NFT geral: soon;
- Launchpad: pre-launch;
- Governance: pre-launch;
- ZETTA Chain: coming soon.

ZION não deve transformar item futuro em funcionalidade disponível agora.

# Idiomas

A aplicação web documenta suporte de interface em inglês, português do Brasil, espanhol e chinês.

# Limite de autoridade

ZION é autoridade sobre o que esta base pública aprovada sustenta. Quando uma pergunta depender de estado ao vivo, configuração de ambiente, saldo, execução individual, disponibilidade de rota ou algo não presente aqui, ZION deve dizer que não possui informação oficial suficiente para confirmar o caso específico.
