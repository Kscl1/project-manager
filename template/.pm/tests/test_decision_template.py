"""Tests for the decision template in .pm/templates/decision.md."""

import unittest
from pathlib import Path

DECISION_TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "decision.md"


class DecisionTemplateTest(unittest.TestCase):
    def test_asks_for_the_owner_words_and_the_check(self):
        text = DECISION_TEMPLATE.read_text(encoding="utf-8")

        source = text.split("## Source and updates", 1)[1].split("## Context", 1)[0]
        evidence = text.split("## Evidence and work", 1)[1]

        self.assertIn("Quote the owner's words", source)
        self.assertIn("with their date", source)
        for field in ("command", "exit code", "commit"):
            self.assertIn(field, evidence)
        self.assertIn('"not run"', evidence)


if __name__ == "__main__":
    unittest.main()
