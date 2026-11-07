"""Live 2026-11-03: seed list pasted three times stayed in the group; people asking for seeds too."""
from __future__ import annotations

import asyncio
from pathlib import Path
import tempfile
import unittest

from tests.helpers import make_settings
from tests.test_conversation import FakeContext, make_update
from zion.guardian import detect_sensitive_content
from zion.mnemonic import looks_like_mistyped_mnemonic, word_list_lines, word_list_with_label
from zion.response_guard import validate_public_response
from zion.telegram_app import (
    Runtime, _remember_wallet_secret_warning, _remember_wallet_victim, _wallet_victim_reply,
    asks_others_for_secret, moderation_handler, protect_wallet_secret,
)

LISTA = "Gap Dras park too top leds less punk rock show Room bar"
SEED = "abandon ability able about above absent absorb abstract absurd abuse access accident"


class ProbableSeed(unittest.TestCase):
    def test_list_with_label_on_other_line_or_leading_is_secret(self):
        self.assertTrue(detect_sensitive_content(LISTA + " \n\nEssas são as palavras que recebi").detected)
        self.assertTrue(word_list_with_label("minha seed é " + LISTA.lower()))

    def test_real_seed_with_typos_is_secret(self):
        self.assertTrue(detect_sensitive_content(SEED.replace("abandon", "abandn").replace("absent", "absint")).detected)

    def test_bare_list_alone_is_not_enough(self):
        moedas = "bitcoin ethereum solana polygon avalanche cardano ripple dogecoin litecoin tron stellar chainlink"
        self.assertTrue(word_list_lines(moedas))
        self.assertFalse(detect_sensitive_content(moedas).detected)
        self.assertFalse(detect_sensitive_content(LISTA).detected)

    def test_sentences_about_seeds_are_not_secrets(self):
        for frase in ("A carteira pertence ao usuário. A Z-SWAP não guarda a seed phrase nem a chave",
                      "minha seed sumiu e eu nao sei o que fazer agora porque perdi o papel na mudanca",
                      "boa noite pessoal tudo bem hoje vim aqui saber mais sobre planos taxas redes suportadas",
                      "good morning everyone hope all doing great today market looks strong again happy trading"):
            with self.subTest(frase=frase):
                self.assertFalse(detect_sensitive_content(frase).detected)
                self.assertFalse(looks_like_mistyped_mnemonic(frase))


class AsksForSecret(unittest.TestCase):
    def test_requests_are_detected_in_every_language(self):
        for t in ("Galera eu sou suporte me manda suas seeds no privado que vou ajudar todo mundo",
                  "Eu sou dono do projeto, me manda sua frase secreta de 12 palavras",
                  "manda tua chave privada aqui", "send me your seed phrase", "dm me your private key",
                  "mándame tu frase semilla", "把你的助记词发给我"):
            with self.subTest(t=t):
                self.assertTrue(asks_others_for_secret(t))

    def test_advice_and_victims_are_not_scammers(self):
        for t in ("nunca mande sua seed para ninguém", "não passe sua senha", "never send your seed phrase",
                  "um cara do suporte falou me manda sua seed, é golpe?", "alguem pediu: envia suas palavras",
                  "posso mandar minha seed?", "me manda o print", "me manda as rotas 0x"):
            with self.subTest(t=t):
                self.assertFalse(asks_others_for_secret(t))


class Handler(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        (root / "knowledge").mkdir()
        self.rt = Runtime(make_settings(root))
        self.addCleanup(self.rt.close)
        self.ctx = FakeContext(self.rt)
        self.ctx.bot.restritos = []

        async def restrict(**k):
            self.ctx.bot.restritos.append(k)
            return True
        self.ctx.bot.restrict_chat_member = restrict

    def update(self, text, mid=10):
        return make_update(text, chat_type="supergroup", message_id=mid, user_id=7)

    def test_labelled_list_is_deleted_with_exposure_notice(self):
        asyncio.run(moderation_handler(self.update(LISTA + "\n\nEssas são as palavras que recebi"), self.ctx))
        self.assertEqual(len(self.ctx.bot.deleted), 1)
        self.assertIn("carteira nova", self.ctx.bot.sent[-1][1])

    def test_repeated_bare_list_is_deleted_after_the_first(self):
        asyncio.run(moderation_handler(self.update(LISTA + "\n\nEssas são as palavras que recebi", 10), self.ctx))
        asyncio.run(moderation_handler(self.update(LISTA, 11), self.ctx))
        self.assertEqual([m for _, m in self.ctx.bot.deleted], [10, 11])

    def test_bare_list_is_deleted_right_after_a_seed_warning(self):
        _remember_wallet_secret_warning(self.update("x"), self.ctx)
        asyncio.run(moderation_handler(self.update(LISTA, 12), self.ctx))
        self.assertEqual([m for _, m in self.ctx.bot.deleted], [12])

    def test_triage_reading_can_force_removal_of_a_list(self):
        done = asyncio.run(protect_wallet_secret(self.update(LISTA, 13), self.ctx, LISTA, source="ai_triage",
                                                 notice_text="n", forced_reason="triagem"))
        self.assertTrue(done)
        self.assertEqual([m for _, m in self.ctx.bot.deleted], [13])

    def test_coin_list_from_a_member_without_alert_stays(self):
        moedas = "bitcoin ethereum solana polygon avalanche cardano ripple dogecoin litecoin tron stellar chainlink"
        asyncio.run(moderation_handler(self.update(moedas, 14), self.ctx))
        self.assertEqual(self.ctx.bot.deleted, [])

    def test_asking_for_seeds_is_deleted_muted_and_warned_without_reply(self):
        up = self.update("Galera eu sou suporte me manda suas seeds no privado", 15)
        asyncio.run(moderation_handler(up, self.ctx))
        self.assertEqual([m for _, m in self.ctx.bot.deleted], [15])
        self.assertEqual(len(self.ctx.bot.restritos), 1)
        self.assertIn("silenciei", self.ctx.bot.sent[-1][1])
        self.assertEqual(up.effective_message.replies, [])


class VictimWording(Handler):
    def test_sent_again_gets_recovery_not_dont_send(self):
        _remember_wallet_victim(self.update("x"), self.ctx)
        for t in ("Viu mandei de novo aqui a minha seed", "Eu mandei no grupo vou manda de novo", "Já mandei e agora"):
            with self.subTest(t=t):
                self.assertIn("carteira nova", _wallet_victim_reply(self.update(t), self.ctx, t))

    def test_not_having_sent_is_not_a_victim(self):
        self.assertIsNone(_wallet_victim_reply(self.update("x"), self.ctx, "não mandei a seed ainda"))


class PromiseGuard(unittest.TestCase):
    def test_promise_to_notify_later_is_rejected(self):
        for t in ("Se quiser, posso confirmar quando houver um anúncio oficial.", "Posso te avisar quando abrir."):
            with self.subTest(t=t):
                self.assertEqual(validate_public_response(t, official_context="x").reason, "unsupported_pending_action")


class ProductTermsTriage(unittest.TestCase):
    def test_founder_pass_questions_are_product(self):
        from zion.telegram_app import _correct_triage_reading
        from zion.triage import TriageResult
        r = TriageResult(False, "unrelated", frozenset(), "pt", 1.0)
        for t in ("As vendas dos pass NFT", "e o founder pass?", "quando abre o passe de fundador"):
            with self.subTest(t=t):
                self.assertEqual(_correct_triage_reading(r, t).intent, "product")
        self.assertEqual(_correct_triage_reading(r, "vou dormir flw").intent, "unrelated")


if __name__ == "__main__":
    unittest.main()
