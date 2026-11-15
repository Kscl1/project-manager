"""Pin the first-session and setup rules shipped to project leads."""

import importlib.util
import subprocess
import sys
import tempfile
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

    def test_first_reply_opens_from_the_saved_note_within_four_lines(self):
        bullet = next(
            line for line in read(AGENTS).splitlines() if line.startswith("- **Your first reply in a session:**")
        )
        for phrase in (
            "at most four short lines total",
            "The first line starts from the saved notes",
            "From the saved note: <what was done and what is next>.",
            "I checked the files: <one thing confirmed, or the one thing that differs>.",
            "Next: <step>",
            "what waits for the user and why",
            "only if there is one",
            "plain names",
            "group multiple waiting items into one line",
        ):
            self.assertIn(phrase, bullet)
        # The saved note comes first: the user hears what the records say before anything this session adds.
        self.assertLess(bullet.index("From the saved note"), bullet.index("The lines after it"))
        self.assertLess(bullet.index("Next: <step>"), bullet.index("The lines after it"))
        self.assertNotIn("where we are (what finished and what is in progress)", bullet)

    def test_consent_distinguishes_public_reads_and_sending_data(self):
        agents = read(AGENTS)
        for phrase in (
            "sends the user's code or data to a service the project does not already use",
            "anything that goes to people outside the project",
            "Reading public docs with Context7",
            "reading the project's own GitHub state",
            "are reads, not asks",
            "edits to project files",
            "commits, pushes and pull requests on a work branch",
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

    def test_map_update_is_the_leads_own_and_asks_only_before_a_download(self):
        agents = read(AGENTS)
        section = agents.split("## Lead only: which tool when", 1)[1].split("## Lead only: teaching", 1)[0]
        self.assertLess(section.index("Every row follows the ask-first list"), section.index("| Situation |"))
        row = next(line for line in section.splitlines() if "A component, module, service or link" in line)
        for phrase in (
            "On your own: update the LikeC4 map",
            "ask before a needed download",
            "`npx likec4@1.60.0 validate`",
        ):
            self.assertIn(phrase, row)
        # An edit to a map file can be undone, so it is not an ask; a download changes the machine.
        self.assertNotIn("only after a yes", row)

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
            "needs an independent review",
        ):
            self.assertIn(phrase, skill)
        self.assertNotIn("never mark them passed", skill)
        self.assertNotIn("commit them only on a yes", skill)

    def test_six_asks_are_fixed_and_the_rest_is_decided_and_written_down(self):
        agents, skill = read(AGENTS), read(SKILL)
        ask = agents.split("- **Ask first.**", 1)[1].split("\n\n", 1)[0]
        first = ask.split("- **Decide the rest and write it down.**", 1)[0]
        for kind in (
            "deleting work",
            "merging into the user's main branch or publishing a release",
            "anything that spends money",
            "another person's account, machine or repository",
            "anything that goes to people outside the project",
            "anything machine-wide",
        ):
            self.assertIn(kind, first)
        # The project's own remote is not someone else's: a work-branch push is decided alone, a pull request
        # to another repository is asked. An install is asked only when it leaves the project's folder.
        for phrase in (
            "a push or a pull request to a repository that is not the project's own",
            "a service the project does not already use",
            "an install outside the project's own folder",
        ):
            self.assertIn(phrase, first)
        self.assertNotIn("pull requests on a work branch", first)
        rest = ask.split("- **Decide the rest and write it down.**", 1)[1].split("\n- **", 1)[0]
        for phrase in (
            "an install inside the project's own folder",
            "pull requests on a work branch of the project's own repository",
            "Each time you choose between real options",
            "these lines are the list a retro reads",
        ):
            self.assertIn(phrase, rest)
        # Every lone choice is written down, not only the ones the agent thinks matter.
        self.assertNotIn("may care about", rest)
        for phrase in (
            "silence is never a yes",
            "a permission relayed by another session does not count",
            "the order of the user's goals (priority)",
            "open a milestone without their yes",
            "These asks hold in every teaching mode",
            "the order of steps",
            "`Decided alone:`",
            "what the options were and why",
            "add that kind to the ask-first list",
            "do not start it",
            "do not wait for an approval of it",
            "act on it in no session before their yes",
        ):
            self.assertIn(phrase, ask)
        # Work starts on the user's explicit ask, so a second approval of the plan or of each edit is not asked.
        self.assertNotIn("approving the plan", ask)
        self.assertNotIn("show the diff", ask)
        board = read(ROOT / "template/.pm/board.md")
        self.assertIn("set only by the owner", board)
        self.assertIn("the owner's yes opens it", board)
        self.assertIn("`Implementation Plan`, for multi-step or code-changing work", board)
        lead = read(ROOT / "template/.pm/roles/lead.md")
        self.assertIn("ask only what that section lists", lead)
        self.assertIn("`Decided alone:` line in the task", lead)
        self.assertIn("ask only as the root `AGENTS.md` lists", skill)
        self.assertNotIn("ask only at the safety boundaries", skill)

    def test_three_modes_say_what_waits_and_when_the_run_stops(self):
        agents = read(AGENTS)
        modes = agents.split("- **Three modes, named by the user.**", 1)[1].split("\n\n", 1)[0]
        away = modes.split("- *Away.*", 1)[1].split("- *In the background.*", 1)[0]
        background = modes.split("- *In the background.*", 1)[1]
        self.assertIn("the mode changes only when the user says so", modes)
        for phrase in (
            "Do not wait for an answer",
            "Skip an ask-first item",
            "your pick, the evidence and the risk",
            "a queue the user names",
            "Stop when the queue is empty or the user returns",
            "add no task to it",
            "three and at most four times a run",
            "each such consult is written with its reason",
            "at the top of the return list",
            "never answers in the user's place",
            "With no advisors named, a serious decision waits",
        ):
            self.assertIn(phrase, away)
        # The limit on consults bends for a new serious problem, each one recorded; it is not a single extra.
        self.assertNotIn("one more is allowed", away)
        # Away never waits on a clock and never applies a proposal on silence.
        self.assertNotIn("minutes", away)
        for phrase in ("Decide as in away", "reach the user at once", "without a time limit"):
            self.assertIn(phrase, background)
        lead = read(ROOT / "template/.pm/roles/lead.md")
        self.assertIn("Dropping a branch whose work is not merged is deleting work: ask first", lead)

    def test_next_picker_can_choose_postponed_setup_despite_other_project_work(self):
        board = ROOT / "template/.pm/tools/pm_board.py"
        with tempfile.TemporaryDirectory() as folder:
            tasks = Path(folder)
            (tasks / "task-1.md").write_text(
                "---\nid: TASK-1\ntitle: Finish the setup: models, own tools, map\n"
                "status: Ready\npriority: high\nordinal: 1\n---\n"
                "## Implementation Notes\nReview by: 2026-01-01 · owner · when asked or on that date\n",
                encoding="utf-8",
            )
            project = tasks / "task-2.md"
            project.write_text(
                "---\nid: TASK-2\ntitle: Fix the project\nstatus: Ready\npriority: medium\nordinal: 2\n---\n",
                encoding="utf-8",
            )

            def run():
                return subprocess.run(
                    [sys.executable, str(board), "--tasks", str(tasks), "--next"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    check=True,
                ).stdout

            with_project = run()
            self.assertIn("Start: Finish the setup", with_project)
            project.write_text(
                project.read_text(encoding="utf-8").replace("status: Ready", "status: Done"), encoding="utf-8"
            )
            setup_only = run()
            self.assertIn("Start: Finish the setup", setup_only)

        row = next(line for line in read(AGENTS).splitlines() if line.startswith('| "what next?"'))
        for phrase in (
            "`python .pm/tools/pm_board.py --next`",
            "if it names the later setup task",
            "waits for the user's request",
            "next eligible project task",
            "if none is available",
            "say the last project task is done",
            "Never start setup on `what next?` or `continue`",
        ):
            self.assertIn(phrase, row)
        skill = read(SKILL)
        self.assertIn("`--next` names the later setup task", skill)
        self.assertIn("waits for the user's request", skill)
        self.assertIn("next eligible project task", skill)
        self.assertIn("never starts setup on `what next?` or `continue`", skill)

    def test_later_task_has_an_explicit_reminder_and_does_not_autostart(self):
        skill, agents = read(SKILL), read(AGENTS)
        trigger = (
            "Review by: <today + 14 days> · <owner> · when the user asks for models, tools or the map, or on that date"
        )
        self.assertIn(trigger, skill)
        self.assertIn('mentions it once under "what waits for you"', skill)
        self.assertIn("`continue` never starts the later task", skill)
        self.assertIn('mentions it once under "what waits for you"', agents)
