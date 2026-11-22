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
        primary_bot=FakeBot(fail), db=FakeDb(), ai=ScriptedAI(replies), dm_exchanges={}, dm_languages={}, dm_loaded=set(),
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
        # de OFERECER; recebe só o fato real do envio (2026-11-21), que não libera oferta.
        from zion.response_guard import HANDOFF_DONE_CAPABILITY
        turn(rt, "e em quanto tempo eles costumam responder?", 4)
        ultima = rt.ai.calls[-1]
        self.assertEqual(ultima["capabilities"], HANDOFF_DONE_CAPABILITY)
        self.assertNotIn(HANDOFF_CAPABILITY, ultima["capabilities"])
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
        # A pergunta do FREYR no turno 2 ("qual o tamanho da audiência?") substituiu a oferta do
        # turno 1; respondida, a oferta volta a ser a pergunta em aberto (2026-11-21).
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


class PacoteDoPrivado(unittest.TestCase):
    """2026-11-21: estado que sobrevive a reinício (sem conteúdo), oferta que não se
    repete, consentimento ligado à pergunta em aberto, "digitando…"."""

    def setUp(self):
        import tempfile
        from pathlib import Path
        from zion.db import ZionDB
        self.tmp = tempfile.TemporaryDirectory()
        self.db = ZionDB(Path(self.tmp.name) / "z.db")
        self.db.initialize()

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def rt_com_banco(self, replies):
        rt = fake_rt(replies)
        rt.db = self.db
        return rt

    def payload(self, user_id=7728504427):
        row = self.db._conn.execute("SELECT payload FROM dm_memory WHERE user_id=?", (user_id,)).fetchone()
        return row["payload"] if row else None

    # ── memória que sobrevive a reinício, sem conteúdo ──────────────────────

    def test_estado_sobrevive_a_reinicio_sem_conteudo(self):
        import json as _json
        rt1 = self.rt_com_banco([OFERTA])
        turn(rt1, "Posso fazer sheel em várias comunidades e agendar AMAs no TikTok, cobro 100 dólares", 1)
        bruto = self.payload()
        self.assertIsNotNone(bruto)
        for proibido in ("sheel", "dólares", "dolares", "comunidades", "AMAs", "Posso", "cobro", "Entendi"):
            self.assertNotIn(proibido, bruto)        # nada do que a pessoa escreveu vai para o SQLite
        dados = _json.loads(bruto)
        self.assertEqual(set(dados), {"v", "lead", "lang", "envios"})
        self.assertEqual(set(dados["lead"]), {"language", "updated", "kinds", "platforms", "paid", "human_requested",
                                              "awaiting_confirm", "offer_open", "forwarded_at", "said"})
        rt2 = self.rt_com_banco([])                  # "reinício": runtime novo, mesmo banco
        r = turn(rt2, "sim", 2)
        self.assertIn("Encaminhei sua proposta", r)
        resumo = rt2.primary_bot.sent[0][1]
        for trecho in ("divulgação da Z-SWAP", "TikTok", "Serviço pago: sim", "ZION reiniciou"):
            self.assertIn(trecho, resumo)
        self.assertNotIn("100 dólares", resumo)       # o detalhe não foi guardado — e o operador é avisado

    def test_depois_do_reinicio_nao_encaminha_duas_vezes(self):
        rt1 = self.rt_com_banco([OFERTA])
        turn(rt1, "Faço divulgação paga no Telegram por 100 dólares", 1)
        turn(rt1, "sim", 2)
        self.assertEqual(len(rt1.primary_bot.sent), 1)
        rt2 = self.rt_com_banco([])
        r = turn(rt2, "pode encaminhar", 3)
        self.assertEqual(rt2.primary_bot.sent, [])
        self.assertEqual(r, pl.texto("already", "pt"))

    def test_idioma_volta_e_o_texto_nao(self):
        rt1 = self.rt_com_banco(["Entendido: ofreces paquetes de marketing con KOLs de LATAM."])
        turn(rt1, "Tengo una agencia de marketing cripto, ofrecemos paquetes desde 2000 USD con KOLs. ¿Les interesa?", 1)
        rt2 = self.rt_com_banco(["Gracias por la información."])
        turn(rt2, "LATAM 2000", 2)                   # sem idioma próprio: vale o da conversa
        chamada = rt2.ai.calls[0]
        self.assertEqual(chamada["reply_language"], "es")
        self.assertNotIn("agencia de marketing", chamada["conversation_context"])   # o texto não sobrevive
        self.assertIn("Proposta:", chamada["conversation_context"])                  # o estado sim
        self.assertIn("não estão nesta memória", chamada["conversation_context"])

    def test_sem_proposta_nada_e_gravado(self):
        rt = self.rt_com_banco(["Suportamos várias redes; a lista atual fica no app."])
        turn(rt, "quais redes vocês suportam?", 1, agent=AgentId.MIMIR)
        self.assertIsNone(self.payload())

    def test_memoria_expira(self):
        import time as _t
        rt1 = self.rt_com_banco([OFERTA])
        turn(rt1, "Faço divulgação paga no Telegram por 100 dólares", 1)
        self.assertIsNotNone(self.db.get_dm_memory(20, 7728504427, _t.time()))
        self.assertIsNone(self.db.get_dm_memory(20, 7728504427, _t.time() + 3601))
        self.assertEqual(self.db.prune_dm_memory(_t.time() + 3601), 1)

    def test_registro_corrompido_nao_quebra_a_conversa(self):
        import time as _t
        self.db.put_dm_memory(20, 7728504427, "{isso não é json", expires_at=_t.time() + 600, now=_t.time())
        rt = self.rt_com_banco(["Pode perguntar."])
        with self.assertLogs("zion.telegram", level="WARNING"):
            r = turn(rt, "sim", 1)
        self.assertEqual(r, "Pode perguntar.")
        self.assertEqual(rt.primary_bot.sent, [])

    def test_payload_estranho_e_filtrado(self):
        import time as _t
        agora_ = _t.time()
        lead = pl.lead_de_dict({"updated": agora_, "kinds": ["promotion", "<script>", 3],
                                "platforms": ["TikTok", "MySpace"], "awaiting_confirm": "yes", "language": "xx",
                                "said": ["payment", "understood:Entendi: 100 dólares"]}, agora_)
        self.assertEqual(lead.kinds, ["promotion"])
        self.assertEqual(lead.platforms, ["TikTok"])
        self.assertEqual(lead.said, {"payment"})
        self.assertFalse(lead.awaiting_confirm)          # só o booleano True vale
        self.assertEqual(lead.language, "pt")
        self.assertIsNone(pl.lead_de_dict({"updated": "ontem"}, agora_))
        self.assertIsNone(pl.lead_de_dict({"updated": agora_ + 9999}, agora_))
        self.assertIsNone(pl.lead_de_dict({}, agora_))

    def test_pedido_explicito_depois_do_reinicio_encaminha(self):
        rt1 = self.rt_com_banco(["Entendido: ofreces una reseña pagada en YouTube. ¿Cuántos suscriptores tienes?"])
        turn(rt1, "Tengo un canal de YouTube, quiero hacer una reseña pagada de Z-SWAP", 1)
        rt2 = self.rt_com_banco([])                  # reinício: sem histórico, com a proposta restaurada
        r = turn(rt2, "sí, envíalo", 2)
        self.assertEqual(len(rt2.primary_bot.sent), 1)
        self.assertEqual(r, pl.texto("forwarded", "es", handle=" (@carlos)"))

    # ── a oferta não se repete; o consentimento é a resposta à oferta ────────

    def test_nao_repete_a_oferta_em_aberto(self):
        rt = fake_rt([OFERTA, "Entendi: são 3 comunidades com 20 mil membros. Quer que eu encaminhe sua proposta para a equipe?"])
        turn(rt, "Faço divulgação paga no Telegram por 100 dólares", 1)
        r = turn(rt, "são 3 comunidades com 20 mil membros", 2)
        self.assertIn("20 mil membros", r)
        self.assertNotIn("Quer que eu encaminhe", r)
        r = turn(rt, "sim", 3)                       # a oferta continua sendo a pergunta em aberto
        self.assertIn("Encaminhei sua proposta", r)

    def test_sim_depois_de_outra_pergunta_nao_encaminha_no_escuro(self):
        rt = fake_rt([OFERTA,
                      "A equipe define pagamentos caso a caso. Você já trabalhou com outros projetos cripto?",
                      "Ótimo, experiência ajuda. Quer que eu encaminhe sua proposta para a equipe agora?"])
        turn(rt, "Faço divulgação paga no Telegram por 100 dólares", 1)
        turn(rt, "antes, como funciona o pagamento de vocês?", 2)
        r = turn(rt, "sim", 3)                       # responde à pergunta do modelo, não à oferta
        self.assertEqual(rt.primary_bot.sent, [])
        self.assertIn("Quer que eu encaminhe", r)    # a oferta volta: deixou de ser a pergunta em aberto
        r = turn(rt, "sim", 4)
        self.assertIn("Encaminhei sua proposta", r)

    def test_pedido_explicito_vale_mesmo_depois_de_outra_pergunta(self):
        rt = fake_rt([OFERTA, "A equipe define pagamentos caso a caso. Você já trabalhou com outros projetos cripto?"])
        turn(rt, "Faço divulgação paga no Telegram por 100 dólares", 1)
        turn(rt, "antes, como funciona o pagamento de vocês?", 2)
        r = turn(rt, "sim, pode mandar para a equipe", 3)
        self.assertIn("Encaminhei sua proposta", r)

    def test_pergunta_sobre_humano_mantem_a_oferta(self):
        rt = fake_rt([OFERTA, "Temos sim uma equipe. Posso encaminhar sua proposta agora. Quer que eu encaminhe?"])
        turn(rt, "Faço divulgação paga no Telegram por 100 dólares", 1)
        r = turn(rt, "tem algum humano aí pra ver isso?", 2)
        self.assertIn("Quer que eu encaminhe?", r)
        self.assertEqual(rt.primary_bot.sent, [])

    def test_quero_falar_com_humano_com_oferta_aberta_encaminha(self):
        rt = fake_rt([OFERTA])
        turn(rt, "Faço divulgação paga no Telegram por 100 dólares", 1)
        r = turn(rt, "quero falar com um humano", 2)
        self.assertIn("Encaminhei sua proposta", r)

    def test_detalhe_dito_junto_com_o_sim_entra_no_resumo(self):
        rt = fake_rt([OFERTA])
        turn(rt, "Faço divulgação paga no Telegram por 100 dólares", 1)
        turn(rt, "sim, são 3 comunidades", 2)
        self.assertIn("Comunidades: 3 comunidades", rt.primary_bot.sent[0][1])

    def test_confirmacao_estrita(self):
        for sim in ("sim", "Sim!", "pode", "pode sim", "quero", "ok", "ok obrigado", "sim por favor",
                    "claro, pode mandar", "yes please", "sure, go ahead", "sí, dale", "sim, quero falar com o dono",
                    "quero falar com um humano", "isso mesmo", "pode ser", "sim, são 3 comunidades",
                    "sim, mas quanto vocês pagam?", "s"):
            self.assertTrue(pl.analisar(sim).confirms, sim)
        for nao in ("ok, e quais as taxas?", "quero saber as taxas", "pode me explicar como funciona",
                    "manda o link do app", "ok mas antes quero entender", "isso é seguro?", "claro que não",
                    "si me pagan lo hago", "y cuánto pagan?", "simples assim?", "sim, não tenho pressa"):
            self.assertFalse(pl.analisar(nao).confirms, nao)

    def test_recusa_estrita(self):
        for nao in ("não", "nao", "não, obrigado", "agora não", "ainda não", "não precisa", "no", "no thanks",
                    "not now", "nope", "não precisa encaminhar", "não, mas quais as taxas?", "No, I'll think about it"):
            self.assertTrue(pl.analisar(nao).declines, nao)
        for outra in ("não entendi", "não sei", "no entiendo", "nao tenho carteira ainda", "não sei se vale a pena"):
            self.assertFalse(pl.analisar(outra).declines, outra)

    # ── "digitando…" ────────────────────────────────────────────────────────

    def test_digitando_durante_a_resposta(self):
        from telegram.constants import ChatAction
        from zion.telegram_app import _digitando

        class LentoAI(ScriptedAI):
            async def answer(self, **kw):
                await asyncio.sleep(0.05)
                return await super().answer(**kw)

        acoes = []
        rt = fake_rt([])
        rt.ai = LentoAI(["Pode perguntar."])
        update = make_update("quais redes vocês suportam?", chat_type="private", message_id=1)

        async def send_action(acao):
            acoes.append(acao)
        update.effective_chat.send_action = send_action

        async def rodar():
            async with _digitando(update):
                return await _dm_model_reply(rt, update, "quais redes vocês suportam?", AgentId.FREYR)
        self.assertEqual(asyncio.run(rodar()), "Pode perguntar.")
        self.assertIn(ChatAction.TYPING, acoes)

    def test_falha_do_digitando_nao_quebra_a_resposta(self):
        from zion.telegram_app import _digitando
        rt = fake_rt(["ok, respondido."])
        update = make_update("quais taxas?", chat_type="private", message_id=1)

        async def quebra(_acao):
            raise RuntimeError("telegram fora")
        update.effective_chat.send_action = quebra

        async def rodar():
            async with _digitando(update):
                return await _dm_model_reply(rt, update, "quais taxas?", AgentId.FREYR)
        self.assertEqual(asyncio.run(rodar()), "ok, respondido.")

    def test_digitando_termina_junto_com_a_resposta(self):
        from zion.telegram_app import _digitando
        update = make_update("oi", chat_type="private", message_id=1)
        update.effective_chat.send_action = lambda _a: asyncio.sleep(0)

        async def rodar():
            async with _digitando(update):
                await asyncio.sleep(0)
            pendentes = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
            return pendentes
        self.assertEqual(asyncio.run(rodar()), [])


