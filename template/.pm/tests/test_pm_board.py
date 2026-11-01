"""Tests for tools/pm_board.py.

pm_board reads Backlog task files and prints an English status board in Markdown.
These tests run the CLI via subprocess against task files in temporary directories,
testing each acceptance line from the task brief without inspecting implementation.
"""

import importlib.util
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

PM_BOARD = Path(__file__).resolve().parent.parent / "tools" / "pm_board.py"
_PM_BOARD_SPEC = importlib.util.spec_from_file_location("pm_board", PM_BOARD)
pm_board = importlib.util.module_from_spec(_PM_BOARD_SPEC)
_PM_BOARD_SPEC.loader.exec_module(pm_board)


def _remove_readonly(func, path, _exc_info):
    """Windows safety for temp dir cleanup."""
    os.chmod(path, stat.S_IWRITE)
    func(path)


class PmBoardTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="pm_board_test_"))
        self.addCleanup(shutil.rmtree, self.temp_dir, False, _remove_readonly)
        self.tasks_dir = self.temp_dir / "tasks"
        self.tasks_dir.mkdir(parents=True, exist_ok=True)

    def write_task(self, filename, content):
        path = self.tasks_dir / filename
        path.write_text(content, encoding="utf-8")
        return path

    def run_board(self, *args):
        return subprocess.run(
            [sys.executable, str(PM_BOARD), *args],
            cwd=self.temp_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )


class ReadTaskMetadataTest(PmBoardTestCase):
    def test_reads_type_and_parent_task_id(self):
        path = self.write_task(
            "task-1.md",
            "---\nid: TASK-2\ntype: package\nparent_task_id: TASK-1\n---\n",
        )

        task = pm_board.read_task(path)

        self.assertEqual(task["type"], "package")
        self.assertEqual(task["parent"], "TASK-1")

    def test_missing_type_and_parent_default_to_empty_strings(self):
        path = self.write_task("task-1.md", "---\nid: TASK-1\n---\n")

        task = pm_board.read_task(path)

        self.assertEqual(task["type"], "")
        self.assertEqual(task["parent"], "")

    def test_quoted_parent_task_id_is_unquoted(self):
        path = self.write_task(
            "task-1.md",
            "---\nid: TASK-2\ntype: task\nparent_task_id: 'TASK-1'\n---\n",
        )

        task = pm_board.read_task(path)

        self.assertEqual(task["parent"], "TASK-1")

    def test_folded_title_is_joined_into_one_line(self):
        path = self.write_task(
            "task-1.md",
            "---\nid: TASK-1\ntitle: >-\n  Harden the runner: stop before retry,\n  time limits\nstatus: Ready\n---\n",
        )

        task = pm_board.read_task(path)

        self.assertEqual(task["title"], "Harden the runner: stop before retry, time limits")
        self.assertEqual(task["status"], "Ready")

    def test_single_quoted_title_unescapes_doubled_apostrophe(self):
        path = self.write_task("task-1.md", "---\nid: TASK-1\ntitle: 'Sam''s foundations'\n---\n")

        task = pm_board.read_task(path)

        self.assertEqual(task["title"], "Sam's foundations")


class SampleOutputTest(PmBoardTestCase):
    def test_sample_output_reproduced_exactly(self):
        """Sample output above is reproduced exactly for the same three tasks."""
        self.write_task(
            "task-1.md",
            ("---\nid: TASK-1\ntitle: Test suite\nstatus: Done\nlabels: []\n---\n\nBody of task 1.\n"),
        )
        self.write_task(
            "task-2.md",
            ("---\nid: TASK-2\ntitle: pm board\nstatus: Active\nlabels: []\n---\n\nBody of task 2.\n"),
        )
        self.write_task(
            "task-3.md",
            ("---\nid: TASK-3\ntitle: Next thing\nstatus: Ready\nlabels: []\n---\n\nBody of task 3.\n"),
        )

        result = self.run_board("--tasks", str(self.tasks_dir), "--today", "2026-09-22")

        self.assertEqual(result.returncode, 0)
        expected = (
            "# Status board (2026-09-22)\n"
            "\n"
            "WIP: 1/7 · Urgent: 0/1 · Active: 1 · In review: 0 · Owner check: 0 · Ready: 1 · Done: 1\n"
            "\n"
            "Ready: 1 (< 2) → time to plan\n"
            "\n"
            "## Active\n"
            "- TASK-2 · pm board\n"
            "\n"
            "## In review\n"
            "- (none)\n"
            "\n"
            "## Owner check\n"
            "- (none)\n"
            "\n"
            "## Ready\n"
            "- TASK-3 · Next thing\n"
            "\n"
            "## Done\n"
            "- TASK-1 · Test suite\n"
        )
        self.assertEqual(result.stdout.strip(), expected.strip())


