from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from .agents import (
    DEFAULT_AGENT_REGISTRY,
    AgentProfile,
    AgentRegistry,
    AgentRole,
    ConversationIntent,
)


def _fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    return "".join(
        char for char in normalized if not unicodedata.combining(char)
    ).casefold()


_PARTNERSHIP = re.compile(
    r"\b(?:parceria|partner(?:ship)?|business|comercial|b2b|empresa|"
    r"projeto|integracao comercial|integrar (?:nossa|minha)|afiliad|"
    r"patrocin|sponsor|listing|market maker|liquidez institucional)\b"
)
_SUPPORT = re.compile(
    r"\b(?:nao conecta|nao consigo|erro|falha|bug|problema|travou|"
    r"carteira|wallet|saldo|transacao|swap|bridge|ordem|plano|assinatura|"
    r"como (?:faco|usar|conectar|trocar|comprar|vender)|passo a passo|"
    r"ajuda|support|suporte|troubleshoot)\b"
)
_SUPPORT_PROBLEM = re.compile(
    r"\b(?:nao|erro|falha|bug|problema|travou|pendente|sumiu|"
    r"recusad|rejeitad|nao consigo|ajuda|suporte|support)\b"
)
_SUPPORT_ACTION = re.compile(
    r"\b(?:como (?:faco|usar|conectar|trocar|comprar|vender)|"
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
    r"boa noite|ola|oi|salve|estou perdido|nao estou entendendo)\b"
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
    ) -> RouteDecision:
        return RouteDecision(
            intent=intent,
            speaker=self.registry.speaker_for(intent),
            confidence=max(0.0, min(1.0, confidence)),
            reason=reason,
        )

    def route_group(
        self,
        text: str,
        *,
        moderation_detected: bool = False,
        explicitly_addressed: bool = False,
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
            )
        if partnership:
            return self._decision(
                ConversationIntent.PARTNERSHIP,
                confidence=0.98,
                reason="explicit_partnership",
            )
        if support and support_problem:
            return self._decision(
                ConversationIntent.SUPPORT,
                confidence=0.97,
                reason="user_problem",
            )
        if technical and question:
            return self._decision(
                ConversationIntent.TECHNICAL,
                confidence=0.95,
                reason="technical_question",
            )
        if support and support_action:
            return self._decision(
                ConversationIntent.SUPPORT,
                confidence=0.90,
                reason="operational_question",
            )
        if community and question:
            return self._decision(
                ConversationIntent.COMMUNITY,
                confidence=0.90,
                reason="community_question",
            )
        if support and question:
            return self._decision(
                ConversationIntent.SUPPORT,
                confidence=0.85,
                reason="support_topic_question",
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
            )
        if explicitly_addressed:
            return self._decision(
                ConversationIntent.AMBIGUOUS,
                confidence=0.0,
                reason="addressed_but_ambiguous",
            )
        return self._decision(
            ConversationIntent.UNRELATED,
            confidence=0.95,
            reason="no_official_intent",
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
