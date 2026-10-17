from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from .agents import (
    DEFAULT_AGENT_REGISTRY,
    AgentId,
    AgentProfile,
    AgentRegistry,
    AgentRole,
    ConversationIntent,
)
from .models import AIRouteClassification


def _fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    return "".join(
        char for char in normalized if not unicodedata.combining(char)
    ).casefold()


_PARTNERSHIP = re.compile(
    r"\b(?:parcerias?|partner(?:ship)?|business|comercial|b2b|empresa|"
    r"projeto|integracao comercial|integrar (?:nossa|minha)|afiliad|"
    r"patrocin|sponsor|listing|market maker|liquidez institucional)\b"
)
_SUPPORT = re.compile(
    r"\b(?:nao conecta|nao consigo|erro|falha|bug|problem(?:a|inha)|travou|"
    r"carteira|wallet|saldo|transacao|swap|bridge|ordem|plano|assinatura|"
    r"como (?:faco|usar|conectar|trocar|comprar|vender|"
    r"(?:posso )?resolver)|passo a passo|"
    r"ajuda|support|suporte|troubleshoot)\b"
)
_SUPPORT_PROBLEM = re.compile(
    r"\b(?:nao|erro|falha|bug|problem(?:a|inha)|travou|pendente|sumiu|"
    r"recusad|rejeitad|nao consigo|ajuda|suporte|support)\b"
)
_SUPPORT_ACTION = re.compile(
    r"\b(?:como (?:faco|usar|conectar|trocar|comprar|vender|"
    r"(?:posso )?resolver)|"
    r"passo a passo|preciso de ajuda|me ajuda)\b"
)
_TECHNICAL = re.compile(
    r"\b(?:arquitetura|technical paper|tecnico|tecnica|tecnologia|"
    r"roteamento|routing|multi[- ]?chain|chain|blockchain|rede|evm|solana|"
    r"ethereum|arbitrum|optimism|polygon|avalanche|base|bnb|0x|lifi|"
    r"li\.fi|jupiter|cow protocol|dex|cex|api|sdk|smart contract|"
    r"contrato inteligente|liquidez|slippage|terminal pro|indicador|"
    r"ema|vwap|bollinger|rsi|macd|stochastic|obv|atr|oco)\b"
)
_COMMUNITY = re.compile(
    r"\b(?:zion|z[- ]?swap|comunidade|community|grupo|regras|guardian|"
    r"moderacao|onboarding|quem (?:sao|e)|o que e|bom dia|boa tarde|"
    r"boa noite|ola|oi|salve|estou perdido|nao estou entendendo|"
    r"cronograma (?:de |do |da )?lancamento|lancamento da plataforma|"
    r"roadmap)\b"
)
_CONFIDENTIALITY = re.compile(
    r"\b(?:system prompt|prompt do sistema|ignore (?:as )?instrucoes|"
    r"ip do servidor|ssh|firewall|schema sql|rota admin|api key|token|"
    r"segredo|secret|fonte interna|arquivo interno|repositorio|commit)\b"
)
_QUESTION = re.compile(
    r"\?|\b(?:como|qual|quais|quando|onde|porque|por que|o que|"
    r"pode|podem|tem|existe|funciona)\b"
)


@dataclass(frozen=True, slots=True)
class RouteDecision:
    intent: ConversationIntent
    speaker: AgentProfile | None
    confidence: float
    reason: str
    handoff_from: AgentId | None = None
    used_ai_fallback: bool = False

    @property
    def handoff_count(self) -> int:
        return int(
            self.handoff_from is not None
            and self.speaker is not None
            and self.handoff_from is not self.speaker.agent_id
        )