class StatusMappingAndSectionsTest(PmBoardTestCase):
    def test_status_mapping_to_sections(self):
        """'Active' -> Active, 'Ready' -> Ready, 'Done' -> Done."""
        self.write_task(
            "task-1.md",
            "---\nid: TASK-1\ntitle: Alpha\nstatus: Active\nlabels: []\n---\n",
        )
        self.write_task(
            "task-2.md",
            "---\nid: TASK-2\ntitle: Beta\nstatus: Ready\nlabels: []\n---\n",
        )
        self.write_task(
            "task-3.md",
            "---\nid: TASK-3\ntitle: Gamma\nstatus: Done\nlabels: []\n---\n",
        )

        result = self.run_board("--tasks", str(self.tasks_dir), "--today", "2026-09-22")

        self.assertEqual(result.returncode, 0)
        self.assertIn("## Active\n- TASK-1 · Alpha", result.stdout)
        self.assertIn("## Ready\n- TASK-2 · Beta", result.stdout)
        self.assertIn("## Done\n- TASK-3 · Gamma", result.stdout)
        self.assertNotIn("## Other", result.stdout)

    def test_empty_sections_show_none(self):
        """Sections are always present; empty section shows '- (none)'."""
        self.write_task(
            "task-1.md",
            "---\nid: TASK-1\ntitle: Only Done\nstatus: Done\nlabels: []\n---\n",
        )

        result = self.run_board("--tasks", str(self.tasks_dir), "--today", "2026-09-22")

        self.assertEqual(result.returncode, 0)
        self.assertIn("## Active\n- (none)", result.stdout)
        self.assertIn("## Ready\n- (none)", result.stdout)
        self.assertIn("## Done\n- TASK-1 · Only Done", result.stdout)
        self.assertNotIn("## Other", result.stdout)

    def test_other_section_appears_only_when_other_status_exists(self):
        """Any other status maps to Other, which only appears when such tasks exist."""
        self.write_task(
            "task-1.md",
            "---\nid: TASK-1\ntitle: Blocked task\nstatus: Blocked\nlabels: []\n---\n",
        )
        self.write_task(
            "task-2.md",
            "---\nid: TASK-2\ntitle: Review task\nstatus: In Review\nlabels: []\n---\n",
        )

        result = self.run_board("--tasks", str(self.tasks_dir), "--today", "2026-09-22")

        self.assertEqual(result.returncode, 0)
        self.assertIn("## Other", result.stdout)
        self.assertIn("- TASK-1 · Blocked task", result.stdout)
        self.assertIn("- TASK-2 · Review task", result.stdout)
        # Counts line only tracks the five known lanes
        self.assertIn(
            "WIP: 0/7 · Urgent: 0/1 · Active: 0 · In review: 0 · Owner check: 0 · Ready: 0 · Done: 0",
            result.stdout,
        )

    def test_expedite_lane_and_urgent_label(self):
        """An `acil` label routes the task to the Urgent count and appends ' (urgent)'."""
        self.write_task(
            "task-1.md",
            "---\nid: TASK-1\ntitle: Normal progress\nstatus: Active\nlabels: []\n---\n",
        )
        self.write_task(
            "task-2.md",
            "---\nid: TASK-2\ntitle: Urgent progress\nstatus: Active\nlabels: [acil]\n---\n",
        )
        self.write_task(
            "task-3.md",
            "---\nid: TASK-3\ntitle: Urgent todo\nstatus: Ready\nlabels: [acil]\n---\n",
        )

        result = self.run_board("--tasks", str(self.tasks_dir), "--today", "2026-09-22")

        self.assertEqual(result.returncode, 0)
        self.assertIn(
            "WIP: 1/7 · Urgent: 1/1 · Active: 2 · In review: 0 · Owner check: 0 · Ready: 1 · Done: 0",
            result.stdout,
        )
        self.assertIn("- TASK-1 · Normal progress", result.stdout)
        self.assertIn("- TASK-2 · Urgent progress (urgent)", result.stdout)
        self.assertIn("- TASK-3 · Urgent todo (urgent)", result.stdout)


