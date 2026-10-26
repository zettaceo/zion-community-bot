from __future__ import annotations
import unittest
from zion.response_guard import public_fallback_for, validate_public_response


class ResponseGuardTests(unittest.TestCase):
    def test_known_unsupported_claims_are_rejected(self):
        for value in (
            'Garantimos o melhor preço possível.',
            'Garantimos, sem ressalvas, o melhor preço.',
            'A plataforma vai garantir a melhor taxa possível.',
            'Todos os swaps são executados por smart contracts.',
            'É seguro usar a Z-SWAP.',
            'Não cobramos aqui, mas é seguro usar a Z-SWAP.',
            'É totalmente seguro.',
            'Usa provedores confiáveis para garantir que a transação seja segura e transparente.',
            'Garantimos a segurança de todas as transações.',
            'Esta plataforma é livre de riscos.',
            'Nenhuma plataforma é livre de risco, mas é seguro usar a Z-SWAP.',
            'Aprovei sua parceria.',
            'Nenhuma rota é livre de riscos, mas a nossa é totalmente segura.',
            'A Z-SWAP é segura para usar.',
            'A plataforma é completamente segura.',
            'Sua segurança está garantida.',
            'A segurança da operação é garantida.',
            'A segurança está plenamente garantida.',
            'A operação não tem risco.',
            'A operação é risco zero.',
            'A plataforma garante proteção total.',
            'A Z-SWAP oferece segurança total.',
            'Garantimos que você não corre risco.',
            'Não garantimos segurança, mas a operação é completamente segura.',
        ):
            with self.subTest(value=value):
                self.assertFalse(validate_public_response(value, official_context='').allowed)

    def test_caveats_and_route_specific_explanation_are_allowed(self):
        for value in (
            'Não podemos garantir o melhor preço.',
            'Não dá para garantir o melhor preço.',
            'Nenhuma plataforma pode garantir o melhor preço.',
            'É impossível garantir a melhor taxa.',
            'Não podemos garantir que a transação seja segura.',
            'Não há como garantir a segurança de qualquer swap.',
            'Não se pode garantir segurança absoluta.',
            'Sem garantir a segurança, explique os controles.',
            'Ninguém pode garantir segurança absoluta.',
            'Não é seguro usar qualquer plataforma sem avaliar os riscos.',
            'A Z-SWAP implementa controles para reduzir riscos, mas nenhuma plataforma ou transação é livre de risco.',
            'Nenhuma plataforma é livre de riscos.',
            'Nenhuma transação é totalmente segura.',
            'Nenhuma rota é livre de riscos.',
            'Nenhum swap é 100% seguro.',
            'As rotas são comparadas conforme as condições daquele momento.',
            'A execução depende da rede, rota e provedor.',
            'Não posso fornecer endpoints internos. Qual caso de uso você quer implementar?',
        ):
            with self.subTest(value=value):
                self.assertTrue(validate_public_response(value, official_context='').allowed)

    def test_scoped_price_denial_does_not_excuse_later_guarantee(self):
        for value in (
            'Não dá para garantir o melhor preço, mas a Z-SWAP garante a melhor taxa.',
            'Nenhuma plataforma pode garantir o melhor preço. A nossa garante a melhor taxa.',
        ):
            with self.subTest(value=value):
                self.assertEqual(validate_public_response(
                    value, official_context='').reason, 'best_price_guarantee')

    def test_guarantee_noun_denials_are_not_promises(self):
        for text in ('Não há garantia de melhor preço.',
                     'Não existe garantia de melhor preço.',
                     'A Z-SWAP não oferece garantia de melhor preço.',
                     'Não há qualquer garantia de melhor preço.',
                     'Não existe uma garantia de melhor preço.',
                     'Não damos garantia de melhor preço.',
                     'Nenhuma plataforma oferece garantia do melhor preço.',
                     'Garantia de melhor preço não existe.',
                     'Não existe melhor preço garantido.',
                     'Não temos garantia de melhor preço.',
                     'Não há garantia de segurança.'):
            with self.subTest(text=text):
                self.assertTrue(validate_public_response(text, official_context='').allowed)
        for text in ('Há garantia de melhor preço.',
                     'A Z-SWAP oferece garantia de melhor preço.',
                     'Não há garantia de melhor preço, mas garantimos a melhor taxa.',
                     'Garantia de melhor preço não existe, mas oferecemos a melhor taxa garantida.',
                     'O melhor preço é garantido.',
                     'A Z-SWAP oferece sempre o melhor preço.',
                     'A menor taxa do mercado é garantida.'):
            with self.subTest(text=text):
                self.assertEqual(validate_public_response(
                    text, official_context='').reason, 'best_price_guarantee')

    def test_execution_guarantee_from_native_smoke_is_rejected_with_scoped_negation(self):
        for text in (
            'Assim, você evita surpresas e garante que a transação seja executada conforme o planejado.',
            'Isso assegura que a ordem seja concluída.',
            'Garantimos a execução da sua transação.',
            'Não prometemos lucro, mas garantimos a execução da sua transação.',
        ):
            with self.subTest(text=text):
                check = validate_public_response(text, official_context='Revise a rota.')
                self.assertFalse(check.allowed)
                self.assertEqual(check.reason, 'execution_guarantee')
        for text in (
            'Não podemos garantir que a transação seja executada conforme o planejado.',
            'Não garantimos a execução da sua transação.',
            'Revise a rota; a execução depende da rede e do provedor.',
        ):
            with self.subTest(text=text):
                self.assertTrue(validate_public_response(text, official_context='').allowed)

    def test_provenance_paths_addresses_and_unapproved_links_are_blocked(self):
        for value in ('Veja /home/operator/app', 'use 10.20.30.40',
                      'Leia migration.sql', 'https://private.invalid/api',
                      '/api/admin/users', 'db.production.internal',
                      'zettaceo/zion-community-bot'):
            self.assertFalse(validate_public_response(value, official_context='').allowed)
        self.assertTrue(validate_public_response('Veja https://public.example/help.',
            official_context='Ajuda pública: https://public.example/help').allowed)

    def test_observed_free_swap_and_unapproved_competitor_claims_are_blocked(self):
        self.assertEqual(validate_public_response(
            'A Z-SWAP não cobra por transações de swap, mas taxas podem variar conforme a rede.',
            official_context='Taxas da plataforma variam por plano e rota.').reason, 'unsupported_free_swap')
        self.assertFalse(validate_public_response('Os swaps são gratuitos.', official_context='').allowed)
        self.assertEqual(validate_public_response(
            'Uniswap, PancakeSwap, 1inch Network, Raydium e Bisq já são bem estabelecidas.',
            official_context='GeckoTerminal e DexScreener são fontes de dados.').reason,
            'unapproved_market_service_claim')
        self.assertTrue(validate_public_response('A execução pode usar Uniswap.',
            official_context='A execução pode usar Uniswap.').allowed)
        self.assertTrue(validate_public_response('Taxas dependem do plano, da rota e da rede.',
            official_context='Taxas da plataforma variam por plano e rota.').allowed)

    def test_live_kimi_unsourced_market_and_partnership_fee_claims_are_blocked(self):
        market = ('Há sim plataformas consolidadas com taxas competitivas e '
                  'funcionalidades similares.')
        fee = 'Não há taxa padrão de parceria comercial.'
        for answer, reason in ((market, 'unsupported_competitor_comparison'),
                               ('Várias plataformas oferecem swap e análise de forma separada.',
                                'unsupported_competitor_comparison'),
                               ('Várias das peças já existem de forma isolada em outras plataformas.',
                                'unsupported_competitor_comparison'),
                               ('A proposta não é exclusiva da Z-SWAP.',
                                'unsupported_competitor_comparison'),
                               ('A existência de plataformas com abordagens similares é uma preocupação válida.',
                                'unsupported_competitor_comparison'),
                               (fee, 'unsupported_partnership_fee_policy'),
                               ('Parcerias não têm taxa fixa.', 'unsupported_partnership_fee_policy')):
            with self.subTest(answer=answer):
                check = validate_public_response(answer,
                    official_context='Uma conversa de parceria não equivale a contrato.')
                self.assertFalse(check.allowed)
                self.assertEqual(check.reason, reason)
        self.assertTrue(validate_public_response(market, official_context=market).allowed)
        self.assertTrue(validate_public_response(fee, official_context=fee).allowed)
        self.assertTrue(validate_public_response(
            'Não tenho informação oficial sobre taxa padrão de parceria.',
            official_context='Uma conversa de parceria não equivale a contrato.').allowed)
        self.assertTrue(validate_public_response(
            'Não sei se outras plataformas oferecem os mesmos recursos.',
            official_context='A Z-SWAP documenta seus próprios recursos.').allowed)

    def test_monetary_claim_requires_currency_and_amount_in_official_context(self):
        for answer in ('O plano custa US$ 99.', 'A taxa custa 40 reais.', 'Custa € 12.'):
            with self.subTest(answer=answer):
                result = validate_public_response(answer, official_context='Preço ainda não publicado.')
                self.assertFalse(result.allowed)
                self.assertEqual(result.reason, 'unsupported_monetary_claim')
        self.assertTrue(validate_public_response('Custa US$ 0.10.', official_context='Preço: USD 0,10').allowed)
        self.assertFalse(validate_public_response('Custa R$ 10.', official_context='Preço: US$ 10').allowed)
        self.assertFalse(validate_public_response('Custa US$ 1.000.', official_context='Preço: USD 1').allowed)
        self.assertTrue(validate_public_response('Nenhuma plataforma é 100% segura.', official_context='').allowed)

    def test_evm_plan_fee_enumeration_uses_complete_official_matrix(self):
        context = '\n\n'.join((
            '[Contexto oficial: Plano Free ou Thrall]\nA platform fee nas rotas EVM é 1,00%.',
            '[Contexto oficial: Plano Pro ou profissional]\nA platform fee EVM pública é 0,50%.',
            '[Contexto oficial: Plano Trader]\nA platform fee EVM pública é 0,25%.',
            '[Contexto oficial: Plano Pilot ou plano piloto]\nA platform fee EVM pública é 0,10%.',
        ))
        partial = 'Nas rotas EVM: Free 1,00%, Pro 0,50% e Pilot 0,10%.'
        partial_without_network = 'As taxas por plano são Free 1%, Pro 0,5% e Pilot 0,1%.'
        wrong = 'Nas rotas EVM: Free 1,00%, Pro 0,50%, Trader 0,50% e Pilot 0,10%.'
        complete = 'Nas rotas EVM: Free 1%, Pro 0,5%, Trader 0,25% e Pilot 0,1%.'
        complete_reverse = ('Nas rotas EVM, as taxas são 1% no Free, 0,5% no Pro, '
                            '0,25% no Trader e 0,1% no Pilot.')
        for answer in (partial, partial_without_network, wrong):
            with self.subTest(answer=answer):
                check = validate_public_response(answer, official_context=context)
                self.assertFalse(check.allowed)
                self.assertEqual(check.reason, 'incomplete_plan_fee_matrix')
        self.assertTrue(validate_public_response(complete, official_context=context).allowed)
        self.assertTrue(validate_public_response(
            complete_reverse, official_context=context).allowed)
        self.assertTrue(validate_public_response(
            'No Pro a platform fee EVM é 0,50%.', official_context=context).allowed)
        self.assertTrue(validate_public_response(
            'Na Solana, Free 1%, Pro 0,5% e Pilot 0,1% podem ser elegíveis.',
            official_context=context).allowed)
        self.assertEqual(validate_public_response(
            partial, official_context=context.split('[Contexto oficial: Plano Trader]')[0]
        ).reason, 'incomplete_plan_fee_matrix')
        fallback = public_fallback_for('incomplete_plan_fee_matrix')
        self.assertIn('Trader', fallback)
        self.assertTrue(validate_public_response(fallback, official_context='').allowed)

    def test_solana_jupiter_fee_condition_is_not_generalized_to_every_route(self):
        context = ('[Contexto oficial: Taxas Solana, Jupiter e LI.FI]\n'
                   'Na Jupiter, essa cobrança se aplica quando USDC ou SOL é um dos lados do swap. '
                   'A política também abrange rotas LI.FI saindo da Solana.')
        wrong = (
            'Em Solana, a mesma escada vale quando USDC ou SOL é um dos lados do swap; '
            'outros pares Solana não têm platform fee da Z-SWAP.',
            'Na Solana, só há platform fee quando USDC ou SOL participa do swap.',
            'Outros pares Solana não têm platform fee da Z-SWAP.',
            'Em Solana, só há cobrança quando USDC ou SOL participa, e Jupiter também existe.',
            'Todas as rotas Solana, inclusive Jupiter e LI.FI, só pagam taxa com USDC ou SOL.',
            'Na Solana, não há platform fee para swaps sem USDC ou SOL.',
            'Em Solana, swaps que não incluem USDC ou SOL não pagam a taxa da plataforma.',
            'Pela Jupiter ou LI.FI na Solana, a taxa só incide quando USDC ou SOL entra no par.',
            'Em Solana, a taxa depende de USDC ou SOL; outros pares não pagam taxa.',
            'Em Solana, os pares com USDC ou SOL pagam a platform fee. '
            'Os demais pares não pagam taxa.',
        )
        for text in wrong:
            with self.subTest(text=text):
                self.assertEqual(validate_public_response(
                    text, official_context=context).reason, 'overbroad_solana_fee_scope')
        for text in (
            'Na Jupiter, a condição de USDC ou SOL vale para a cobrança. '
            'Rotas LI.FI saindo da Solana devem ser avaliadas separadamente.',
            'Em Solana, quando USDC ou SOL é um dos lados do swap na Jupiter, '
            'há cobrança. LI.FI é diferente.',
            'Em Solana, a taxa varia quando USDC ou SOL participa, conforme a rota.',
            'As taxas na Solana dependem do provedor e da rota. Confira os custos antes do swap.',
        ):
            with self.subTest(text=text):
                self.assertTrue(validate_public_response(text, official_context=context).allowed)
        self.assertTrue(validate_public_response(
            'Em Solana, USDC ou SOL pode importar conforme a rota.',
            official_context='Sem política de taxa aprovada.').allowed)
        self.assertTrue(validate_public_response(
            'Na Solana, somente a Jupiter condiciona a cobrança à presença de USDC ou SOL.',
            official_context=context).allowed)
        self.assertTrue(validate_public_response(
            public_fallback_for('overbroad_solana_fee_scope'), official_context='').allowed)

    def test_snapshot_evidence_is_not_called_live_proof(self):
        for text in (
            'O que é fato verificável agora: Free tem cinco análises diárias.',
            'Vou trazer só o que é verificável hoje sobre os planos.',
            'Abra a plataforma e rode um backtest no Free. Isso é prova.',
            'Eu confirmei hoje que está aberto.',
            'Testei a interface agora e confirmei.',
            'Foi verificado hoje que a função está disponível.',
            'Está disponível agora na plataforma.',
            'Hoje testei a interface e confirmei que funciona.',
            'Acabei de testar a interface e confirmei que funciona.',
            'Confirmei em tempo real que funciona.',
            'A interface foi testada em tempo real e está funcionando.',
            'No momento, as funções estão disponíveis na plataforma.',
            'No momento, o recurso está disponível na plataforma.',
        ):
            with self.subTest(text=text):
                self.assertEqual(validate_public_response(
                    text, official_context='Snapshot público datado.').reason,
                    'unverified_live_proof')
        for text in (
            'Na base pública revisada, o recurso está listado; confira sua disponibilidade na interface.',
            'Não verifiquei agora a disponibilidade da sua conta.',
            'Isso não é verificável hoje pela base pública revisada.',
            'Não é possível afirmar que seja comprovado hoje.',
            'Não foi verificado hoje na plataforma.',
            'Não está disponível agora na plataforma segundo a base pública.',
            'Não comprovado hoje pela base pública.',
            'Sem prova verificável hoje, prefiro não afirmar.',
            'Não há nada verificável hoje na base pública.',
            'No momento, as funções não estão disponíveis na plataforma.',
            'As redes ativas documentadas são Ethereum e Polygon.',
        ):
            with self.subTest(text=text):
                self.assertTrue(validate_public_response(
                    text, official_context='Snapshot público datado.').allowed)
        self.assertTrue(validate_public_response(
            public_fallback_for('unverified_live_proof'), official_context='').allowed)

    def test_approved_beta_and_partial_status_survive_feature_comparison(self):
        context = ('[Contexto oficial: Beta]\nTerminal Pro está marcado como beta.\n\n'
                   '[Contexto oficial: Produto antes de promessa]\n'
                   'Portfolio e Orders estão parcialmente disponíveis.')
        for answer in (
            'O Terminal Pro reúne gráficos e o Portfolio acompanha ativos.',
            'O Terminal Pro reúne gráficos e indicadores.',
            'O Portfolio acompanha ativos.',
            'Orders está totalmente disponível.',
            'O Terminal Pro deixou o beta e está totalmente disponível.',
        ):
            with self.subTest(answer=answer):
                self.assertEqual(validate_public_response(
                    answer, official_context=context).reason, 'missing_feature_status')
        self.assertTrue(validate_public_response(
            'O Terminal Pro está em beta; o Portfolio e Orders estão parcialmente disponíveis. '
            'O Terminal Pro inclui análise e Orders apresenta ordens.',
            official_context=context).allowed)
        self.assertTrue(validate_public_response(
            'O Terminal Pro reúne gráficos.', official_context='Sem estado oficial publicado.').allowed)
        self.assertTrue(validate_public_response(
            public_fallback_for('missing_feature_status'), official_context='').allowed)
