"""Financial-outcome and reliability promises must never reach a member.

Found by the production-baseline delivery probe: the guard accepted
"A Z-SWAP garante lucro" and "Os swaps nunca falham" before this rule set.
"""
from __future__ import annotations

from pathlib import Path
import re
import unittest

from zion.knowledge import KnowledgeBase
from zion.response_guard import public_fallback_for, validate_public_response


ROOT = Path(__file__).resolve().parents[1]
CTX = '[Contexto oficial: Swaps]\nA Z-SWAP compara rotas.'
NEW_REASONS = {'financial_return_guarantee', 'absolute_reliability'}

PROMISES = (
    'A Z-SWAP garante lucro em todos os swaps.',
    'Lucro garantido em todo swap.',
    'O rendimento é garantido.',
    'Seu lucro está garantido.',
    'Prometemos rentabilidade de 10% ao mês.',
    'Asseguramos ganhos consistentes.',
    'A valorização é certa.',
    'Os swaps nunca falham.',
    'A plataforma nunca trava.',
    'We guarantee profits on every swap.',
    'Guaranteed returns!',
    'The platform never fails.',
    'It is risk-free.',
    # Negation-shaped bypasses.
    'It not only guarantees profits but more.',
    'Não só garante lucro como também segurança.',
    'Não apenas promete lucro, entrega.',
    'A Z-SWAP não garante segurança, mas garante lucro.',
    'Sem taxas, prometemos lucro.',
    'Nem precisa se preocupar: garantimos lucro.',
    'O passe é uma garantia de valorização.',
    'O APN não é dividendo; é garantia de valorização.',
)

HONEST = (
    'Não há garantia de lucro em nenhuma operação.',
    'Desconfie de quem promete lucro garantido.',
    'Cuidado com golpes que prometem rendimentos altos.',
    'Ninguém garante lucro com criptoativos.',
    'A Z-SWAP não garante lucro; resultados dependem do mercado.',
    'Nenhuma plataforma pode garantir lucro.',
    'Nenhum dos planos promete lucro.',
    'O ZION orienta sem assumir a carteira ou prometer lucro.',
    'A Z-SWAP não promete lucro, retorno garantido ou operação sem risco.',
    'Ele não deve prometer lucro, retorno ou valorização.',
    'Nunca prometemos rentabilidade.',
    'Não prometemos rendimentos.',
    'O lucro não é garantido.',
    'Lucro garantido não existe em cripto.',
    'Sem garantia de lucro, confira os custos.',
    'Nenhuma transação é livre de risco.',
    'We cannot guarantee profits.',
    'There are no guaranteed returns.',
    'Isso não é risk-free.',
    'A equipe dará retorno pelo canal oficial.',
    'O swap falhou? Diga qual rede você usou.',
    'Não é participação societária, dividendo, revenue share, renda passiva, '
    'royalty distribuído, treasury governance, garantia de valorização ou retorno.',
)


class FinancialPromiseGuardTests(unittest.TestCase):
    def test_promises_are_blocked(self):
        for text in PROMISES:
            with self.subTest(text=text):
                self.assertFalse(validate_public_response(text, official_context=CTX).allowed)

    def test_honest_caveats_and_scam_warnings_are_accepted(self):
        for text in HONEST:
            with self.subTest(text=text):
                check = validate_public_response(text, official_context=CTX)
                self.assertTrue(check.allowed, check.reason)

    def test_fallback_is_itself_accepted_and_promises_nothing(self):
        for reason in NEW_REASONS:
            reply = public_fallback_for(reason, official_context=CTX)
            self.assertTrue(validate_public_response(reply, official_context=CTX).allowed)
            self.assertIn('Não posso prometer lucro', reply)

    def test_no_official_knowledge_sentence_trips_the_new_rules(self):
        # The model paraphrases these caveats; blocking them would degrade
        # the honest answer into a generic fallback.
        kb = KnowledgeBase(ROOT / 'knowledge')
        kb.reload()
        flagged = []
        for chunk in kb.chunks:
            text = re.sub(r'\s*\n\s*', ' ', chunk.text)
            for sentence in re.split(r'(?<=[.!?])\s+', text):
                reason = validate_public_response(sentence, official_context=chunk.text).reason
                if sentence.strip() and reason in NEW_REASONS:
                    flagged.append((chunk.authority.filename, sentence[:80]))
        self.assertEqual(flagged, [])


if __name__ == '__main__':
    unittest.main()
