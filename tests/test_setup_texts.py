"""The fixed texts /pm-setup shows: every model must show the same words, whatever its own style.

These checks keep the text file, the skill and the root AGENTS.md template pointing at each other, and the English
and Turkish versions in step: a sentence added to one language and not the other fails here.
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "template" / ".agents" / "skills" / "pm-setup"
TEXTS = SKILL / "texts.md"
AGENTS = ROOT / "template" / ".pm" / "templates" / "root" / "AGENTS.md"


def section(text, heading):
    """The lines under a `### EN` or `### TR` heading, up to the next heading."""
    match = re.search(rf"^### {heading}\n(.*?)(?=^#)", text, re.S | re.M)
    return match.group(1) if match else ""


class FixedTexts(unittest.TestCase):
    def setUp(self):
        self.texts = TEXTS.read_text(encoding="utf-8")

    def test_opening_has_the_same_shape_in_both_languages(self):
        en, tr = section(self.texts, "EN"), section(self.texts, "TR")
        for lang, block in (("EN", en), ("TR", tr)):
            self.assertEqual(re.findall(r"^> (\d)\. \*\*", block, re.M), ["1", "2", "3"], f"{lang} options")
            self.assertEqual(len(re.findall(r"^> \S", block, re.M)), 6, f"{lang}: three sentences, question, close")
        self.assertIn("**Kısa ipucu** (önerilen)", tr)
        self.assertIn("**Short hint** (recommended)", en)

    def test_every_hint_and_moment_has_both_languages(self):
        en = re.findall(r"^- EN: ", self.texts, re.M)
        tr = re.findall(r"^- TR: ", self.texts, re.M)
        self.assertEqual(len(en), len(tr))
        self.assertGreaterEqual(len(en), 6)  # task, board, resume, the task moment twice, known
        for concept in ("task", "board", "resume"):
            self.assertIn(f"**{concept}**:", self.texts)

    def test_statuses_stay_english_in_turkish(self):
        """Statuses are machine words, read by the tools: the board shows them in English in every language."""
        self.assertIn("Ready, Active, Done", self.texts)
        for word in ("Yapılacak", "Yapılıyor", "Bitti sütun"):
            self.assertNotIn(word, self.texts)

    def test_skill_and_agents_point_at_the_texts(self):
        skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        agents = AGENTS.read_text(encoding="utf-8")
        self.assertIn("`texts.md`", skill)
        self.assertIn("handover.md", skill)
        self.assertIn(".agents/skills/pm-setup/texts.md", agents)
        self.assertIn("## Lead only: teaching", agents)
        self.assertIn("hinted", agents)

    def test_what_you_can_say_matches_the_phrases_the_lead_handles(self):
        """The finish line promises phrases; the root AGENTS.md table must say what the lead does for each."""
        agents = AGENTS.read_text(encoding="utf-8")
        self.assertIn("## Lead only: talking to the user", agents)
        en = re.search(r"^- EN: From now on you can just say: (.*)$", self.texts, re.M)
        self.assertTrue(en, "the EN 'what you can say' line")
        self.assertRegex(self.texts, r"(?m)^- TR: Bundan sonra şunları demen yeter: ")
        promised = re.findall(r'"([^"]+)"', en.group(1))
        table = [p for p in promised if p != "stop teaching"]
        self.assertEqual(table, ["continue", "what next?", "show the board", "explain <word>"])
        for phrase in table:
            self.assertIn(f'"{phrase}', agents, phrase)
        self.assertIn("pm_board.py --next", agents)


if __name__ == "__main__":
    unittest.main()
