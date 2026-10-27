from __future__ import annotations
import unittest
from pathlib import Path
from time import perf_counter
from zion.knowledge import KnowledgeBase
from zion.knowledge_tools import KnowledgeTools
from zion.response_guard import public_fallback_for, validate_public_response


class ResponseGuardTests(unittest.TestCase):
    def test_broad_comparison_fallback_requires_complete_public_evidence(self):
        question = 'Qual a diferença da Z-SWAP para outras plataformas?'
        knowledge = KnowledgeBase(Path(__file__).resolve().parents[1] / 'knowledge')
        context = KnowledgeTools(knowledge).call(
            'search_approved_knowledge', {'query': question}, agent_id='zion').render()
        reply = public_fallback_for(
            'missing_feature_status', question=question, official_context=context)
        self.assertIn('reúne análise, simulação, planejamento de ordens', reply)
        self.assertIn('Terminal Pro está em beta', reply)
        self.assertIn('Portfolio e Orders estão parcialmente disponíveis', reply)
        self.assertIn('Não tenho uma comparação oficial', reply)
        self.assertTrue(validate_public_response(reply, official_context=context).allowed)
        without_positioning = context.replace(
            '[Contexto oficial: Z-SWAP — Posicionamento institucional público]',
            '[Contexto oficial: Seção não relacionada]')
        without_map = context.replace(
            '[Contexto oficial: Mapa público da plataforma]',
            '[Contexto oficial: Seção não relacionada]')
        for unapproved in (without_positioning, without_map):
            with self.subTest(unapproved=unapproved[:70]):
                self.assertNotIn('reúne análise, simulação', public_fallback_for(
                    'missing_feature_status', question=question,
                    official_context=unapproved))
        self.assertNotIn('reúne análise, simulação', public_fallback_for(
            'missing_feature_status', question='O Terminal Pro está disponível?',
            official_context=context))

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

    def test_unproved_automatic_best_route_claims_are_rejected(self):
        context = KnowledgeTools(KnowledgeBase(
            Path(__file__).resolve().parents[1] / 'knowledge')).call(
                'search_approved_knowledge', {'query': 'Como funciona os swaps?'},
                agent_id='mimir').render()
        self.assertIn('[Contexto oficial: Swaps e pontes]', context)
        self.assertIn('[Contexto oficial: Swap]', context)
        for answer in (
            'A Z-SWAP analisa taxas e liquidez e escolhe automaticamente a melhor cotação para você.',
            'A plataforma então **consulta provedores autorizados** (como Jupiter '
            'ou LI.FI) para encontrar a melhor cotação disponível **naquele momento**, '
            'considerando liquidez e taxas.',
            'A plataforma não compara todas as fontes e escolhe a melhor rota.',
            'A plataforma não compara todas as fontes e escolhe a melhor '
            'cotação disponível naquele momento.',
            'A Z-SWAP não realiza bridge diretamente e encontra a melhor '
            'cotação para o swap.',
            'A plataforma consulta os provedores autorizados, inclusive os '
            'que operam em várias redes, como Jupiter, LI.FI e outros '
            'disponíveis naquele momento, para encontrar a melhor cotação.',
            'A plataforma consulta Jupiter e LI.FI. Então encontra a melhor cotação.',
            'A plataforma não promete encontrar a melhor rota, mas encontra '
            'a melhor cotação.',
            'A plataforma fornece dados para você avaliar as opções e '
            'encontra a melhor cotação.',
            'A plataforma mostra custos para você comparar e seleciona '
            'a melhor rota.',
            'A plataforma mostra como escolher, e depois ela encontra '
            'a melhor rota.',
            'A Z-SWAP encaminha você para a rota com o menor preço.',
            'A Z-SWAP decide a rota ótima para cada troca.',
            'A plataforma sempre acha a cotação mais vantajosa.',
            'O motor encontra o caminho mais barato para seu swap.',
            'A Z-SWAP entrega o preço mínimo disponível.',
            'A plataforma encontra a melhor rota que você escolheu.',
            'A plataforma escolhe a melhor rota que você selecionou.',
            'A plataforma mostra a melhor rota que você escolheu e '
            'encontra a melhor cotação.',
            'A plataforma consulta Jupiter e LI. FI para encontrar a melhor cotação.',
            'A plataforma consulta Jupiter e LI.**FI para encontrar a melhor cotação.',
            'A plataforma consulta Jupiter e LI[.]FI para encontrar a melhor cotação.',
            'A plataforma seleciona a rota mais eficiente com base em taxas e liquidez.',
            'O sistema encontra o melhor preço para a sua troca.',
            'A Z-SWAP busca a rota com menor custo.',
            'Seleciona a melhor rota por taxas e liquidez.',
            'The platform selects the best quote for each swap.',
            'Não afirmo que a Z-SWAP escolhe a melhor cotação, mas entrega a rota mais eficiente.',
            'A Z-SWAP escolhe automaticamente a rota de menor custo.',
            'Ela não compara todas as fontes, porém escolhe automaticamente a rota com menor preço.',
            'A Z-SWAP compara taxas e liquidez para escolher automaticamente a rota mais econômica.',
            'The platform always picks the lowest-cost route.',
            'A Z-SWAP entrega sempre o menor preço.',
            'A melhor cotação é escolhida automaticamente pela Z-SWAP.',
            'A Z-SWAP afirma: "A plataforma escolhe a melhor rota".',
            'Você perguntou: "A plataforma escolhe a melhor rota?" '
            'Mas ela escolhe a rota de menor custo.',
        ):
            with self.subTest(answer=answer):
                self.assertEqual(validate_public_response(
                    answer, official_context=context).reason,
                    'unsupported_route_optimization')
        for answer in (
            'A Z-SWAP seleciona a fonte de cotação conforme as redes e mostra a rota retornada.',
            'A plataforma mostra as rotas disponíveis para você escolher '
            'a melhor rota para seu caso.',
            'A plataforma fornece os custos para você escolher a melhor '
            'rota conforme suas preferências.',
            'A plataforma recomenda que você compare a melhor cotação '
            'com outros provedores antes de confirmar.',
            'A Z-SWAP permite ao usuário selecionar a melhor rota para '
            'sua estratégia entre as opções disponíveis.',
            'A plataforma destaca os custos, e cabe a você escolher a melhor rota.',
            'A plataforma mostra como escolher a melhor rota por conta própria.',
            'A plataforma explica como encontrar a melhor cotação entre '
            'as rotas disponíveis.',
            'A tela compara rotas disponíveis antes da execução; confira os custos.',
            'Você perguntou se a Z-SWAP escolhe a melhor rota automaticamente; '
            'a base pública não confirma isso.',
            'A Z-SWAP escolhe a melhor rota automaticamente? A base pública não confirma isso.',
            'A Z-SWAP não escolhe automaticamente a melhor rota por taxas e liquidez.',
            'A plataforma não promete encontrar a melhor rota.',
            'A plataforma não pode escolher a melhor rota em todos os casos.',
            'A plataforma não consegue encontrar a melhor cotação entre '
            'todos os provedores.',
            'A plataforma não afirma que escolhe a melhor rota.',
            'A plataforma não tem como encontrar a melhor cotação em todos os casos.',
            'A plataforma não pode garantir que encontra a melhor cotação.',
            'A plataforma nunca disse que escolhe a melhor rota.',
            'A plataforma seleciona a fonte conforme as redes, não a melhor rota.',
            'A plataforma mostra critérios para encontrar a melhor cotação '
            'por sua conta.',
            'A plataforma recomenda comparar as opções e escolher a melhor '
            'rota para seu caso.',
            'A plataforma mostra o custo da rota antes de confirmar.',
            'A plataforma mostra custos e deixa claro que o menor preço '
            'não é garantido.',
            'O motor encontra uma rota com custos exibidos, sem garantia '
            'de preço mínimo.',
            'A plataforma mostra apenas o custo da rota, sem prometer '
            'o menor preço.',
            'A Z-SWAP mostra custos externos; não garante preço mínimo.',
            'O preço mínimo não é garantido.',
            'A Z-SWAP mostra a rota que você selecionou; avalie se ela '
            'é a melhor para você.',
            'A plataforma mostra a melhor rota que você escolheu.',
            'A plataforma apresenta a melhor rota que você selecionou.',
            'O material público não comprova que a plataforma escolhe a melhor rota.',
            'O material público não permite afirmar que a plataforma '
            'escolhe a melhor rota.',
            'Escolher a melhor rota depende da avaliação do usuário.',
            'Não posso afirmar que a Z-SWAP escolhe automaticamente a melhor cotação.',
            '"A Z-SWAP escolhe a melhor rota" é a sua dúvida; a fonte pública não confirma isso.',
            'Você pode comparar os custos da rota antes de confirmar.',
            'O sistema recomenda a melhor opção de suporte para o seu caso.',
            'A plataforma mostra os custos da rota antes da confirmação.',
            'Não é verdade que a Z-SWAP escolhe a melhor rota.',
            'Não há evidências de que a plataforma escolhe a melhor rota.',
            'Não é correto afirmar que a plataforma escolhe a melhor rota.',
            'Não há confirmação de que a plataforma encontra a melhor cotação disponível.',
            "'A Z-SWAP escolhe a melhor rota' foi sua dúvida; "
            'a fonte pública não confirma isso.',
            'A melhor cotação é escolhida automaticamente pela Z-SWAP?',
            'Não posso confirmar que a melhor cotação é escolhida pela Z-SWAP.',
        ):
            with self.subTest(answer=answer):
                self.assertTrue(validate_public_response(
                    answer, official_context=context).allowed)

    def test_best_route_fallback_requires_canonical_public_section(self):
        context = KnowledgeTools(KnowledgeBase(
            Path(__file__).resolve().parents[1] / 'knowledge')).call(
                'search_approved_knowledge', {'query': 'Como funciona os swaps?'},
                agent_id='mimir').render()
        for reason in ('best_price_guarantee', 'unsupported_route_optimization'):
            with self.subTest(reason=reason):
                reply = public_fallback_for(reason, official_context=context)
                self.assertIn('seleciona a fonte de cotação conforme as redes', reply)
                self.assertIn('mostra a rota retornada', reply)
                self.assertTrue(validate_public_response(
                    reply, official_context=context).allowed)
                for weak in ('', context.replace(
                        '[Contexto oficial: Swaps e pontes]',
                        '[Contexto oficial: Outra seção]'), context.replace(
                        'Não compara todas as fontes em cada pedido.', '')):
                    fallback = public_fallback_for(reason, official_context=weak)
                    self.assertNotIn('seleciona a fonte de cotação', fallback)
                    self.assertTrue(validate_public_response(
                        fallback, official_context=weak).allowed)

    def test_every_swap_signature_claim_requires_explicit_public_support(self):
        context = KnowledgeTools(KnowledgeBase(
            Path(__file__).resolve().parents[1] / 'knowledge')).call(
                'search_approved_knowledge', {'query': 'Como funciona os swaps?'},
                agent_id='mimir').render()
        self.assertIn('[Contexto oficial: Swaps e pontes]', context)
        self.assertNotIn('assinatura', context.casefold())
        for answer in (
            'Todos os swaps exigem assinatura na carteira do usuário.',
            'Toda confirmação de swap é feita por assinatura na carteira.',
            'A confirmação de qualquer swap exige assinatura na carteira.',
            'Para cada swap, o usuário assina na própria carteira.',
            'Uma assinatura na carteira é obrigatória para cada swap.',
        ):
            with self.subTest(answer=answer):
                self.assertEqual(validate_public_response(
                    answer, official_context=context).reason,
                    'unsupported_universal_swap_signature')
        for answer in (
            'Nem todos os swaps exigem assinatura na carteira.',
            'Não é verdade que todos os swaps exigem assinatura na carteira.',
            'Todos os swaps exigem assinatura na carteira?',
            'Você perguntou: "Todos os swaps exigem assinatura na carteira?" '
            'A base não confirma isso.',
            'A autenticação por assinatura é diferente da confirmação de um swap.',
            'Confira a operação antes de confirmar. Não compartilhe seed phrase '
            'ou chave privada.',
            'A Z-SWAP nunca deve pedir seed phrase ou chave privada.',
            'A rota de bridge depende da disponibilidade no momento da consulta.',
        ):
            with self.subTest(answer=answer):
                self.assertTrue(validate_public_response(
                    answer, official_context=context).allowed)
        supported = ('[Contexto oficial: Confirmação de swaps]\n'
                     'Todos os swaps exigem assinatura na carteira do usuário.')
        self.assertTrue(validate_public_response(
            'Todos os swaps exigem assinatura na carteira do usuário.',
            official_context=supported).allowed)
        fallback = public_fallback_for('unsupported_universal_swap_signature',
                                       official_context=context)
        self.assertTrue(validate_public_response(
            fallback, official_context=context).allowed)

    def test_named_quote_source_and_swap_confirmation_need_retrieved_evidence(self):
        retrieved = KnowledgeTools(KnowledgeBase(
            Path(__file__).resolve().parents[1] / 'knowledge')).call(
                'search_approved_knowledge', {'query': 'Como funciona os swaps?'},
                agent_id='mimir').render()
        self.assertIn('[Contexto oficial: Agregadores de swap]', retrieved)
        self.assertIn('Jupiter', retrieved)
        context = ('[Contexto oficial: Swaps e pontes]\n'
                   'A Z-SWAP seleciona a fonte conforme as redes e mostra '
                   'a rota retornada. Antes de confirmar, confira os custos.')
        self.assertNotIn('Jupiter', context)
        self.assertNotIn('assinatura', context.casefold())
        for answer in (
            'Se você trocar tokens na Solana, a cotação pode vir de um '
            'provedor como a Jupiter.',
            'A cotação vem de Jupiter na Solana.',
            'LI.FI é fonte de cotação entre redes.',
            'A cotação é fornecida pela 0x para redes EVM.',
            'CoW Protocol é fonte de cotação para swaps.',
        ):
            with self.subTest(answer=answer):
                self.assertEqual(validate_public_response(
                    answer, official_context=context).reason,
                    'unsupported_named_quote_source')
        for answer in (
            'A confirmação é feita por assinatura na carteira.',
            'No swap, a confirmação é feita por assinatura na carteira.',
        ):
            with self.subTest(answer=answer):
                self.assertEqual(validate_public_response(
                    answer, official_context=context).reason,
                    'unsupported_swap_confirmation_signature')
        for answer in (
            'A cotação pode vir de um provedor como a Jupiter?',
            'A cotação não vem da Jupiter.',
            'A cotação de Jupiter não é confirmada.',
            'Jupiter não é fonte de cotação.',
            'O usuário perguntou se a cotação viria de Jupiter.',
            'Você mencionou Jupiter como fonte de cotação; a base não confirma isso.',
            'A documentação não lista Jupiter como fonte de cotação.',
            'Não há confirmação de que a cotação venha da Jupiter.',
            'A confirmação não é feita por assinatura na carteira.',
            'Não posso confirmar que a confirmação é feita por assinatura na carteira.',
            'A confirmação é feita por assinatura na carteira?',
            'Confira se é necessário assinar antes de confirmar o swap.',
            'Na autenticação, a confirmação é feita por assinatura na carteira.',
            'Nunca compartilhe seed phrase ou chave privada.',
        ):
            with self.subTest(answer=answer):
                self.assertTrue(validate_public_response(
                    answer, official_context=context).allowed)
        quote_source = ('[Contexto oficial: Swap]\n'
                        'As fontes de cotação são 0x para a mesma rede EVM, '
                        'Jupiter para a mesma rede Solana e LI.FI para '
                        'operações entre redes. CoW Protocol não é fonte de '
                        'cotação do fluxo de Swap.')
        for answer in (
            'A cotação pode vir de um provedor como a Jupiter.',
            'LI.FI é fonte de cotação entre redes.',
            'A cotação é fornecida pela 0x para redes EVM.',
        ):
            with self.subTest(answer=answer):
                self.assertTrue(validate_public_response(
                    answer, official_context=quote_source).allowed)
        self.assertEqual(validate_public_response(
            'CoW Protocol é fonte de cotação para swaps.',
            official_context=quote_source).reason, 'unsupported_named_quote_source')
        fee_only = ('[Contexto oficial: Taxas Solana, Jupiter e LI.FI]\n'
                    'Na Jupiter, a cobrança varia conforme o par.')
        self.assertTrue(validate_public_response(
            'Na Jupiter, a taxa varia e a cotação pode mudar.',
            official_context=fee_only).allowed)
        self.assertEqual(validate_public_response(
            'A cotação vem da Jupiter.', official_context=fee_only).reason,
            'unsupported_named_quote_source')
        signature_source = ('[Contexto oficial: Confirmação de swaps]\n'
                            'No swap, a confirmação é feita por assinatura na carteira.')
        self.assertTrue(validate_public_response(
            'A confirmação é feita por assinatura na carteira.',
            official_context=signature_source).allowed)
        for reason in ('unsupported_named_quote_source',
                       'unsupported_swap_confirmation_signature'):
            with self.subTest(reason=reason):
                fallback = public_fallback_for(reason, official_context=context)
                self.assertTrue(validate_public_response(
                    fallback, official_context=context).allowed)

    def test_normative_seed_rule_is_not_an_absolute_future_promise(self):
        normative = ('[Contexto oficial: Swaps e pontes]\n'
                     'A Z-SWAP nunca deve pedir seed phrase ou chave privada '
                     'para concluir uma operação.')
        for answer in (
            'A Z-SWAP nunca vai pedir sua seed phrase ou chave privada.',
            'A Z-SWAP jamais pedirá sua chave privada.',
            'A plataforma nunca irá solicitar sua seed phrase.',
            'E nunca será pedida sua seed phrase ou chave privada.',
            'Sua seed phrase nunca será solicitada.',
            'Sua chave privada jamais vai ser pedida.',
        ):
            with self.subTest(answer=answer):
                self.assertEqual(validate_public_response(
                    answer, official_context=normative).reason,
                    'unsupported_absolute_seed_promise')
        for answer in (
            'A Z-SWAP nunca deve pedir seed phrase ou chave privada.',
            'Não compartilhe sua seed phrase ou chave privada.',
            'A Z-SWAP nunca vai pedir sua seed phrase?',
            'Sua seed phrase nunca será solicitada?',
            'Não posso garantir que a Z-SWAP nunca vai pedir sua seed phrase.',
            'Não posso garantir que sua seed phrase nunca será solicitada.',
            'O usuário perguntou: "A Z-SWAP nunca vai pedir minha seed phrase?"',
            'O usuário perguntou: "Minha seed phrase nunca será pedida?"',
        ):
            with self.subTest(answer=answer):
                self.assertTrue(validate_public_response(
                    answer, official_context=normative).allowed)
        explicit_future = ('[Contexto oficial: Política pública]\n'
                           'A Z-SWAP nunca vai pedir sua seed phrase. '
                           'Sua chave privada jamais será solicitada.')
        self.assertTrue(validate_public_response(
            'A Z-SWAP nunca vai pedir sua seed phrase.',
            official_context=explicit_future).allowed)
        self.assertTrue(validate_public_response(
            'Sua chave privada jamais será solicitada.',
            official_context=explicit_future).allowed)
        fallback = public_fallback_for('unsupported_absolute_seed_promise',
                                       official_context=normative)
        self.assertTrue(validate_public_response(
            fallback, official_context=normative).allowed)

    def test_wallet_connection_is_not_equated_with_authentication_signature(self):
        context = KnowledgeTools(KnowledgeBase(
            Path(__file__).resolve().parents[1] / 'knowledge')).call(
                'search_approved_knowledge',
                {'query': 'n consigo conecta carteira'}, agent_id='eir').render()
        self.assertIn('[Contexto oficial: Segurança de autenticação]', context)
        self.assertIn('SIWE', context)
        for answer in (
            'A conexão acontece só com assinatura dentro da sua própria carteira.',
            'Para conectar sua carteira, basta assinar uma mensagem.',
            'Sua carteira se conecta somente por assinatura.',
            'Só com assinatura é possível conectar a carteira.',
            'A carteira só se conecta com uma assinatura.',
            'Você não consegue conectar sem assinar.',
            'Para conectar a carteira, é obrigatório assinar uma mensagem.',
            'A conexão não acontece só com assinatura, mas a carteira só se '
            'conecta com uma assinatura.',
            "'A conexão acontece só com assinatura' foi sua dúvida, mas "
            'a carteira só se conecta com uma assinatura.',
            'Toda carteira precisa de uma assinatura para se conectar.',
            'Você só consegue usar a carteira depois de assinar uma mensagem.',
        ):
            with self.subTest(answer=answer):
                self.assertEqual(validate_public_response(
                    answer, official_context=context).reason,
                    'unsupported_wallet_connection_signature')
        for answer in (
            'Para autenticar carteiras EVM, a base documenta SIWE.',
            'Na Solana, a autenticação usa assinatura de mensagem.',
            'Conecte sua carteira e, para autenticar, assine uma mensagem.',
            'Não posso confirmar que toda conexão ocorre só por assinatura.',
            'A conexão não acontece só com assinatura.',
            'Você perguntou se a conexão ocorre só por assinatura; '
            'a base pública não confirma isso.',
            '"A conexão acontece só com assinatura" foi sua pergunta; '
            'a base pública não confirma isso.',
            'Qual carteira, rede e mensagem de erro aparecem? '
            'Não compartilhe seed phrase ou chave privada.',
            'A conexão não exige assinatura.',
            'Não posso confirmar que você não consegue conectar sem assinar.',
            'Você perguntou se para conectar a carteira é obrigatório assinar.',
            "'A conexão acontece só com assinatura' foi sua dúvida; "
            'a base não confirma isso.',
            'Toda carteira precisa de uma assinatura para se conectar?',
            'Não posso confirmar que toda carteira precisa de uma assinatura para se conectar.',
            'Você só consegue usar a carteira depois de assinar uma mensagem?',
        ):
            with self.subTest(answer=answer):
                self.assertTrue(validate_public_response(
                    answer, official_context=context).allowed)
        explicit_connection_source = (
            '[Contexto oficial: Conexão de carteira]\n'
            'A conexão da carteira acontece só com assinatura dentro da carteira.')
        self.assertTrue(validate_public_response(
            'A conexão da carteira acontece só com assinatura dentro da carteira.',
            official_context=explicit_connection_source).allowed)
        negative_connection_source = (
            '[Contexto oficial: Conexão de carteira]\n'
            'Não é verdade que a conexão só acontece com assinatura.')
        self.assertEqual(validate_public_response(
            'A conexão só acontece com assinatura.',
            official_context=negative_connection_source).reason,
            'unsupported_wallet_connection_signature')

    def test_wallet_brand_examples_require_retrieved_public_evidence(self):
        context = KnowledgeTools(KnowledgeBase(
            Path(__file__).resolve().parents[1] / 'knowledge')).call(
                'search_approved_knowledge',
                {'query': 'n consigo conecta carteira'}, agent_id='eir').render()
        for brand in ('MetaMask', 'Phantom', 'Rabby'):
            self.assertNotIn(brand.casefold(), context.casefold())
            answer = f'Qual carteira você está tentando conectar (por exemplo {brand})?'
            with self.subTest(brand=brand):
                self.assertEqual(validate_public_response(
                    answer, official_context=context).reason,
                    'unapproved_wallet_example')
        self.assertEqual(validate_public_response(
            'Qual carteira você usa, MetaMask, Phantom ou Rabby?',
            official_context=context).reason, 'unapproved_wallet_example')
        self.assertEqual(validate_public_response(
            'A Z-SWAP suporta Phantom.',
            official_context=context).reason, 'unapproved_wallet_example')
        self.assertEqual(validate_public_response(
            'Z-SWAP supports MetaMask.',
            official_context=context).reason, 'unapproved_wallet_example')
        for answer in (
            'Tente conectar usando MetaMask.',
            'A Z-SWAP tem integração com MetaMask.',
            'O app suporta Phantom.',
            'A plataforma sugere MetaMask.',
            'Você pode conectar MetaMask à Z-SWAP.',
            'MetaMask funciona na Z-SWAP.',
            'Que tal MetaMask?',
            'Você perguntou se a Z-SWAP suporta Phantom, mas a plataforma suporta Phantom.',
            'Não use MetaMask, mas tente conectar usando Phantom.',
        ):
            with self.subTest(answer=answer):
                self.assertEqual(validate_public_response(
                    answer, official_context=context).reason,
                    'unapproved_wallet_example')
        self.assertTrue(validate_public_response(
            'Qual carteira você usa e qual erro aparece?',
            official_context=context).allowed)
        official_wallet_source = (
            '[Contexto oficial: Carteiras suportadas]\n'
            'MetaMask, Phantom e Rabby aparecem como carteiras suportadas.')
        self.assertTrue(validate_public_response(
            'Qual carteira você usa, MetaMask, Phantom ou Rabby?',
            official_context=official_wallet_source).allowed)
        for misleading_source in (
            '[Contexto oficial: Carteiras]\nPhantom não é suportada.',
            '[Contexto oficial: Carteiras suportadas]\nPhantom não é suportada.',
            '[Contexto oficial: Carteiras]\nPhantom é suportada?',
            '[Contexto oficial: Carteiras]\nPhantom é citada como exemplo.',
            '[Contexto oficial: Carteiras suportadas]\nPhantom é citada como exemplo.',
        ):
            with self.subTest(source=misleading_source):
                self.assertEqual(validate_public_response(
                    'A Z-SWAP suporta Phantom.',
                    official_context=misleading_source).reason,
                    'unapproved_wallet_example')
        self.assertTrue(validate_public_response(
            'Você perguntou se Phantom funciona; a base pública não confirma.',
            official_context=context).allowed)
        self.assertTrue(validate_public_response(
            'Não posso confirmar que a Z-SWAP suporta Phantom.',
            official_context=context).allowed)
        self.assertTrue(validate_public_response(
            'Z-SWAP does not support MetaMask.',
            official_context=context).allowed)
        self.assertTrue(validate_public_response(
            '"A Z-SWAP suporta Phantom?" foi sua pergunta; '
            'não tenho confirmação pública.',
            official_context=context).allowed)
        for answer in (
            'A Z-SWAP suporta MetaMask?',
            'Você perguntou se pode conectar MetaMask; a base não confirma.',
            'Não posso confirmar que você pode conectar MetaMask.',
            "'A Z-SWAP suporta Phantom?' foi sua pergunta; "
            'não tenho confirmação pública.',
            'Não use MetaMask; diga apenas a mensagem de erro.',
        ):
            with self.subTest(answer=answer):
                self.assertTrue(validate_public_response(
                    answer, official_context=context).allowed)
        self.assertTrue(validate_public_response(
            'Não preciso de sua seed phrase para ajudar com a conexão.',
            official_context=context).allowed)

    def test_wallet_guard_bounded_on_large_disjoint_token_blocks(self):
        # The pre-fix three-way cross product stalls for minutes at this size.
        answer = ('conectar ' * 790) + ('só ' * 790) + ('assinar ' * 790)
        self.assertGreater(len(answer), 15000)
        self.assertLess(len(answer), 16000)
        start = perf_counter()
        check = validate_public_response(answer, official_context='')
        elapsed = perf_counter() - start
        self.assertTrue(check.allowed)
        self.assertLess(elapsed, 10.0)

    def test_wallet_guard_fallback_triages_without_unsupported_details(self):
        for reason in ('unsupported_wallet_connection_signature',
                       'unapproved_wallet_example'):
            reply = public_fallback_for(reason,
                question='n consigo conecta carteira', official_context='')
            self.assertIn('carteira', reply.lower())
            self.assertIn('erro', reply.lower())
            self.assertNotIn('Phantom', reply)
            self.assertNotIn('só com assinatura', reply)
            self.assertTrue(validate_public_response(reply, official_context='').allowed)

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

    def test_single_and_two_tier_evm_rates_match_retrieved_public_sections(self):
        knowledge = KnowledgeBase(Path(__file__).resolve().parents[1] / 'knowledge')
        tools = KnowledgeTools(knowledge)
        context = tools.call('search_approved_knowledge',
                             {'query': 'Quais as taxas EVM dos planos?'},
                             agent_id='zion').render()
        self.assertIn('[Contexto oficial: Plano Free ou Thrall]', context)
        self.assertIn('[Contexto oficial: Plano Pro ou profissional]', context)
        for answer in (
            'No Free, a taxa EVM é 9%.',
            'No Free, a taxa EVM é 0,50%.',
            'A taxa EVM de 0,50% no plano Free é a mesma do Pro.',
            'A taxa EVM de 9% é do Free.',
            'A taxa EVM é de 9% para quem está no Free.',
            'Nas rotas EVM, Free paga 1% e Pro paga 9%.',
            '9% no plano Free EVM.',
            'Não, o Free não cobra 9%; a taxa EVM é 8%.',
        ):
            with self.subTest(answer=answer):
                self.assertEqual(validate_public_response(
                    answer, official_context=context).reason,
                    'incomplete_plan_fee_matrix')
        for answer in (
            'No Free, a taxa EVM é 1%.',
            'A taxa EVM é de 1% para quem está no Free.',
            'No Pro, a taxa EVM é 0,50%.',
            'Não, o Free não cobra 9%; a taxa EVM é 1%.',
            'O Free não cobra 9% de taxa EVM.',
            'O Free não é gratuito e cobra 1% de taxa EVM.',
            'Nas rotas EVM, Free 1% e Pro 0,50%.',
            'Na Solana, Free 7%, mas em EVM Free 1%.',
            'Em EVM, Free 1%; na Solana, Free 7%.',
        ):
            with self.subTest(answer=answer):
                self.assertTrue(validate_public_response(
                    answer, official_context=context).allowed)
        free_only = tools.call('search_approved_knowledge',
                               {'query': 'Quanto paga de platform fee EVM no Free?'},
                               agent_id='zion').render()
        self.assertIn('[Contexto oficial: Plano Free ou Thrall]', free_only)
        self.assertTrue(validate_public_response(
            'No Free, a taxa EVM é 1%.', official_context=free_only).allowed)
        self.assertEqual(validate_public_response(
            'No Pro, a taxa EVM é 0,50%.', official_context=free_only).reason,
            'incomplete_plan_fee_matrix')

    def test_written_out_evm_plan_fee_is_bounded_by_public_rate(self):
        knowledge = KnowledgeBase(Path(__file__).resolve().parents[1] / 'knowledge')
        context = KnowledgeTools(knowledge).call(
            'search_approved_knowledge',
            {'query': 'Quanto paga de platform fee EVM no Free?'},
            agent_id='zion').render()
        self.assertIn('[Contexto oficial: Plano Free ou Thrall]', context)
        for answer in (
            'No Free, a taxa em EVM é nove por cento.',
            'A taxa EVM é nove por cento para quem está no Free.',
            'No Free, a taxa em EVM é quatorze por cento.',
        ):
            with self.subTest(answer=answer):
                self.assertEqual(validate_public_response(
                    answer, official_context=context).reason,
                    'unsupported_spelled_plan_fee')
        self.assertEqual(validate_public_response(
            'No Free, a taxa em EVM é um por cento.',
            official_context='').reason, 'unsupported_spelled_plan_fee')
        for answer in (
            'No Free, a taxa em EVM é um por cento.',
            'O progresso da pesquisa aumentou nove por cento.',
            'No Free, a taxa EVM é 1%. O progresso aumentou nove por cento.',
            'No Free, a taxa EVM é baixa, e o progresso cresceu nove por cento.',
            'No Free, a taxa EVM é um por cento, e o progresso cresceu nove por cento.',
        ):
            with self.subTest(answer=answer):
                self.assertTrue(validate_public_response(
                    answer, official_context=context).allowed)
        reply = public_fallback_for('unsupported_spelled_plan_fee',
                                    question='Qual é a taxa EVM do Free?',
                                    official_context=context)
        self.assertIn('plano Free é 1,00%', reply)
        self.assertIn('rotas EVM suportadas onde a cobrança está ativa', reply)
        self.assertTrue(validate_public_response(reply, official_context=context).allowed)
        without_free_heading = context.replace(
            '[Contexto oficial: Plano Free ou Thrall]',
            '[Contexto oficial: Outra seção]')
        self.assertNotIn('1,00%', public_fallback_for(
            'unsupported_spelled_plan_fee', question='Qual é a taxa EVM do Free?',
            official_context=without_free_heading))
        self.assertNotIn('1,00%', public_fallback_for(
            'unsupported_spelled_plan_fee', question='Qual é a taxa EVM do Pro?',
            official_context=context))
        all_plans = KnowledgeTools(knowledge).call(
            'search_approved_knowledge', {'query': 'Quais as taxas EVM dos planos?'},
            agent_id='zion').render()
        complete_reply = public_fallback_for(
            'unsupported_spelled_plan_fee', question='Quais as taxas EVM dos planos?',
            official_context=all_plans)
        for expected in ('Free 1,00%', 'Pro 0,50%', 'Trader 0,25%', 'Pilot 0,10%'):
            self.assertIn(expected, complete_reply)
        self.assertTrue(validate_public_response(
            complete_reply, official_context=all_plans).allowed)
        self.assertTrue(validate_public_response(
            'No Free, a taxa EVM é um por cento, e o Pro é meio por cento.',
            official_context=all_plans).allowed)
        self.assertEqual(validate_public_response(
            'No Free, a taxa EVM é um por cento, e o Pro é nove por cento.',
            official_context=all_plans).reason, 'unsupported_spelled_plan_fee')

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

    def test_solana_fee_fallback_uses_complete_public_section_values(self):
        section = (
            '[Contexto oficial: Taxas Solana, Jupiter e LI.FI]\n'
            'Desde 16 de outubro de 2026, as rotas Solana elegíveis usam a mesma escada '
            'de platform fee: Free/Thrall 7%, Pro/Drengr 6%, Trader/Berserkr 5% '
            'e Pilot/Einherjar 4%.\n\n'
            'Na Jupiter, essa cobrança se aplica quando USDC ou SOL é um dos lados do swap. '
            'Na Jupiter, outros pares Solana não têm platform fee da Z-SWAP. '
            'As rotas LI.FI saindo da Solana são tratadas separadamente e não seguem '
            'essa condição de par. Se a conta de recebimento da taxa estiver '
            'indisponível, o swap prossegue sem a platform fee da Z-SWAP.\n\n'
            'Isso não significa operação sem custo: rede, DEX, agregador, bridge ou '
            'exchange podem cobrar separadamente. Confira os custos apresentados '
            'para a rota antes de confirmar.'
        )
        context = '[Contexto oficial: Outro tema]\nSem política de taxa.\n\n' + section
        answer = public_fallback_for('overbroad_solana_fee_scope',
                                     official_context=context)
        self.assertIn('Free/Thrall 7%', answer)
        self.assertIn('Pilot/Einherjar 4%', answer)
        self.assertIn('outros pares na Jupiter não têm essa taxa', answer)
        self.assertIn('LI.FI saindo da Solana são tratadas separadamente', answer)
        self.assertNotIn('Sem política de taxa', answer)
        self.assertIn('não posso dizer se a Z-SWAP cobra mais ou menos', answer)
        self.assertTrue(validate_public_response(answer, official_context=context).allowed)

        conservative = public_fallback_for('overbroad_solana_fee_scope')
        for invalid in (
            section.replace('Pilot/Einherjar 4%', 'Pilot/Einherjar'),
            section.replace('Na Jupiter, outros pares', 'Outros pares'),
            section.replace('são tratadas separadamente', 'seguem a mesma condição'),
            section.replace('Confira os custos apresentados para a rota antes de confirmar.', ''),
            section.replace('[Contexto oficial: Taxas Solana, Jupiter e LI.FI]',
                            '[Contexto oficial: Outro tema]'),
        ):
            with self.subTest(invalid=invalid[-80:]):
                self.assertEqual(public_fallback_for(
                    'overbroad_solana_fee_scope', official_context=invalid), conservative)
        self.assertEqual(public_fallback_for('best_price_guarantee',
            official_context=context), public_fallback_for('best_price_guarantee'))

    def test_bridge_costs_do_not_assume_universal_platform_fee(self):
        # The public source mentions third-party costs, but only in a section
        # that first limits where the Z-SWAP platform fee applies.
        context = (
            '[Contexto oficial: Plano Free ou Thrall]\n'
            'A platform fee nas rotas EVM suportadas onde o mecanismo está ativo '
            'é 1,00%. Custos de rede e terceiros podem existir além da platform fee.\n\n'
            '[Contexto oficial: Taxas Solana, Jupiter e LI.FI]\n'
            'Na Jupiter, a cobrança se aplica quando USDC ou SOL é um dos lados '
            'do swap. Rotas LI.FI saindo da Solana são tratadas separadamente. '
            'Se a conta de recebimento estiver indisponível, o swap prossegue '
            'sem a platform fee da Z-SWAP.'
        )
        unsupported = (
            'Um ponto importante: nem todo par de redes e tokens tem rota disponível '
            'o tempo todo, e custos de rede, bridge ou terceiros podem existir '
            'além da platform fee.',
            'Custos de rede e terceiros podem surgir além da platform fee.',
            'Numa bridge, os custos de rede vêm além da taxa da plataforma.',
            'Fora a taxa da Z-SWAP, você pode pagar a bridge.',
            'Toda bridge paga platform fee.',
            'Qualquer swap tem taxa da plataforma.',
            'A platform fee sempre incide em cada rota.',
            'A Z-SWAP cobra platform fee em todas as bridges.',
            'Sempre há taxa da plataforma nas bridges.',
            'Todas as bridges incluem a taxa da plataforma.',
            'A platform fee é aplicada a qualquer bridge.',
            'The platform fee applies on every bridge.',
            'Os custos de bridge são cobrados por cima da taxa da plataforma.',
            'A taxa da plataforma entra no total de todas as pontes.',
            'A taxa da plataforma se soma ao gas de cada bridge.',
            'Nas pontes, sempre há duas taxas: da rede e da Z-SWAP.',
            'A cobrança da Z-SWAP vale para todos os swaps.',
            'Every cross-chain route includes the Z-SWAP platform fee.',
            'Há platform fee em toda bridge.',
            'Em qualquer bridge há platform fee.',
            'Sempre existe platform fee nas bridges.',
            'The platform fee is charged for all bridges.',
            'Across every bridge, the platform fee applies.',
            'Custos da rede se somam à platform fee.',
            'Custos da rede somam-se à taxa da plataforma.',
            'A Z-SWAP cobra taxa em toda bridge.',
            'A Z-SWAP sempre cobra sua taxa em bridges.',
            'A taxa da Z-SWAP é cobrada sempre que houver bridge.',
            'Em todas as pontes, uma platform fee se aplica.',
            'As bridges sempre incluem a platform fee.',
            'There is always a platform fee on bridges.',
            'Network gas comes on top of the platform fee.',
            'Bridge fees are in addition to the platform fee.',
            'Custos de rede são adicionais à taxa da plataforma.',
            'Nas rotas EVM suportadas onde o mecanismo está ativo há cobrança, '
            'e em todas as demais bridges os custos da rede vêm além da platform fee.',
        )
        for answer in unsupported:
            with self.subTest(answer=answer):
                self.assertEqual(validate_public_response(
                    answer, official_context=context).reason,
                    'overbroad_platform_fee')
        allowed = (
            'Custos de rede e terceiros podem existir mesmo quando a platform fee não incide.',
            'Custos de rede podem existir além da platform fee, quando aplicável.',
            'Quando a taxa da plataforma for aplicável, custos de rede podem '
            'existir além da taxa da plataforma.',
            'Nas rotas EVM suportadas onde o mecanismo está ativo, custos de '
            'terceiros podem existir além da platform fee.',
            'Na Jupiter, se a taxa da plataforma for aplicável, custos de '
            'rede podem existir além da platform fee.',
            'Na rota em que a cobrança está ativa, custos de terceiros podem '
            'existir além da platform fee.',
            'Custos externos podem existir além da platform fee quando ela for cobrada.',
            'Se aplicável, custos de rede podem existir além da platform fee.',
            'Se a rota cobrar a platform fee, custos externos podem existir '
            'além da platform fee.',
            'Além da taxa da plataforma, se houver, podem existir custos de rede.',
            'Nas rotas em que a cobrança incide, custos de rede podem existir '
            'além da platform fee.',
            'Custos de rede podem existir além da platform fee na rota EVM '
            'se o mecanismo estiver ativo.',
            'Na rota EVM com mecanismo ativo, os custos externos existem '
            'além da platform fee.',
            'Custos externos podem existir além da platform fee na rota aplicável.',
            'Quando aplicável, os custos de rede se somam à taxa da plataforma.',
            'Nas rotas EVM suportadas com mecanismo ativo, custos de rede vêm '
            'além da platform fee.',
            'Nas rotas elegíveis, custos externos podem existir além da taxa '
            'da plataforma.',
            'Além da platform fee, quando houver, pode existir custo de rede.',
            'Se houver platform fee; os custos da bridge vêm além da platform fee.',
            'A platform fee não incide em todas as rotas.',
            'Nem toda bridge paga platform fee.',
            'Toda bridge paga platform fee?',
            'Você perguntou: "Toda bridge paga platform fee?" Não posso '
            'confirmar isso de modo geral.',
            'Você perguntou: "Custos de rede podem existir além da platform fee?" '
            'Depende da rota e da cobrança aplicável.',
            'Não é verdade que custos externos existam além da platform fee '
            'em toda rota.',
            'Não devemos assumir que custos externos existam além da platform fee '
            'em toda rota.',
            'A frase ‘Toda bridge paga platform fee’ está incorreta.',
            'A ideia de que toda bridge cobra platform fee é falsa.',
            'It is incorrect to say that every bridge pays a platform fee.',
            'Não assuma que custos de rede vêm além da platform fee em todas as rotas.',
        )
        for answer in allowed:
            with self.subTest(answer=answer):
                self.assertTrue(validate_public_response(
                    answer, official_context=context).allowed)
        fallback = public_fallback_for('overbroad_platform_fee')
        self.assertIn('quando a taxa da plataforma não incide', fallback)
        self.assertTrue(validate_public_response(
            fallback, official_context=context).allowed)

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
        source_reply = public_fallback_for('missing_feature_status', official_context=context)
        self.assertIn('Terminal Pro está em beta', source_reply)
        self.assertIn('Portfolio está parcialmente disponível', source_reply)
        self.assertIn('Orders está parcialmente disponível', source_reply)
        self.assertTrue(validate_public_response(source_reply, official_context=context).allowed)
        self.assertNotIn('Portfolio', public_fallback_for(
            'missing_feature_status', official_context='Terminal Pro está em beta.'))

    def test_terminal_beta_does_not_become_broad_public_production(self):
        knowledge = KnowledgeBase(Path(__file__).resolve().parents[1] / 'knowledge')
        context = KnowledgeTools(knowledge).call(
            'search_approved_knowledge', {'query': 'Qual o estado do Terminal Pro?'},
            agent_id='zion').render()
        self.assertIn('[Contexto oficial: Beta]', context)
        for answer in (
            'O Terminal Pro está em beta. Já está em produção para todos.',
            'O Terminal Pro está em beta e já está em produção para todos.',
            'O Terminal Pro está em beta; ele já está totalmente lançado.',
            'O Terminal Pro está em beta. O recurso foi lançado sem restrições.',
            'O Terminal Pro está em beta, mas já saiu de beta e está disponível sem restrições.',
            'O Terminal Pro está em beta. A fase de testes acabou, versão final.',
        ):
            with self.subTest(answer=answer):
                self.assertEqual(validate_public_response(
                    answer, official_context=context).reason,
                    'missing_feature_status')
        for answer in (
            'O Terminal Pro está disponível em beta para usuários autorizados.',
            'O Terminal Pro está em beta. Já está em produção para todos os participantes do beta.',
            'O Terminal Pro está em beta; a disponibilidade para a sua conta depende do acesso.',
            'O Terminal Pro está em beta. Não está em produção para todos.',
            'O Terminal Pro está em beta. O Swap já está em produção para todos.',
            'O Terminal Pro está em beta. A fase de testes não acabou.',
            'O Terminal Pro está em beta e não saiu de beta.',
            'O Terminal Pro está em beta. O Swap já saiu de beta.',
        ):
            with self.subTest(answer=answer):
                self.assertTrue(validate_public_response(
                    answer, official_context=context).allowed)

    def test_feature_status_does_not_cross_sections_or_invert_negation(self):
        cases = (
            ('[Contexto oficial: Terminal Pro]\nO Terminal Pro oferece gráficos.\n'
             '[Contexto oficial: Produto X]\nO Produto X está em beta.',
             'O Terminal Pro oferece gráficos.', 'Terminal Pro está em beta'),
            ('[Contexto oficial: Terminal Pro]\nO Terminal Pro não está em beta; '
             'o Beta antigo terminou.',
             'O Terminal Pro oferece gráficos.', 'Terminal Pro está em beta'),
            ('[Contexto oficial: Portfolio]\nPortfolio agrega saldos.\n'
             '[Contexto oficial: Produto X]\nO Produto X está parcialmente disponível.',
             'Portfolio agrega saldos.', 'Portfolio está parcialmente disponível'),
            ('[Contexto oficial: Orders]\nOrders mostra planos.\n'
             '[Contexto oficial: Produto X]\nO Produto X está parcialmente disponível.',
             'Orders mostra planos.', 'Orders está parcialmente disponível'),
            ('[Contexto oficial: Recursos]\nTerminal Pro oferece gráficos e '
             'Produto X está em beta.',
             'O Terminal Pro oferece gráficos.', 'Terminal Pro está em beta'),
            ('[Contexto oficial: Recursos]\nPortfolio agrega saldos e '
             'Produto X está parcialmente disponível.',
             'Portfolio agrega saldos.', 'Portfolio está parcialmente disponível'),
        )
        for context, answer, false_status in cases:
            with self.subTest(false_status=false_status):
                self.assertTrue(validate_public_response(
                    answer, official_context=context).allowed)
                self.assertNotIn(false_status, public_fallback_for(
                    'missing_feature_status', official_context=context))
