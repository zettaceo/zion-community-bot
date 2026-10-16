from __future__ import annotations

import unittest

from zion.agent_workflows import (
    SupportCaseType,
    partnership_intake_prompt,
    qualify_partnership,
    triage_support,
)


class SupportWorkflowTests(unittest.TestCase):
    def test_support_triage_covers_required_classes(self) -> None:
        cases = {
            "Como conecto minha carteira?": SupportCaseType.QUESTION,
            "Minha carteira não conecta": SupportCaseType.USAGE_PROBLEM,
            "Escolhi a rede errada": SupportCaseType.USER_ERROR,
            "Minha conta foi invadida": SupportCaseType.POSSIBLE_INCIDENT,
            "A tela branca trava sempre, parece bug": SupportCaseType.POSSIBLE_BUG,
            "Minha conta está bloqueada": SupportCaseType.ACCOUNT,
            "Quero falar com um atendente": SupportCaseType.HUMAN,
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(triage_support(text).case_type, expected)

    def test_incident_account_and_human_require_human_review(self) -> None:
        for text in (
            "Não reconheço esta transação",
            "Minha conta está bloqueada",
            "Preciso de atendimento humano",
        ):
            with self.subTest(text=text):
                self.assertTrue(triage_support(text).requires_human)


class PartnershipWorkflowTests(unittest.TestCase):
    def test_minimized_labeled_intake_builds_operator_summary(self) -> None:
        result = qualify_partnership(
            "Nome: Ana\n"
            "Empresa/projeto: Acme Labs\n"
            "Contato: ana@example.com\n"
            "Objetivo: integração de liquidez\n"
            "Região: Brasil"
        )
        self.assertTrue(result.ready_for_operator)
        self.assertEqual(result.fields["company_project"], "Acme Labs")
        summary = result.operator_summary()
        self.assertIn("Empresa/projeto: Acme Labs", summary)
        self.assertNotIn("missing", summary.lower())

    def test_unlabeled_text_is_not_guessed_or_persisted(self) -> None:
        result = qualify_partnership(
            "Somos uma empresa grande e queremos conversar."
        )
        self.assertEqual(dict(result.fields), {})
        self.assertFalse(result.ready_for_operator)

    def test_commitment_zone_always_requires_human(self) -> None:
        result = qualify_partnership(
            "Empresa: Acme\nContato: ana@example.com\n"
            "Proposta: fechar contrato com exclusividade"
        )
        self.assertTrue(result.ready_for_operator)
        self.assertTrue(result.requires_human_decision)

    def test_intake_prompt_rejects_sensitive_material(self) -> None:
        prompt = partnership_intake_prompt().lower()
        self.assertIn("não envie credenciais", prompt)
        self.assertIn("decisão comercial será humana", prompt)


if __name__ == "__main__":
    unittest.main()
