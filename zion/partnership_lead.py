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

Nothing here is persisted. Raw text kept in a lead is bounded, and the caller
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
        r"postagens?|posts? patrocinad\w*)\b")),
    ("ama", re.compile(r"\b(?:amas?|ask me anything|spaces?|lives?)\b")),
    ("integration", re.compile(r"\b(?:integra\w*|listagem|listar|listing|api|sdk)\b")),
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
_CHANNEL = re.compile(r"(?:https?://)?(?:t\.me|telegram\.me|x\.com|twitter\.com|youtube\.com|discord\.gg)/[\w/+-]{2,64}|@[A-Za-z0-9_]{4,32}")
_AUDIENCE = re.compile(
    r"\b\d[\d.,]*\s?(?:k|mil)?\s?(?:membros|members|miembros|seguidores|followers|pessoas|inscritos|"
    r"subscribers|usuarios|users)\b")
_COMMUNITY_COUNT = re.compile(r"\b(?:\d+|v[aá]rias|muitas|several|many)\s+(?:comunidades|communities|grupos|groups|canais|channels)\b")
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
    audience: str | None
    community_count: str | None
    product_question: bool

    @property
    def lead_signal(self) -> bool:
        return bool(self.kinds or self.interest or self.paid_offer or self.asks_payment or self.price
                    or self.asks_human or self.channels or self.audience or self.community_count)


def analisar(text: str) -> Sinais:
    folded = _fold(text)
    short = len(folded) <= 40
    lowered = " ".join((text or "").lower().split())
    price = _PRICE.search(lowered)
    audience = _AUDIENCE.search(folded)
    count = _COMMUNITY_COUNT.search(lowered) or _COMMUNITY_COUNT.search(folded)
    kinds = tuple(name for name, rx in _KINDS if rx.search(folded))
    asks_payment = bool(_ASKS_PAYMENT.search(folded))
    return Sinais(
        kinds=kinds,
        interest=bool(_INTEREST.search(folded)),
        paid_offer=bool(_PAID_OFFER.search(folded)) or (bool(price) and not asks_payment),
        asks_payment=asks_payment,
        price=price.group(0).strip() if price else None,
        asks_human=bool(_ASKS_HUMAN.search(folded)),
        confirms=short and bool(_CONFIRM.search(folded)),
        declines=short and bool(_DECLINE.search(folded)),
        channels=tuple(dict.fromkeys(m.group(0) for m in _CHANNEL.finditer(text or "")))[:6],
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

    @property
    def has_substance(self) -> bool:
        return bool(self.kinds or self.notes or self.channels or self.price)

    def absorver(self, s: Sinais, text: str, now: float) -> None:
        self.updated = now
        for k in s.kinds:
            if k not in self.kinds:
                self.kinds.append(k)
        for c in s.channels:
            if c not in self.channels and len(self.channels) < 6:
                self.channels.append(c)
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

    def start(self, key: tuple[int, int], language: str, now: float) -> Lead:
        if len(self._leads) >= self.max_entries:
            for stale in sorted(self._leads, key=lambda k: self._leads[k].updated)[: max(1, self.max_entries // 8)]:
                self._leads.pop(stale, None)
        lead = Lead(language=language, updated=now)
        self._leads[key] = lead
        return lead

    def may_forward(self, user_id: int, now: float) -> bool:
        recent = [t for t in self._forwards.get(user_id, []) if now - t < 86400]
        self._forwards[user_id] = recent
        return len(recent) < MAX_FORWARDS_PER_DAY

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
    "pt": {"promotion": "divulgação da Z-SWAP", "ama": "AMAs", "integration": "integração",
           "content": "criação de conteúdo", "event": "eventos"},
    "en": {"promotion": "promoting Z-SWAP", "ama": "AMAs", "integration": "integration",
           "content": "content creation", "event": "events"},
    "es": {"promotion": "difusión de Z-SWAP", "ama": "AMAs", "integration": "integración",
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
    if lead.channels or lead.community_count or any("telegram" in _fold(n) for n in lead.notes):
        where = {"pt": " em comunidades do Telegram", "en": " in Telegram communities",
                 "es": " en comunidades de Telegram"}[lang]
    paid = {"pt": ", como serviço pago", "en": ", as a paid service", "es": ", como servicio pagado"}[lang] if lead.paid else ""
    price = f" ({lead.price})" if lead.price else ""
    return {"pt": "Entendi: você oferece ", "en": "Got it: you are offering ",
            "es": "Entendido: ofreces "}[lang] + _join(kinds, lang) + where + paid + price + "."


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
        "confirm_short": "¿Lo envío al equipo?",
        "payment_short": "Ese pago no lo puedo prometer: solo decide el equipo.",
    },
}


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


def resumo_operador(lead: Lead, *, handle: str, user_id: int) -> str:
    labels = _KIND_LABEL["pt"]
    linhas = ["FREYR — PROPOSTA DE PARCERIA (conversa privada)",
              f"Contato: {handle or '(sem @usuário)'} · Telegram id {user_id}"]
    if lead.kinds:
        linhas.append("Tipo: " + ", ".join(labels.get(k, k) for k in lead.kinds))
    if lead.paid or lead.price:
        linhas.append("Serviço pago: sim" + (f" · valor pedido: {lead.price}" if lead.price else ""))
    if lead.channels:
        linhas.append("Canais: " + ", ".join(lead.channels))
    if lead.community_count:
        linhas.append("Comunidades: " + lead.community_count)
    if lead.audience:
        linhas.append("Audiência: " + lead.audience)
    if lead.notes:
        linhas.append("O que a pessoa escreveu:")
        linhas.extend(f"- {n}" for n in lead.notes)
    linhas.append("Pediu contato humano: " + ("sim" if lead.human_requested else "não"))
    linhas.append("Decisão humana necessária: SIM (FREYR não aprovou valor, pagamento, contrato ou prazo)")
    return "\n".join(linhas)


def agora() -> float:
    return time.monotonic()