class WarningsTest(PmBoardTestCase):
    def test_warnings_not_shown_at_or_below_limit(self):
        """No warnings when WIP <= 7 and Urgent <= 1."""
        for i in range(1, 4):
            self.write_task(
                f"task-{i}.md",
                f"---\nid: TASK-{i}\ntitle: Active {i}\nstatus: Active\nlabels: []\n---\n",
            )
        self.write_task(
            "task-4.md",
            "---\nid: TASK-4\ntitle: Expedited\nstatus: Active\nlabels: [acil]\n---\n",
        )

        result = self.run_board("--tasks", str(self.tasks_dir), "--today", "2026-09-22")

        self.assertEqual(result.returncode, 0)
        self.assertIn(
            "WIP: 3/7 · Urgent: 1/1 · Active: 4 · In review: 0 · Owner check: 0 · Ready: 0 · Done: 0",
            result.stdout,
        )
        self.assertNotIn("WIP limit exceeded", result.stdout)
        self.assertNotIn("Urgent lane full", result.stdout)

    def test_wip_warning_when_active_over_limit(self):
        """'⚠️ WIP limit exceeded: N/7' when WIP > 7."""
        for i in range(1, 9):
            self.write_task(
                f"task-{i}.md",
                f"---\nid: TASK-{i}\ntitle: Active {i}\nstatus: Active\nlabels: []\n---\n",
            )

        result = self.run_board("--tasks", str(self.tasks_dir), "--today", "2026-09-22")

        self.assertEqual(result.returncode, 0)
        self.assertIn(
            "WIP: 8/7 · Urgent: 0/1 · Active: 8 · In review: 0 · Owner check: 0 · Ready: 0 · Done: 0",
            result.stdout,
        )
        self.assertIn("⚠️ WIP limit exceeded: 8/7", result.stdout)
        self.assertNotIn("Urgent lane full", result.stdout)

    def test_urgent_warning_when_urgent_over_limit(self):
        """'⚠️ Urgent lane full: N/1' when Urgent > 1."""
        for i in range(1, 3):
            self.write_task(
                f"task-{i}.md",
                f"---\nid: TASK-{i}\ntitle: Urgent {i}\nstatus: Active\nlabels: [acil]\n---\n",
            )

        result = self.run_board("--tasks", str(self.tasks_dir), "--today", "2026-09-22")

        self.assertEqual(result.returncode, 0)
        self.assertIn(
            "WIP: 0/7 · Urgent: 2/1 · Active: 2 · In review: 0 · Owner check: 0 · Ready: 0 · Done: 0",
            result.stdout,
        )
        self.assertIn("⚠️ Urgent lane full: 2/1", result.stdout)
        self.assertNotIn("WIP limit exceeded", result.stdout)

    def test_both_warnings_appear_in_stated_order(self):
        """Warnings appear right after counts and before the Ready line, in order: WIP then Urgent."""
        for i in range(1, 9):
            self.write_task(
                f"task-act-{i}.md",
                f"---\nid: TASK-{i}\ntitle: Active {i}\nstatus: Active\nlabels: []\n---\n",
            )
        for i in range(9, 11):
            self.write_task(
                f"task-acl-{i}.md",
                f"---\nid: TASK-{i}\ntitle: Urgent {i}\nstatus: Active\nlabels: [acil]\n---\n",
            )

        result = self.run_board("--tasks", str(self.tasks_dir), "--today", "2026-09-22")

        self.assertEqual(result.returncode, 0)
        self.assertIn("⚠️ WIP limit exceeded: 8/7", result.stdout)
        self.assertIn("⚠️ Urgent lane full: 2/1", result.stdout)

        pos_counts = result.stdout.index("WIP: 8/7 · Urgent: 2/1")
        pos_wip = result.stdout.index("⚠️ WIP limit exceeded: 8/7")
        pos_urgent = result.stdout.index("⚠️ Urgent lane full: 2/1")
        pos_ready = result.stdout.index("Ready: 0 (< 2) → time to plan")

        self.assertTrue(pos_counts < pos_wip < pos_urgent < pos_ready)

    def test_three_wip_lanes_three_total_no_warning(self):
        """One non-urgent task in Active, In review and Owner check is WIP 3/3, no warning."""
        self.write_task(
            "task-1.md",
            "---\nid: TASK-1\ntitle: Active one\nstatus: Active\nlabels: []\n---\n",
        )
        self.write_task(
            "task-2.md",
            "---\nid: TASK-2\ntitle: Review one\nstatus: In review\nlabels: []\n---\n",
        )
        self.write_task(
            "task-3.md",
            "---\nid: TASK-3\ntitle: Owner one\nstatus: Owner check\nlabels: []\n---\n",
        )

        result = self.run_board("--tasks", str(self.tasks_dir), "--today", "2026-09-22")

        self.assertEqual(result.returncode, 0)
        self.assertIn(
            "WIP: 3/7 · Urgent: 0/1 · Active: 1 · In review: 1 · Owner check: 1 · Ready: 0 · Done: 0",
            result.stdout,
        )
        self.assertNotIn("WIP limit exceeded", result.stdout)
        self.assertNotIn("Urgent lane full", result.stdout)

    def test_eighth_top_level_task_warns(self):
        """An eighth open top-level task in the WIP lanes triggers the warning (limit 7)."""
        for i in range(5, 9):
            self.write_task(
                f"task-{i}.md",
                f"---\nid: TASK-{i}\ntitle: Active {i}\nstatus: Active\nlabels: []\n---\n",
            )
        self.write_task(
            "task-1.md",
            "---\nid: TASK-1\ntitle: Active one\nstatus: Active\nlabels: []\n---\n",
        )
        self.write_task(
            "task-2.md",
            "---\nid: TASK-2\ntitle: Active two\nstatus: Active\nlabels: []\n---\n",
        )
        self.write_task(
            "task-3.md",
            "---\nid: TASK-3\ntitle: Review one\nstatus: In review\nlabels: []\n---\n",
        )
        self.write_task(
            "task-4.md",
            "---\nid: TASK-4\ntitle: Owner one\nstatus: Owner check\nlabels: []\n---\n",
        )

        result = self.run_board("--tasks", str(self.tasks_dir), "--today", "2026-09-22")

        self.assertEqual(result.returncode, 0)
        self.assertIn(
            "WIP: 8/7 · Urgent: 0/1 · Active: 6 · In review: 1 · Owner check: 1 · Ready: 0 · Done: 0",
            result.stdout,
        )
        self.assertIn("⚠️ WIP limit exceeded: 8/7", result.stdout)
        self.assertNotIn("Urgent lane full", result.stdout)

    def test_sub_tasks_do_not_count_toward_wip(self):
        """Only top-level work counts; any number of sub-tasks under an Epic may be open."""
        self.write_task("task-1.md", "---\nid: TASK-1\ntitle: Epic\nstatus: Active\nlabels: []\n---\n")
        for i in range(1, 10):
            self.write_task(
                f"task-1.{i}.md",
                f"---\nid: TASK-1.{i}\ntitle: Leaf {i}\nstatus: Active\nparent_task_id: TASK-1\nlabels: []\n---\n",
            )

        result = self.run_board("--tasks", str(self.tasks_dir), "--today", "2026-09-22")

        self.assertIn("WIP: 1/7 · Urgent: 0/1 · Active: 10 ·", result.stdout)
        self.assertNotIn("WIP limit exceeded", result.stdout)


