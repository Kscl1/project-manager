"""Tests for tools/pm_land.py.

Each test builds a throw-away git repository and a separate records folder holding one Backlog-style task.
The Backlog CLI is replaced by a fake append function, so the tests need no Backlog install.
"""

import contextlib
import importlib.util
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PM_LAND = Path(__file__).resolve().parent.parent / "tools" / "pm_land.py"
_PM_LAND_SPEC = importlib.util.spec_from_file_location("pm_land", PM_LAND)
pm_land = importlib.util.module_from_spec(_PM_LAND_SPEC)
_PM_LAND_SPEC.loader.exec_module(pm_land)

TASK_TEXT = """---
id: TASK-1
title: Land a change
status: Active
---

## Description

Fixture task.

## Implementation Notes

Next: land the change
"""


def run_git(repo, *args):
    result = subprocess.run(
        ["git", *args],
        cwd=str(repo),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def python_command(code):
    return f'"{sys.executable}" -c "{code}"'


def marker_command(marker):
    return python_command(f"import pathlib; pathlib.Path('{marker.as_posix()}').write_text('ran')")


class LandTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        self.repo = base / "repo"
        self.records = base / "records"
        self.repo.mkdir()
        tasks = self.records / ".pm" / "backlog" / "tasks"
        tasks.mkdir(parents=True)
        self.task_path = tasks / "task-1 - land-a-change.md"
        self.task_path.write_text(TASK_TEXT, encoding="utf-8")
        run_git(self.repo, "init", "-b", "main")
        run_git(self.repo, "config", "user.name", "Test")
        run_git(self.repo, "config", "user.email", "test@example.com")
        (self.repo / "base.txt").write_text("base\n", encoding="utf-8")
        self.commit("base")
        self.base_tip = self.rev("main")
        self.patch = mock.patch.object(pm_land, "append_note", self.append_note)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def append_note(self, records, task_id, note):
        """Stand in for `backlog task edit <ID> --append-notes`; no CLI is installed for a test."""
        self.assertEqual(Path(records), self.records)
        self.assertIn(f"id: {task_id}", TASK_TEXT)
        with self.task_path.open("a", encoding="utf-8") as handle:
            handle.write(f"{note}\n")
        return 0

    def commit(self, message):
        run_git(self.repo, "add", "-A")
        run_git(self.repo, "commit", "-m", message)

    def rev(self, revision):
        return run_git(self.repo, "rev-parse", revision).strip()

    def make_feature(self):
        run_git(self.repo, "checkout", "-b", "feature")
        (self.repo / "feature.txt").write_text("feature\n", encoding="utf-8")
        self.commit("feature")
        sha = self.rev("feature")
        run_git(self.repo, "checkout", "main")
        return sha

    def task_text(self):
        return self.task_path.read_text(encoding="utf-8")

    def worktree_count(self):
        return run_git(self.repo, "worktree", "list", "--porcelain").count("worktree ")

    def run_action(self, action, commit, command=None, into="main"):
        argv = [
            action,
            commit,
            "--into",
            into,
            "--task",
            "TASK-1",
            "--repo",
            str(self.repo),
            "--records",
            str(self.records),
        ]
        if command is not None:
            argv += ["--cmd", command]
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = pm_land.main(argv)
        return code, output.getvalue()

    def test_passing_check_then_land(self):
        feature = self.make_feature()
        marker = Path(self._tmp.name) / "checked.txt"
        code, _ = self.run_action("check", feature, marker_command(marker))
        self.assertEqual(code, 0)
        self.assertTrue(marker.is_file())
        self.assertEqual(self.rev("main"), self.base_tip)  # a check never merges
        self.assertEqual(self.worktree_count(), 1)
        text = self.task_text()
        self.assertIn(f"Receipt: {feature} onto {self.base_tip} | ", text)
        self.assertIn("| exit 0 |", text)
        code, _ = self.run_action("land", feature)
        self.assertEqual(code, 0)
        self.assertEqual(self.rev("main"), feature)
        self.assertTrue((self.repo / "feature.txt").is_file())
        text = self.task_text()
        self.assertRegex(text, rf"Landed: {feature} into main \| \d{{4}}-\d{{2}}-\d{{2}}T\d{{2}}:\d{{2}}:\d{{2}}Z")
        self.assertEqual(text.count(f"Landed: {feature} into main |"), 1)

    def test_failed_check_makes_land_refuse(self):
        feature = self.make_feature()
        code, _ = self.run_action("check", feature, python_command("import sys; sys.exit(3)"))
        self.assertEqual(code, 3)
        self.assertIn("| exit 3 |", self.task_text())
        code, output = self.run_action("land", feature)
        self.assertEqual(code, 2)
        self.assertEqual(len(output.strip().splitlines()), 1)
        self.assertEqual(self.rev("main"), self.base_tip)
        self.assertNotIn("Landed:", self.task_text())
        self.assertEqual(self.worktree_count(), 1)

    def test_land_refuses_without_a_receipt(self):
        feature = self.make_feature()
        code, output = self.run_action("land", feature)
        self.assertEqual(code, 2)
        self.assertEqual(len(output.strip().splitlines()), 1)
        self.assertEqual(self.rev("main"), self.base_tip)
        self.assertNotIn("Landed:", self.task_text())

    def test_moved_target_makes_land_refuse(self):
        feature = self.make_feature()
        marker = Path(self._tmp.name) / "checked.txt"
        code, _ = self.run_action("check", feature, marker_command(marker))
        self.assertEqual(code, 0)
        (self.repo / "later.txt").write_text("later\n", encoding="utf-8")
        self.commit("later")
        moved = self.rev("main")
        code, output = self.run_action("land", feature)
        self.assertEqual(code, 2)
        self.assertEqual(len(output.strip().splitlines()), 1)
        self.assertEqual(self.rev("main"), moved)
        self.assertNotIn("Landed:", self.task_text())

    def test_landing_again_writes_nothing_and_merges_nothing(self):
        feature = self.make_feature()
        marker = Path(self._tmp.name) / "checked.txt"
        self.assertEqual(self.run_action("check", feature, marker_command(marker))[0], 0)
        self.assertEqual(self.run_action("land", feature)[0], 0)
        tip = self.rev("main")
        history = run_git(self.repo, "log", "--all", "--oneline")
        code, output = self.run_action("land", feature)
        self.assertEqual(code, 0)
        self.assertEqual(output, "")
        self.assertEqual(self.rev("main"), tip)
        self.assertEqual(run_git(self.repo, "log", "--all", "--oneline"), history)
        self.assertEqual(self.task_text().count("Landed: "), 1)

    def test_land_uses_a_throw_away_worktree_when_the_branch_is_not_checked_out(self):
        feature = self.make_feature()
        marker = Path(self._tmp.name) / "checked.txt"
        self.assertEqual(self.run_action("check", feature, marker_command(marker))[0], 0)
        run_git(self.repo, "checkout", "--detach", "HEAD")
        code, _ = self.run_action("land", feature)
        self.assertEqual(code, 0)
        self.assertEqual(self.rev("main"), feature)
        self.assertEqual(self.worktree_count(), 1)
        self.assertIn(f"Landed: {feature} into main |", self.task_text())

    def test_merge_conflict_is_a_failed_check(self):
        run_git(self.repo, "checkout", "-b", "feature")
        (self.repo / "shared.txt").write_text("feature\n", encoding="utf-8")
        self.commit("feature side")
        feature = self.rev("feature")
        run_git(self.repo, "checkout", "main")
        (self.repo / "shared.txt").write_text("main\n", encoding="utf-8")
        self.commit("main side")
        tip = self.rev("main")
        marker = Path(self._tmp.name) / "checked.txt"
        code, output = self.run_action("check", feature, marker_command(marker))
        self.assertEqual(code, 1)
        self.assertFalse(marker.exists())
        self.assertEqual(self.rev("main"), tip)
        self.assertIn("| exit 1 |", self.task_text())
        self.assertIn("Merge conflict", output)
        self.assertEqual(self.worktree_count(), 1)
        code, _ = self.run_action("land", feature)
        self.assertEqual(code, 2)

    def test_find_task_ignores_id_outside_the_frontmatter(self):
        self.task_path.unlink()
        decoy = self.task_path.with_name("task-2 - decoy.md")
        decoy.write_text("---\nid: TASK-2\ntitle: Decoy\n---\n\nid: TASK-1\n", encoding="utf-8")
        self.assertIsNone(pm_land.find_task(self.records, "TASK-1"))
        self.assertEqual(pm_land.find_task(self.records, "TASK-2"), decoy)

    def test_only_a_line_starting_with_receipt_or_landed_counts(self):
        feature = self.make_feature()
        mentioned = f"Note: Receipt: {feature} onto {self.base_tip} | true | exit 0 | 2026-01-01T00:00:00Z\n"
        mentioned += f"Note: Landed: {feature} into main | 2026-01-01T00:00:00Z\n"
        with self.task_path.open("a", encoding="utf-8") as handle:
            handle.write(mentioned)
        code, _ = self.run_action("land", feature)
        self.assertEqual(code, 2)  # a mention is not a receipt
        self.assertEqual(self.rev("main"), self.base_tip)
        self.assertNotIn("\nLanded:", self.task_text())
        receipt = f"  Receipt: {feature} onto {self.base_tip} | true | exit 0 | 2026-01-01T00:00:00Z\n"
        with self.task_path.open("a", encoding="utf-8") as handle:
            handle.write(receipt)
        code, _ = self.run_action("land", feature)
        self.assertEqual(code, 0)  # leading spaces are allowed
        text = self.task_text()
        self.assertIn(f"\nLanded: {feature} into main |", text)
        self.assertEqual(text.count(f"\nLanded: {feature}"), 1)

    def test_a_tag_named_like_the_branch_does_not_supply_the_tip(self):
        feature = self.make_feature()
        run_git(self.repo, "tag", "main", feature)
        marker = Path(self._tmp.name) / "checked.txt"
        code, _ = self.run_action("check", feature, marker_command(marker))
        self.assertEqual(code, 0)
        self.assertIn(f"Receipt: {feature} onto {self.base_tip} |", self.task_text())
        code, _ = self.run_action("land", feature, into="refs/heads/main")
        self.assertEqual(code, 0)
        self.assertEqual(self.rev("refs/heads/main"), feature)
        self.assertIn(f"Landed: {feature} into main |", self.task_text())


if __name__ == "__main__":
    unittest.main()
