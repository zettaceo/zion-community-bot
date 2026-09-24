# Z-SWAP — Planos, Cotas e Taxas

Fonte aprovada para esta versão: snapshot público de `zetta-world/swap-z-app` em 25fc4b0fa55db72472c7ae00af42596209d7c362, de 15/09/2026. Este arquivo contém somente informações próprias para suporte público.

# Níveis de acesso

Os níveis do produto, em ordem crescente, são:

- Free
- Pro
- Trader
- Pilot

Trader satisfaz recursos que exigem Pro. Pilot satisfaz recursos que exigem Pro ou Trader.

ZION nunca deve confundir o plano Pilot com a função de piloto automático/autopilot.

# Cota diária do ZION na plataforma Z-SWAP

A matriz atual de análises por dia é:

- Free: 5 análises/dia
- Pro: 10 análises/dia
- Trader: 25 análises/dia
- Pilot: 30 análises/dia

Esses limites pertencem ao produto Z-SWAP e são diferentes dos limites do ZION Community Bot no Telegram.

# Taxa de swap por plano em EVM

A escada pública atual de taxa da plataforma para swaps EVM é:

- Free: 1,00%
- Pro: 0,50%
- Trader: 0,25%
- Pilot: 0,10%

A lógica do produto é que planos mais altos paguem menos taxa por operação.

Taxa de rede/gas, slippage, spread e custos de terceiros não são a mesma coisa que a taxa da plataforma.

# Solana

No estado atual do produto, a taxa de plataforma da Z-SWAP em swaps Solana está desabilitada por decisão de produto.

ZION pode dizer que a taxa de plataforma da Z-SWAP em Solana está atualmente em zero, mas não deve prometer que outros custos de rede, rota, agregador ou mercado sejam zero.

# O Panteão — passes de lançamento

A superfície de lançamento usa os níveis:

- Pro — Freyr
- Trader — Thor
- Pilot — Odin

Os valores de 1,5 SOL, 4 SOL e 30 SOL são referências de lançamento/marketing. A regra atual de preço no código é ancorada em USD e convertida para SOL pela cotação vigente, portanto ZION não deve prometer um número fixo de SOL sem consultar a oferta pública atual.

A página de lançamento descreve o passe como utilitário, com benefícios premium por 3 anos e status Founder permanente.

ZION não deve descrever esses passes como investimento, participação societária, dividendo ou promessa de retorno.

# A Hird — planos mensais

A assinatura mensal recorrente usa estas identidades e preços-base em USD:

- Pro — Drengr — US$ 7,90/mês
- Trader — Berserkr — US$ 20,90/mês
- Pilot — Einherjar — US$ 159/mês

A superfície pública descreve o pagamento em SOL usando preço ancorado em USD.

# Recursos mínimos por tier

A matriz atual do produto declara:

- ZION advisory: disponível a partir do Free, diferenciado principalmente pela cota;
- CEX Autopilot: Pro ou superior;
- scanner de arbitragem: Trader ou superior;
- suporte prioritário: Trader ou superior;
- backtest na Bancada/Laboratório: Free ou superior;
- papel adiante na Bancada/Laboratório: Trader ou superior.

A disponibilidade efetiva pode depender do rollout/configuração atual do produto. Se uma interface pública atual disser que algo está indisponível, ZION deve respeitar o estado da interface em vez de prometer acesso.

# Cotas da Bancada/Laboratório

A matriz atual para testes de estratégia é:

Free:
- até 10 backtests por janela móvel de 24h;
- capital simulado até US$ 1.000;
- 1 estratégia salva;
- janela histórica até 365 dias;
- até 3 símbolos por teste;
- sem mesa de papel adiante.

Pro:
- até 100 backtests por janela móvel de 24h;
- capital simulado até US$ 25.000;
- 10 estratégias salvas;
- janela histórica até 730 dias;
- até 10 símbolos por teste;
- sem mesa de papel adiante.

Trader:
- até 500 backtests por janela móvel de 24h;
- capital simulado até US$ 250.000;
- 50 estratégias salvas;
- janela histórica até 730 dias;
- até 10 símbolos por teste;
- até 3 mesas de papel adiante.

Pilot:
- até 5.000 backtests por janela móvel de 24h;
- capital simulado até US$ 100.000.000;
- 200 estratégias salvas;
- janela histórica até 730 dias;
- até 10 símbolos por teste;
- até 10 mesas de papel adiante.

Essas cotas são limites de produto e não representam recomendação de capital real.

# O que ZION não deve prometer

ZION nunca deve prometer:

- lucro;
- retorno mínimo;
- ausência de perda;
- execução garantida;
- slippage zero;
- disponibilidade permanente de uma rota;
- valorização de NFT ou token;
- que um plano pago torna uma operação financeiramente segura.

Quando a pergunta envolver decisão de investimento, ZION deve limitar-se ao funcionamento factual do produto e aos riscos relevantes.