class ReadyLineTest(PmBoardTestCase):
    def test_ready_line_shown_when_ready_is_0(self):
        """'Ready: N (< 2) → time to plan' appears when the Ready count == 0."""
        result = self.run_board("--tasks", str(self.tasks_dir), "--today", "2026-09-22")
        self.assertEqual(result.returncode, 0)
        self.assertIn("Ready: 0 (< 2) → time to plan", result.stdout)

    def test_ready_line_shown_when_ready_is_1(self):
        """'Ready: N (< 2) → time to plan' appears when the Ready count == 1."""
        self.write_task(
            "task-1.md",
            "---\nid: TASK-1\ntitle: One todo\nstatus: Ready\nlabels: []\n---\n",
        )
        result = self.run_board("--tasks", str(self.tasks_dir), "--today", "2026-09-22")
        self.assertEqual(result.returncode, 0)
        self.assertIn("Ready: 1 (< 2) → time to plan", result.stdout)

    def test_ready_line_not_shown_when_ready_is_2(self):
        """The Ready line does not appear when the Ready count == 2."""
        self.write_task(
            "task-1.md",
            "---\nid: TASK-1\ntitle: Todo 1\nstatus: Ready\nlabels: []\n---\n",
        )
        self.write_task(
            "task-2.md",
            "---\nid: TASK-2\ntitle: Todo 2\nstatus: Ready\nlabels: []\n---\n",
        )
        result = self.run_board("--tasks", str(self.tasks_dir), "--today", "2026-09-22")
        self.assertEqual(result.returncode, 0)
        self.assertNotIn("time to plan", result.stdout)
        self.assertNotIn("(< 2)", result.stdout)

    def test_ready_line_not_shown_when_ready_greater_than_2(self):
        """The Ready line does not appear when the Ready count > 2."""
        for i in range(1, 4):
            self.write_task(
                f"task-{i}.md",
                f"---\nid: TASK-{i}\ntitle: Todo {i}\nstatus: Ready\nlabels: []\n---\n",
            )
        result = self.run_board("--tasks", str(self.tasks_dir), "--today", "2026-09-22")
        self.assertEqual(result.returncode, 0)
        self.assertNotIn("time to plan", result.stdout)


class SortingTest(PmBoardTestCase):
    def test_sorting_by_id_number_not_text(self):
        """Tasks inside each section are sorted by the number in their id (TASK-2 before TASK-10)."""
        self.write_task(
            "task-10.md",
            "---\nid: TASK-10\ntitle: Tenth\nstatus: Ready\nlabels: []\n---\n",
        )
        self.write_task(
            "task-2.md",
            "---\nid: TASK-2\ntitle: Second\nstatus: Ready\nlabels: []\n---\n",
        )
        self.write_task(
            "task-1.md",
            "---\nid: TASK-1\ntitle: First\nstatus: Ready\nlabels: []\n---\n",
        )
        self.write_task(
            "task-20.md",
            "---\nid: TASK-20\ntitle: Twentieth\nstatus: Ready\nlabels: []\n---\n",
        )

        result = self.run_board("--tasks", str(self.tasks_dir), "--today", "2026-09-22")

        self.assertEqual(result.returncode, 0)
        pos_1 = result.stdout.index("- TASK-1 · First")
        pos_2 = result.stdout.index("- TASK-2 · Second")
        pos_10 = result.stdout.index("- TASK-10 · Tenth")
        pos_20 = result.stdout.index("- TASK-20 · Twentieth")

        self.assertTrue(pos_1 < pos_2 < pos_10 < pos_20)


