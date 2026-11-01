"""Keep both languages of the beginner guides in step with the shipped flow."""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


class BeginnerDocsTest(unittest.TestCase):
    def test_both_guides_put_tools_in_the_later_task(self):
        for path, phrases in (
            ("docs/own-tools.md", ("later setup task", "outside the setup Epic", "one of its children")),
            ("docs/tr/own-tools.md", ("sonraki kurulum görevi", "kurulum Epic'inin dışında", "alt görev")),
        ):
            with self.subTest(path=path):
                content = read(path)
                for phrase in phrases:
                    self.assertIn(phrase, content)

    def test_getting_started_describes_quick_setup_in_both_languages(self):
        for path, phrases in (
            (
                "docs/getting-started.md",
                ("reads the project back", "confirm the charter", "one later task", "outside `.pm/`", "work branch"),
            ),
            (
                "docs/tr/getting-started.md",
                (
                    "projeyi nasıl anladığını",
                    "tüzüğünü (amacı ve sınırları) onaylarsın",
                    "tek bir sonraki görev",
                    "`.pm/` dışındaki",
                    "çalışma dalı",
                ),
            ),
        ):
            with self.subTest(path=path):
                content = read(path)
                for phrase in phrases:
                    self.assertIn(phrase, content)
        self.assertNotIn("Nothing changes without your yes", read("docs/getting-started.md"))
        self.assertNotIn("Sen onay vermeden hiçbir şey değiştirilmez", read("docs/tr/getting-started.md"))

    def test_both_workflow_guides_distinguish_risk_and_consent(self):
        for path, phrases in (
            (
                "docs/how-it-works.md",
                ("main branch", "security, data, money, permissions or a public release", "lead self-check", "consent"),
            ),
            (
                "docs/tr/how-it-works.md",
                ("Ana dal", "güvenlik, veri, para, izinler veya herkese açık yayın", "lead self-check", "onay"),
            ),
        ):
            with self.subTest(path=path):
                content = read(path)
                for phrase in phrases:
                    self.assertIn(phrase, content)
