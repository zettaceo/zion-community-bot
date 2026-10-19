"""Local allowlisted public knowledge operations; never a general executor.

Results are snapshots from the reviewed corpus, not live availability claims.
Caller supplies trusted identity; model arguments cannot select identity, paths,
URLs, classification or privilege. No provider-specific tool schema is assumed.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType

from .agents import AgentId
from .knowledge import KnowledgeBase, KnowledgeClassification
from .language_recovery import recover_language


_QUERIES = MappingProxyType({
    'get_current_fee_policy': 'taxas plataforma EVM Solana fee politica',
    'get_plan_matrix': 'planos Free Pro Trader Pilot limites beneficios',
    'get_feature_status': 'estado lancamento recursos soon pre-launch beta',
    'get_public_roadmap': 'cronograma roadmap lancamento soon pre-launch',
    'get_supported_networks': 'redes suportadas blockchains ZETTA Chain',
    'get_public_integrations': 'corretoras CEX integracoes suportadas',
    'get_public_security_summary': 'seguranca riscos nao custodial chaves permissoes',
})
TOOL_NAMES = frozenset(_QUERIES) | {'search_approved_knowledge', 'get_public_api_capabilities'}


class KnowledgeToolError(ValueError):
    """Only fixed error codes are exposed; never echo supplied arguments."""


@dataclass(frozen=True, slots=True)
class PublicEvidence:
    heading: str
    text: str


@dataclass(frozen=True, slots=True)
class KnowledgeToolResult:
    operation: str
    evidence: tuple[PublicEvidence, ...]
    status: str
    classification: str = 'PUBLIC'
    provenance: str = 'reviewed_corpus_snapshot_not_live_probe'

    def render(self) -> str:
        return '\n\n'.join('[Contexto oficial: ' + item.heading + ']\n' + item.text
                           for item in self.evidence)


class KnowledgeTools:
    def __init__(self, knowledge: KnowledgeBase):
        self._knowledge = knowledge

    def call(self, operation: str, arguments: dict, *, agent_id: AgentId | str) -> KnowledgeToolResult:
        if not isinstance(operation, str) or operation not in TOOL_NAMES:
            raise KnowledgeToolError('unknown_operation')
        if not isinstance(arguments, dict):
            raise KnowledgeToolError('invalid_arguments')
        try:
            agent = AgentId(agent_id)
        except (ValueError, TypeError):
            raise KnowledgeToolError('invalid_agent') from None
        if operation == 'search_approved_knowledge':
            if set(arguments) != {'query'}:
                raise KnowledgeToolError('invalid_arguments')
            query = arguments['query']
            if not isinstance(query, str) or not query.strip() or len(query) > 6000:
                raise KnowledgeToolError('invalid_query')
            query = recover_language(query).canonical
        else:
            if arguments:
                raise KnowledgeToolError('invalid_arguments')
            if operation == 'get_public_api_capabilities':
                # No approved public interface publication exists in this
                # version. Never infer endpoints from generic API mentions.
                return KnowledgeToolResult(operation, (), 'NOT_PUBLISHED')
            query = _QUERIES[operation]
        if self._knowledge.load_errors:
            return KnowledgeToolResult(operation, (), 'SOURCE_INVALID')
        chunks = self._knowledge.search(query, limit=12, agent_id=agent)
        evidence = []
        remaining = 8000
        for chunk in chunks:
            # Defense in depth: do not trust a future retrieval implementation
            # to enforce both source status and audience classification.
            if (not chunk.authority.allows(agent)
                    or chunk.authority.classification is not KnowledgeClassification.PUBLIC):
                continue
            size = len(chunk.heading) + len(chunk.text) + 24
            if size > remaining:
                continue  # Never truncate a finite list or status qualifier.
            evidence.append(PublicEvidence(chunk.heading, chunk.text))
            remaining -= size
        return KnowledgeToolResult(operation, tuple(evidence), 'FOUND' if evidence else 'NO_EVIDENCE')
