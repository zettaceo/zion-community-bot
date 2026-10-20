from __future__ import annotations
import unittest
from zion.response_guard import validate_public_response


class ResponseGuardTests(unittest.TestCase):
    def test_known_unsupported_claims_are_rejected(self):
        for value in (
            'Garantimos o melhor preço possível.',
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
        ):
            with self.subTest(value=value):
                self.assertFalse(validate_public_response(value, official_context='').allowed)

    def test_caveats_and_route_specific_explanation_are_allowed(self):
        for value in (
            'Não podemos garantir o melhor preço.',
            'Não podemos garantir que a transação seja segura.',
            'Não é seguro usar qualquer plataforma sem avaliar os riscos.',
            'A Z-SWAP implementa controles para reduzir riscos, mas nenhuma plataforma ou transação é livre de risco.',
            'Nenhuma plataforma é livre de riscos.',
            'Nenhuma transação é totalmente segura.',
            'As rotas são comparadas conforme as condições daquele momento.',
            'A execução depende da rede, rota e provedor.',
            'Não posso fornecer endpoints internos. Qual caso de uso você quer implementar?',
        ):
            with self.subTest(value=value):
                self.assertTrue(validate_public_response(value, official_context='').allowed)

    def test_provenance_paths_addresses_and_unapproved_links_are_blocked(self):
        for value in ('Veja /home/operator/app', 'use 10.20.30.40',
                      'Leia migration.sql', 'https://private.invalid/api',
                      '/api/admin/users', 'db.production.internal',
                      'zettaceo/zion-community-bot'):
            self.assertFalse(validate_public_response(value, official_context='').allowed)
        self.assertTrue(validate_public_response('Veja https://public.example/help.',
            official_context='Ajuda pública: https://public.example/help').allowed)

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
