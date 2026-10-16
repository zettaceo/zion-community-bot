from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Mapping


def _fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    return "".join(
        char for char in normalized if not unicodedata.combining(char)
    ).casefold()


class SupportCaseType(str, Enum):
    QUESTION = "question"
    USAGE_PROBLEM = "usage_problem"
    USER_ERROR = "user_error"
    POSSIBLE_INCIDENT = "possible_incident"
    POSSIBLE_BUG = "possible_bug"
    ACCOUNT = "account"
    HUMAN = "human"


@dataclass(frozen=True, slots=True)
class SupportTriage:
    case_type: SupportCaseType
    requires_human: bool


_SUPPORT_PATTERNS: tuple[tuple[SupportCaseType, re.Pattern[str]], ...] = (
    (
        SupportCaseType.POSSIBLE_INCIDENT,
        re.compile(
            r"\b(?:transacao desconhecida|nao reconheco|fundos? sumiu|"
            r"saldo sumiu|conta (?:foi )?invadida|fui hackead|phishing|golpe|"
            r"movimentacao suspeita)\b"
        ),
    ),
    (
        SupportCaseType.HUMAN,
        re.compile(
            r"\b(?:atendente|atendimento humano|falar com (?:uma pessoa|"
            r"a equipe|humano)|preciso de um humano|escalar para)\b"
        ),
    ),
    (
        SupportCaseType.ACCOUNT,
        re.compile(
            r"\b(?:minha conta|login|acesso a conta|assinatura|cobranca|"
            r"pagamento duplicado|plano nao ativou|conta bloqueada)\b"
        ),
    ),
    (
        SupportCaseType.POSSIBLE_BUG,
        re.compile(
            r"\b(?:bug|erro interno|tela branca|crash|travou|trava sempre|"
            r"comportamento inesperado|consigo reproduzir)\b"
        ),
    ),
    (
        SupportCaseType.USER_ERROR,
        re.compile(
            r"\b(?:rede errada|endereco errado|digitei errado|saldo "
            r"insuficiente|gas insuficiente|slippage baixo|nonce)\b"
        ),
    ),
    (
        SupportCaseType.USAGE_PROBLEM,
        re.compile(
            r"\b(?:nao consigo|nao conecta|nao funciona|falha|erro|"
            r"pendente|recusad|rejeitad|ajuda com)\b"
        ),
    ),
)


def triage_support(text: str) -> SupportTriage:
    folded = _fold(text)
    for case_type, pattern in _SUPPORT_PATTERNS:
        if pattern.search(folded):
            return SupportTriage(
                case_type=case_type,
                requires_human=case_type in {
                    SupportCaseType.POSSIBLE_INCIDENT,
                    SupportCaseType.ACCOUNT,
                    SupportCaseType.HUMAN,
                },
            )
    return SupportTriage(
        case_type=SupportCaseType.QUESTION,
        requires_human=False,
    )


_PARTNERSHIP_FIELDS = MappingProxyType(
    {
        "nome": "name",
        "empresa": "company_project",
        "projeto": "company_project",
        "empresa projeto": "company_project",
        "contato": "contact",
        "categoria": "category",
        "mercado": "market",
        "pais": "region",
        "regiao": "region",
        "pais regiao": "region",
        "audiencia": "audience",
        "proposta": "proposal",
        "objetivo": "objective",
        "integracao": "desired_integration",
        "integracao desejada": "desired_integration",
        "timing": "timing",
        "prazo desejado": "timing",
        "informacoes adicionais": "additional_information",
        "informacao adicional": "additional_information",
    }
)

_PARTNERSHIP_LABEL = re.compile(
    r"^\s*([^:\n]{2,40})\s*:\s*(.{1,500})\s*$"
)
_COMMITMENT_ZONE = re.compile(
    r"\b(?:fechar contrato|assinar contrato|garantir pagamento|comissao|"
    r"equity|exclusividade|prazo vinculante|prometer integracao|"
    r"condicao comercial final|aceitar a proposta)\b"
)


@dataclass(frozen=True, slots=True)
class PartnershipQualification:
    fields: Mapping[str, str]
    missing_required: tuple[str, ...]
    ready_for_operator: bool
    requires_human_decision: bool

    def operator_summary(self) -> str:
        labels = {
            "name": "Nome",
            "company_project": "Empresa/projeto",
            "contact": "Contato",
            "category": "Categoria",
            "market": "Mercado",
            "region": "País/região",
            "audience": "Audiência",
            "proposal": "Proposta",
            "objective": "Objetivo",
            "desired_integration": "Integração desejada",
            "timing": "Timing",
            "additional_information": "Informações adicionais",
        }
        lines = ["FREYR — OPORTUNIDADE QUALIFICADA"]
        for key, label in labels.items():
            value = self.fields.get(key)
            if value:
                lines.append(f"{label}: {value}")
        lines.append(
            "Decisão humana necessária: "
            + ("SIM" if self.requires_human_decision else "NÃO")
        )
        return "\n".join(lines)


def qualify_partnership(text: str) -> PartnershipQualification:
    extracted: dict[str, str] = {}
    for line in (text or "").splitlines():
        match = _PARTNERSHIP_LABEL.match(line)
        if not match:
            continue
        label = re.sub(r"[^a-z0-9 ]", " ", _fold(match.group(1)))
        key = _PARTNERSHIP_FIELDS.get(" ".join(label.split()))
        if key is None or key in extracted:
            continue
        value = " ".join(match.group(2).strip().split())[:500]
        if value:
            extracted[key] = value

    required_groups = (
        ("company_project",),
        ("contact",),
        ("proposal", "objective", "desired_integration"),
    )
    missing = tuple(
        "/".join(group)
        for group in required_groups
        if not any(extracted.get(field) for field in group)
    )
    return PartnershipQualification(
        fields=MappingProxyType(extracted),
        missing_required=missing,
        ready_for_operator=not missing,
        requires_human_decision=bool(_COMMITMENT_ZONE.search(_fold(text))),
    )


def partnership_intake_prompt() -> str:
    return (
        "Para qualificar a oportunidade sem coletar dados desnecessários, "
        "envie somente: Empresa/projeto, Contato e Proposta, objetivo ou "
        "integração desejada. Se ajudar, inclua mercado, país/região, "
        "audiência e timing. Não envie credenciais, documentos sigilosos ou "
        "dados pessoais desnecessários. A decisão comercial será humana."
    )
