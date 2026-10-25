from __future__ import annotations
import unittest
from zion.response_guard import validate_public_response


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
