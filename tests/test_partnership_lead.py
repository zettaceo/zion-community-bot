"""Live 2026-11-03 (FREYR, private): partnership lead treated like a FAQ.

"Posso fazer sheel em várias comunidades e agendar AMAs" was read as the $SHELL
token; "vou cobrar 100 dólares" / "vocês vão pagar?" fell into the generic
fallback; "quero falar com alguém real" got "não tenho acesso a contatos",
although a real operator handoff existed (only for a labeled form).
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
import unittest

from tests.test_conversation import make_update
from zion import partnership_lead as pl
from zion.response_guard import repair_public_response
from zion.telegram_app import _freyr_lead_turn


class FakeBot:
    def __init__(self, fail: bool = False):
        self.sent: list[tuple[int, str]] = []
        self.fail = fail

    async def send_message(self, chat_id: int, text: str) -> None:
        if self.fail:
            raise RuntimeError("down")
        self.sent.append((chat_id, text))


class FakeDb:
    def __init__(self):
        self.actions: list[dict] = []

    def record_action(self, **kw) -> None:
        self.actions.append(kw)


def fake_rt(fail: bool = False):
    return SimpleNamespace(
        partnership_leads=pl.LeadWindow(), settings=SimpleNamespace(admin_user_ids={111}),
        primary_bot=FakeBot(fail), db=FakeDb(),
    )


def turn(rt, text: str, n: int, user_id: int = 7728504427):
    update = make_update(text, chat_type="private", message_id=n, user_id=user_id)
    handled = asyncio.run(_freyr_lead_turn(rt, update, text))
    replies = update.effective_message.replies if hasattr(update.effective_message, "replies") else update.effective_message.sent
    return handled, (replies[-1] if replies else None)


class ConversaDe0311(unittest.TestCase):
    def test_replay_completo(self):
        rt = fake_rt()
        ok, r = turn(rt, "Tenho interesse em me tornar parceiro", 1)
        self.assertTrue(ok)
        self.assertIn("que tipo de parceria", r)
        self.assertNotIn("Outro tipo de colaboração", r)

        ok, r = turn(rt, "Posso fazer sheel em várias comunidades e agendar AMAs", 2)
        self.assertTrue(ok)
        self.assertIn("divulgação da Z-SWAP", r)
        self.assertIn("AMAs", r)
        self.assertNotIn("$SHELL", r)
        self.assertNotIn("shell", r.lower())

        self.assertIn("não tem um programa público de divulgação paga", r)

        ok, r = turn(rt, "Eu estou oferecendo meus serviços, de divulgar a plataforma e você me pagam", 3)
        self.assertIn("como serviço pago", r)
        self.assertIn("Não posso confirmar pagamento", r)

        ok, r = turn(rt, "Divulgação em comunidades do telegram", 4)
        self.assertIn("tamanho aproximado da audiência", r)
        self.assertNotIn("Entendi", r)                                    # nada novo: não repete
        self.assertNotIn("não tem um programa público de divulgação paga", r)   # já dito no turno 2

        ok, r = turn(rt, "Eu quero divulgar a plataforma z-swap em minha comunidade, vou cobrar 100 dólares", 5)
        self.assertIn("100 dólares", r)

        ok, r = turn(rt, "Você vai pagar 100 dólares ?", 6)
        self.assertIn("Quer que eu encaminhe?", r)
        self.assertIn("Esse pagamento eu não posso prometer: só a equipe decide.", r)   # resposta direta, curta
        self.assertNotIn("informação oficial suficiente", r)

        ok, r = turn(rt, "Com quem falo, melhor falar com um humano", 7)
        self.assertIn("Posso encaminhar agora para a equipe", r)
        self.assertIn("@carlos", r)
        self.assertEqual(rt.primary_bot.sent, [])          # nada sai sem confirmação

        ok, r = turn(rt, "sim", 8)
        self.assertIn("Encaminhei sua proposta", r)
        self.assertIn("Nenhum valor, pagamento, contrato ou prazo está confirmado", r)
        self.assertEqual(len(rt.primary_bot.sent), 1)
        destino, resumo = rt.primary_bot.sent[0]
        self.assertEqual(destino, 111)
        for trecho in ("@carlos", "divulgação da Z-SWAP", "AMAs", "valor pedido: 100 dólares",
                       "Pediu contato humano: sim", "Decisão humana necessária: SIM"):
            self.assertIn(trecho, resumo)
        self.assertEqual(rt.db.actions[-1]["action_type"], "partnership_handoff")
        self.assertTrue(rt.db.actions[-1]["success"])

        ok, r = turn(rt, "Me encaminha para alguém real, pode ser o dono do projeto", 9)
        self.assertIn("já foi encaminhada", r)
        self.assertEqual(len(rt.primary_bot.sent), 1)      # não repete

    def test_humano_logo_de_cara_pede_o_assunto_antes(self):
        rt = fake_rt()
        ok, r = turn(rt, "quero falar com um humano sobre parceria", 1)
        self.assertTrue(ok)
        self.assertIn("me diga em uma frase qual é a proposta", r)

    def test_recusa_nao_encaminha(self):
        rt = fake_rt()
        turn(rt, "Posso fazer divulgação paga em 3 comunidades, cobro US$ 300", 1)
        ok, r = turn(rt, "não", 2)
        self.assertIn("não encaminhei nada", r)
        self.assertEqual(rt.primary_bot.sent, [])

    def test_canal_fora_e_honesto(self):
        rt = fake_rt(fail=True)
        turn(rt, "Faço divulgação no Telegram, cobro 100 dólares", 1)
        ok, r = turn(rt, "pode encaminhar", 2)
        self.assertIn("Não consegui encaminhar agora", r)
        self.assertFalse(rt.db.actions[-1]["success"])

    def test_pergunta_de_produto_vai_para_a_ia(self):
        rt = fake_rt()
        ok, _ = turn(rt, "Quais são as taxas do plano Pro?", 1)
        self.assertFalse(ok)
        turn(rt, "Quero fazer parceria de divulgação", 2)
        ok, _ = turn(rt, "E quais redes vocês suportam no swap?", 3)
        self.assertFalse(ok)

    def test_ingles_e_espanhol(self):
        rt = fake_rt()
        update = make_update("I can promote Z-SWAP in my Telegram communities, I charge 200 USD", chat_type="private", user_id=5)
        update.effective_user.language_code = "en"
        asyncio.run(_freyr_lead_turn(rt, update, update.effective_message.text))
        r = (getattr(update.effective_message, "replies", None) or update.effective_message.sent)[-1]
        self.assertIn("Got it: you are offering promoting Z-SWAP", r)
        self.assertIn("no public paid-promotion program", r)

    def test_limite_diario_de_encaminhamento(self):
        rt = fake_rt()
        for i, chat in enumerate((10, 20, 30)):
            u1 = make_update("faço divulgação paga, cobro 50 dólares", chat_type="private", user_id=9, message_id=i * 10 + 1)
            u1.effective_chat.id = chat
            asyncio.run(_freyr_lead_turn(rt, u1, u1.effective_message.text))
            u2 = make_update("sim", chat_type="private", user_id=9, message_id=i * 10 + 2)
            u2.effective_chat.id = chat
            asyncio.run(_freyr_lead_turn(rt, u2, "sim"))
        self.assertEqual(len(rt.primary_bot.sent), pl.MAX_FORWARDS_PER_DAY)


class ListaDanificada(unittest.TestCase):
    def test_lista_que_perde_item_some_inteira_com_a_introducao(self):
        texto = ("O primeiro passo é entender melhor o seu projeto ou iniciativa e o objetivo da conversa.\n\n"
                 "Para começar, qual é o tipo de parceria que você está considerando? Por exemplo:\n"
                 "• Swap integrado com garantia de volume diário.\n"
                 "• Integração de carteira garantida em 2 semanas.\n"
                 "• Outro tipo de colaboração (especifique).\n\n"
                 "Também é importante saber qual é o objetivo principal dessa parceria, para direcionar a avaliação.")
        reparado = repair_public_response(texto, official_context="", reason="unverified_claim")
        if reparado is not None:
            self.assertNotIn("Outro tipo de colaboração", reparado)
            self.assertNotIn("Por exemplo:", reparado)


if __name__ == "__main__":
    unittest.main()
