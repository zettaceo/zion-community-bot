"""FREYR partnership lead conversation (private chat), deterministic and bounded.

Why this exists (03/11 transcript): the human handoff already existed but only
fired for a form ("Empresa: ...", "Contato: ..."). A real person writes "posso
fazer shill e agendar AMAs, cobro 100 dólares, quero falar com um humano", and
the model then misread "shill" as a token, never acknowledged the offer, used
the generic fallback for "vão me pagar?" and denied that a human path existed.

This module understands that conversation in plain language, keeps a small
ephemeral lead (kinds, channels, audience, asked price, the person's own short
statements) and offers the REAL handoff: with the person's confirmation, the
lead is summarized to the operators (admins) by the caller. It never approves
payment, price, contract, deadline or integration; it never promises a reply.

Only content-free STATE is persisted (dm_memory, 1 h TTL) to survive restarts:
kinds, platforms, flags and language. Values, audience, channels and the
person's own words stay in process memory only (docs/DEPLOYMENT-MODEL.md: a
partnership DM must not appear in SQLite or logs). Raw text kept in a lead is bounded, and the caller
only stores it after the guardian already ran on the message.
"""
from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import dataclass, field

TTL_SECONDS = 3600.0
MAX_LEADS = 2048
MAX_NOTES = 6
MAX_NOTE_CHARS = 280
MAX_FORWARDS_PER_DAY = 2


def _fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.lower().split())


# ── sinais ─────────────────────────────────────────────────────────────────

_KINDS = (
    ("promotion", re.compile(
        r"\b(?:shil+\w*|shel+\w*|sheel\w*|xil+\w*|divulg\w*|promov\w*|promoc\w*|promot\w*|"
        r"publicid\w*|anunci\w*|marketing|kols?|influenc\w*|difund\w*|difusion|advertis\w*|"
        r"postagens?|posts? patrocinad\w*|publicac\w*|publicar|publis?)\b")),
    ("ama", re.compile(r"\b(?:amas?|ask me anything|spaces?|lives?)\b")),
    ("listing", re.compile(r"\b(?:listagem|listar|listado|listing|list(?:ar|e) (?:o|meu|nosso|um) token)\b")),
    ("integration", re.compile(r"\b(?:integra\w*|api|sdk)\b")),
    ("content", re.compile(r"\b(?:conteudos?|content|videos?|youtube|artigos?|articles?|educativ\w*|tutoria\w*)\b")),
    ("event", re.compile(r"\b(?:eventos?|events?|meetups?|hackathons?|conferenc\w*)\b")),
)
_INTEREST = re.compile(r"\b(?:parceri\w*|parceir\w*|partner\w*|socio\w*|colabora\w*|alianza|asociacion)\b")
_PAID_OFFER = re.compile(r"\b(?:cobr\w*|charge|cobro|cuesta|meu preco|my price|mi precio|valor do servico|servicos?|services?)\b")
_ASKS_PAYMENT = re.compile(
    r"\b(?:(?:vai|vao|voces?|vcs?|z ?swap|equipe|time|ustedes|you|will you)\s+(?:me\s+|nos\s+)?(?:pag\w*|pay)|"
    r"pagam\b|quanto (?:voces )?pag\w*|how much (?:do|will) you pay|me pagan|pay me|"
    r"(?:tem|ha|existe) (?:pagamento|remuneracao|cache))\b")
_PRICE = re.compile(
    r"(?:(?:us\s?\$|usd|usdt|r\s?\$|\$|€)\s?\d[\d.,]*\s?k?\b|"
    r"\b\d[\d.,]*\s?k?\s?(?:d[oó]lares?|dollars?|usd|usdt|reais|brl|euros?)\b)")
_ASKS_HUMAN = re.compile(
    r"\b(?:humanos?|human|pessoa real|alguem real|alguien real|real person|someone real|"
    r"dono|donos|fundador|founder|owner|ceo|atendente|"
    r"falar com (?:alguem|uma pessoa|o responsavel|a equipe|o time)|"
    r"hablar con (?:alguien|una persona)|talk to (?:a person|someone|a human|the team)|"
    r"me encaminh\w*|encaminh\w* (?:para|pra|a) )")
_CONFIRM = re.compile(r"^(?:sim|s|pode|pode sim|ok|okay|claro|isso|manda|pode mandar|encaminha|encaminhar|"
                      r"pode encaminhar|quero|yes|y|sure|go ahead|si|dale|confirmo|confirmado)\b")
_DECLINE = re.compile(r"^(?:nao|no|nope|agora nao|ainda nao|not now|todavia no|espera)\b")
# Consentimento é estrito (2026-11-21): "ok, e quais as taxas?" e "quero saber as taxas"
# NÃO são "sim". Vale: só palavras de confirmação ("sim, pode mandar", "ok obrigado"),
# confirmação + pedido de humano ("quero falar com o dono") ou um sim forte no começo
# ("sim, são 3 comunidades") — nunca com negação. Recusa idem ("não entendi" não é recusa).
_WORD = re.compile(r"[a-z0-9]+")
_CONFIRM_FILLER = frozenset((
    "sim s pode claro isso ok okay manda mandar encaminha encaminhar encaminhe quero yes y sure si dale "
    "confirmo confirmado por favor pf pfv porfa please pls plz obrigado obrigada valeu thanks thank you "
    "gracias mesmo ser go ahead beleza blz perfeito otimo show top fechado combinado ai faz faca mande "
    "envia enviar envie envialo bora vamos vai la com certeza uhum aham yep yeah yup fine great perfect "
    "do it vale venga adelante agora ja entao a o pra para equipe time team the to this isto tambem tb"
).split())
_STRONG_YES = re.compile(r"^(?:sim|s|yes|yep|yeah|yup|sure|claro|confirmo|confirmado|dale|sí|si(?=\s*[,.!]|\s*$))(?!\w)")
_NEGATION = frozenset("nao no not nope nunca never jamais".split())
_DECLINE_FILLER = frozenset((
    "nao no nope not now yet agora ainda todavia espera obrigado obrigada valeu thanks thank you gracias "
    "precisa necessario quero deixa pra para depois later mais tarde por enquanto momento so isso ok tudo bem "
    "encaminhar encaminha encaminhe mandar enviar repassar it"
).split())
_STRONG_NO = re.compile(r"^(?:não|nao|no|nope)\s*[,.!]")


