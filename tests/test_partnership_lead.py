"""Private agents must handle questions nobody scripted (live FREYR, 2026-11-03).

The 03/11 conversation failed for structural reasons, not for a missing phrase
rule: the private path sent the model NO history, the FREYR prompt FORBADE
offering a handoff, and the real operator handoff only fired for a labeled
form. Now the model answers every turn with history + the system's memory +
the real capability; code owns only memory, real actions and verification.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
import unittest

from tests.test_conversation import make_update
from zion import partnership_lead as pl
from zion.agents import AgentId
from zion.response_guard import (HANDOFF_CAPABILITY, offers_human_handoff, repair_public_response,
                                 validate_public_response)
from zion.telegram_app import _dm_handoff_action, _dm_model_reply


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


class ScriptedAI:
    """Stands in for the model: returns scripted replies and records what it was given."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls: list[dict] = []

    async def answer(self, **kw):
        self.calls.append(kw)
        return SimpleNamespace(text=self.replies.pop(0))


def fake_rt(replies=(), *, fail=False, admins=frozenset({111})):
    return SimpleNamespace(
        partnership_leads=pl.LeadWindow(), settings=SimpleNamespace(admin_user_ids=set(admins)),
        primary_bot=FakeBot(fail), db=FakeDb(), ai=ScriptedAI(replies), dm_exchanges={}, dm_languages={},
    )


def turn(rt, text, n, agent=AgentId.FREYR, user_id=7728504427):
    update = make_update(text, chat_type="private", message_id=n, user_id=user_id)
    if asyncio.run(_dm_handoff_action(rt, update, text, agent)):
        return update.effective_message.replies[-1]
    return asyncio.run(_dm_model_reply(rt, update, text, agent))


OFERTA = ("Entendi: você oferece divulgação paga da Z-SWAP em comunidades do Telegram e AMAs. "
          "Eu não aprovo valores nem pagamentos; quem decide é a equipe. Quer que eu encaminhe sua proposta para a equipe?")


class MemoriaECapacidade(unittest.TestCase):
    def test_o_modelo_recebe_historico_memoria_e_capacidade(self):
        rt = fake_rt(["Que tipo de parceria você tem em mente?", OFERTA])
        turn(rt, "Tenho interesse em me tornar parceiro", 1)
        turn(rt, "Posso fazer sheel em várias comunidades e agendar AMAs, cobro 100 dólares", 2)
        segunda = rt.ai.calls[1]
        self.assertIn("Tenho interesse em me tornar parceiro", segunda["conversation_context"])   # histórico
        self.assertIn("Que tipo de parceria", segunda["conversation_context"])                 # e a própria resposta
        self.assertIn("valor pedido: 100 dólares", segunda["conversation_context"])            # memória do sistema
        self.assertEqual(segunda["capabilities"], HANDOFF_CAPABILITY)

    def test_sem_admins_nao_ha_capacidade(self):
        rt = fake_rt(["ok"], admins=frozenset())
        turn(rt, "quero falar com um humano", 1)
        self.assertIsNone(rt.ai.calls[0]["capabilities"])


