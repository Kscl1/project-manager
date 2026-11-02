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

    def test_agent_install_page_names_folders_in_words(self):
        # The agent printed paths and file names for 34 of 42 words a beginner could not follow (a re-run with a
        # folders-only rule still showed 36, mostly file names), so files are named by what they hold too; only the
        # project folder question stays a full path, because the user has to act on that one.
        for path, phrases in (
            (
                "docs/install-with-agent.md",
                (
                    "Name files and folders by what they hold",
                    "not `.pm/local/setup.json`",
                    "not file by file",
                    "the project-manager copy next to it",
                    "Show a path or file name only when the user must type, open or check it",
                    "**The project folder**, as a full path",
                ),
            ),
            (
                "docs/tr/install-with-agent.md",
                (
                    "Dosya ve klasörleri yoluyla ya da dosya adıyla değil, içinde ne olduğuyla an",
                    "`.pm/local/setup.json` değil",
                    "dosya dosya sayma",
                    "yanındaki project-manager kopyası",
                    "Yolu ya da dosya adını yalnızca kullanıcı yazacaksa, açacaksa ya da kontrol edecekse göster",
                    "**Proje klasörü**, tam dosya yoluyla",
                ),
            ),
        ):
            with self.subTest(path=path):
                content = read(path)
                for phrase in phrases:
                    self.assertIn(phrase, content)

    def test_turkish_pages_use_one_word_for_the_assistant(self):
        # The first page says "Yardımcınla kur"; the page that link opens was titled "Ajanınla kur", so a reader met
        # two words for the same thing. The file name and every link target stay as they were.
        self.assertIn("[Yardımcınla kur](install-with-agent.md)", read("docs/tr/first-time.md"))
        self.assertIn("title: Yardımcınla kur", read("docs/tr/install-with-agent.md"))
        for path in ("docs/tr/index.md", "docs/tr/getting-started.md"):
            with self.subTest(path=path):
                content = read(path)
                self.assertIn("[Yardımcınla kur](install-with-agent.md)", content)
                self.assertNotIn("Ajanınla kur", content)
                self.assertNotIn("Ajanla", content)
        self.assertIn("title: Install with your agent", read("docs/install-with-agent.md"))

    def test_readme_names_the_one_agent_path_without_a_terminal(self):
        # The install section offers "cd ..." then "claude" as one way in, so "needs no terminal skills" promised too much.
        readme = read("README.md")
        self.assertIn("no terminal if you open the agent in Claude Desktop's Code tab", readme)
        self.assertIn("paid Claude plan", readme)
        self.assertNotIn("needs no terminal skills", readme)

    def test_docs_tie_the_no_terminal_promise_to_the_code_tab(self):
        # The home and getting-started pages repeated the old promise in both languages.
        for path in ("docs/index.md", "docs/getting-started.md"):
            with self.subTest(path=path):
                content = read(path)
                self.assertNotIn("no terminal skills", content)
                self.assertIn("Claude Desktop's Code tab", content)
        for path in ("docs/tr/index.md", "docs/tr/getting-started.md"):
            with self.subTest(path=path):
                content = read(path)
                self.assertNotIn("terminal bilgisi istemez", content)
                self.assertNotIn("terminal bilgisi ve", content)
                self.assertIn("Code sekmesinde", content)

    def test_first_time_pages_link_the_glossary_of_their_language(self):
        # The link is relative, so each page points at the glossary in its own folder; both pages stay short.
        for path in ("docs/first-time.md", "docs/tr/first-time.md"):
            with self.subTest(path=path):
                content = read(path)
                self.assertIn("](glossary.md)", content)
                self.assertLess(len(content.split()), 470)

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

    def test_both_workflow_guides_name_the_independent_review_and_consent(self):
        for path, phrases in (
            (
                "docs/how-it-works.md",
                (
                    "main branch",
                    "Every change gets an independent review",
                    "different model family",
                    "consent",
                ),
            ),
            (
                "docs/tr/how-it-works.md",
                ("Ana dal", "Her değişiklik bağımsız bir incelemeden geçer", "farklı bir model ailesi", "onay"),
            ),
        ):
            with self.subTest(path=path):
                content = read(path)
                for phrase in phrases:
                    self.assertIn(phrase, content)