def _confirma(lowered: str, folded: str, asks_human: bool) -> bool:
    palavras = _WORD.findall(folded)
    if not palavras or _NEGATION.intersection(palavras):
        return False
    if len(folded) <= 120 and _STRONG_YES.match(lowered):
        return True
    if len(folded) > 40 or not _CONFIRM.search(folded):
        return False
    return asks_human or all(p in _CONFIRM_FILLER for p in palavras)


def _recusa(lowered: str, folded: str) -> bool:
    if len(folded) <= 120 and _STRONG_NO.match(lowered):
        return True
    if len(folded) > 40 or not _DECLINE.search(folded):
        return False
    return all(p in _DECLINE_FILLER for p in _WORD.findall(folded))


_MENCIONA_HANDOFF = re.compile(
    r"\b(?:encaminh\w*|repass\w*|forward\w*|reenvi\w*|equipe|time|team|equipo|humanos?|human|responsavel|"
    r"dono|fundador|founder|owner|ceo|contato|contact|contacto|proposta|proposal|propuesta)\b")


_STATUS = re.compile(r"\b(?:ja|e ai|status|retorno|resposta|responde\w*|respondeu|quando|algum\w*|noticia\w*|"
                     r"novidade\w*|update|already|yet|ya|cuando|alguna)\b")


def pergunta_de_status(text: str, s: "Sinais") -> bool:
    """"e aí, já encaminhou?", "e a minha proposta?", "quando a equipe responde?" — depois
    de um envio real, a resposta é o estado verdadeiro (texto fixo), não o modelo."""
    folded = _fold(text)
    return (menciona_encaminhamento(text) and ("?" in (text or "") or bool(_STATUS.search(folded)))
            and not s.product_question and not s.kinds)


def menciona_encaminhamento(text: str) -> bool:
    """A pessoa falou de encaminhar / equipe / humano: a oferta pode (e deve) aparecer."""
    return bool(_MENCIONA_HANDOFF.search(_fold(text)))
_CHANNEL = re.compile(r"(?:https?://)?(?:t\.me|telegram\.me|x\.com|twitter\.com|youtube\.com|discord\.gg)/[\w/+-]{2,64}|@[A-Za-z0-9_]{4,32}")
_AUDIENCE = re.compile(
    r"\b\d[\d.,]*\s?(?:k|mil|m)?\s?(?:de\s+)?(?:membros|members|miembros|seguidores|followers|pessoas|inscritos|"
    r"subscribers|usuarios|users|ouvintes|listeners|holders|views|visualizac\w*)\b")
_PLATFORMS = (
    ("TikTok", r"tik ?tok"), ("Instagram", r"instagram|insta"), ("YouTube", r"you ?tube"), ("X", r"twitter|x\.com"),
    ("Telegram", r"telegram"), ("Discord", r"discord"), ("Kwai", r"kwai"), ("Twitch", r"twitch"),
    ("Facebook", r"facebook"), ("LinkedIn", r"linkedin"), ("Reddit", r"reddit"), ("WhatsApp", r"whats ?app"),
)
_PLATFORM_RX = tuple((nome, re.compile(r"\b(?:" + rx + r")\b")) for nome, rx in _PLATFORMS)
_COMMUNITY_COUNT = re.compile(r"\b(?:\d+|v[aá]rias|muitas|several|many)\s+(?:comunidades|communities|grupos|groups|canais|channels)\b")
_FORWARD_REQUEST = re.compile(
    r"\b(?:pode (?:me )?encaminhar|encaminha (?:a|minha|isso|pra|para)|encaminhe|pode mandar (?:pra|para) (?:a )?equipe|"
    r"(?:please )?forward (?:it|this|my)|send (?:it|this) to (?:the )?team|"
    r"envialo|enviala|reenvialo|pasalo al equipo|puedes enviar(?:lo|la))\b")
# Pedido para a Z-SWAP (ou a pessoa) PAGAR/ENVIAR cripto a um endereço — taxa de
# listagem, "liberação", "verificação": golpe clássico, alertado sem depender do modelo.
_SCAM_PAYMENT = re.compile(
    r"\b(?:pag\w*|envi\w*|mand\w*|transfir\w*|deposit\w*|pay|send|transfer)\b(?:[^.?!\n]|\.(?=\d)){0,80}"
    r"(?:\b0x[0-9a-f]{4,}|\bcarteira\b|\bwallet\b|\bendereco\b|\baddress\b)")
_SCAM_HOOK = re.compile(r"\b(?:taxa|fee|listagem|listing|liberac\w*|verificac\w*|ativac\w*|urgente|urgent|hoje|today|vaga)\b")
_GREETING = re.compile(r"^(?:oi+|ola|ola+|opa|e ai|eai|bom dia|boa tarde|boa noite|hello|hi|hey|hola|buenas|buenos dias)[\s!.,?]*$")
_PRODUCT_TOPIC = re.compile(
    r"\b(?:taxas?|fees?|planos?|plans?|swap|redes?|chains?|carteira|wallet|ordem|ordens|stop|seguranca|"
    r"founder pass|roadmap|token)\b")