class EncaminhamentoReal(unittest.TestCase):
    def test_oferta_do_modelo_mais_sim_encaminha_de_verdade(self):
        rt = fake_rt([OFERTA, "Sua proposta já está com a equipe; se houver interesse, eles falam com você."])
        r = turn(rt, "Posso fazer sheel em várias comunidades e agendar AMAs, cobro 100 dólares", 1)
        self.assertEqual(r, OFERTA)
        self.assertEqual(rt.primary_bot.sent, [])                     # nada sai sem confirmação
        r = turn(rt, "sim", 2)
        self.assertIn("Encaminhei sua proposta", r)
        self.assertEqual(len(rt.primary_bot.sent), 1)
        resumo = rt.primary_bot.sent[0][1]
        for trecho in ("@carlos", "divulgação da Z-SWAP", "AMAs", "valor pedido: 100 dólares", "Decisão humana necessária: SIM"):
            self.assertIn(trecho, resumo)
        self.assertTrue(rt.db.actions[-1]["success"])
        # depois do envio, pedir de novo recebe o ESTADO REAL, sem modelo e sem reenviar
        chamadas = len(rt.ai.calls)
        r = turn(rt, "Me encaminha para alguém real, pode ser o dono", 3)
        self.assertIn("já foi encaminhada", r)
        self.assertEqual(len(rt.ai.calls), chamadas)
        # pergunta livre depois do envio: o modelo sabe que já foi e não tem mais a capacidade
        turn(rt, "e em quanto tempo eles costumam responder?", 4)
        ultima = rt.ai.calls[-1]
        self.assertIsNone(ultima["capabilities"])
        self.assertIn("JÁ ENVIADO", ultima["conversation_context"])
        self.assertEqual(len(rt.primary_bot.sent), 1)

    def test_sem_oferta_sim_nao_encaminha(self):
        rt = fake_rt(["As taxas do plano Pro são 0,50% em EVM.", "Pode perguntar."])
        turn(rt, "Quais as taxas do plano Pro?", 1)
        turn(rt, "sim", 2)
        self.assertEqual(rt.primary_bot.sent, [])

    def test_recusa(self):
        rt = fake_rt([OFERTA])
        turn(rt, "Faço divulgação paga no Telegram por 100 dólares", 1)
        r = turn(rt, "não", 2)
        self.assertIn("não encaminhei nada", r)
        self.assertEqual(rt.primary_bot.sent, [])

    def test_canal_fora_e_honesto(self):
        rt = fake_rt([OFERTA], fail=True)
        turn(rt, "Faço divulgação paga no Telegram por 100 dólares", 1)
        r = turn(rt, "pode encaminhar", 2)
        self.assertIn("Não consegui encaminhar agora", r)
        self.assertFalse(rt.db.actions[-1]["success"])

    def test_qualquer_agente_encaminha_pedido_de_humano(self):
        oferta_eir = "Entendo. Posso encaminhar seu caso para a equipe humana de suporte. Quer que eu encaminhe?"
        rt = fake_rt([oferta_eir])
        turn(rt, "meu swap não chegou e quero falar com um atendente humano", 1, agent=AgentId.EIR)
        turn(rt, "sim", 2, agent=AgentId.EIR)
        self.assertEqual(len(rt.primary_bot.sent), 1)
        self.assertIn("EIR — PEDIDO DE ATENDIMENTO HUMANO", rt.primary_bot.sent[0][1])
        self.assertIn("meu swap não chegou", rt.primary_bot.sent[0][1])

    def test_limite_diario(self):
        rt = fake_rt([OFERTA] * 4)   # o 3º "sim" volta ao modelo: sem capacidade, nada a confirmar
        for i, chat in enumerate((10, 20, 30)):
            for n, t in ((1, "faço divulgação paga, cobro 50 dólares"), (2, "sim")):
                u = make_update(t, chat_type="private", user_id=9, message_id=i * 10 + n)
                u.effective_chat.id = chat
                if not asyncio.run(_dm_handoff_action(rt, u, t, AgentId.FREYR)):
                    asyncio.run(_dm_model_reply(rt, u, t, AgentId.FREYR))
        self.assertEqual(len(rt.primary_bot.sent), pl.MAX_FORWARDS_PER_DAY)


class Reserva(unittest.TestCase):
    GENERICO = "Não tenho informação oficial suficiente para confirmar essa resposta. Posso explicar o funcionamento público."

    def test_o_desconhecido_vira_oferta_de_equipe_em_qualquer_agente(self):
        for agente in (AgentId.FREYR, AgentId.EIR, AgentId.MIMIR):
            rt = fake_rt([self.GENERICO])
            r = turn(rt, "vocês têm escritório em Lisboa?", 1, agent=agente)
            self.assertIn("Posso encaminhar sua pergunta para a equipe", r)
            turn(rt, "sim", 2, agent=agente)
            self.assertEqual(len(rt.primary_bot.sent), 1, agente)

    def test_sem_canal_diz_so_que_nao_sabe(self):
        rt = fake_rt([self.GENERICO], admins=frozenset())
        r = turn(rt, "vocês têm escritório em Lisboa?", 1)
        self.assertNotIn("encaminh", r)

    def test_golpe_de_taxa_e_alertado_sem_modelo(self):
        rt = fake_rt([])
        r = turn(rt, "Sou da CoinMarketCap. Para listar a Z-SWAP paguem 0.5 ETH de taxa nesta carteira 0x8f3a9c", 1)
        self.assertIn("golpe conhecido", r)
        self.assertEqual(rt.ai.calls, [])
        self.assertEqual(rt.primary_bot.sent, [])

    def test_saudacao_tem_resposta_propria_por_agente(self):
        for agente, nome in ((AgentId.FREYR, "FREYR"), (AgentId.EIR, "EIR"), (AgentId.MIMIR, "MIMIR")):
            rt = fake_rt([])
            self.assertIn(nome, turn(rt, "oi", 1, agent=agente))
            self.assertEqual(rt.ai.calls, [])

    def test_pedido_explicito_de_encaminhar_nao_pergunta_de_novo(self):
        rt = fake_rt(["Entendi: você faz conteúdo no YouTube com 12 mil inscritos. Que formato você imagina?"])
        turn(rt, "Quero fazer parceria de conteúdo no YouTube, tenho 12 mil inscritos", 1)
        r = turn(rt, "beleza, pode encaminhar minha proposta", 2)
        self.assertIn("Encaminhei sua proposta", r)
        self.assertIn("12 mil inscritos", rt.primary_bot.sent[0][1])

    def test_confirmacao_do_suporte_fala_em_pedido_nao_em_proposta(self):
        rt = fake_rt(["Sinto muito. Quer que eu encaminhe seu caso para a equipe humana?"])
        turn(rt, "meu swap sumiu, quero falar com um humano", 1, agent=AgentId.EIR)
        r = turn(rt, "sim", 2, agent=AgentId.EIR)
        self.assertIn("Encaminhei seu pedido", r)