class IntentRouter:
    """Deterministic high-confidence group router.

    Ambiguous inputs fail to silence. A future bounded AI classifier may only
    return an intent to this same registry; it cannot return a token, bot, or
    moderation action.
    """

    def __init__(
        self,
        registry: AgentRegistry = DEFAULT_AGENT_REGISTRY,
    ) -> None:
        self.registry = registry

    def _decision(
        self,
        intent: ConversationIntent,
        *,
        confidence: float,
        reason: str,
        handoff_from: AgentId | None = None,
        used_ai_fallback: bool = False,
    ) -> RouteDecision:
        return RouteDecision(
            intent=intent,
            speaker=self.registry.speaker_for(intent),
            confidence=max(0.0, min(1.0, confidence)),
            reason=reason,
            handoff_from=handoff_from,
            used_ai_fallback=used_ai_fallback,
        )

    def addressed_agent(self, text: str) -> AgentId | None:
        """Return one unambiguous official identity addressed in text."""

        folded = _fold(text)
        candidates: set[AgentId] = set()
        for profile in self.registry:
            names = {profile.agent_id.value}
            if profile.telegram_username:
                names.add(profile.telegram_username.casefold())
            if profile.agent_id is AgentId.MIMIR:
                names.add("mimir")
            for name in names:
                normalized = _fold(name)
                if re.search(
                    rf"(?<![a-z0-9_])@?{re.escape(normalized)}(?![a-z0-9_])",
                    folded,
                ):
                    candidates.add(profile.agent_id)
                    break
        if len(candidates) == 1:
            return next(iter(candidates))
        return None

    def route_group(
        self,
        text: str,
        *,
        moderation_detected: bool = False,
        explicitly_addressed: bool = False,
        addressed_agent: AgentId | None = None,
    ) -> RouteDecision:
        folded = _fold(text).strip()
        if moderation_detected:
            return self._decision(
                ConversationIntent.MODERATION,
                confidence=1.0,
                reason="deterministic_guardian",
            )
        if not folded:
            return self._decision(
                ConversationIntent.UNRELATED,
                confidence=1.0,
                reason="empty",
            )

        partnership = bool(_PARTNERSHIP.search(folded))
        support = bool(_SUPPORT.search(folded))
        support_problem = bool(_SUPPORT_PROBLEM.search(folded))
        support_action = bool(_SUPPORT_ACTION.search(folded))
        technical = bool(_TECHNICAL.search(folded))
        community = bool(_COMMUNITY.search(folded))
        confidentiality = bool(_CONFIDENTIALITY.search(folded))
        question = bool(_QUESTION.search(folded))

        if confidentiality:
            return self._decision(
                ConversationIntent.COMMUNITY,
                confidence=1.0,
                reason="confidentiality_boundary",
                handoff_from=addressed_agent,
            )
        if support and support_problem:
            return self._decision(
                ConversationIntent.SUPPORT,
                confidence=0.97,
                reason="user_problem",
                handoff_from=addressed_agent,
            )
        if partnership:
            return self._decision(
                ConversationIntent.PARTNERSHIP,
                confidence=0.98,
                reason="explicit_partnership",
                handoff_from=addressed_agent,
            )
        if technical and question:
            return self._decision(
                ConversationIntent.TECHNICAL,
                confidence=0.95,
                reason="technical_question",
                handoff_from=addressed_agent,
            )
        if support and support_action:
            return self._decision(
                ConversationIntent.SUPPORT,
                confidence=0.90,
                reason="operational_question",
                handoff_from=addressed_agent,
            )
        if community and question:
            return self._decision(
                ConversationIntent.COMMUNITY,
                confidence=0.90,
                reason="community_question",
                handoff_from=addressed_agent,
            )
        if support and question:
            return self._decision(
                ConversationIntent.SUPPORT,
                confidence=0.85,
                reason="support_topic_question",
                handoff_from=addressed_agent,
            )
        if explicitly_addressed and (technical or support):
            intent = (
                ConversationIntent.TECHNICAL
                if technical
                else ConversationIntent.SUPPORT
            )
            return self._decision(
                intent,
                confidence=0.80,
                reason="addressed_topic",
                handoff_from=addressed_agent,
            )
        if explicitly_addressed:
            return self._decision(
                ConversationIntent.AMBIGUOUS,
                confidence=0.0,
                reason="addressed_but_ambiguous",
                handoff_from=addressed_agent,
            )
        return self._decision(
            ConversationIntent.UNRELATED,
            confidence=0.95,
            reason="no_official_intent",
        )

    def accept_ai_fallback(
        self,
        initial: RouteDecision,
        fallback: AIRouteClassification | None,
        *,
        minimum_confidence: float = 0.80,
    ) -> RouteDecision:
        """Accept a bounded interpretation result without granting authority.

        AI is consulted only after deterministic routing chose silence. It may
        select one conversational intent from an allowlist. It cannot select
        moderation, a token, a bot outside the registry, or any action.
        """

        if initial.speaker is not None or initial.intent not in {
            ConversationIntent.AMBIGUOUS,
            ConversationIntent.UNRELATED,
        }:
            return initial
        if fallback is None or fallback.confidence < minimum_confidence:
            return initial
        try:
            intent = ConversationIntent(fallback.intent)
        except ValueError:
            return initial
        if intent in {
            ConversationIntent.MODERATION,
            ConversationIntent.AMBIGUOUS,
            ConversationIntent.UNRELATED,
        }:
            return initial
        speaker = self.registry.speaker_for(intent)
        if speaker is None:
            return initial
        return self._decision(
            intent,
            confidence=fallback.confidence,
            reason="bounded_ai_fallback",
            handoff_from=initial.handoff_from,
            used_ai_fallback=True,
        )

    def route_private(
        self,
        receiver: AgentProfile,
        text: str,
    ) -> RouteDecision:
        """Keep an allowed DM on its receiving identity.

        DM access must already have been approved. Cross-agent handoff is a
        separate explicit decision and never occurs by pretending the receiver
        has another identity.
        """

        role_intent = {
            AgentRole.COMMUNITY: ConversationIntent.COMMUNITY,
            AgentRole.TECHNICAL: ConversationIntent.TECHNICAL,
            AgentRole.SUPPORT: ConversationIntent.SUPPORT,
            AgentRole.BUSINESS: ConversationIntent.PARTNERSHIP,
        }[receiver.role]
        if not (text or "").strip():
            return self._decision(
                ConversationIntent.UNRELATED,
                confidence=1.0,
                reason="empty_private_message",
            )
        speaker = self.registry.speaker_for(role_intent)
        if speaker is None or speaker.agent_id is not receiver.agent_id:
            return self._decision(
                ConversationIntent.AMBIGUOUS,
                confidence=0.0,
                reason="receiver_authority_mismatch",
            )
        return RouteDecision(
            intent=role_intent,
            speaker=receiver,
            confidence=1.0,
            reason="authorized_private_receiver",
        )