@dataclass(frozen=True)
class Sinais:
    kinds: tuple[str, ...]
    interest: bool
    paid_offer: bool
    asks_payment: bool
    price: str | None
    asks_human: bool
    confirms: bool
    declines: bool
    channels: tuple[str, ...]
    platforms: tuple[str, ...]
    forward_request: bool
    scam_payment: bool
    greeting: bool
    audience: str | None
    community_count: str | None
    product_question: bool

    @property
    def lead_signal(self) -> bool:
        return bool(self.kinds or self.interest or self.paid_offer or self.asks_payment or self.price
                    or self.asks_human or self.channels or self.platforms or self.audience or self.community_count)


def analisar(text: str) -> Sinais:
    folded = _fold(text)
    lowered = " ".join((text or "").lower().split())
    price = _PRICE.search(lowered)
    audience = _AUDIENCE.search(folded)
    count = _COMMUNITY_COUNT.search(lowered) or _COMMUNITY_COUNT.search(folded)
    kinds = tuple(name for name, rx in _KINDS if rx.search(folded))
    asks_payment = bool(_ASKS_PAYMENT.search(folded))
    asks_human = bool(_ASKS_HUMAN.search(folded))
    return Sinais(
        kinds=kinds,
        interest=bool(_INTEREST.search(folded)),
        paid_offer=bool(_PAID_OFFER.search(folded)) or (bool(price) and not asks_payment),
        asks_payment=asks_payment,
        price=price.group(0).strip() if price else None,
        asks_human=asks_human,
        confirms=_confirma(lowered, folded, asks_human),
        declines=_recusa(lowered, folded),
        channels=tuple(dict.fromkeys(m.group(0) for m in _CHANNEL.finditer(text or "")))[:6],
        platforms=tuple(nome for nome, rx in _PLATFORM_RX if rx.search(folded)),
        forward_request=bool(_FORWARD_REQUEST.search(folded)),
        scam_payment=bool(_SCAM_PAYMENT.search(folded) and _SCAM_HOOK.search(folded)),
        greeting=bool(_GREETING.match(folded)),
        audience=audience.group(0) if audience else None,
        community_count=count.group(0) if count else None,
        product_question="?" in (text or "") and bool(_PRODUCT_TOPIC.search(folded)) and not kinds,
    )


# ── lead ───────────────────────────────────────────────────────────────────

@dataclass
class Lead:
    language: str
    updated: float
    kinds: list[str] = field(default_factory=list)
    channels: list[str] = field(default_factory=list)
    platforms: list[str] = field(default_factory=list)
    audience: str | None = None
    community_count: str | None = None
    price: str | None = None
    paid: bool = False
    human_requested: bool = False
    notes: list[str] = field(default_factory=list)
    awaiting_confirm: bool = False
    forwarded_at: float | None = None
    # o que FREYR já disse nesta conversa: cada informação uma vez só
    said: set[str] = field(default_factory=set)
    # A oferta de encaminhar é a pergunta EM ABERTO (nenhuma outra pergunta depois dela):
    # só então ela não se repete e um "sim" solto vale como consentimento (2026-11-21).
    offer_open: bool = False
    # Reconstruído do banco após um reinício: só o estado, sem os detalhes da conversa.
    restaurado: bool = False

    @property
    def has_substance(self) -> bool:
        return bool(self.kinds or self.notes or self.channels or self.price)

    def absorver(self, s: Sinais, text: str, now: float, *, parceria: bool = True) -> None:
        self.updated = now
        self.human_requested = self.human_requested or s.asks_human
        if not parceria:
            # outros agentes: só a fala da pessoa (para o resumo) e o pedido de humano
            note = " ".join((text or "").split())[:MAX_NOTE_CHARS]
            if note and not (s.confirms or s.declines) and note not in self.notes and len(self.notes) < MAX_NOTES:
                self.notes.append(note)
            return
        for k in s.kinds:
            if k not in self.kinds:
                self.kinds.append(k)
        for c in s.channels:
            if c not in self.channels and len(self.channels) < 6:
                self.channels.append(c)
        for p in s.platforms:
            if p not in self.platforms and len(self.platforms) < 6:
                self.platforms.append(p)
        self.audience = s.audience or self.audience
        self.community_count = s.community_count or self.community_count
        self.price = s.price or self.price
        self.paid = self.paid or s.paid_offer or bool(s.price)
        self.human_requested = self.human_requested or s.asks_human
        if not (s.confirms or s.declines):
            note = " ".join((text or "").split())[:MAX_NOTE_CHARS]
            if note and note not in self.notes and len(self.notes) < MAX_NOTES:
                self.notes.append(note)