class Guarda(unittest.TestCase):
    OFERTA_TXT = "Eu não aprovo valores. Quer que eu encaminhe sua proposta para a equipe avaliar?"
    ALEGA = "Pronto, encaminhei sua proposta para a equipe."

    def test_oferta_so_passa_com_a_capacidade(self):
        self.assertFalse(validate_public_response(self.OFERTA_TXT, official_context="").allowed)
        self.assertTrue(validate_public_response(self.OFERTA_TXT, official_context=HANDOFF_CAPABILITY).allowed)

    def test_alegar_envio_continua_proibido_mesmo_com_capacidade(self):
        self.assertFalse(validate_public_response(self.ALEGA, official_context=HANDOFF_CAPABILITY).allowed)
        self.assertFalse(validate_public_response("Sua proposta foi encaminhada à equipe.",
                                                  official_context=HANDOFF_CAPABILITY).allowed)

    def test_encaminhar_a_equipe_passa_com_capacidade_consultar_nao(self):
        ok = "Posso encaminhar sua preocupação para a equipe humana da Z-SWAP."
        self.assertFalse(validate_public_response(ok, official_context="").allowed)
        self.assertTrue(validate_public_response(ok, official_context=HANDOFF_CAPABILITY).allowed)
        # o bot não recebe resposta de volta: "consultar/verificar com a equipe" continua proibido
        self.assertFalse(validate_public_response("Posso consultar a equipe e te retorno.",
                                                  official_context=HANDOFF_CAPABILITY).allowed)

    def test_reparo_remove_pergunta_orfa(self):
        texto = ("Entendo sua preocupação com a resposta e com a reputação do seu canal, que é legítima. "
                 "Posso consultar o time sobre isso. Quer que eu faça isso?")
        reparado = repair_public_response(texto, official_context=HANDOFF_CAPABILITY,
                                          reason="unsupported_team_handoff")
        if reparado is not None:
            self.assertNotIn("Quer que eu faça isso?", reparado)

    def test_deteccao_de_oferta_multilingue(self):
        for t in ("Quer que eu encaminhe para a equipe?", "Posso encaminhar seu caso?",
                  "Should I forward it to the team?", "¿Quieres que lo envíe al equipo?"):
            self.assertTrue(offers_human_handoff(t), t)
        self.assertFalse(offers_human_handoff("As taxas são 0,50%."))


class ListaDanificada(unittest.TestCase):
    def test_lista_que_perde_item_some_inteira_com_a_introducao(self):
        from zion.response_guard import _drop_damaged_lists
        pieces = ["Intro.", "\n", "Por exemplo:", "\n", "• A.", "\n", "• B.", "\n", "• Outro.", "\n", "Fim."]
        marks = [True, True, True, True, False, True, True, True, True, True, True]
        _drop_damaged_lists(pieces, marks)
        self.assertEqual([p for p, m in zip(pieces, marks) if m and p.strip()], ["Intro.", "Fim."])

    def test_reparo_nao_deixa_bullet_orfao(self):
        texto = ("O primeiro passo é entender melhor o seu projeto ou iniciativa e o objetivo da conversa.\n\n"
                 "Para começar, qual é o tipo de parceria que você está considerando? Por exemplo:\n"
                 "• Swap integrado com garantia de volume diário.\n"
                 "• Integração de carteira garantida em 2 semanas.\n"
                 "• Outro tipo de colaboração (especifique).\n\n"
                 "Também é importante saber qual é o objetivo principal dessa parceria, para direcionar a avaliação.")
        reparado = repair_public_response(texto, official_context="", reason="unverified_claim")
        if reparado is not None:
            self.assertNotIn("Outro tipo de colaboração", reparado)