class LabelsParsingTest(PmBoardTestCase):
    def test_inline_labels_format_and_unknown_fields(self):
        """Inline list format labels: [a, b] is read, unknown fields are ignored."""
        self.write_task(
            "task-1.md",
            (
                "---\n"
                "id: TASK-1\n"
                "title: Inline Urgent\n"
                "status: Active\n"
                "assignee: [someone]\n"
                "labels: [pilot, acil]\n"
                "ordinal: 500\n"
                "---\n"
            ),
        )
        self.write_task(
            "task-2.md",
            ("---\nid: TASK-2\ntitle: Inline Empty\nstatus: Active\nlabels: []\n---\n"),
        )

        result = self.run_board("--tasks", str(self.tasks_dir), "--today", "2026-09-22")

        self.assertEqual(result.returncode, 0)
        self.assertIn(
            "WIP: 1/7 · Urgent: 1/1 · Active: 2 · In review: 0 · Owner check: 0 · Ready: 0 · Done: 0",
            result.stdout,
        )
        self.assertIn("- TASK-1 · Inline Urgent (urgent)", result.stdout)
        self.assertIn("- TASK-2 · Inline Empty", result.stdout)

    def test_block_labels_format(self):
        """Block list format labels: followed by lines '  - item' is read."""
        self.write_task(
            "task-1.md",
            ("---\nid: TASK-1\ntitle: Block Urgent\nstatus: Active\nlabels:\n  - pilot\n  - acil\n---\n"),
        )
        self.write_task(
            "task-2.md",
            ("---\nid: TASK-2\ntitle: Block Non-Urgent\nstatus: Active\nlabels:\n  - pilot\n---\n"),
        )

        result = self.run_board("--tasks", str(self.tasks_dir), "--today", "2026-09-22")

        self.assertEqual(result.returncode, 0)
        self.assertIn(
            "WIP: 1/7 · Urgent: 1/1 · Active: 2 · In review: 0 · Owner check: 0 · Ready: 0 · Done: 0",
            result.stdout,
        )
        self.assertIn("- TASK-1 · Block Urgent (urgent)", result.stdout)
        self.assertIn("- TASK-2 · Block Non-Urgent", result.stdout)

    def test_both_urgent_and_acil_labels_count(self):
        """The 'urgent' label counts the same as `acil`; the title suffix is ' (urgent)'."""
        self.write_task(
            "task-1.md",
            "---\nid: TASK-1\ntitle: Urgent label\nstatus: Active\nlabels: [urgent]\n---\n",
        )
        self.write_task(
            "task-2.md",
            "---\nid: TASK-2\ntitle: Acil label\nstatus: Active\nlabels: [acil]\n---\n",
        )

        result = self.run_board("--tasks", str(self.tasks_dir), "--today", "2026-09-22")

        self.assertEqual(result.returncode, 0)
        self.assertIn(
            "WIP: 0/7 · Urgent: 2/1 · Active: 2 · In review: 0 · Owner check: 0 · Ready: 0 · Done: 0",
            result.stdout,
        )
        self.assertIn("- TASK-1 · Urgent label (urgent)", result.stdout)
        self.assertIn("- TASK-2 · Acil label (urgent)", result.stdout)
        self.assertIn("⚠️ Urgent lane full: 2/1", result.stdout)


class FrontmatterAndExitCodeTest(PmBoardTestCase):
    def test_files_without_frontmatter_skipped_silently_and_exits_0(self):
        """Files without frontmatter are skipped silently; exit code is 0."""
        self.write_task(
            "valid.md",
            "---\nid: TASK-1\ntitle: Valid\nstatus: Done\nlabels: []\n---\n",
        )
        self.write_task(
            "no_frontmatter.md",
            "# Meeting Notes\nSome body text without dashes.\n",
        )
        self.write_task("empty.md", "")
        self.write_task(
            "malformed.md",
            "--- title without end delimiter\njust some text\n",
        )
        # Non-.md file in DIR should also not be parsed
        (self.tasks_dir / "notes.txt").write_text("Hello", encoding="utf-8")

        result = self.run_board("--tasks", str(self.tasks_dir), "--today", "2026-09-22")

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")
        self.assertIn(
            "WIP: 0/7 · Urgent: 0/1 · Active: 0 · In review: 0 · Owner check: 0 · Ready: 0 · Done: 1",
            result.stdout,
        )
        self.assertIn("- TASK-1 · Valid", result.stdout)
        self.assertNotIn("no_frontmatter", result.stdout)
        self.assertNotIn("Meeting Notes", result.stdout)

    def test_a_task_saved_in_a_windows_code_page_is_still_listed(self):
        """One cp1254 byte (0xfd, a Turkish dotless i) must not make the board drop the whole task."""
        (self.tasks_dir / "task-1.md").write_bytes(
            b"---\nid: TASK-1\ntitle: I\xfdlk ad\xfdm\xfd\nstatus: Ready\nlabels: []\n---\n"
        )

        result = self.run_board("--tasks", str(self.tasks_dir), "--today", "2026-09-22")

        self.assertEqual(result.returncode, 0)
        self.assertIn("- TASK-1 · I", result.stdout)

    def test_empty_tasks_directory_exits_0(self):
        """Empty DIR produces empty board with empty sections showing '- (none)'."""
        result = self.run_board("--tasks", str(self.tasks_dir), "--today", "2026-09-22")

        self.assertEqual(result.returncode, 0)
        self.assertIn(
            "WIP: 0/7 · Urgent: 0/1 · Active: 0 · In review: 0 · Owner check: 0 · Ready: 0 · Done: 0",
            result.stdout,
        )
        self.assertIn("Ready: 0 (< 2) → time to plan", result.stdout)
        self.assertIn("## Active\n- (none)", result.stdout)
        self.assertIn("## Ready\n- (none)", result.stdout)
        self.assertIn("## Done\n- (none)", result.stdout)
        self.assertNotIn("## Other", result.stdout)


