"""Tests for tools/pm_board.py --tree (Epic tree with progress).

pm_board --tree prints the Epic tree with per-node [done/total] progress in
Turkish Markdown. These tests run the CLI via subprocess against task files in
temporary directories, testing each acceptance rule from the tree brief without
inspecting the implementation.
"""

import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PM_BOARD = Path(__file__).resolve().parent.parent / "tools" / "pm_board.py"

TODAY = "2026-09-23"


def _remove_readonly(func, path, _exc_info):
    """Windows safety for temp dir cleanup."""
    os.chmod(path, stat.S_IWRITE)
    func(path)


class PmTreeTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="pm_tree_test_"))
        self.addCleanup(shutil.rmtree, self.temp_dir, False, _remove_readonly)
        self.tasks_dir = self.temp_dir / "tasks"
        self.tasks_dir.mkdir(parents=True, exist_ok=True)

    def write_task(self, filename, content):
        path = self.tasks_dir / filename
        path.write_text(content, encoding="utf-8")
        return path

    def make_task(self, filename, task_id, title, status, type_="", parent=""):
        """Write a task file with the brief's frontmatter shape."""
        lines = [
            "---",
            f"id: {task_id}",
            f"title: {title}",
            f"status: {status}",
        ]
        if type_:
            lines.append(f"type: {type_}")
        if parent:
            lines.append(f"parent_task_id: {parent}")
        lines.append("---")
        return self.write_task(filename, "\n".join(lines) + "\n")

    def run_board(self, *args):
        return subprocess.run(
            [sys.executable, str(PM_BOARD), *args],
            cwd=self.temp_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )

    def run_tree(self):
        return self.run_board("--tasks", str(self.tasks_dir), "--tree", "--today", TODAY)


class SampleTreeOutputTest(PmTreeTestCase):
    def test_sample_tree_reproduced_exactly(self):
        """AC: the brief's example tree is reproduced exactly."""
        self.make_task("task-1.md", "TASK-1", "Epic A", "Active", type_="epic")
        self.make_task(
            "task-1-1.md",
            "TASK-1.1",
            "Package A1",
            "Done",
            type_="package",
            parent="TASK-1",
        )
        self.make_task("task-1-1-1.md", "TASK-1.1.1", "Leaf", "Done", parent="TASK-1.1")
        self.make_task(
            "task-1-2.md",
            "TASK-1.2",
            "Package A2",
            "Ready",
            type_="package",
            parent="TASK-1",
        )
        self.make_task("task-5.md", "TASK-5", "Small epic", "Ready", type_="epic")
        self.make_task("task-9.md", "TASK-9", "Lost child", "Ready", parent="TASK-8")

        result = self.run_tree()

        self.assertEqual(result.returncode, 0)
        expected = (
            "# Epic ağacı (2026-09-23)\n"
            "- TASK-1 · Epic A · Devam ediyor [1/2]\n"
            "  - TASK-1.1 · Package A1 · Bitti [1/1]\n"
            "    - TASK-1.1.1 · Leaf · Bitti\n"
            "  - TASK-1.2 · Package A2 · Sırada\n"
            "- TASK-5 · Small epic · Sırada [0/0]\n"
            "\n"
            "## Sahipsiz\n"
            "- TASK-9 · Lost child · Sırada (ebeveyn yok: TASK-8)\n"
        )
        self.assertEqual(result.stdout.strip(), expected.strip())


class EpicWithoutChildrenTest(PmTreeTestCase):
    def test_epic_without_children_shows_zero_zero(self):
        """Rule 4: an epic without children shows [0/0]; leaves show no brackets."""
        self.make_task("task-5.md", "TASK-5", "Small epic", "Ready", type_="epic")

        result = self.run_tree()

        self.assertEqual(result.returncode, 0)
        expected = "# Epic ağacı (2026-09-23)\n- TASK-5 · Small epic · Sırada [0/0]\n"
        self.assertEqual(result.stdout.strip(), expected.strip())
        self.assertNotIn("## Sahipsiz", result.stdout)


class OrphanSectionTest(PmTreeTestCase):
    def test_orphan_listed_under_sahipsiz(self):
        """Rule 6: a task whose parent id does not exist goes under '## Sahipsiz'."""
        self.make_task("task-1.md", "TASK-1", "Epic A", "Active", type_="epic")
        self.make_task("task-9.md", "TASK-9", "Lost child", "Ready", parent="TASK-8")

        result = self.run_tree()

        self.assertEqual(result.returncode, 0)
        self.assertIn("## Sahipsiz", result.stdout)
        self.assertIn("- TASK-9 · Lost child · Sırada (ebeveyn yok: TASK-8)", result.stdout)
        # the orphan is not a tree node: no indented line for it
        self.assertNotIn("  - TASK-9", result.stdout)

    def test_sahipsiz_section_absent_without_orphans(self):
        """Rule 6: the '## Sahipsiz' section is omitted when there are no orphans."""
        self.make_task("task-1.md", "TASK-1", "Epic A", "Active", type_="epic")
        self.make_task("task-1-1.md", "TASK-1.1", "Package A1", "Done", parent="TASK-1")

        result = self.run_tree()

        self.assertEqual(result.returncode, 0)
        self.assertNotIn("## Sahipsiz", result.stdout)
        self.assertNotIn("ebeveyn yok", result.stdout)