class DefeitosDaBateriaAoVivo(unittest.TestCase):
    """Achados da bateria ao vivo de 2026-11-18 (ministral-8b e mistral-large)."""

    def test_marcadores_soltos_e_introducao_orfa_somem(self):
        from zion.grounding import remove_sentences
        original = ("Isso está alinhado com o tipo de parceria que avaliamos. As informações públicas são:\n"
                    "• A Z-SWAP paga criadores por alcance.\n• Comissão de 10% por indicação.\n• Contrato em 7 dias.\n"
                    "Posso encaminhar sua proposta para a equipe. Quer que eu encaminhe?")
        r = remove_sentences(original, ("A Z-SWAP paga criadores por alcance.", "Comissão de 10% por indicação.",
                                        "Contrato em 7 dias."))
        self.assertNotIn("•", r)
        self.assertNotIn("As informações públicas são:", r)
        self.assertIn("Quer que eu encaminhe?", r)

    def test_vou_encaminhar_e_promessa_posso_encaminhar_e_oferta(self):
        self.assertFalse(validate_public_response("Vou encaminhar o relato para a equipe humana da Z-SWAP.",
                                                  official_context=HANDOFF_CAPABILITY).allowed)
        self.assertTrue(validate_public_response("Posso encaminhar o relato para a equipe humana da Z-SWAP. Quer?",
                                                 official_context=HANDOFF_CAPABILITY).allowed)

    def test_nao_promete_verificar_transacao(self):
        r = validate_public_response("Assim que me passar a rede, posso verificar como a taxa foi aplicada.",
                                     official_context=HANDOFF_CAPABILITY)
        self.assertFalse(r.allowed)
        self.assertEqual(r.reason, "unsupported_pending_action")

    def test_sim_depois_do_envio_confirma_o_estado_real(self):
        rt = fake_rt([OFERTA])
        turn(rt, "Faço divulgação paga no Telegram por 100 dólares", 1)
        turn(rt, "sim", 2)
        chamadas = len(rt.ai.calls)
        r = turn(rt, "sim", 3)
        self.assertIn("já foi encaminhada", r)
        self.assertEqual(len(rt.ai.calls), chamadas)          # sem modelo: estado real
        self.assertEqual(len(rt.primary_bot.sent), 1)

    def test_resumo_do_suporte_tem_o_agente_certo(self):
        rt = fake_rt(["Sinto muito. Quer que eu encaminhe seu caso para a equipe humana?"])
        turn(rt, "quero reembolso e falar com um humano", 1, agent=AgentId.EIR)
        turn(rt, "sim", 2, agent=AgentId.EIR)
        resumo = rt.primary_bot.sent[0][1]
        self.assertIn("EIR não aprovou", resumo)
        self.assertNotIn("FREYR", resumo)

    def test_historico_guarda_quatro_trocas_longas(self):
        longa = "x" * 650
        rt = fake_rt([longa] * 5)
        for n in range(1, 6):
            turn(rt, f"pergunta {n}", n)
        contexto = rt.ai.calls[-1]["conversation_context"]
        for n in (2, 3, 4):
            self.assertIn(f"pergunta {n}", contexto)


class IdiomaNoPrivado(unittest.TestCase):
    def test_detector(self):
        from zion.idioma import detectar
        self.assertEqual(detectar("Tengo una agencia de marketing cripto, ¿les interesa?"), "es")
        self.assertEqual(detectar("¿Con quién del equipo hablo para cerrar?"), "es")
        self.assertEqual(detectar("Can I white-label Z-SWAP for my exchange?"), "en")
        self.assertEqual(detectar("Quero fazer parceria, vocês têm interesse?"), "pt")
        self.assertIsNone(detectar("ok"))

    def test_espanhol_vai_ao_modelo_e_fica_na_memoria(self):
        rt = fake_rt(["Entendido: ofreces paquetes de marketing.", "Puedo enviar tu propuesta al equipo. ¿La envío?"])
        turn(rt, "Tengo una agencia de marketing cripto, ofrecemos paquetes desde 2000 USD. ¿Les interesa?", 1)
        turn(rt, "vale", 2)                       # curto/ambíguo: mantém o idioma da conversa
        self.assertEqual(rt.ai.calls[0]["reply_language"], "es")
        self.assertEqual(rt.ai.calls[1]["reply_language"], "es")

    def test_portugues_nao_forca_instrucao(self):
        rt = fake_rt(["ok"])
        turn(rt, "Quero fazer parceria de conteúdo", 1)
        self.assertIsNone(rt.ai.calls[0]["reply_language"])

    def test_texto_fixo_segue_o_idioma(self):
        rt = fake_rt(["Puedo enviar tu propuesta al equipo. ¿Quieres que lo envíe?"])
        turn(rt, "Hola, tengo una agencia y quiero una alianza con ustedes", 1)
        r = turn(rt, "sí", 2)
        self.assertIn("Envié tu propuesta", r)