class CommandLineInterfaceTest(PmBoardTestCase):
    def test_today_flag_overrides_date(self):
        result = self.run_board("--tasks", str(self.tasks_dir), "--today", "2025-01-15")
        self.assertEqual(result.returncode, 0)
        self.assertTrue(result.stdout.startswith("# Status board (2025-01-15)"))

    def test_default_today_uses_local_date(self):
        result = self.run_board("--tasks", str(self.tasks_dir))
        self.assertEqual(result.returncode, 0)
        expected_header = f"# Status board ({date.today().isoformat()})"
        self.assertTrue(
            result.stdout.startswith(expected_header),
            f"Expected header starting with {expected_header!r}, got: {result.stdout[:50]!r}",
        )

    def test_default_tasks_dir_reads_pm_backlog(self):
        """Without --tasks, pm_board reads <root>/.pm/backlog/tasks."""
        pm_tools = self.temp_dir / ".pm" / "tools"
        pm_tasks = self.temp_dir / ".pm" / "backlog" / "tasks"
        pm_tools.mkdir(parents=True)
        pm_tasks.mkdir(parents=True)
        (self.temp_dir / "backlog.config.yml").write_text("", encoding="utf-8")
        copied = pm_tools / "pm_board.py"
        shutil.copy(PM_BOARD, copied)
        (pm_tasks / "task-1.md").write_text(
            "---\nid: TASK-1\ntitle: New layout task\nstatus: Active\nlabels: []\n---\n",
            encoding="utf-8",
        )

        result = subprocess.run(
            [sys.executable, str(copied), "--today", "2026-09-22"],
            cwd=self.temp_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("WIP: 1/7", result.stdout)
        self.assertIn("- TASK-1 · New layout task", result.stdout)

    def test_unclosed_frontmatter_is_skipped(self):
        """A file that opens --- but never closes it has no frontmatter."""
        self.write_task("task-1.md", "---\nid: TASK-1\ntitle: Real\nstatus: Ready\nlabels: []\n---\n")
        self.write_task("broken.md", "---\nid: TASK-9\ntitle: Broken\nstatus: Ready\n")
        result = self.run_board("--tasks", str(self.tasks_dir), "--today", "2026-09-22")
        self.assertEqual(result.returncode, 0)
        self.assertIn("TASK-1 · Real", result.stdout)
        self.assertNotIn("TASK-9", result.stdout)

    def test_exact_output_with_both_warnings(self):
        """Pin the full layout when both warnings are present."""
        for i in range(1, 9):
            self.write_task(f"task-{i}.md", f"---\nid: TASK-{i}\ntitle: A{i}\nstatus: Active\nlabels: []\n---\n")
        for i in (9, 10):
            self.write_task(f"task-{i}.md", f"---\nid: TASK-{i}\ntitle: E{i}\nstatus: Active\nlabels: [acil]\n---\n")
        result = self.run_board("--tasks", str(self.tasks_dir), "--today", "2026-09-22")
        expected = (
            "# Status board (2026-09-22)\n\n"
            "WIP: 8/7 · Urgent: 2/1 · Active: 10 · In review: 0 · Owner check: 0 · Ready: 0 · Done: 0\n\n"
            "⚠️ WIP limit exceeded: 8/7\n\n"
            "⚠️ Urgent lane full: 2/1\n\n"
            "Ready: 0 (< 2) → time to plan\n\n"
            "## Active\n"
            "- TASK-1 · A1\n- TASK-2 · A2\n- TASK-3 · A3\n- TASK-4 · A4\n"
            "- TASK-5 · A5\n- TASK-6 · A6\n- TASK-7 · A7\n- TASK-8 · A8\n"
            "- TASK-9 · E9 (urgent)\n- TASK-10 · E10 (urgent)\n\n"
            "## In review\n- (none)\n\n"
            "## Owner check\n- (none)\n\n"
            "## Ready\n- (none)\n\n"
            "## Done\n- (none)\n"
        )
        self.assertEqual(result.stdout, expected)


class StdoutGuardTest(PmBoardTestCase):
    def test_main_prints_when_stdout_cannot_be_reconfigured(self):
        """A replaced stdout without reconfigure (a test harness, a wrapped console) must not crash the board."""
        import io
        from unittest import mock

        buffer = io.StringIO()
        plain = type("Plain", (), {"encoding": "utf-8", "write": buffer.write, "flush": buffer.flush})()
        argv = ["pm_board.py", "--tasks", str(self.tasks_dir), "--today", "2026-09-22"]

        with mock.patch.object(sys, "stdout", plain), mock.patch.object(sys, "argv", argv):
            code = pm_board.main()

        self.assertEqual(code, 0)
        self.assertIn("# Status board (2026-09-22)", buffer.getvalue())


class NextCommandTest(PmBoardTestCase):
    """`--next` answers one question in plain words: what do I do now?"""

    def task_file(self, name, body="", **frontmatter):
        """Write one task file; the frontmatter keys are written in the order given."""
        lines = ["---", *(f"{key}: {value}" for key, value in frontmatter.items()), "---", "", body, ""]
        return self.write_task(name, "\n".join(lines))

    def run_next(self):
        return self.run_board("--tasks", str(self.tasks_dir), "--next")

    def test_active_task_wins_over_a_ready_one(self):
        body = (
            "## Acceptance Criteria\n"
            "- [x] #1 already checked\n"
            "- [ ] #2 still open\n\n"
            "## Implementation Notes\n"
            "Next: run the tests\n"
        )
        self.task_file("task-1.md", body, id="TASK-2", title="Fix the board", status="Active")
        self.task_file(
            "task-2.md",
            "## Acceptance Criteria\n- [ ] #1 start here\n",
            id="TASK-3",
            title="Start something",
            status="Ready",
            priority="high",
        )

        result = self.run_next()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Continue: Fix the board (TASK-2)", result.stdout)
        self.assertIn("Next: run the tests", result.stdout)
        self.assertIn("- [ ] #2 still open", result.stdout)
        self.assertNotIn("already checked", result.stdout, "only the criteria still open are listed")
        self.assertNotIn("TASK-3", result.stdout, "an Active task comes before any Ready one")

    def test_several_active_tasks_newest_first_and_the_one_to_continue(self):
        self.task_file(
            "task-1.md",
            "## Acceptance Criteria\n- [ ] #1 older\n",
            id="TASK-1",
            title="Older work",
            status="Active",
            updated_date="'2026-10-30 09:00'",
        )
        self.task_file(
            "task-2.md",
            "## Acceptance Criteria\n- [ ] #1 newer\n",
            id="TASK-2",
            title="Newer work",
            status="Active",
            updated_date="'2026-10-31 18:00'",
        )

        out = self.run_next().stdout

        self.assertIn("2 tasks are Active; continue the newest one.", out)
        self.assertIn("Continue: Newer work (TASK-2)", out)
        self.assertIn("- [ ] #1 newer", out)
        self.assertIn("- Older work (TASK-1) · updated 2026-10-30 09:00", out)
        self.assertLess(out.index("Continue: Newer work"), out.index("Older work"), "newest first")

    def test_ready_task_with_the_highest_priority_starts(self):
        self.task_file(
            "task-1.md", "", id="TASK-1", title="Medium work", status="Ready", priority="medium", ordinal="100"
        )
        self.task_file("task-2.md", "", id="TASK-2", title="High work", status="Ready", priority="high", ordinal="900")
        self.task_file("task-3.md", "", id="TASK-3", title="No priority", status="Ready", ordinal="1")

        result = self.run_next()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Start: High work (TASK-2) · priority high · ordinal 900", result.stdout)
        self.assertNotIn("Start: Medium work", result.stdout)
        self.assertNotIn("Start: No priority", result.stdout)

    def test_lowest_ordinal_wins_between_equal_priorities(self):
        self.task_file("task-1.md", "", id="TASK-1", title="Later", status="Ready", priority="high", ordinal="900")
        self.task_file("task-2.md", "", id="TASK-2", title="Sooner", status="Ready", priority="high", ordinal="200")

        out = self.run_next().stdout

        self.assertIn("Start: Sooner (TASK-2) · priority high · ordinal 200", out)

    def test_a_ready_task_waiting_on_an_unfinished_task_is_skipped(self):
        self.task_file("task-5.md", "", id="TASK-5", title="Waiting task", status="In review")
        self.write_task(
            "task-1.md",
            "---\nid: TASK-1\ntitle: Blocked start\nstatus: Ready\npriority: high\nordinal: 10\n"
            "dependencies:\n  - TASK-5\n---\n",
        )
        self.task_file("task-2.md", "", id="TASK-2", title="Free to start", status="Ready", ordinal="900")

        result = self.run_next()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Start: Free to start (TASK-2)", result.stdout)
        self.assertNotIn("Blocked start", result.stdout)

    def test_a_dependency_closed_into_the_completed_folder_counts_as_done(self):
        self.task_file(
            "task-1.md",
            "",
            id="TASK-1",
            title="Waits for the old one",
            status="Ready",
            ordinal="900",
            dependencies="[TASK-7]",
        )
        self.task_file("task-2.md", "", id="TASK-2", title="Free to start", status="Ready", ordinal="1000")
        completed = self.temp_dir / "completed"
        completed.mkdir()
        (completed / "task-7.md").write_text("---\nid: TASK-7\ntitle: Finished\nstatus: Done\n---\n", encoding="utf-8")

        out = self.run_next().stdout

        self.assertIn("Start: Waits for the old one (TASK-1)", out)

    def test_nothing_ready_prints_one_plain_line(self):
        self.task_file("task-1.md", "", id="TASK-1", title="Done already", status="Done")

        result = self.run_next()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout.strip(),
            "Nothing is Ready to start. The lead can open a task from the user's next request.",
        )

    def test_a_blocked_ready_task_is_named_after_the_plain_line(self):
        self.task_file(
            "task-1.md",
            "",
            id="TASK-1",
            title="Waits on another",
            status="Ready",
            ordinal="10",
            dependencies="[TASK-9]",
        )

        out = self.run_next().stdout

        self.assertIn("Nothing is Ready to start.", out)
        self.assertIn("- Ready but waiting for another task: TASK-1 (needs TASK-9)", out)

    def test_a_draft_is_never_picked(self):
        self.task_file("task-1.md", "", id="TASK-1", title="Private idea", status="Draft", priority="high", ordinal="1")
        self.task_file("task-2.md", "", id="TASK-2", title="Real work", status="Ready", ordinal="900")

        out = self.run_next().stdout

        self.assertIn("Start: Real work (TASK-2)", out)
        self.assertNotIn("Private idea", out)

    def test_an_active_task_without_a_live_block_reads_not_set(self):
        self.task_file("task-1.md", "", id="TASK-1", title="Active work", status="Active")

        result = self.run_next()

        self.assertIn("Next: not set", result.stdout)
        self.assertNotIn("Next: ?", result.stdout)

    def test_no_open_criteria_is_stated_in_plain_words(self):
        self.task_file(
            "task-1.md",
            "## Acceptance Criteria\n- [x] #1 all done\n",
            id="TASK-1",
            title="Nearly done",
            status="Active",
        )

        self.assertIn("Acceptance criteria: none unchecked", self.run_next().stdout)

        (self.tasks_dir / "task-1.md").unlink()
        self.task_file("task-2.md", "", id="TASK-2", title="No criteria yet", status="Ready")

        self.assertIn("Acceptance criteria: none written yet", self.run_next().stdout)

    def test_a_ready_task_held_with_a_review_by_date_is_skipped(self):
        self.task_file(
            "task-1.md",
            "## Implementation Notes\nReview by: 2099-12-31 · Sam · after the design talk\n",
            id="TASK-1",
            title="Parked on purpose",
            status="Ready",
            priority="high",
            ordinal="1",
        )
        self.task_file(
            "task-2.md", "", id="TASK-2", title="Free to start", status="Ready", priority="low", ordinal="900"
        )

        out = self.run_next().stdout

        self.assertIn("Start: Free to start (TASK-2)", out)
        self.assertNotIn("Parked on purpose", out)

    def test_a_held_task_whose_review_date_passed_is_offered_again(self):
        self.task_file(
            "task-1.md",
            "## Implementation Notes\nReview by: 2020-01-01 · Sam · after the design talk\n",
            id="TASK-1",
            title="Hold is over",
            status="Ready",
            priority="high",
            ordinal="1",
        )

        out = self.run_next().stdout

        self.assertIn("Start: Hold is over (TASK-1)", out)

    def test_only_held_tasks_left_says_so_in_plain_words(self):
        for number, review_by in ((1, "2099-12-31"), (2, "2099-11-30")):
            self.task_file(
                f"task-{number}.md",
                f"## Implementation Notes\nReview by: {review_by} · Sam · after the design talk\n",
                id=f"TASK-{number}",
                title=f"Parked {number}",
                status="Ready",
                priority="high",
            )

        result = self.run_next()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout.strip(),
            "Nothing to start; 2 task(s) wait on purpose (Review by). Ask the user what to build or fix next.",
        )

    def test_next_appears_in_the_help(self):
        result = self.run_board("--help")

        self.assertEqual(result.returncode, 0)
        self.assertIn("--next", result.stdout)


if __name__ == "__main__":
    unittest.main()
