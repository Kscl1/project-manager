"""Independent acceptance tests for ``python .pm/tools/pm_resume.py``.

Written black-box against ``.pm/templates/live-block.md`` without reading
the implementation.

Every test builds a throwaway repository in a temporary directory: a real
git repo with commits, Backlog-style task files under
``.pm/backlog/tasks/`` and worktree directories under ``.worktrees/``. The
script under test is copied from this worktree's ``.pm/tools/pm_resume.py``
into the fixture and executed with ``subprocess`` from the fixture root.

Standard library only. Tests skip when the script is missing from
``.pm/tools/``.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

SCRIPT_SOURCE = Path(__file__).resolve().parent.parent / "tools" / "pm_resume.py"

HEADINGS = [
    "# Resume summary",
    "## Git status",
    "## Last 5 commits",
    "## Open tasks",
    "## Waiting on the owner",
    "## Warnings",
]

ACTIVE_TASK_LINE = "- TASK-1.2 · Package B: resume summary [Active]"
LIVE_LINES = [
    "  Next: Run tests",
    "  Evidence: abc123 passed 4 tests",
    "  Blocker: none",
    "  Needs owner: nothing",
    "  Worker: GPT-6 Luna · .worktrees/b1-resume · .worktrees/b1-resume/.pm-report.md",
]
# The live block inside the task's Implementation Notes is the same five
# lines without the two-space output indent.
LIVE_BLOCK = "\n".join(line.lstrip() for line in LIVE_LINES)

MISSING_WORKER_BLOCK = "Next: Wait\nWorker: GPT-6 Luna · .worktrees/missing · .worktrees/missing/.pm-report.md"

NO_WORKER_BLOCK = "Next: Run tests\nEvidence: abc123 passed 4 tests\nBlocker: none\nNeeds owner: nothing"


def run_git(repo, *args):
    """Run a git command inside the fixture repo and return stdout."""
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def write_task(root, task_id, title, status, notes=None):
    """Create a Backlog-style task file under .pm/backlog/tasks/."""
    tasks_dir = root / ".pm" / "backlog" / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    number = task_id.lower().replace("task-", "")
    slug = title.lower().replace(":", "").replace(" ", "-")
    path = tasks_dir / f"task-{number} - {slug}.md"
    parts = [
        "---",
        f"id: {task_id}",
        f"title: {title}",
        f"status: {status}",
        "assignee: []",
        "created_date: '2025-06-01 09:00'",
        "labels: []",
        "dependencies: []",
        "---",
        "",
        "## Description",
        "",
        f"Fixture task {task_id}.",
        "",
    ]
    if notes is not None:
        parts.extend(["## Implementation Notes", "", notes, ""])
    path.write_text("\n".join(parts), encoding="utf-8")
    return path


class ResumeSummaryTest(unittest.TestCase):
    def setUp(self):
        if not SCRIPT_SOURCE.exists():
            self.skipTest("pm_resume.py is missing from .pm/tools")
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        run_git(self.root, "init")
        run_git(self.root, "config", "user.name", "Test")
        run_git(self.root, "config", "user.email", "test@example.com")
        (self.root / "backlog.config.yml").write_text("# test fixture\n", encoding="utf-8")
        tools_dir = self.root / ".pm" / "tools"
        tools_dir.mkdir(parents=True)
        shutil.copy(SCRIPT_SOURCE, tools_dir / "pm_resume.py")

    def commit_subjects(self, subjects):
        for index, subject in enumerate(subjects):
            (self.root / "history.txt").write_text(f"revision {index}\n", encoding="utf-8")
            run_git(self.root, "add", "history.txt")
            run_git(self.root, "commit", "-m", subject)

    def make_worktree(self, name, with_report=False):
        worktree = self.root / ".worktrees" / name
        worktree.mkdir(parents=True, exist_ok=True)
        if with_report:
            (worktree / ".pm-report.md").write_text("# pending report\n", encoding="utf-8")
        return worktree

    def run_resume(self):
        return subprocess.run(
            [sys.executable, str(self.root / ".pm" / "tools" / "pm_resume.py")],
            cwd=self.root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

    def warnings_section(self, out):
        self.assertIn("## Warnings", out)
        return out.split("## Warnings", 1)[1]

    def test_heading_order_and_git_sections(self):
        subjects = [
            "subject-alpha",
            "subject-bravo",
            "subject-charlie",
            "subject-delta",
            "subject-echo",
            "subject-foxtrot",
        ]
        self.commit_subjects(subjects)
        expected_status = run_git(self.root, "status", "-sb")

        result = self.run_resume()

        self.assertEqual(result.returncode, 0, result.stderr)
        out = result.stdout
        positions = []
        for heading in HEADINGS:
            self.assertIn(heading, out)
            positions.append(out.index(heading))
        self.assertEqual(positions, sorted(positions))
        for line in expected_status.strip().splitlines():
            self.assertIn(line.strip(), out)
        for subject in subjects[1:]:
            self.assertIn(subject, out)
        self.assertNotIn(subjects[0], out)

    def test_active_task_live_block_and_status_filter(self):
        self.commit_subjects(["setup"])
        self.make_worktree("b1-resume")
        write_task(self.root, "TASK-1.2", "Package B: resume summary", "Active", notes=LIVE_BLOCK)
        write_task(self.root, "TASK-2.2", "Ready package", "Ready")
        write_task(self.root, "TASK-3.3", "Review package", "In review", notes="Next: Awaiting review")
        write_task(self.root, "TASK-4.4", "Owner check package", "Owner check", notes="Next: Awaiting approval")
        write_task(self.root, "TASK-5.5", "Done package", "Done")

        result = self.run_resume()

        self.assertEqual(result.returncode, 0, result.stderr)
        out = result.stdout.split("## Open tasks", 1)[1].split("## Waiting on the owner", 1)[0]
        self.assertIn(ACTIVE_TASK_LINE, out)
        for line in LIVE_LINES:
            self.assertIn(line, out)
        self.assertIn("TASK-3.3", out)
        self.assertIn("[In review]", out)
        self.assertIn("TASK-4.4", out)
        self.assertIn("[Owner check]", out)
        self.assertNotIn("TASK-2.2", out)
        self.assertNotIn("Ready package", out)
        self.assertNotIn("TASK-5.5", out)
        self.assertNotIn("Done package", out)

    def test_owner_section_lists_open_tasks_waiting_on_owner(self):
        self.commit_subjects(["setup"])
        write_task(self.root, "TASK-1", "Ready", "Ready", notes="Needs owner: A/B/C choice")
        write_task(self.root, "TASK-2", "Active", "Active", notes="Needs owner: none")
        write_task(self.root, "TASK-3", "Done", "Done", notes="Needs owner: old request")
        write_task(self.root, "TASK-4", "Silent", "Ready")
        write_task(self.root, "TASK-5", "Template", "Active", notes="Needs owner: nothing")

        result = self.run_resume()

        self.assertEqual(result.returncode, 0, result.stderr)
        section = result.stdout.split("## Waiting on the owner", 1)[1].split("## Waiting", 1)[0]
        self.assertIn("- TASK-1 [Ready]: A/B/C choice", section)
        self.assertNotIn("TASK-2", section)
        self.assertNotIn("TASK-3", section)
        self.assertNotIn("TASK-4", section)
        self.assertNotIn("TASK-5", section)

    def test_owner_line_with_a_parenthetical_counts(self):
        self.commit_subjects(["setup"])
        write_task(self.root, "TASK-1", "Two leads", "Active", notes="Needs owner (both leads agree): four decisions")

        result = self.run_resume()

        self.assertEqual(result.returncode, 0, result.stderr)
        section = result.stdout.split("## Waiting on the owner", 1)[1].split("## Waiting", 1)[0]
        self.assertIn("- TASK-1 [Active]: four decisions", section)

    def test_warns_when_commits_follow_the_newest_worklog(self):
        worklog_dir = self.root / ".pm" / "worklog"
        worklog_dir.mkdir(parents=True)
        (worklog_dir / "2025-06-01-0900-old.md").write_text("# old\n", encoding="utf-8")
        (worklog_dir / "2025-06-02-0900-new.md").write_text("# new\n", encoding="utf-8")
        run_git(self.root, "add", ".pm/worklog")
        run_git(self.root, "commit", "-m", "worklog")
        self.assertNotIn("worklog", self.warnings_section(self.run_resume().stdout))

        self.commit_subjects(["later work", "more work"])

        warnings = self.warnings_section(self.run_resume().stdout)
        self.assertIn("2025-06-02-0900-new.md", warnings)
        self.assertIn("2 commit", warnings)

        # A commit is recorded by a task closed with a summary or by an open task's file;
        # an unknown task or a Done task without a summary records nothing.
        path = write_task(self.root, "TASK-1", "Closed", "Done")
        text = "\n## Final Summary\n\n<!-- SECTION:FINAL_SUMMARY:BEGIN -->\nDone.\n<!-- SECTION:FINAL_SUMMARY:END -->\n"
        path.write_text(path.read_text(encoding="utf-8") + text, encoding="utf-8")
        write_task(self.root, "TASK-2", "Open", "Active", notes="Next: more")
        write_task(self.root, "TASK-3", "Closed bare", "Done")
        self.commit_with("feat: closed work", "Refs: TASK-1\nAssisted-by: M (high)", "2025-06-03")
        self.commit_with("feat: open work", "Refs: TASK-1, TASK-2\nAssisted-by: M (high)", "2025-06-03")
        self.assertIn("2 commit", self.warnings_section(self.run_resume().stdout))
        self.commit_with("feat: typo", "Refs: TASK-9\nAssisted-by: M (high)", "2025-06-03")
        self.commit_with("feat: bare", "Refs: TASK-3\nAssisted-by: M (high)", "2025-06-03")
        self.assertIn("4 commit", self.warnings_section(self.run_resume().stdout))

        # A draft's file holds its work too, like an open task's.
        drafts_dir = self.root / ".pm" / "backlog" / "drafts"
        drafts_dir.mkdir(parents=True)
        draft = "---\nid: DRAFT-1\ntitle: Parked idea\nstatus: Draft\n---\n"
        (drafts_dir / "draft-1 - Parked-idea.md").write_text(draft, encoding="utf-8")
        self.commit_with("chore: park the idea", "Refs: DRAFT-1\nAssisted-by: M (high)", "2025-06-03")
        self.assertIn("4 commit", self.warnings_section(self.run_resume().stdout))

        # So does an archived draft's.
        archived_dir = self.root / ".pm" / "backlog" / "archive" / "drafts"
        archived_dir.mkdir(parents=True)
        archived = "---\nid: DRAFT-2\ntitle: Settled idea\nstatus: Draft\n---\n"
        (archived_dir / "draft-2 - Settled-idea.md").write_text(archived, encoding="utf-8")
        self.commit_with("chore: settle the idea", "Refs: DRAFT-2\nAssisted-by: M (high)", "2025-06-03")
        self.assertIn("4 commit", self.warnings_section(self.run_resume().stdout))

    def test_names_finished_tasks_in_the_newest_worklogs_next(self):
        worklog_dir = self.root / ".pm" / "worklog"
        worklog_dir.mkdir(parents=True)
        (worklog_dir / "2025-06-01-0900-old.md").write_text("## Next\n\n1. TASK-3\n", encoding="utf-8")
        text = "## Asked\n\n1. TASK-1\n\n## Next: resume here\n\n1. TASK-1, then TASK-1.1.\n2. TASK-2.\n\n## Found\n\nTASK-3\n"
        (worklog_dir / "2025-06-02-0900-new.md").write_text(text, encoding="utf-8")
        write_task(self.root, "TASK-2", "Open", "Active", notes="Next: more")
        self.assertNotIn("are done now", self.warnings_section(self.run_resume().stdout))

        for task_id in ("TASK-1", "TASK-1.1", "TASK-3"):
            write_task(self.root, task_id, "Closed", "Done")
        warnings = self.warnings_section(self.run_resume().stdout)
        self.assertIn("(2025-06-02-0900-new.md) are done now: TASK-1, TASK-1.1\n", warnings)

    def commit_files(self, message, *paths):
        for path in paths:
            (self.root / path).parent.mkdir(parents=True, exist_ok=True)
            (self.root / path).write_text("x\n", encoding="utf-8")
        run_git(self.root, "add", "-A")
        run_git(self.root, "commit", "-m", message)

    def test_warns_when_folders_change_after_the_map(self):
        # No map, no warning: the map layer is optional.
        self.commit_files("start", "src/app/main.py")
        self.commit_files("more", "src/lib/util.py")
        self.assertNotIn("Map may be", self.warnings_section(self.run_resume().stdout))

        self.commit_files("map", "map/model.c4")
        # New files in known folders, docs, dot-folders and the map's own folder are no structural change.
        self.commit_files("same shape", "src/app/cli.py", "docs/guide/a.md", ".github/x.yml", "map/sub/b.c4")
        self.assertNotIn("Map may be", self.warnings_section(self.run_resume().stdout))

        self.commit_files("new module", "src/store/db.py")
        run_git(self.root, "rm", "-q", "src/lib/util.py")
        run_git(self.root, "commit", "-m", "drop lib")
        warnings = self.warnings_section(self.run_resume().stdout)
        self.assertIn("Map may be out of date", warnings)
        self.assertIn(": src/lib, src/store\n", warnings)

        # The map catches up: the warning goes away.
        (self.root / "map" / "model.c4").write_text("y\n", encoding="utf-8")
        run_git(self.root, "commit", "-am", "map store")
        self.assertNotIn("Map may be", self.warnings_section(self.run_resume().stdout))

        # A map kept beside the code does not hide that code's folders.
        self.commit_files("map beside code", "src/model.c4")
        self.commit_files("new module", "src/api/routes.py")
        self.assertIn(": src/api\n", self.warnings_section(self.run_resume().stdout))

    def test_last_closed_tasks_show_their_summary_newest_first(self):
        self.commit_subjects(["setup"])

        def done(task_id, title, updated, summary, folder="tasks"):
            path = write_task(self.root, task_id, title, "Done")
            text = path.read_text(encoding="utf-8").replace("labels: []", f"labels: []\nupdated_date: '{updated}'")
            if summary:
                text += "\n## Final Summary\n\n<!-- SECTION:FINAL_SUMMARY:BEGIN -->\n" + summary
                text += "\n<!-- SECTION:FINAL_SUMMARY:END -->\n"
            if folder != "tasks":
                target = self.root / ".pm" / "backlog" / folder
                target.mkdir(parents=True, exist_ok=True)
                path.unlink()
                path = target / path.name
            path.write_text(text, encoding="utf-8")

        done("TASK-1", "Oldest", "2025-06-01 09:00", "Oldest summary.")
        done("TASK-2", "Middle", "2025-06-02 09:00", "Middle summary.\nEvidence: 9 tests OK\nNext: none.")
        done("TASK-3", "Moved", "2025-06-03 09:00", "Completed summary.", folder="completed")
        done(
            "TASK-4",
            "Newest",
            "2025-06-04 09:00",
            "Newest summary.\nSam said: ship it.\nFound: one gap.",
            folder="archive/tasks",
        )
        done("TASK-5", "No summary", "2025-06-05 09:00", None)
        write_task(self.root, "TASK-6", "Still open", "Ready", notes="Next: later")

        out = self.run_resume().stdout
        self.assertLess(out.index("## Last 5 commits"), out.index("## Recently closed tasks"))
        section = out.split("## Recently closed tasks", 1)[1].split("\n## ", 1)[0]
        order = [line.split(" · ")[0] for line in section.splitlines() if line.startswith("- ")]
        self.assertEqual(order, ["- TASK-4", "- TASK-3", "- TASK-2"])
        self.assertIn(
            "- TASK-4 · Newest (2025-06-04)\n  Newest summary.\n  Sam said: ship it.\n  Found: one gap.", section
        )
        self.assertIn("  Next: none.", section)
        self.assertNotIn("Evidence: 9 tests OK", section, "only the first line and the closing-summary lines are shown")
        for absent in ("TASK-1", "TASK-5", "TASK-6"):
            self.assertNotIn(absent, section)

    def commit_with(self, subject, body, day):
        (self.root / "history.txt").write_text(subject, encoding="utf-8")
        run_git(self.root, "add", "history.txt")
        run_git(self.root, "commit", "-m", subject, "-m", body, "--date", f"{day}T12:00:00")
        return run_git(self.root, "log", "-1", "--format=%h").strip()

    def run_tool(self, *args):
        return subprocess.run(
            [sys.executable, str(self.root / ".pm" / "tools" / "pm_resume.py"), *args],
            cwd=self.root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

    def test_did_lists_tasks_closed_that_day_with_that_days_commits(self):
        # Backlog writes updated_date in UTC; the tool reports the local day it falls on.
        day = datetime(2025, 6, 4, 12, 0, tzinfo=timezone.utc).astimezone().date().isoformat()
        for task_id, title, stamp in (
            ("TASK-1", "Closed today", "2025-06-04 12:00"),
            ("TASK-2", "Closed before", "2025-06-01 12:00"),
        ):
            path = write_task(self.root, task_id, title, "Done")
            text = path.read_text(encoding="utf-8").replace("labels: []", f"labels: []\nupdated_date: '{stamp}'")
            text += f"\n## Final Summary\n\n<!-- SECTION:FINAL_SUMMARY:BEGIN -->\n{title} summary.\nNext: none.\n"
            path.write_text(text + "<!-- SECTION:FINAL_SUMMARY:END -->\n", encoding="utf-8")
        write_task(self.root, "TASK-3", "Open", "Ready", notes="Next: later")
        today = self.commit_with("feat: today", "Refs: TASK-1\nAssisted-by: M (high)", day)
        self.commit_with("feat: earlier", "Refs: TASK-1\nAssisted-by: M (high)", "2025-05-30")

        out = self.run_tool("--did", day).stdout

        self.assertIn(f"Generated by `pm_board.py --did {day}`", out)
        self.assertIn(f"- TASK-1 · Closed today: Closed today summary. ({today})", out)
        for absent in ("TASK-2", "TASK-3", "Next: none"):
            self.assertNotIn(absent, out)
        self.assertIn("- (no task closed on 2025-07-01)", self.run_tool("--did", "2025-07-01").stdout)

    def test_commits_lists_one_tasks_commits_and_models(self):
        first = self.commit_with("feat: one", "Refs: TASK-1\nAssisted-by: Model A (high)", "2025-06-01")
        second = self.commit_with("fix: two", "Refs: TASK-10, TASK-1\nAssisted-by: Model B (low)", "2025-06-02")
        self.commit_with("docs: other", "Refs: TASK-1.1, TASK-10\nAssisted-by: Model C (max)", "2025-06-03")
        self.commit_with("docs: none", "Refs: none\nAssisted-by: none (human)", "2025-06-04")

        out = self.run_tool("--commits", "TASK-1").stdout

        self.assertIn("## TASK-1: 2 commits", out)
        self.assertLess(out.index(second), out.index(first), "newest first")
        self.assertIn(f"- {first} 2025-06-01 feat: one · Model A (high)", out)
        self.assertIn("Models: Model B (low), Model A (high)", out)
        self.assertNotIn("Model C", out, "TASK-1.1 and TASK-10 are other tasks")

    def test_no_closed_section_without_done_tasks(self):
        self.commit_subjects(["setup"])
        write_task(self.root, "TASK-1", "Open", "Ready", notes="Next: later")
        self.assertNotIn("## Recently closed tasks", self.run_resume().stdout)

    def test_drafts_listed_only_when_present(self):
        self.commit_subjects(["setup"])
        self.assertNotIn("## Drafts", self.run_resume().stdout)
        draft = write_task(self.root, "task-9", "Private idea", "Draft")
        drafts_dir = self.root / ".pm" / "backlog" / "drafts"
        drafts_dir.mkdir(parents=True, exist_ok=True)
        text = draft.read_text(encoding="utf-8").replace("id: task-9", "id: DRAFT-1")
        (drafts_dir / "draft-1 - private-idea.md").write_text(text, encoding="utf-8")
        draft.unlink()

        out = self.run_resume().stdout

        self.assertIn("## Drafts\n- DRAFT-1 · Private idea", out)
        self.assertLess(out.index("## Drafts"), out.index("## Warnings"))

    def run_with(self, *args, path_first=None):
        env = dict(os.environ)
        if path_first:
            env["PATH"] = str(path_first) + os.pathsep + env.get("PATH", "")
        return subprocess.run(
            [sys.executable, str(self.root / ".pm" / "tools" / "pm_resume.py"), *args],
            cwd=self.root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )

    def fake_gh(self, stdout, exit_code=0):
        """A `gh` on PATH that prints `stdout` and records its arguments in gh-args.txt."""
        bin_dir = self.root / "fake-bin"
        bin_dir.mkdir(exist_ok=True)
        script = bin_dir / "fake_gh.py"
        script.write_text(
            "import sys\n"
            f"open({str(bin_dir / 'gh-args.txt')!r}, 'a').write(' '.join(sys.argv[1:]) + '\\n')\n"
            f"sys.stdout.write({stdout!r})\n"
            f"sys.exit({exit_code})\n",
            encoding="utf-8",
        )
        if os.name == "nt":
            (bin_dir / "gh.bat").write_text(f'@"{sys.executable}" "{script}" %*\n', encoding="utf-8")
        else:
            wrapper = bin_dir / "gh"
            wrapper.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n', encoding="utf-8")
            wrapper.chmod(0o755)
        return bin_dir

    def test_ready_tasks_listed_by_name(self):
        self.commit_subjects(["setup"])
        write_task(self.root, "TASK-1", "Write the guide", "Ready")
        write_task(self.root, "TASK-2", "Ship it", "Active", notes="Next: build")

        out = self.run_resume().stdout

        section = out.split("## Ready\n", 1)[1].split("\n## ", 1)[0]
        self.assertIn("- TASK-1 · Write the guide", section)
        self.assertNotIn("TASK-2", section)
        self.assertNotIn("## Open pull requests", out, "no GitHub remote and no pr-repos.txt: nothing to ask")

    def test_brief_keeps_next_steps_and_owner_asks_only(self):
        self.commit_subjects(["setup"])
        self.make_worktree("b1-resume")
        write_task(self.root, "TASK-1.2", "Package B: resume summary", "Active", notes=LIVE_BLOCK)
        write_task(self.root, "TASK-3", "Pick a name", "Active", notes="Next: wait\nNeeds owner: pick A or B")
        write_task(self.root, "TASK-4", "Write the guide", "Ready")

        out = self.run_with("--brief").stdout

        self.assertTrue(out.startswith("# Briefing\n"))
        headings = [line for line in out.splitlines() if line.startswith("## ")]
        self.assertEqual(headings, ["## Git", "## Open tasks", "## Waiting on the owner", "## Ready", "## Warnings"])
        self.assertIn("- TASK-1.2 · Package B: resume summary [Active]\n  Next: Run tests\n", out)
        self.assertIn("  Needs owner: pick A or B", out)
        for detail in ("Evidence:", "Worker:", "Blocker:", "Needs owner: nothing"):
            self.assertNotIn(detail, out)
        self.assertIn("python .pm/tools/pm_board.py --resume", out.splitlines()[-1])

    def test_open_pull_requests_of_listed_repos(self):
        self.commit_subjects(["setup"])
        (self.root / ".pm" / "pr-repos.txt").write_text("# product\nacme/widgets\n", encoding="utf-8")
        pulls = '[{"number": 7, "title": "Fix the thing", "isDraft": false}, {"number": 9, "title": "Try", "isDraft": true}]'
        bin_dir = self.fake_gh(pulls)

        out = self.run_with(path_first=bin_dir).stdout

        section = out.split("## Open pull requests\n", 1)[1].split("\n## ", 1)[0]
        self.assertIn("- acme/widgets#7 · Fix the thing", section)
        self.assertIn("- acme/widgets#9 · Try (draft)", section)
        self.assertIn("--repo acme/widgets", (bin_dir / "gh-args.txt").read_text(encoding="utf-8"))

    def test_failed_pull_request_listing_says_so(self):
        self.commit_subjects(["setup"])
        (self.root / ".pm" / "pr-repos.txt").write_text("acme/widgets\n", encoding="utf-8")
        bin_dir = self.fake_gh("", exit_code=1)

        section = self.run_with(path_first=bin_dir).stdout.split("## Open pull requests\n", 1)[1]

        self.assertTrue(section.startswith("- ⚠️ Could not list the open pull requests of acme/widgets"))

    def test_weekly_audit_warning_until_a_recent_weekly_run(self):
        self.commit_subjects(["setup"])
        audits = self.root / ".pm" / "local" / "audits"

        self.assertIn("Weekly doc audit due (never ran)", self.warnings_section(self.run_resume().stdout))

        (audits / "weekly-2020-01-01").mkdir(parents=True)
        (audits / "weekly-2020-01-01" / "lead-verification.md").write_text("all true\n", encoding="utf-8")
        self.assertIn("(last: 2020-01-01)", self.warnings_section(self.run_resume().stdout))

        today = audits / f"weekly-{date.today().isoformat()}"
        today.mkdir()
        (audits / "delivery-2099-01-01").mkdir()
        self.assertIn("(last: 2020-01-01)", self.warnings_section(self.run_resume().stdout), "an empty folder counts")

        (today / "lead-verification.md").write_text("\n", encoding="utf-8")
        self.assertIn("(last: 2020-01-01)", self.warnings_section(self.run_resume().stdout), "an empty file counts")

        (today / "lead-verification.md").write_text("15 findings, all true\n", encoding="utf-8")
        self.assertNotIn("Weekly doc audit", self.run_resume().stdout)

    def held_section(self, out):
        return out.split("## Waiting and ageing work", 1)[1].split("\n## ", 1)[0]

    def test_held_section_lists_stale_ready_tasks_and_passed_review_dates(self):
        self.commit_subjects(["setup"])
        future = (date.today() + timedelta(days=30)).isoformat()
        write_task(self.root, "TASK-1", "Old and silent", "Ready")
        write_task(self.root, "TASK-2", "Held with a date", "Ready", notes=f"Review by: {future} · Sam · after TASK-9")
        write_task(self.root, "TASK-3", "Date passed", "Ready", notes="Review by: 2025-07-01 · Sam · after TASK-9")
        write_task(self.root, "TASK-4", "Looked at today", "Ready", notes=f"Reviewed: {date.today().isoformat()}")
        write_task(self.root, "TASK-5", "Working", "Active")

        section = self.held_section(self.run_resume().stdout)

        self.assertIn("WIP): 1/7 · Ready: 4", section)
        self.assertIn("💤 TASK-1 ·", section)
        self.assertIn("(opened 2025-06-01): Old and silent", section)
        self.assertNotIn("TASK-2", section)
        self.assertIn("⏰ TASK-3 · review date passed: 2025-07-01", section)
        self.assertNotIn("TASK-4", section)
        self.assertNotIn("TASK-5", section)

    def test_passed_review_date_shows_for_open_tasks_of_any_status(self):
        self.commit_subjects(["setup"])
        passed = "Review by: 2025-07-01 · Sam · after TASK-9"
        for task_id, status in (("TASK-1", "Active"), ("TASK-2", "In review"), ("TASK-3", "Owner check")):
            write_task(self.root, task_id, f"Followup {task_id}", status, notes=passed)
        write_task(self.root, "TASK-4", "Closed", "Done", notes=passed)

        section = self.held_section(self.run_resume().stdout)

        for task_id in ("TASK-1", "TASK-2", "TASK-3"):
            self.assertIn(f"⏰ {task_id} · review date passed", section)
        self.assertNotIn("TASK-4", section)

    def test_age_counts_from_the_newest_reviewed_date_and_ignores_updated_date(self):
        self.commit_subjects(["setup"])
        old, recent = (date.today() - timedelta(days=40)).isoformat(), (date.today() - timedelta(days=3)).isoformat()
        write_task(self.root, "TASK-1", "Reviewed twice", "Ready", notes=f"Reviewed: {old}\nReviewed: {recent}")
        path = write_task(self.root, "TASK-2", "Touched lately", "Ready", notes="Next: a plain note")
        path.write_text(
            path.read_text(encoding="utf-8").replace("labels: []", f"labels: []\nupdated_date: '{recent} 09:00'"),
            encoding="utf-8",
        )
        write_task(
            self.root, "TASK-3", "Fourteen days", "Ready", notes=f"Reviewed: {date.today() - timedelta(days=14)}"
        )
        write_task(self.root, "TASK-4", "Fifteen days", "Ready", notes=f"Reviewed: {date.today() - timedelta(days=15)}")

        section = self.held_section(self.run_resume().stdout)

        self.assertNotIn("TASK-1", section)
        self.assertIn("💤 TASK-2 ·", section)
        self.assertNotIn("TASK-3", section)
        self.assertIn("💤 TASK-4 · waiting 15 days", section)

    def test_wip_counts_top_level_tasks_only(self):
        self.commit_subjects(["setup"])
        write_task(self.root, "TASK-1", "Epic", "Active")
        write_task(self.root, "TASK-1.1", "Leaf", "Active")
        write_task(self.root, "TASK-2", "Finished parent", "Active")
        write_task(self.root, "TASK-2.1", "Done child", "Done")
        tasks = self.root / ".pm" / "backlog" / "tasks"
        for name, parent in (("task-1.1 - leaf.md", "TASK-1"), ("task-2.1 - done-child.md", "TASK-2")):
            path = tasks / name
            path.write_text(
                path.read_text(encoding="utf-8").replace("labels: []", f"labels: []\nparent_task_id: {parent}"),
                encoding="utf-8",
            )

        self.assertIn("WIP): 2/7 ·", self.held_section(self.run_resume().stdout))

    def test_report_findings_skip_fenced_examples_and_other_sections(self):
        self.commit_subjects(["setup"])
        report = self.root / ".pm" / "local" / "audits" / "weekly-2025-06-01" / "report.md"
        report.parent.mkdir(parents=True)
        report.write_text(
            "## Findings\n\n| # | Where |\n|---|---|\n| 1 | a |\n\n```\n| 99 | example |\n```\n\n"
            "### Detail\n\n| 2 | b |\n\n# Appendix\n\n| 77 | unrelated |\n\n## Other\n\n| 88 | unrelated |\n",
            encoding="utf-8",
        )
        table = (
            "Audit outcomes:\n| # | Verified | Outcome | Evidence |\n|---|---|---|---|\n| 1 | yes | fixed | abc1234 |"
        )
        notes = "Audit report: .pm/local/audits/weekly-2025-06-01/report.md\n" + table
        write_task(self.root, "TASK-1", "Audit", "Active", notes=notes)

        warnings = self.warnings_section(self.run_resume().stdout)

        self.assertIn("Audit without outcomes: TASK-1 has no outcome for finding 2", warnings)
        for number in ("99", "77", "88"):
            self.assertNotIn(number, warnings)

    def test_open_audit_task_without_outcomes_warns(self):
        self.commit_subjects(["setup"])
        report = self.root / ".pm" / "local" / "audits" / "weekly-2025-06-01" / "report.md"
        report.parent.mkdir(parents=True)
        report.write_text("## Findings\n\n| # | Where |\n|---|---|\n| 1 | a |\n| 2 | b |\n", encoding="utf-8")
        line = "Audit report: .pm/local/audits/weekly-2025-06-01/report.md"
        write_task(self.root, "TASK-1", "Audit", "Active", notes=line)

        self.assertIn(
            "Audit without outcomes: TASK-1 has no outcome written for its findings",
            self.warnings_section(self.run_resume().stdout),
        )

        table = (
            "Audit outcomes:\n| # | Verified | Outcome | Evidence |\n|---|---|---|---|\n| 1 | yes | fixed | abc1234 |"
        )
        write_task(self.root, "TASK-1", "Audit", "Active", notes=line + "\n" + table)
        self.assertIn(
            "Audit without outcomes: TASK-1 has no outcome for finding 2",
            self.warnings_section(self.run_resume().stdout),
        )

        write_task(self.root, "TASK-1", "Audit", "Active", notes=line + "\n" + table + "\n| 2 | yes | asked | TASK-1 |")
        self.assertNotIn("Audit without outcomes", self.run_resume().stdout)

    def test_owner_section_lists_drafts_waiting_on_owner(self):
        self.commit_subjects(["setup"])
        drafts = self.root / ".pm" / "backlog" / "drafts"
        drafts.mkdir(parents=True)
        draft = write_task(self.root, "DRAFT-1", "Private idea", "Draft", notes="Needs owner: try the shortcut")
        draft.rename(drafts / "draft-1 - private-idea.md")

        section = self.run_resume().stdout.split("## Waiting on the owner", 1)[1].split("## Waiting", 1)[0]

        self.assertIn("- DRAFT-1 [Draft]: try the shortcut", section)

    def test_backlog_section_markers_preserve_live_block(self):
        self.commit_subjects(["setup"])
        self.make_worktree("b1-resume")
        write_task(
            self.root,
            "TASK-1.2",
            "Package B: resume summary",
            "Active",
            notes="<!-- SECTION:NOTES:BEGIN -->\n" + LIVE_BLOCK + "\n<!-- SECTION:NOTES:END -->",
        )

        result = self.run_resume()

        self.assertEqual(result.returncode, 0, result.stderr)
        for line in LIVE_LINES:
            self.assertIn(line, result.stdout)
        self.assertNotIn("Orphan worktree: .worktrees/b1-resume", self.warnings_section(result.stdout))

    def test_warnings_for_orphan_missing_and_pending_report(self):
        self.commit_subjects(["setup"])
        self.make_worktree("orphan")
        self.make_worktree("b1-resume", with_report=True)
        write_task(self.root, "TASK-1.2", "Package B: resume summary", "Active", notes=LIVE_BLOCK)
        write_task(self.root, "TASK-9.9", "Lost worktree", "Active", notes=MISSING_WORKER_BLOCK)

        result = self.run_resume()

        self.assertEqual(result.returncode, 0, result.stderr)
        out = result.stdout
        section = self.warnings_section(out)
        self.assertIn("- ⚠️ Orphan worktree: .worktrees/orphan", section)
        self.assertIn("- ⚠️ Missing worktree: TASK-9.9", section)
        self.assertIn("- ⚠️ Pending report: .worktrees/b1-resume/.pm-report.md", section)
        self.assertNotIn("- (none)", section)

    def test_multiple_worker_lines_render_and_reference_worktrees(self):
        self.commit_subjects(["setup"])
        self.make_worktree("b1-resume")
        self.make_worktree("b2-resume-tests")
        notes = (
            "Next: Run tests\n"
            "Evidence: abc123 passed 4 tests\n"
            "Blocker: none\n"
            "Needs owner: nothing\n"
            "Worker: GPT-6 Luna · .worktrees/b1-resume · .worktrees/b1-resume/.pm-report.md\n"
            "Worker: Kimi K3 · .worktrees/b2-resume-tests · .worktrees/b2-resume-tests/.pm-report.md"
        )
        write_task(self.root, "TASK-1.2", "Package B: resume summary", "Active", notes=notes)

        result = self.run_resume()

        self.assertEqual(result.returncode, 0, result.stderr)
        out = result.stdout
        self.assertIn("Worker: GPT-6 Luna · .worktrees/b1-resume", out)
        self.assertIn("Worker: Kimi K3 · .worktrees/b2-resume-tests", out)
        section = self.warnings_section(out)
        self.assertNotIn("Orphan worktree: .worktrees/b1-resume", section)
        self.assertNotIn("Orphan worktree: .worktrees/b2-resume-tests", section)

    def test_missing_worktree_warns_per_worker(self):
        self.commit_subjects(["setup"])
        notes = (
            "Next: Run tests\n"
            "Worker: GPT-6 Luna · .worktrees/missing-a · .worktrees/missing-a/.pm-report.md\n"
            "Worker: Kimi K3 · .worktrees/missing-b · .worktrees/missing-b/.pm-report.md"
        )
        write_task(self.root, "TASK-1.2", "Package B: resume summary", "Active", notes=notes)

        result = self.run_resume()

        self.assertEqual(result.returncode, 0, result.stderr)
        section = self.warnings_section(result.stdout)
        self.assertEqual(section.count("- ⚠️ Missing worktree: TASK-1.2"), 2)
        self.assertIn("Missing worktree: TASK-1.2 · .worktrees/missing-a", section)
        self.assertIn("Missing worktree: TASK-1.2 · .worktrees/missing-b", section)

    def test_find_root_resolves_root_from_nested_package_layout(self):
        self.commit_subjects(["setup"])
        self.make_worktree("b1-resume")
        write_task(self.root, "TASK-1.2", "Package B: resume summary", "Active", notes=LIVE_BLOCK)

        # Copy the script into a package nested more than two levels deep; the
        # old fixed parents[2] root would miss the fixture root.
        nested_tools = self.root / "vendor" / "pkg" / ".pm" / "tools"
        nested_tools.mkdir(parents=True)
        shutil.copy(SCRIPT_SOURCE, nested_tools / "pm_resume.py")

        result = subprocess.run(
            [sys.executable, str(nested_tools / "pm_resume.py")],
            cwd=self.root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(ACTIVE_TASK_LINE, result.stdout)

    def test_done_task_worker_names_worktree_without_being_listed(self):
        self.commit_subjects(["setup"])
        self.make_worktree("old-worker")
        write_task(
            self.root,
            "TASK-6.6",
            "Finished task",
            "Done",
            notes="Worker: Kimi K3 · .worktrees/old-worker · .worktrees/old-worker/.pm-report.md",
        )
        write_task(self.root, "TASK-1.2", "Package B: resume summary", "Active", notes=NO_WORKER_BLOCK)

        result = self.run_resume()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("TASK-6.6", result.stdout)
        self.assertNotIn("Orphan worktree: .worktrees/old-worker", self.warnings_section(result.stdout))

    def test_no_pending_report_warning_without_report_files(self):
        self.commit_subjects(["setup"])
        self.make_worktree("orphan")
        write_task(self.root, "TASK-1.2", "Package B: resume summary", "Active", notes=NO_WORKER_BLOCK)

        result = self.run_resume()

        self.assertEqual(result.returncode, 0, result.stderr)
        out = result.stdout
        section = self.warnings_section(out)
        self.assertIn("- ⚠️ Orphan worktree: .worktrees/orphan", section)
        self.assertNotIn("Pending report", section)

    def test_missing_live_fields_show_question_mark(self):
        self.commit_subjects(["setup"])
        write_task(self.root, "TASK-1.2", "Package B: resume summary", "Active", notes="Next: Run tests")

        result = self.run_resume()

        self.assertEqual(result.returncode, 0, result.stderr)
        out = result.stdout
        self.assertIn("Next: Run tests", out)
        self.assertIn("Evidence: ?", out)
        self.assertIn("Blocker: ?", out)
        self.assertIn("Needs owner: ?", out)

    def test_malformed_task_file_does_not_crash(self):
        self.commit_subjects(["setup"])
        self.make_worktree("b1-resume")
        tasks_dir = self.root / ".pm" / "backlog" / "tasks"
        tasks_dir.mkdir(parents=True, exist_ok=True)
        (tasks_dir / "task-7.7 - broken.md").write_text(
            "---\nid: TASK-7.7\ntitle: Broken task\nstatus: Active\n## Implementation Notes\nNext: yok\n",
            encoding="utf-8",
        )
        write_task(self.root, "TASK-1.2", "Package B: resume summary", "Active", notes=LIVE_BLOCK)

        result = self.run_resume()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(ACTIVE_TASK_LINE, result.stdout)


class FrontmatterTitleTest(unittest.TestCase):
    """Backlog writes long titles as folded YAML and escapes apostrophes by doubling them."""

    @classmethod
    def setUpClass(cls):
        import importlib.util

        spec = importlib.util.spec_from_file_location("pm_resume", SCRIPT_SOURCE)
        cls.pm_resume = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.pm_resume)

    def test_folded_title_is_joined_into_one_line(self):
        lines = [
            "---",
            "id: TASK-1",
            "title: >-",
            "  Harden the runner: stop",
            "  before retry",
            "status: Ready",
            "---",
        ]

        fields = self.pm_resume.read_frontmatter(lines)

        self.assertEqual(fields["title"], "Harden the runner: stop before retry")
        self.assertEqual(fields["status"], "Ready")

    def test_single_quoted_title_unescapes_doubled_apostrophe(self):
        fields = self.pm_resume.read_frontmatter(["---", "title: 'Sam''s foundations'", "---"])

        self.assertEqual(fields["title"], "Sam's foundations")


if __name__ == "__main__":
    unittest.main()
