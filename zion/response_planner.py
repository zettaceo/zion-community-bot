"""Bounded response shape and risk hints; never authority, facts or punishment."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import re

from .agents import AgentId
from .language_recovery import recover_language


class ResponseMode(str, Enum):
    DIRECT_ANSWER = 'direct_answer'
    EXPLANATION = 'explanation'
    COMPARISON = 'comparison'
    OBJECTION = 'objection'
    SUPPORT_DIAGNOSIS = 'support_diagnosis'
    CLARIFICATION = 'clarification'
    PARTNERSHIP_QUALIFICATION = 'partnership_qualification'
    SECURITY_EXPLANATION = 'security_explanation'


_HINTS = {
    ResponseMode.DIRECT_ANSWER: 'Responda diretamente e preserve listas oficiais completas.',
    ResponseMode.EXPLANATION: 'Explique o mecanismo sustentado pelas fontes, suas condições e limitações.',
    ResponseMode.COMPARISON: 'Compare pelos mesmos critérios e diga quando faltam dados; não invente superioridade.',
    ResponseMode.OBJECTION: 'Reconheça a parte válida da objeção; compare diferenças verificáveis e limites relevantes. Indique dados ausentes, não invente superioridade, economia ou retorno e não pressione pela compra. Responda ao ponto atual sem despejar um catálogo de recursos. Não atribua características ou preços a concorrentes sem evidência comparativa explícita no contexto. Parceria comercial não é taxa de swap; não invente uma política comercial quando faltarem termos publicados.',
    ResponseMode.SUPPORT_DIAGNOSIS: 'Separe o relato do usuário de fatos confirmados. Peça apenas o próximo detalhe público necessário; não conclua execução, cancelamento ou perda sem evidência.',
    ResponseMode.CLARIFICATION: 'Faça uma pergunta curta para esclarecer o recurso ou objetivo; não preencha lacunas por suposição.',
    ResponseMode.PARTNERSHIP_QUALIFICATION: 'Entenda o tipo e objetivo da parceria; não aprove acordos, descontos ou prazos.',
    ResponseMode.SECURITY_EXPLANATION: 'Explique os controles comprovados e seus limites. Nenhuma plataforma ou transação é livre de risco; não dê garantia de segurança.',
}


@dataclass(frozen=True, slots=True)
class ResponsePlan:
    mode: ResponseMode
    risk: str
    complexity: str

    def instruction(self) -> str:
        # Fixed reviewed text only. Never copy a user claim into system scope.
        caution = (' Não solicite credenciais nem tome ações financeiras ou administrativas.'
                   if self.risk != 'low' else '')
        return _HINTS[self.mode] + caution


def plan_response(*, agent_id: AgentId | str, question: str, has_evidence: bool) -> ResponsePlan:
    agent = AgentId(agent_id)  # Invalid identity fails closed.
    interpretation = recover_language(question)
    text = interpretation.canonical
    high = re.search(r'\b(?:seed|senha|secret|chave privada|token|api key|perdi|roubad\w*|saque|hack\w*)\b', text)
    financial = re.search(r'\b(?:swap|ordens?|taxas?|lucro|rendimento|fundos|segur\w*|risco)\b', text)
    risk = 'high' if high else 'medium' if financial else 'low'
    complexity = 'complex' if len(text) > 500 or text.count('?') > 1 or re.search(r'\b(?:compare|comparar|diferenca|versus)\b', text) else 'simple'
    # Objections and comparisons are recognised before the EIR support mode:
    # live acceptance (2026-11-02) sent "existe plataforma mais barata" to EIR
    # as support diagnosis, so it never reached the approved stronger model.
    objection = re.search(r'\b(?:ja existe|faz igual|mesma coisa|pagaria|por que pagar|car[oa]s?|nao vale|'
                          r'mais barat[oa]s?|concorrentes?|motivos? (?:para|pra)(?: \w+)? (?:usar|escolher)|'
                          r'por que (?:usar|escolher)|vale a pena|vantagens?)\b', text)
    # A real operational problem still comes first for EIR ("isso é caro e
    # minha ordem travou" is support, not an objection).
    support_problem = agent is AgentId.EIR and re.search(
        r'\b(?:travou|travad\w*|erro|falh\w*|nao (?:conecta|liga|funciona|consigo|chegou|caiu)|'
        r'sumiu|pendente|deu ruim|deu zica|nao dá|perdi)\b', text)
    if not has_evidence or interpretation.clarification:
        mode = ResponseMode.CLARIFICATION
    elif support_problem:
        mode = ResponseMode.SUPPORT_DIAGNOSIS
    elif re.search(r'\b(?:compare|comparar|diferenca|versus|vs)\b', text):
        mode = ResponseMode.COMPARISON
    elif objection:
        mode = ResponseMode.OBJECTION
    elif re.search(r'\b(?:segur\w*|riscos?|protecao|hacke\w*|ataque|vulnera\w*|invas\w*)\b', text):
        mode = ResponseMode.SECURITY_EXPLANATION
    elif agent is AgentId.EIR:
        mode = ResponseMode.SUPPORT_DIAGNOSIS
    elif agent is AgentId.FREYR:
        mode = ResponseMode.PARTNERSHIP_QUALIFICATION
    elif re.search(r'\b(?:como|explique|explica|porque|por que)\b', text):
        mode = ResponseMode.EXPLANATION
    else:
        mode = ResponseMode.DIRECT_ANSWER
    return ResponsePlan(mode, risk, complexity)