class LeadWindow:
    """Ephemeral leads keyed by (chat, user). Bounded; expires after TTL."""

    def __init__(self, ttl: float = TTL_SECONDS, max_entries: int = MAX_LEADS):
        self.ttl = ttl
        self.max_entries = max_entries
        self._leads: dict[tuple[int, int], Lead] = {}
        self._forwards: dict[int, list[float]] = {}

    def get(self, key: tuple[int, int], now: float) -> Lead | None:
        lead = self._leads.get(key)
        if lead is not None and now - lead.updated > self.ttl:
            self._leads.pop(key, None)
            return None
        return lead

    def _podar(self) -> None:
        if len(self._leads) >= self.max_entries:
            for stale in sorted(self._leads, key=lambda k: self._leads[k].updated)[: max(1, self.max_entries // 8)]:
                self._leads.pop(stale, None)

    def start(self, key: tuple[int, int], language: str, now: float) -> Lead:
        self._podar()
        lead = Lead(language=language, updated=now)
        self._leads[key] = lead
        return lead

    def may_forward(self, user_id: int, now: float) -> bool:
        recent = [t for t in self._forwards.get(user_id, []) if now - t < 86400]
        self._forwards[user_id] = recent
        return len(recent) < MAX_FORWARDS_PER_DAY

    def exportar(self, key: tuple[int, int], user_id: int, now: float) -> tuple[dict | None, list[float]]:
        lead = self.get(key, now)
        envios = [t for t in self._forwards.get(user_id, []) if now - t < 86400]
        return (lead_para_dict(lead) if lead is not None else None), envios

    def importar(self, key: tuple[int, int], user_id: int, lead: Lead | None, envios: list[float], now: float) -> None:
        if lead is not None and now - lead.updated <= self.ttl and key not in self._leads:
            self._podar()
            self._leads[key] = lead
        if envios:
            atuais = set(self._forwards.get(user_id, []))
            self._forwards[user_id] = sorted(atuais | {float(t) for t in envios if now - float(t) < 86400})

    def mark_forwarded(self, user_id: int, lead: Lead, now: float) -> None:
        lead.forwarded_at = now
        lead.awaiting_confirm = False
        self._forwards.setdefault(user_id, []).append(now)


# ── decisão ────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Passo:
    reply: str
    forward: bool = False


_KIND_LABEL = {
    "pt": {"promotion": "divulgação da Z-SWAP", "ama": "AMAs", "integration": "integração", "listing": "listagem de token",
           "content": "criação de conteúdo", "event": "eventos"},
    "en": {"promotion": "promoting Z-SWAP", "ama": "AMAs", "integration": "integration", "listing": "token listing",
           "content": "content creation", "event": "events"},
    "es": {"promotion": "difusión de Z-SWAP", "ama": "AMAs", "integration": "integración", "listing": "listado de token",
           "content": "creación de contenido", "event": "eventos"},
}


def _lang(language: str) -> str:
    return language if language in ("pt", "en", "es") else ("en" if language == "zh" else "pt")


def _join(items: list[str], lang: str) -> str:
    conj = {"pt": " e ", "en": " and ", "es": " y "}[lang]
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + conj + items[-1]


def _understood(lead: Lead, lang: str) -> str:
    kinds = [_KIND_LABEL[lang][k] for k in lead.kinds if k in _KIND_LABEL[lang]]
    if not kinds:
        return ""
    where = ""
    outras = [p for p in lead.platforms if p != "Telegram"]
    if outras:
        where = {"pt": " no ", "en": " on ", "es": " en "}[lang] + _join(outras, lang)
    elif lead.channels or lead.community_count or "Telegram" in lead.platforms:
        where = {"pt": " em comunidades do Telegram", "en": " in Telegram communities",
                 "es": " en comunidades de Telegram"}[lang]
    if lead.audience:
        where += f" ({lead.audience})"
    paid = {"pt": ", como serviço pago", "en": ", as a paid service", "es": ", como servicio pagado"}[lang] if lead.paid else ""
    price = f" ({lead.price})" if lead.price else ""
    return {"pt": "Entendi: você propõe ", "en": "Got it: you are proposing ",
            "es": "Entendido: propones "}[lang] + _join(kinds, lang) + where + paid + price + "."


def _missing(lead: Lead, lang: str) -> str:
    want = []
    if not (lead.channels or lead.community_count):
        want.append({"pt": "os links das comunidades", "en": "the links to your communities",
                     "es": "los enlaces de las comunidades"}[lang])
    if not lead.audience:
        want.append({"pt": "o tamanho aproximado da audiência", "en": "the approximate audience size",
                     "es": "el tamaño aproximado de la audiencia"}[lang])
    if lead.paid and not lead.price:
        want.append({"pt": "o valor e o formato que você cobra", "en": "your price and format",
                     "es": "el valor y el formato que cobras"}[lang])
    return _join(want, lang) if want else ""


_TXT = {
    "pt": {
        "opening": ("Que bom! Para eu entender a proposta, me conte em uma mensagem: que tipo de parceria "
                    "(por exemplo, divulgação em comunidades, AMA, conteúdo, integração técnica ou evento), "
                    "onde ela acontece e se envolve algum valor."),
        "no_program": ("A Z-SWAP não tem um programa público de divulgação paga, e eu não aprovo valores, "
                       "pagamentos nem contratos. Quem decide é a equipe."),
        "ask_missing": "Para eu encaminhar à equipe, me mande {missing}.",
        "offer_forward": "Se preferir, já encaminho o que você me contou para avaliação humana. Quer que eu encaminhe?",
        "payment": ("Não posso confirmar pagamento: sou a IA da Z-SWAP e não aprovo valores, contratação nem "
                    "prazos. Isso é decisão da equipe."),
        "payment_offer": "Posso encaminhar sua proposta{price} para a equipe avaliar. Quer que eu encaminhe?",
        "human": ("Posso encaminhar agora para a equipe da Z-SWAP, que decide parcerias. Vou enviar um resumo "
                  "do que você me contou e o seu contato do Telegram{handle}."),
        "human_empty": " Antes, me diga em uma frase qual é a proposta, para a equipe saber do que se trata.",
        "confirm_q": " Posso encaminhar?",
        "forwarded": ("Encaminhei sua proposta para a equipe da Z-SWAP com o seu contato do Telegram{handle}. "
                      "Se houver interesse, alguém da equipe fala com você diretamente. Nenhum valor, pagamento, "
                      "contrato ou prazo está confirmado nesta etapa."),
        "forward_failed": ("Não consegui encaminhar agora: o canal com a equipe está indisponível. Tente de novo "
                           "mais tarde; nada foi confirmado."),
        "forward_limit": ("Você já tem propostas encaminhadas hoje. A equipe avalia o que recebeu e fala com você "
                          "se houver interesse."),
        "already": ("Sua proposta já foi encaminhada para a equipe. Se houver interesse, alguém fala com você "
                    "diretamente pelo Telegram. Eu não consigo confirmar valores nem prazos."),
        "declined": "Tudo bem, não encaminhei nada. Se quiser, me conte mais detalhes da proposta.",
        "details": "Anotei.",
        "team_decides": "Isso é decidido pela equipe da Z-SWAP; eu não aprovo propostas, valores nem prazos.",
        "already_case": ("Seu pedido já foi encaminhado para a equipe. Alguém fala com você diretamente pelo Telegram. "
                         "Se quiser, pode me contar mais detalhes aqui enquanto isso."),
        "forwarded_case": ("Encaminhei seu pedido para a equipe da Z-SWAP com o seu contato do Telegram{handle}. "
                           "Alguém da equipe fala com você diretamente. Não envie seed phrase, chave privada ou senha a ninguém."),
        "unknown": ("Não tenho informação pública confirmada sobre isso, e prefiro não adivinhar. "
                    "Posso encaminhar sua pergunta para a equipe da Z-SWAP responder. Quer que eu encaminhe?"),
        "unknown_nohandoff": "Não tenho informação pública confirmada sobre isso, e prefiro não adivinhar.",
        "scam": ("Atenção: pedido para pagar ou enviar cripto a uma carteira como \"taxa\" de listagem, liberação ou "
                 "verificação é um golpe conhecido. A Z-SWAP não paga nem cobra taxas assim por mensagem, e nada aqui "
                 "deve ser pago. Não envie fundos a esse endereço."),
        "confirm_short": "Quer que eu encaminhe para a equipe?",
        "payment_short": "Esse pagamento eu não posso prometer: só a equipe decide.",
    },
    "en": {
        "opening": ("Great! To understand the proposal, tell me in one message: what kind of partnership "
                    "(for example, promotion in communities, AMA, content, technical integration or an event), "
                    "where it happens and whether there is a cost."),
        "no_program": ("Z-SWAP has no public paid-promotion program, and I don't approve prices, payments or "
                       "contracts. The team decides."),
        "ask_missing": "To forward it to the team, send me {missing}.",
        "offer_forward": "If you prefer, I can forward what you told me for human review now. Should I forward it?",
        "payment": ("I can't confirm payment: I'm Z-SWAP's AI and I don't approve prices, hiring or deadlines. "
                    "That is the team's decision."),
        "payment_offer": "I can forward your proposal{price} for the team to review. Should I forward it?",
        "human": ("I can forward this to the Z-SWAP team now; they decide on partnerships. I'll send a summary "
                  "of what you told me and your Telegram contact{handle}."),
        "human_empty": " First, tell me the proposal in one sentence so the team knows what it is about.",
        "confirm_q": " Should I forward it?",
        "forwarded": ("I forwarded your proposal to the Z-SWAP team with your Telegram contact{handle}. If there "
                      "is interest, someone from the team will contact you directly. No price, payment, contract "
                      "or deadline is confirmed at this stage."),
        "forward_failed": ("I couldn't forward it right now: the channel to the team is unavailable. Please try "
                           "again later; nothing was confirmed."),
        "forward_limit": ("You already have proposals forwarded today. The team reviews them and will contact you "
                          "if there is interest."),
        "already": ("Your proposal was already forwarded to the team. If there is interest, someone will contact "
                    "you directly on Telegram. I can't confirm prices or deadlines."),
        "declined": "Okay, I didn't forward anything. Tell me more about the proposal if you like.",
        "details": "Noted.",
        "team_decides": "That is decided by the Z-SWAP team; I don't approve proposals, prices or deadlines.",
        "already_case": ("Your request was already forwarded to the team. Someone will contact you directly on Telegram. "
                         "Feel free to share more details here in the meantime."),
        "forwarded_case": ("I forwarded your request to the Z-SWAP team with your Telegram contact{handle}. "
                           "Someone from the team will contact you directly. Never share your seed phrase, private key or password."),
        "unknown": ("I don't have confirmed public information about that, and I'd rather not guess. "
                    "I can forward your question to the Z-SWAP team. Should I forward it?"),
        "unknown_nohandoff": "I don't have confirmed public information about that, and I'd rather not guess.",
        "scam": ("Warning: a request to pay or send crypto to a wallet as a listing, release or verification \"fee\" "
                 "is a known scam. Z-SWAP does not pay or charge fees like this by message. Do not send funds to that address."),
        "confirm_short": "Should I forward it to the team?",
        "payment_short": "I can't promise that payment: only the team decides.",
    },
    "es": {
        "opening": ("¡Qué bien! Para entender la propuesta, cuéntame en un mensaje: qué tipo de alianza "
                    "(por ejemplo, difusión en comunidades, AMA, contenido, integración técnica o evento), "
                    "dónde ocurre y si implica algún valor."),
        "no_program": ("Z-SWAP no tiene un programa público de difusión pagada, y yo no apruebo valores, pagos "
                       "ni contratos. Decide el equipo."),
        "ask_missing": "Para enviarlo al equipo, mándame {missing}.",
        "offer_forward": "Si prefieres, envío ahora lo que me contaste para revisión humana. ¿Lo envío?",
        "payment": ("No puedo confirmar pago: soy la IA de Z-SWAP y no apruebo valores, contratación ni plazos. "
                    "Eso lo decide el equipo."),
        "payment_offer": "Puedo enviar tu propuesta{price} para que el equipo la evalúe. ¿La envío?",
        "human": ("Puedo enviarlo ahora al equipo de Z-SWAP, que decide las alianzas. Enviaré un resumen de lo "
                  "que me contaste y tu contacto de Telegram{handle}."),
        "human_empty": " Antes, dime en una frase cuál es la propuesta, para que el equipo sepa de qué se trata.",
        "confirm_q": " ¿Lo envío?",
        "forwarded": ("Envié tu propuesta al equipo de Z-SWAP con tu contacto de Telegram{handle}. Si hay "
                      "interés, alguien del equipo te escribirá directamente. Ningún valor, pago, contrato o plazo "
                      "está confirmado en esta etapa."),
        "forward_failed": ("No pude enviarlo ahora: el canal con el equipo no está disponible. Inténtalo más tarde; "
                           "no se confirmó nada."),
        "forward_limit": ("Ya tienes propuestas enviadas hoy. El equipo las revisa y te escribirá si hay interés."),
        "already": ("Tu propuesta ya fue enviada al equipo. Si hay interés, alguien te escribirá directamente por "
                    "Telegram. No puedo confirmar valores ni plazos."),
        "declined": "De acuerdo, no envié nada. Si quieres, cuéntame más detalles de la propuesta.",
        "details": "Anotado.",
        "team_decides": "Eso lo decide el equipo de Z-SWAP; yo no apruebo propuestas, valores ni plazos.",
        "already_case": ("Tu solicitud ya fue enviada al equipo. Alguien te escribirá directamente por Telegram. "
                         "Si quieres, puedes contarme más detalles aquí mientras tanto."),
        "forwarded_case": ("Envié tu solicitud al equipo de Z-SWAP con tu contacto de Telegram{handle}. "
                           "Alguien del equipo te escribirá directamente. Nunca compartas tu frase semilla, clave privada o contraseña."),
        "unknown": ("No tengo información pública confirmada sobre eso y prefiero no adivinar. "
                    "Puedo enviar tu pregunta al equipo de Z-SWAP. ¿La envío?"),
        "unknown_nohandoff": "No tengo información pública confirmada sobre eso y prefiero no adivinar.",
        "scam": ("Atención: pedir que se pague o envíe cripto a una billetera como \"tarifa\" de listado, liberación o "
                 "verificación es una estafa conocida. Z-SWAP no paga ni cobra tarifas así por mensaje. No envíes fondos a esa dirección."),
        "confirm_short": "¿Lo envío al equipo?",
        "payment_short": "Ese pago no lo puedo prometer: solo decide el equipo.",
    },
}


_GREETINGS = {
    "freyr": {"pt": "Oi! Sou o FREYR, cuido de parcerias da Z-SWAP. Me conte o que você tem em mente: o que você faz, onde e o que propõe.",
              "en": "Hi! I'm FREYR, I handle partnerships at Z-SWAP. Tell me what you have in mind: what you do, where, and what you propose.",
              "es": "¡Hola! Soy FREYR, me ocupo de las alianzas de Z-SWAP. Cuéntame qué tienes en mente: qué haces, dónde y qué propones."},
    "eir": {"pt": "Oi! Sou a EIR, do suporte da Z-SWAP. Me conte o que aconteceu e em qual rede ou carteira.",
            "en": "Hi! I'm EIR from Z-SWAP support. Tell me what happened and on which network or wallet.",
            "es": "¡Hola! Soy EIR, del soporte de Z-SWAP. Cuéntame qué pasó y en qué red o billetera."},
    "mimir": {"pt": "Oi! Sou o MIMIR, cuido das dúvidas técnicas da Z-SWAP. Qual é a sua pergunta?",
              "en": "Hi! I'm MIMIR, I handle technical questions at Z-SWAP. What's your question?",
              "es": "¡Hola! Soy MIMIR, me ocupo de las dudas técnicas de Z-SWAP. ¿Cuál es tu pregunta?"},
}


def saudacao(agente: str, language: str) -> str:
    opcoes = _GREETINGS.get(agente, _GREETINGS["freyr"])
    return opcoes[_lang(language)]


def resposta_de_reserva(lead: "Lead | None", s: Sinais, language: str, *, pode_encaminhar: bool) -> str | None:
    """Quando o guarda barra a resposta do modelo numa conversa de PROPOSTA, a reserva
    não é o genérico "não sei": repete o que foi entendido (com os dados que a pessoa
    deu), diz com clareza o que só a equipe decide e oferece o encaminhamento.
    ``None`` = sem proposta reconhecível; o chamador usa a reserva genérica."""
    if lead is None or not (lead.kinds or lead.paid or lead.price):
        return None
    lang = _lang(language)
    t = _TXT[lang]
    partes = [_understood(lead, lang)]
    if s.asks_payment or s.paid_offer or s.price or lead.paid:
        partes.append(t["payment"])
    else:
        partes.append(t["team_decides"])
    if pode_encaminhar:
        preco = f" ({lead.price})" if lead.price else ""
        partes.append(t["payment_offer"].format(price=preco))
    return " ".join(p for p in partes if p)


def texto(chave: str, language: str, **fmt: str) -> str:
    return _TXT[_lang(language)][chave].format(**fmt)


def decidir(lead: Lead | None, s: Sinais, *, handle: str = "") -> Passo | None:
    """What FREYR answers in private. ``None`` = not a lead turn (the AI answers).

    The caller owns the window: it creates ``lead`` when this returns a step for
    a new lead, absorbs the signals before calling, forwards when ``forward``.
    """
    if lead is None:
        return None
    lang = _lang(lead.language)
    t = _TXT[lang]
    h = f" ({handle})" if handle else ""

    if lead.forwarded_at is not None:
        if s.asks_human or s.asks_payment or s.confirms:
            return Passo(t["already"])
        if s.product_question:
            return None
        return Passo(t["already"])

    if lead.awaiting_confirm and s.confirms:
        return Passo("", forward=True)
    if lead.awaiting_confirm and s.declines:
        lead.awaiting_confirm = False
        return Passo(t["declined"])

    if s.product_question and not (s.asks_human or s.asks_payment):
        return None

    if s.asks_human:
        lead.awaiting_confirm = True
        reply = t["human"].format(handle=h)
        reply += t["human_empty"] if not lead.has_substance else t["confirm_q"]
        return Passo(reply)

    if s.asks_payment:
        lead.awaiting_confirm = True
        price = f" ({lead.price})" if lead.price else ""
        parts = [_uma_vez(lead, "understood:" + _understood(lead, lang), _understood(lead, lang))]
        parts.append(t["payment"] if "payment" not in lead.said else t["payment_short"])
        lead.said.add("payment")
        parts.append(t["payment_offer"].format(price=price))
        return Passo(" ".join(p for p in parts if p))

    if not lead.kinds and not (lead.channels or lead.price):
        return Passo(t["opening"])
    return Passo(" ".join(_novidades(lead, lang)))


def _uma_vez(lead: Lead, chave: str, texto_: str) -> str:
    """Devolve ``texto_`` só na primeira vez que esta informação aparece na conversa."""
    if not texto_ or chave in lead.said:
        return ""
    lead.said.add(chave)
    return texto_


def _novidades(lead: Lead, lang: str) -> list[str]:
    t = _TXT[lang]
    understood = _understood(lead, lang)
    parts = [_uma_vez(lead, "understood:" + understood, understood)]
    if lead.paid or "promotion" in lead.kinds:
        parts.append(_uma_vez(lead, "no_program", t["no_program"]))
    missing = _missing(lead, lang)
    if missing:
        parts.append(_uma_vez(lead, "missing:" + missing, t["ask_missing"].format(missing=missing)))
    if not any(parts):
        parts.append(t["details"])
    lead.awaiting_confirm = True
    parts.append(t["offer_forward"] if "offer_forward" not in lead.said else t["confirm_short"])
    lead.said.add("offer_forward")
    return [p for p in parts if p]


def estado_para_modelo(lead: Lead | None, agora_: float) -> str:
    """Memória do sistema sobre esta conversa, para o modelo (não é fala da pessoa)."""
    if lead is None:
        return ""
    labels = _KIND_LABEL["pt"]
    linhas = ["[Memória do sistema sobre esta conversa — fatos já ditos pela pessoa]"]
    idioma_ = {"en": "Conversation language: English. Reply in English.",
               "es": "Idioma de la conversación: español. Responde en español.",
               "zh": "对话语言：中文。请用中文回答。"}.get(lead.language)
    if idioma_:
        # Sem histórico (reinício) nada ancora o idioma; escrita NO idioma, porque a mesma
        # instrução em português puxou uma resposta em inglês para o português (bateria 2026-11-21).
        linhas.append(idioma_)
    if lead.kinds:
        linhas.append("Proposta: " + ", ".join(labels.get(k, k) for k in lead.kinds))
    if lead.paid or lead.price:
        linhas.append("Serviço pago: sim" + (f"; valor pedido: {lead.price}" if lead.price
                                             else ("" if lead.restaurado else "; valor ainda não informado")))
    if lead.channels or lead.community_count or lead.platforms:
        linhas.append("Onde: " + ", ".join(lead.platforms + lead.channels
                                           + ([lead.community_count] if lead.community_count else [])))
    if lead.audience or not lead.restaurado:
        linhas.append("Audiência: " + (lead.audience or "não informada"))
    if lead.restaurado:
        linhas.append("Detalhes ditos antes (valor, audiência, canais): não estão nesta memória. "
                      "Não invente e não diga que a pessoa não informou; se precisar, pergunte de forma breve.")
    if lead.human_requested:
        linhas.append("A pessoa pediu para falar com um humano.")
    if lead.forwarded_at is not None:
        minutos = max(1, int((agora_ - lead.forwarded_at) // 60))
        linhas.append(f"Encaminhamento: JÁ ENVIADO à equipe há {minutos} min. Não ofereça de novo; "
                      "diga que a equipe fala com a pessoa diretamente se houver interesse.")
    elif lead.awaiting_confirm and lead.offer_open:
        linhas.append("Encaminhamento: já oferecido na resposta anterior; se a pessoa disser sim, o sistema "
                      "encaminha. Não repita nem mencione a oferta.")
    elif lead.awaiting_confirm:
        linhas.append("Encaminhamento: oferecido antes; se fizer sentido, pode perguntar de novo se a pessoa quer.")
    else:
        linhas.append("Encaminhamento: ainda não oferecido.")
    return "\n".join(linhas)


def resumo_operador(lead: Lead, *, handle: str, user_id: int, agente: str = "FREYR") -> str:
    labels = _KIND_LABEL["pt"]
    titulo = ("FREYR — PROPOSTA DE PARCERIA (conversa privada)" if agente == "FREYR"
              else f"{agente} — PEDIDO DE ATENDIMENTO HUMANO (conversa privada)")
    linhas = [titulo,
              f"Contato: {handle or '(sem @usuário)'} · Telegram id {user_id}"]
    if lead.kinds:
        linhas.append("Tipo: " + ", ".join(labels.get(k, k) for k in lead.kinds))
    if lead.paid or lead.price:
        linhas.append("Serviço pago: sim" + (f" · valor pedido: {lead.price}" if lead.price else ""))
    if lead.platforms:
        linhas.append("Plataformas: " + ", ".join(lead.platforms))
    if lead.channels:
        linhas.append("Canais: " + ", ".join(lead.channels))
    if lead.community_count:
        linhas.append("Comunidades: " + lead.community_count)
    if lead.audience:
        linhas.append("Audiência: " + lead.audience)
    if lead.notes:
        linhas.append("O que a pessoa escreveu:")
        linhas.extend(f"- {n}" for n in lead.notes)
    if lead.restaurado:
        linhas.append("Obs.: o ZION reiniciou durante a conversa. Por privacidade, valor, audiência, canais e o "
                      "texto da pessoa ditos antes disso não ficam guardados; confirme direto com a pessoa.")
    linhas.append("Pediu contato humano: " + ("sim" if lead.human_requested else "não"))
    linhas.append(f"Decisão humana necessária: SIM ({agente} não aprovou valor, pagamento, contrato, prazo ou reembolso)")
    return "\n".join(linhas)


def agora() -> float:
    # Relógio de parede (não monotônico): a memória do privado é gravada no banco e
    # precisa continuar valendo depois de um reinício (2026-11-21).
    return time.time()


# ── persistência (sobrevive a reinício) ────────────────────────────────────
# Só ESTADO, nunca conteúdo: conversa privada de parceria não pode aparecer no SQLite
# nem em logs (docs/DEPLOYMENT-MODEL.md). Valor, audiência, canais e o texto da pessoa
# ficam só na memória do processo e se perdem num reinício — o resumo avisa o operador.

_KIND_NAMES = frozenset(nome for nome, _rx in _KINDS)
_PLATFORM_NAMES = frozenset(nome for nome, _rx in _PLATFORMS)
_SAID_KEY = re.compile(r"^[a-z_]{1,40}$")      # só as chaves fixas; "understood:<texto>" não sai daqui


def lead_para_dict(lead: Lead) -> dict:
    return {
        "language": lead.language, "updated": lead.updated,
        "kinds": [k for k in lead.kinds if k in _KIND_NAMES],
        "platforms": [p for p in lead.platforms if p in _PLATFORM_NAMES],
        "paid": bool(lead.paid or lead.price), "human_requested": bool(lead.human_requested),
        "awaiting_confirm": bool(lead.awaiting_confirm), "offer_open": bool(lead.offer_open),
        "forwarded_at": lead.forwarded_at,
        "said": sorted(k for k in lead.said if _SAID_KEY.match(k)),
    }


def lead_de_dict(d: dict, now: float) -> Lead | None:
    """Reconstrói só o vocabulário conhecido; qualquer coisa estranha = sem lead
    (a conversa recomeça sem memória e nada é encaminhado sem um novo "sim")."""
    try:
        updated = float(d["updated"])
        if updated > now + 300:
            return None
        language = d.get("language")
        lead = Lead(language=language if language in ("pt", "en", "es", "zh") else "pt", updated=updated)
        lead.kinds = [k for k in (d.get("kinds") or [])[:6] if isinstance(k, str) and k in _KIND_NAMES]
        lead.platforms = [p for p in (d.get("platforms") or [])[:6] if isinstance(p, str) and p in _PLATFORM_NAMES]
        lead.paid = d.get("paid") is True
        lead.human_requested = d.get("human_requested") is True
        lead.awaiting_confirm = d.get("awaiting_confirm") is True
        lead.offer_open = d.get("offer_open") is True
        f = d.get("forwarded_at")
        lead.forwarded_at = float(f) if isinstance(f, (int, float)) and not isinstance(f, bool) else None
        lead.said = {k for k in (d.get("said") or [])[:40] if isinstance(k, str) and _SAID_KEY.match(k)}
        lead.restaurado = True
        return lead
    except (KeyError, TypeError, ValueError, AttributeError):
        return None


# ── não repetir a oferta pendente ──────────────────────────────────────────

_RESTO_DE_OFERTA = re.compile(
    r"^(?:confirme se (?:deseja|quer)|assim que (?:voce )?confirmar|basta confirmar|se (?:quiser|preferir),? (?:e so|basta) confirmar|"
    r"voce gostaria\??|you can confirm|just confirm|confirma si|"
    r"(?:como )?ja (?:te )?ofereci|lembre(?:-se)? de (?:me )?confirmar|e so (?:confirmar|responder|dizer)|"
    r"basta (?:responder|dizer)|"
    # eco da memória do sistema (bateria 2026-11-21): "(A oferta anterior ainda está em aberto.)"
    r"\(?(?:a )?oferta (?:anterior |de encaminhamento )?(?:ainda )?(?:esta|continua|segue) (?:em aberto|valendo|de pe))")


def sem_oferta_repetida(texto: str) -> str:
    """Tira a(s) frase(s) que oferecem encaminhar de novo quando a oferta anterior ainda
    está pendente (o modelo pequeno ignora a instrução). Se sobrar quase nada, devolve
    o texto original: melhor repetir do que responder vazio."""
    from .response_guard import offers_human_handoff
    frases = re.findall(r"[^.!?\n]+[.!?]*|\n+", texto or "")
    mantidas = [f for f in frases
                if f.strip() == "" or not (offers_human_handoff(f) or _RESTO_DE_OFERTA.match(_fold(f.strip())))]
    resultado = re.sub(r"\n{3,}", "\n\n", "".join(mantidas)).strip()
    # "Quer que eu faça isso?" que apontava para a oferta removida sai junto
    from .text_cleanup import limpar_listas_orfas
    resultado = limpar_listas_orfas(texto or "", resultado)
    return resultado if len(resultado) >= 40 else (texto or "").strip()


_PERGUNTAS = re.compile(r"[^.!?？\n]*[?？]")


def ultima_pergunta(texto: str) -> str | None:
    """A última pergunta da resposta: é ela que um "sim" solto responde."""
    perguntas = [p.strip() for p in _PERGUNTAS.findall(texto or "") if p.strip(" ?？¿")]
    return perguntas[-1] if perguntas else None