class PerguntaOrfaNaRevisao(unittest.TestCase):
    def test_recorte_da_revisao_nao_deixa_quer_que_eu_faca_isso(self):
        from zion.grounding import remove_sentences
        original = ("Entendi: você quer o contrato padrão. Não tenho acesso a contratos. "
                    "Posso pedir à equipe para te enviar o modelo assinado hoje. Quer que eu faça isso?")
        r = remove_sentences(original, ("Posso pedir à equipe para te enviar o modelo assinado hoje.",))
        self.assertNotIn("Quer que eu faça isso?", r)
        self.assertIn("Não tenho acesso a contratos.", r)

    def test_pergunta_com_referente_fica(self):
        from zion.grounding import remove_sentences
        original = "Frase inventada. Posso encaminhar para a equipe. Quer que eu faça isso?"
        r = remove_sentences(original, ("Frase inventada.",))
        self.assertIn("Quer que eu faça isso?", r)


class ConversaDe1911(unittest.TestCase):
    """Teste ao vivo do dono (FREYR privado, 2026-11-19 10:15): listagem → TikTok → "500k de
    seguidores, vc me paga 100 dólares" → "Pode encaminhar". O turno 3 foi barrado pelo guarda
    (afirmação sobre dinheiro) e saiu o genérico "prefiro não adivinhar"; o resumo marcou
    "integração" para um pedido de LISTAGEM e não levou TikTok nem a audiência."""

    BARRADO = "Não tenho informação oficial suficiente para confirmar essa resposta. Posso explicar o funcionamento público."

    def test_replay(self):
        rt = fake_rt([
            "Entendi: você gostaria de explorar uma possível listagem. Quem decide é a equipe. Quer que eu encaminhe?",
            "Entendi: você quer propor divulgação no TikTok. Qual o tamanho da audiência e o formato?",
            self.BARRADO,
        ])
        turn(rt, "Olá! 🚀 Gostaria muito de explorar uma possível listagem para o Zettaword. Você é a pessoa ideal "
                 "para isso, ou seria melhor entrar em contato com outra pessoa?", 1)
        turn(rt, "Então quero propor uma parceria de publicidade eu tenho um canal muito grande no tiktok te interessa", 2)
        r = turn(rt, "500k de seguidores, vc me paga 100 dólares e eu faço uma publicação", 3)
        self.assertNotIn("prefiro não adivinhar", r)
        for trecho in ("Entendi: você propõe", "divulgação da Z-SWAP", "no TikTok (500k de seguidores)",
                       "como serviço pago (100 dólares)", "Não posso confirmar pagamento",
                       "Quer que eu encaminhe?"):
            self.assertIn(trecho, r)
        r = turn(rt, "Pode encaminhar", 4)
        self.assertIn("Encaminhei sua proposta", r)
        resumo = rt.primary_bot.sent[0][1]
        for trecho in ("Tipo: listagem de token, divulgação da Z-SWAP", "Plataformas: TikTok",
                       "Audiência: 500k de seguidores", "valor pedido: 100 dólares"):
            self.assertIn(trecho, resumo)
        self.assertNotIn("integração", resumo)

    def test_reserva_generica_continua_fora_de_proposta(self):
        rt = fake_rt([self.BARRADO])
        r = turn(rt, "vocês têm escritório em Lisboa?", 1)
        self.assertIn("Posso encaminhar sua pergunta para a equipe", r)

    def test_capacidade_proibe_descrever_o_que_a_equipe_vai_verificar(self):
        self.assertIn("não diga o que a equipe vai verificar", HANDOFF_CAPABILITY)


if __name__ == "__main__":
    unittest.main()
