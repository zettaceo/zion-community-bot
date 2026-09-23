from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PLAN = ROOT / "ZION-MASTER-PLAN.md"


class MasterPlanContractTests(unittest.TestCase):
    def read(self) -> str:
        return PLAN.read_text(encoding="utf-8")

    def capability_rows(self) -> list[tuple[int, str, str]]:
        rows: list[tuple[int, str, str]] = []
        pattern = re.compile(
            r"^\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|\s*\*\*(DONE|PARTIAL|TODO|FUTURE)\*\*",
            re.MULTILINE,
        )
        for match in pattern.finditer(self.read()):
            rows.append(
                (
                    int(match.group(1)),
                    match.group(2).strip(),
                    match.group(3),
                )
            )
        return rows

    def test_all_25_capabilities_are_present_once(self) -> None:
        rows = self.capability_rows()
        self.assertEqual(len(rows), 25)
        self.assertEqual(
            [number for number, _name, _status in rows],
            list(range(1, 26)),
        )

    def test_declared_capability_counts_match_matrix(self) -> None:
        text = self.read()
        rows = self.capability_rows()
        counts = {
            status: sum(
                1
                for _number, _name, row_status in rows
                if row_status == status
            )
            for status in ("DONE", "PARTIAL", "TODO", "FUTURE")
        }

        self.assertEqual(counts["DONE"], 18)
        self.assertEqual(counts["PARTIAL"], 7)
        self.assertEqual(counts["TODO"], 0)
        self.assertEqual(counts["FUTURE"], 0)

        self.assertIn("- **18 DONE**", text)
        self.assertIn("- **7 PARTIAL**", text)
        self.assertIn("- **0 TODO**", text)
        self.assertIn("- **0 fully FUTURE**", text)

    def test_master_safety_invariant_is_explicit(self) -> None:
        text = self.read()

        self.assertIn(
            "AI may interpret. Objective rules or authorized humans decide "
            "irreversible actions.",
            text,
        )
        self.assertIn("No state grants additional punitive power to AI.", text)
        self.assertIn("criticism remains protected", text)

    def test_each_partial_capability_has_closure_language(self) -> None:
        text = self.read()
        rows = self.capability_rows()
        partial_numbers = {
            number
            for number, _name, status in rows
            if status == "PARTIAL"
        }
        self.assertEqual(
            partial_numbers,
            {1, 2, 6, 11, 14, 15, 23},
        )

        for number in partial_numbers:
            row = next(
                line
                for line in text.splitlines()
                if line.startswith(f"| {number} |")
            )
            cells = [cell.strip() for cell in row.strip("|").split("|")]
            self.assertGreaterEqual(len(cells), 5)
            self.assertTrue(cells[4])

    def test_release_state_is_not_confused_with_production(self) -> None:
        text = self.read()

        self.assertIn(
            "The **development** line contains Blocks 1–5.",
            text,
        )
        self.assertIn(
            "That does not mean production has been upgraded.",
            text,
        )
        self.assertIn(
            "External host/control-plane checks must never be marked DONE "
            "merely because repository CI is green.",
            text,
        )


if __name__ == "__main__":
    unittest.main()