class VerdadeDoEncaminhamento(unittest.TestCase):
    """Bateria 2026-11-21: depois de um envio REAL, "e aí, já encaminhou?" recebeu "eu não
    encaminhei nada" — o guarda barrava o passado e o reparo invertia a verdade."""

    def enviado(self, replies=()):
        rt = fake_rt([OFERTA, *replies])
        turn(rt, "Faço divulgação paga no Telegram por 100 dólares", 1)
        turn(rt, "sim", 2)
        self.assertEqual(len(rt.primary_bot.sent), 1)
        return rt

    def test_status_depois_do_envio_e_a_verdade(self):
        rt = self.enviado()
        for n, pergunta in enumerate(("e aí, já encaminhou?", "e a minha proposta?",
                                      "quando a equipe vai responder?"), 3):
            self.assertEqual(turn(rt, pergunta, n), pl.texto("already", "pt"), pergunta)
        self.assertEqual(len(rt.ai.calls), 1)          # nenhuma dessas foi para o modelo
        self.assertEqual(len(rt.primary_bot.sent), 1)  # e nada foi reenviado

    def test_depois_do_envio_o_modelo_recebe_o_fato(self):
        from zion.response_guard import HANDOFF_DONE_CAPABILITY
        rt = self.enviado(["De nada! Sua proposta já está com a equipe."])
        turn(rt, "obrigado pela ajuda", 3)
        self.assertEqual(rt.ai.calls[-1]["capabilities"], HANDOFF_DONE_CAPABILITY)

    def test_o_passado_so_passa_com_o_fato_real(self):
        from zion.response_guard import HANDOFF_DONE_CAPABILITY
        for verdade in ("Sua proposta já foi encaminhada para a equipe.",
                        "Já encaminhei sua proposta para a equipe."):
            self.assertFalse(validate_public_response(verdade, official_context="").allowed, verdade)
            self.assertTrue(validate_public_response(verdade, official_context=HANDOFF_DONE_CAPABILITY).allowed,
                            verdade)
        for proibido in ("Vou encaminhar sua proposta para a equipe de novo.",
                         "Quer que eu encaminhe sua proposta para a equipe?",
                         "Encaminharei sua proposta para a equipe amanhã.",
                         "Sua proposta será encaminhada para a equipe."):
            self.assertFalse(validate_public_response(proibido, official_context=HANDOFF_DONE_CAPABILITY).allowed,
                             proibido)

    def test_memoria_diz_o_idioma(self):
        lead = pl.Lead(language="es", updated=0.0)
        lead.kinds = ["content"]
        self.assertIn("Idioma de la conversación: español. Responde en español.", pl.estado_para_modelo(lead, 0.0))
        lead.language = "en"
        self.assertIn("Conversation language: English. Reply in English.", pl.estado_para_modelo(lead, 0.0))
        self.assertNotIn("language", pl.estado_para_modelo(pl.Lead(language="pt", updated=0.0), 0.0))

    def test_ultima_pergunta_decide_o_que_o_sim_responde(self):
        rt = fake_rt([OFERTA,
                      "Entendi: 12 mil inscritos. Quer conteúdo exclusivo ou menções orgânicas nos seus reviews? "
                      "(A oferta anterior ainda está em aberto.)",
                      "Combinado. Quer que eu encaminhe sua proposta para a equipe?"])
        turn(rt, "Faço divulgação paga no Telegram por 100 dólares", 1)
        r = turn(rt, "tenho 12 mil inscritos e faço reviews de DeFi", 2)
        self.assertNotIn("oferta anterior", r)        # o eco da memória sai
        turn(rt, "sim", 3)                             # responde a "exclusivo ou orgânicas?"
        self.assertEqual(rt.primary_bot.sent, [])
        self.assertIn("Encaminhei sua proposta", turn(rt, "sim", 4))

    def test_pergunta_anaforica_sai_com_a_oferta_repetida(self):
        texto = ("Entendi: você quer saber se há possibilidade de acelerar a listagem de um token BEP20. "
                 "Posso encaminhar sua pergunta para a equipe. Quer que eu faça isso?")
        r = pl.sem_oferta_repetida(texto)
        self.assertNotIn("Quer que eu faça isso", r)
        self.assertIn("token BEP20", r)

    def test_lembrete_de_oferta_tambem_nao_se_repete(self):
        texto = ("Entendi: você quer divulgar a Z-SWAP no YouTube com reviews de DeFi para 12 mil inscritos. "
                 "Como já ofereci encaminhar sua proposta, lembre-se de confirmar se deseja que eu faça isso.")
        r = pl.sem_oferta_repetida(texto)
        self.assertNotIn("ofereci", r)
        self.assertIn("12 mil inscritos", r)


if __name__ == "__main__":
    unittest.main()
