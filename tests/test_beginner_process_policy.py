"""Pin the first-session and setup rules shipped to project leads."""

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENTS = ROOT / "template/.pm/templates/root/AGENTS.md"
SKILL = ROOT / "template/.agents/skills/pm-setup/SKILL.md"


def read(path):
    return path.read_text(encoding="utf-8")


class BeginnerProcessPolicyTest(unittest.TestCase):
    def test_first_reply_makes_the_setup_opening_the_explicit_exception(self):
        agents, skill = read(AGENTS), read(SKILL)
        for phrase in (
            "at most four short lines total",
            "group multiple waiting items into one line",
            "first message is `/pm-setup`",
            "fixed setup opening is the first reply",
        ):
            self.assertIn(phrase, agents)
        self.assertIn("first message is `/pm-setup`", skill)
        self.assertIn("fixed opening is the first reply", skill)
        self.assertIn("If installation or language needs a question first", skill)

    def test_consent_distinguishes_public_reads_and_sending_data(self):
        agents = read(AGENTS)
        for phrase in (
            "sending the user's code or data out",
            "changing anything outside the machine",
            "Reading public docs with Context7",
            "reading the project's own GitHub state",
            "are reads, not asks",
            "changing a user file outside `.pm/` (show the diff)",
            "commits on a work branch",
            "merging into the user's main branch",
        ):
            self.assertIn(phrase, agents)

    def test_map_uses_the_local_map_server_outside_desktop(self):
        agents = read(AGENTS)
        row = next(line for line in agents.splitlines() if line.startswith('| "show the map"'))
        for phrase in ("`map` entry", "`npx likec4@1.60.0 start`", "address", "not installed"):
            self.assertIn(phrase, row)
        self.assertIn(
            "serve` (aliases: `start`", read(ROOT / "template/.agents/skills/pm-likec4-dsl/references/cli.md")
        )

    def test_map_update_is_prepared_without_overriding_user_file_consent(self):
        agents = read(AGENTS)
        section = agents.split("## Lead only: which tool when", 1)[1].split("## Lead only: teaching", 1)[0]
        self.assertLess(section.index("Every row follows the consent rule"), section.index("| Situation |"))
        row = next(line for line in section.splitlines() if "A component, module, service or link" in line)
        for phrase in (
            "On your own: prepare the LikeC4 map update",
            "show the diff and write it only after a yes when map files are outside `.pm/`",
            "ask before a needed download",
            "`npx likec4@1.60.0 validate`",
        ):
            self.assertIn(phrase, row)
        self.assertNotIn("On your own: update the LikeC4 map", row)

    def test_map_preview_checks_the_pinned_cli_before_both_routes(self):
        spec = importlib.util.spec_from_file_location("pm_init_map_policy", ROOT / "template/.pm/tools/pm_init.py")
        initializer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(initializer)
        launch = initializer.wanted_launch(True)
        map_entry = next(config for config in launch["configurations"] if config["name"] == "map")
        self.assertEqual(map_entry["runtimeExecutable"], "npx")
        package = map_entry["runtimeArgs"][1]
        self.assertEqual(package, f"likec4@{initializer.LIKEC4_VERSION}")
        self.assertEqual(map_entry["runtimeArgs"][0], "-y")  # cold cache would download without the preflight

        row = next(line for line in read(AGENTS).splitlines() if line.startswith('| "show the map"'))
        check = f"`npx --no-install {package} --version`"
        for phrase in (
            "before the first map preview",
            check,
            "if it fails, ask before downloading",
            "only on a yes",
            "`map` entry",
            f"`npx {package} start`",
        ):
            self.assertIn(phrase, row)
        self.assertLess(row.index(check), row.index("`map` entry"))
        self.assertLess(row.index("ask before downloading"), row.index("`map` entry"))

    def test_read_back_after_choices_preserves_existing_charter(self):
        skill = read(SKILL)
        step = skill.split("## Step 2: read the project back", 1)[1].split("## Standards to keep", 1)[0]
        for phrase in (
            "After the installation check and the teaching choice",
            "before questions about the project's existing setup",
            "check the current branch",
            "only if the install made it",
            "Git keeps committed history",
            "If `.pm/charter.md` is missing",
            "read and preserve it",
            "never replace it with the template",
        ):
            self.assertIn(phrase, step)
        self.assertNotIn("so nothing is lost", step)

    def test_charter_and_checklist_are_epic_children_tools_in_later_task(self):
        skill = read(SKILL)
        for phrase in (
            "Items 1-6 and the charter are children of the setup Epic",
            "The later task is outside the Epic",
            "record each tool in that later task or in one of its children",
            "If an item is done early, record it there",
            "every 'Lead only' section",
        ):
            self.assertIn(phrase, skill)
        self.assertNotIn("both 'Lead only' sections", skill)

    def test_setup_respects_consent_and_honest_review_gates(self):
        skill = read(SKILL)
        for phrase in (
            "The user decides project intent and confirms the charter",
            "work-branch commits do not need an ask",
            "merging into the user's main branch does",
            "Show every change to a user file outside `.pm/` as a diff",
            "Mark a gate passed only when what it names was really done",
            "Review: lead self-check",
        ):
            self.assertIn(phrase, skill)
        self.assertNotIn("never mark them passed", skill)
        self.assertNotIn("commit them only on a yes", skill)

    def test_later_task_has_an_explicit_reminder_and_does_not_autostart(self):
        skill, agents = read(SKILL), read(AGENTS)
        trigger = (
            "Review by: <today + 14 days> · <owner> · when the user asks for models, tools or the map, or on that date"
        )
        self.assertIn(trigger, skill)
        self.assertIn('mentions it once under "what waits for you"', skill)
        self.assertIn("`continue` never starts the later task", skill)
        self.assertIn('mentions it once under "what waits for you"', agents)
