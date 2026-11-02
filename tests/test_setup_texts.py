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


def block(text, heading):
    """The lines under a `## heading`, up to the next heading of the same level."""
    match = re.search(rf"^## {re.escape(heading)}\n(.*?)(?=^#)", text, re.S | re.M)
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
        tr = re.search(r"^- TR: Bundan sonra şunları demen yeter: (.*)$", self.texts, re.M)
        self.assertTrue(tr, "the TR 'what you can say' line")
        en_promised = re.findall(r'"([^"]+)"', en.group(1))
        tr_promised = re.findall(r'"([^"]+)"', tr.group(1))
        pairs = list(zip(en_promised, tr_promised, strict=True))
        self.assertEqual(
            pairs,
            [
                ("continue", "devam"),
                ("what next?", "sırada ne var?"),
                ("show the board", "panoyu göster"),
                ("explain <word>", "<kelime> nedir?"),
                ("stop teaching", "anlatmayı bırak"),
            ],
        )
        rows = agents.split("| They say | You do |", 1)[1].split("\n\n", 1)[0].splitlines()
        for english, turkish in pairs:
            self.assertTrue(any(english in row and turkish in row for row in rows), (english, turkish))
        stop = next(row for row in rows if "stop teaching" in row)
        for phrase in ("mode: off", "known", "hinted", "one line", "safety asks"):
            self.assertIn(phrase, stop)
        self.assertIn("pm_board.py --next", agents)

    def test_after_the_first_task_offers_the_same_three_sentences_in_both_languages(self):
        """The first real task is closed: the user hears what they can now just say, in their own words."""
        after = block(self.texts, "After the first task")
        self.assertTrue(after, "the 'After the first task' section")
        self.assertLess(
            self.texts.index("## What you can say"), self.texts.index("## After the first task")
        )  # next to the finish lines, not inside them
        en = re.search(r"^- EN: (.*)$", after, re.M)
        tr = re.search(r"^- TR: (.*)$", after, re.M)
        self.assertTrue(en, "the EN 'after the first task' line")
        self.assertTrue(tr, "the TR 'after the first task' line")
        pairs = [
            ("What is left?", "Geriye ne kaldı?"),
            ("Why did we choose this?", "Bunu neden seçtik?"),
            ("Explain that word without changing anything.", "Hiçbir şeyi değiştirmeden şu kelimeyi açıkla."),
        ]
        for english, turkish in pairs:
            self.assertIn(f'"{english}"', en.group(1), "EN offers the sentence in the user's words")
            self.assertIn(f'"{turkish}"', tr.group(1), "TR offers the sentence in the user's words")
        for line in (en.group(1), tr.group(1)):
            self.assertNotIn("/pm-", line)  # sentences, not slash commands
            self.assertNotIn("continue", line)

    def test_skill_shows_the_after_the_first_task_text(self):
        skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        task = skill.split("## The first real task", 1)[1].split("## Finish", 1)[0]
        self.assertIn('the "After the first task" text from `texts.md`, as written', task)

    def test_quick_setup_leaves_one_later_task(self):
        skill = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("## Step 2: read the project back", skill)
        self.assertIn('"Finish the setup: models, own tools, map"', skill)
        self.assertIn("Review by: <today + 14 days>", skill)
        # A dated reminder is not permission for "continue" to begin postponed setup.
        self.assertIn("`continue` never starts the later task", skill)
        self.assertIn("when the user asks for models, tools or the map, or on that date", skill)
        row = next(line for line in AGENTS.read_text(encoding="utf-8").splitlines() if line.startswith('| "continue"'))
        self.assertIn("Review by:", row)
        self.assertIn("never starts", row)


if __name__ == "__main__":
    unittest.main()