class CycleTest(PmTreeTestCase):
    def test_two_task_parent_cycle_terminates(self):
        """Rule 8: A's parent is B and B's parent is A; run ends, no node twice."""
        self.make_task("task-1.md", "TASK-1", "Cycle A", "Active", type_="epic", parent="TASK-2")
        self.make_task("task-2.md", "TASK-2", "Cycle B", "Ready", parent="TASK-1")

        # run_board's timeout=60 turns an infinite loop into a test error
        result = self.run_tree()

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.count("TASK-1 ·"), 1)
        self.assertEqual(result.stdout.count("TASK-2 ·"), 1)
        # both parents exist, so nothing is an orphan
        self.assertNotIn("## Sahipsiz", result.stdout)


class OrphanSubtreeTest(PmTreeTestCase):
    def test_orphan_subtree_printed_under_it(self):
        """Finding 1: an orphan's own children are printed beneath it, not dropped."""
        self.make_task("task-1.md", "TASK-1", "Epic A", "Active", type_="epic")
        self.make_task("task-9.md", "TASK-9", "Lost hub", "Ready", parent="TASK-8")
        self.make_task("task-9-1.md", "TASK-9.1", "Lost kid", "Done", parent="TASK-9")

        result = self.run_tree()

        self.assertEqual(result.returncode, 0)
        self.assertIn("## Sahipsiz", result.stdout)
        self.assertIn("- TASK-9 · Lost hub · Sırada (ebeveyn yok: TASK-8)", result.stdout)
        self.assertIn("  - TASK-9.1 · Lost kid · Bitti", result.stdout)


class CycleSectionTest(PmTreeTestCase):
    def test_non_epic_cycle_listed_under_dongu(self):
        """Finding 2: a parent cycle among non-epic tasks is listed under '## Döngü'."""
        self.make_task("task-1.md", "TASK-1", "Cycle A", "Active", parent="TASK-2")
        self.make_task("task-2.md", "TASK-2", "Cycle B", "Ready", parent="TASK-1")

        result = self.run_tree()

        self.assertEqual(result.returncode, 0)
        self.assertIn("## Döngü", result.stdout)
        self.assertIn("- TASK-1 · Cycle A · Devam ediyor (döngü)", result.stdout)
        self.assertIn("- TASK-2 · Cycle B · Sırada (döngü)", result.stdout)
        self.assertEqual(result.stdout.count("TASK-1 ·"), 1)
        self.assertEqual(result.stdout.count("TASK-2 ·"), 1)
        self.assertNotIn("## Sahipsiz", result.stdout)


class EpicOrphanTest(PmTreeTestCase):
    def test_epic_with_missing_parent_shown_once_as_orphan(self):
        """Finding 3: an epic whose parent is missing appears once, as an orphan."""
        self.make_task("task-2.md", "TASK-2", "Lost epic", "Active", type_="epic", parent="TASK-0")
        self.make_task("task-2-1.md", "TASK-2.1", "Epic kid", "Done", parent="TASK-2")

        result = self.run_tree()

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.count("TASK-2 ·"), 1)
        self.assertIn("- TASK-2 · Lost epic · Devam ediyor (ebeveyn yok: TASK-0)", result.stdout)
        self.assertIn("  - TASK-2.1 · Epic kid · Bitti", result.stdout)
        # never printed as a tree root with a progress bracket
        self.assertNotIn("Lost epic · Devam ediyor [", result.stdout)


class BoardUnchangedTest(PmTreeTestCase):
    def test_board_without_tree_still_prints_durum_panosu(self):
        """The normal board (no --tree) still prints '# Durum panosu'."""
        self.make_task("task-1.md", "TASK-1", "Epic A", "Active", type_="epic")

        result = self.run_board("--tasks", str(self.tasks_dir), "--today", TODAY)

        self.assertEqual(result.returncode, 0)
        self.assertIn("# Durum panosu (2026-09-23)", result.stdout)
        self.assertNotIn("Epic ağacı", result.stdout)


class RootSelectionTest(PmTreeTestCase):
    def test_parentless_non_epic_without_children_is_hidden(self):
        """Rule 1: a parentless non-epic task with no children is not shown."""
        self.make_task("task-1.md", "TASK-1", "Epic A", "Active", type_="epic")
        self.make_task("task-7.md", "TASK-7", "Loose task", "Ready")

        result = self.run_tree()

        self.assertEqual(result.returncode, 0)
        self.assertIn("- TASK-1 · Epic A · Devam ediyor [0/0]", result.stdout)
        self.assertNotIn("TASK-7", result.stdout)

    def test_parentless_non_epic_with_children_is_root(self):
        """Rule 1: a parentless non-epic task with children is shown as a root."""
        self.make_task("task-7.md", "TASK-7", "Hub", "Ready")
        self.make_task("task-7-1.md", "TASK-7.1", "Kid", "Done", parent="TASK-7")

        result = self.run_tree()

        self.assertEqual(result.returncode, 0)
        expected = "# Epic ağacı (2026-09-23)\n- TASK-7 · Hub · Sırada [1/1]\n  - TASK-7.1 · Kid · Bitti\n"
        self.assertEqual(result.stdout.strip(), expected.strip())


class UnknownStatusTest(PmTreeTestCase):
    def test_unknown_status_printed_as_is(self):
        """Rule 5: an unknown status word is printed as it is."""
        self.make_task("task-1.md", "TASK-1", "Epic A", "Blocked", type_="epic")

        result = self.run_tree()

        self.assertEqual(result.returncode, 0)
        self.assertIn("- TASK-1 · Epic A · Blocked [0/0]", result.stdout)


if __name__ == "__main__":
    unittest.main()
