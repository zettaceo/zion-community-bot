# Z-SWAP — Guia Público de Recursos

Esta base descreve o comportamento público aprovado da plataforma. Ela serve para perguntas de suporte e produto; não contém implementação operacional, credenciais ou detalhes administrativos.

# Swap

A tela principal de Swap compara rotas disponíveis antes da execução.

As integrações DEX públicas aprovadas incluem:

- 0x v2
- LI.FI
- Jupiter
- CoW Protocol

A disponibilidade e o preço de uma rota dependem do mercado, da rede, da liquidez, do ativo e dos provedores no momento da consulta.

Uma cotação não é promessa de execução futura. Slippage, impacto no preço, gas e condições da rota podem mudar antes da confirmação.

# Redes

A experiência atual inclui:

- Ethereum
- BNB Chain
- Polygon
- Base
- Arbitrum
- Optimism
- Avalanche
- Solana

ZETTA Chain aparece como coming soon e não deve ser tratada como rede ativa.

# Bridge

A Bridge agrega rotas entre redes compatíveis.

O usuário deve revisar:

- rede de origem;
- rede de destino;
- ativo enviado;
- ativo recebido;
- endereço de recebimento;
- valor mínimo esperado;
- custos e impacto da rota.

Nem todo par de redes e tokens terá uma rota disponível o tempo todo.

# Terminal Pro

O Terminal Pro é a área avançada de análise e aparece como beta.

A suíte pública de análise inclui:

Overlays:
- EMA 9
- EMA 21
- EMA 50
- EMA 100
- EMA 200
- VWAP
- Bollinger Bands

Osciladores:
- RSI 14
- MACD 12/26/9
- Stochastic RSI 14/3/3

Indicadores e leituras adicionais:
- OBV
- Relative Volume
- divergência de RSI
- suporte e resistência
- pivôs diários

A plataforma também trabalha com níveis baseados em ATR(14) para cenários Conservative, Moderate e Aggressive.

# Conviction Score

O Conviction Score resume o alinhamento dos indicadores ativos com a direção observada do preço.

Ele é uma leitura analítica e não uma garantia de que o mercado seguirá aquela direção.

# Regime de mercado

A experiência Pro pode classificar o regime em categorias como:

- tendência de alta;
- tendência de baixa;
- volátil;
- lateral/ranging.

A leitura usa condições de volatilidade e alinhamento de médias como sinais. Regime é diagnóstico de mercado, não promessa de resultado.

# Multi-timeframe

A análise multi-timeframe compara alinhamento de EMA 21/50 em múltiplos intervalos.

Os intervalos públicos documentados vão de 1 minuto até 1 dia:

- 1m
- 5m
- 15m
- 1h
- 4h
- 1d

# Tipos de gráfico

A superfície Pro documenta:

- Candlestick
- OHLC Bar
- Line
- Area

# Painel de ordens

A interface Pro documenta suporte a:

- Market
- Limit
- Stop
- OCO

OCO combina condições de take-profit e stop-loss dentro do fluxo de ordens compatível.

A existência do tipo de ordem na interface não garante suporte idêntico em toda rede, agregador, CEX ou mercado. ZION não deve prometer execução sem confirmar o contexto específico.

# Explorer

O Explorer é a superfície de análise de risco de tokens.

As fontes públicas aprovadas incluem:

- GoPlus Security
- Honeypot.is

Os sinais podem ajudar a identificar riscos conhecidos, mas não provam que um ativo é seguro. Um contrato pode ter riscos que ainda não foram detectados ou cobertos por uma fonte.

# Dados de mercado

As fontes públicas documentadas no produto incluem:

- GeckoTerminal
- DexScreener
- Helius para integrações relacionadas a Solana

Fontes externas podem atrasar, limitar requisições, ficar indisponíveis ou divergir temporariamente. ZION deve distinguir "não há dado" de "não foi possível obter dado" sempre que o contexto permitir.

# Pools

A área de Pools ajuda a descobrir e consultar pools de liquidez.

Liquidez, APY, volume e disponibilidade são dados variáveis. ZION não deve transformar uma fotografia histórica ou uma tela anterior em valor garantido atual.

# Portfolio

A área de Portfolio agrega ativos do usuário em múltiplas redes compatíveis.

Valores em USD são estimativas baseadas nas fontes de preço disponíveis e podem mudar com o mercado.

# Orders e History

Orders centraliza o acompanhamento de ordens suportadas.

History reúne histórico das operações que a plataforma consegue registrar e apresentar ao usuário.

ZION não deve assumir que uma operação ausente da interface nunca existiu sem evidência suficiente; falha de leitura e ausência real são estados diferentes.

# CEX

A integração CEX usa CCXT e o registro público atual inclui:

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

Existem superfícies de saldo, mercado, ordens e automação conforme a corretora, a permissão da credencial e o recurso.

Para credenciais usadas em negociação, a orientação pública de segurança é:

- dar apenas as permissões necessárias;
- manter saque/withdrawal desabilitado;
- não enviar API key, secret ou passphrase em grupos ou suporte público;
- revogar ou rotacionar a credencial se houver exposição.

"Não foi possível verificar a permissão" não significa "a chave está segura".

# DCA

DCA é uma superfície separada do Autopilot.

Ela permite trabalhar com planos periódicos conforme o modo e a configuração disponíveis.

O produto possui modo simulado para testar o fluxo sem confundir simulação com dinheiro real.

# Autopilot CEX

Autopilot é um recurso de automação em CEX e começa no plano Pro na matriz atual.

Autopilot não é sinônimo do plano Pilot.

Quando o recurso usa uma credencial de negociação, saque deve permanecer desabilitado.

# Laboratório / Bancada

O Laboratório permite testar estratégias com capital simulado.

A superfície contempla backtests e, nos tiers compatíveis, mesas de papel adiante.

Backtest, paper trading e resultado simulado não garantem desempenho futuro.

# Segurança de autenticação

A plataforma documenta autenticação por assinatura de carteira:

- SIWE para carteiras EVM;
- assinatura de mensagem para Solana.

A Z-SWAP não deve pedir seed phrase ou chave privada para autenticação.

# Idiomas

A aplicação documenta interface em quatro idiomas:

- inglês;
- português do Brasil;
- espanhol;
- chinês.

# ZION na plataforma

ZION dentro da plataforma ajuda a interpretar informações, contexto de mercado e ferramentas da Z-SWAP.

O ZION da plataforma e o ZION Community Bot compartilham identidade de produto, mas são superfícies diferentes. Não se deve transferir automaticamente provedor de IA, cota ou configuração de uma para a outra.

# Limites das respostas

ZION pode explicar todos os recursos públicos acima.

Quando a pergunta depender de:

- saldo individual;
- ordem específica;
- estado atual de uma credencial;
- configuração privada;
- disponibilidade instantânea de rota;
- dado administrativo;
- infraestrutura;
- banco interno;

ele deve explicar a regra pública e dizer que não possui informação oficial suficiente para confirmar o estado específico sem fonte apropriada.
