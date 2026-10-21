"""Local allowlisted public knowledge operations; never a general executor.

Results are snapshots from the reviewed corpus, not live availability claims.
Caller supplies trusted identity; model arguments cannot select identity, paths,
URLs, classification or privilege. No provider-specific tool schema is assumed.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import re
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
TOOL_NAMES = frozenset(_QUERIES) | {'search_approved_knowledge', 'get_public_api_capabilities',
                                  'get_agent_authority'}


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

    @staticmethod
    def schemas() -> list[dict]:
        """Fresh schemas: provider mutation must not modify the registry."""
        return [{'type': 'function', 'function': {
            'name': name,
            'description': 'Read approved PUBLIC corpus snapshots only; not a live probe.',
            'parameters': {'type': 'object', 'additionalProperties': False,
                'properties': {'query': {'type': 'string', 'minLength': 1, 'maxLength': 6000}}
                    if name == 'search_approved_knowledge' else {},
                'required': ['query'] if name == 'search_approved_knowledge' else []},
        }} for name in sorted(TOOL_NAMES)]

    def resolve_calls(self, calls: list[dict], *, agent_id: AgentId | str) -> tuple[list[dict], list[dict], str]:
        """One bounded batch; validate all arguments before resolving any call.

        Returns sanitized assistant calls, PUBLIC tool messages and transient
        evidence for the final output guard. No model-selected identity/scope.
        """
        if not isinstance(calls, list) or not 1 <= len(calls) <= 3:
            raise KnowledgeToolError('tool_batch_bound')
        decoded = []
        seen = set()
        try:
            for item in calls:
                identifier = item['id']
                function = item['function']
                name, raw = function['name'], function['arguments']
                if (item['type'] != 'function' or not isinstance(identifier, str)
                        or not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', identifier)
                        or identifier in seen or name not in TOOL_NAMES
                        or not isinstance(raw, str) or len(raw) > 12000):
                    raise ValueError()
                def pairs(values):
                    result = {}
                    for key, value in values:
                        if key in result:
                            raise ValueError()
                        result[key] = value
                    return result
                args = json.loads(raw, object_pairs_hook=pairs)
                expected = {'query'} if name == 'search_approved_knowledge' else set()
                if not isinstance(args, dict) or set(args) != expected:
                    raise ValueError()
                if expected and (not isinstance(args['query'], str)
                        or not args['query'].strip() or len(args['query']) > 6000):
                    raise ValueError()
                seen.add(identifier)
                decoded.append((identifier, name, args))
        except (KeyError, TypeError, ValueError):
            raise KnowledgeToolError('invalid_tool_batch') from None
        normalized, messages, evidence = [], [], []
        for identifier, name, args in decoded:
            result = self.call(name, args, agent_id=agent_id)
            if result.classification != 'PUBLIC':
                raise KnowledgeToolError('tool_classification')
            rendered = result.render()
            evidence.append(rendered)
            if sum(len(text) for text in evidence) > 12000:
                raise KnowledgeToolError('tool_output_bound')
            normalized.append({'id': identifier, 'type': 'function',
                'function': {'name': name, 'arguments': json.dumps(args)}})
            messages.append({'role': 'tool', 'tool_call_id': identifier, 'name': name,
                'content': json.dumps({'status': result.status,
                    'classification': 'PUBLIC', 'provenance': result.provenance,
                    'evidence': rendered}, ensure_ascii=False)})
        return normalized, messages, '\n\n'.join(evidence)

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
            if operation == 'get_agent_authority':
                descriptions = {
                    AgentId.ZION: 'ZION orienta a comunidade. Somente o Guardian determinístico aplica a política objetiva de moderação.',
                    AgentId.MIMIR: 'MÍMIR explica tecnologia com informação pública aprovada; não executa operações nem modera.',
                    AgentId.EIR: 'EIR orienta o suporte e encaminha casos para revisão humana; não recupera fundos nem modera.',
                    AgentId.FREYR: 'FREYR orienta parcerias; acordos e condições comerciais exigem decisão humana. Não modera.',
                }
                return KnowledgeToolResult(operation,
                    (PublicEvidence('Papel público', descriptions[agent]),), 'FOUND')
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
