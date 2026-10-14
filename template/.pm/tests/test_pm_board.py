"""Tests for tools/pm_board.py.

pm_board reads Backlog task files and prints a Turkish status board in Markdown.
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
        """AC #1: Sample output above is reproduced exactly for the same three tasks."""
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
            "# Durum panosu (2026-09-22)\n"
            "\n"
            "WIP: 1/7 · Acil: 0/1 · Devam ediyor: 1 · İncelemede: 0 · Sahip kontrolü: 0 · Sırada: 1 · Biten: 1\n"
            "\n"
            "Hazır: 1 (< 2) → planlama zamanı\n"
            "\n"
            "## Devam ediyor\n"
            "- TASK-2 · pm board\n"
            "\n"
            "## İncelemede\n"
            "- (yok)\n"
            "\n"
            "## Sahip kontrolü\n"
            "- (yok)\n"
            "\n"
            "## Sırada\n"
            "- TASK-3 · Next thing\n"
            "\n"
            "## Bitti\n"
            "- TASK-1 · Test suite\n"
        )
        self.assertEqual(result.stdout.strip(), expected.strip())


class StatusMappingAndSectionsTest(PmBoardTestCase):
    def test_status_mapping_to_sections(self):
        """AC #2: 'Active' -> Devam ediyor, 'To Do' -> Sırada, 'Done' -> Bitti."""
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
        self.assertIn("## Devam ediyor\n- TASK-1 · Alpha", result.stdout)
        self.assertIn("## Sırada\n- TASK-2 · Beta", result.stdout)
        self.assertIn("## Bitti\n- TASK-3 · Gamma", result.stdout)
        self.assertNotIn("## Diğer", result.stdout)

    def test_empty_sections_show_yok(self):
        """AC #2: Sections are always present; empty section shows '- (yok)'."""
        self.write_task(
            "task-1.md",
            "---\nid: TASK-1\ntitle: Only Done\nstatus: Done\nlabels: []\n---\n",
        )

        result = self.run_board("--tasks", str(self.tasks_dir), "--today", "2026-09-22")

        self.assertEqual(result.returncode, 0)
        self.assertIn("## Devam ediyor\n- (yok)", result.stdout)
        self.assertIn("## Sırada\n- (yok)", result.stdout)
        self.assertIn("## Bitti\n- TASK-1 · Only Done", result.stdout)
        self.assertNotIn("## Diğer", result.stdout)

    def test_diger_section_appears_only_when_other_status_exists(self):
        """AC #2: Any other status maps to Diğer, which only appears when such tasks exist."""
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
        self.assertIn("## Diğer", result.stdout)
        self.assertIn("- TASK-1 · Blocked task", result.stdout)
        self.assertIn("- TASK-2 · Review task", result.stdout)
        # Counts line only tracks the five known lanes
        self.assertIn(
            "WIP: 0/7 · Acil: 0/1 · Devam ediyor: 0 · İncelemede: 0 · Sahip kontrolü: 0 · Sırada: 0 · Biten: 0",
            result.stdout,
        )

    def test_expedite_lane_and_acil_label(self):
        """AC #2: Acil label routes In Progress task to Acil count and appends ' (acil)'."""
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
            "WIP: 1/7 · Acil: 1/1 · Devam ediyor: 2 · İncelemede: 0 · Sahip kontrolü: 0 · Sırada: 1 · Biten: 0",
            result.stdout,
        )
        self.assertIn("- TASK-1 · Normal progress", result.stdout)
        self.assertIn("- TASK-2 · Urgent progress (acil)", result.stdout)
        self.assertIn("- TASK-3 · Urgent todo (acil)", result.stdout)


class WarningsTest(PmBoardTestCase):
    def test_warnings_not_shown_at_or_below_limit(self):
        """AC #3: No warnings when WIP <= 7 and Acil <= 1."""
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
            "WIP: 3/7 · Acil: 1/1 · Devam ediyor: 4 · İncelemede: 0 · Sahip kontrolü: 0 · Sırada: 0 · Biten: 0",
            result.stdout,
        )
        self.assertNotIn("WIP sınırı aşıldı", result.stdout)
        self.assertNotIn("Acil şerit dolu", result.stdout)

    def test_wip_warning_when_aktif_over_limit(self):
        """AC #3: '⚠️ WIP sınırı aşıldı: N/7' when WIP > 7."""
        for i in range(1, 9):
            self.write_task(
                f"task-{i}.md",
                f"---\nid: TASK-{i}\ntitle: Active {i}\nstatus: Active\nlabels: []\n---\n",
            )

        result = self.run_board("--tasks", str(self.tasks_dir), "--today", "2026-09-22")

        self.assertEqual(result.returncode, 0)
        self.assertIn(
            "WIP: 8/7 · Acil: 0/1 · Devam ediyor: 8 · İncelemede: 0 · Sahip kontrolü: 0 · Sırada: 0 · Biten: 0",
            result.stdout,
        )
        self.assertIn("⚠️ WIP sınırı aşıldı: 8/7", result.stdout)
        self.assertNotIn("Acil şerit dolu", result.stdout)

    def test_acil_warning_when_acil_over_limit(self):
        """AC #3: '⚠️ Acil şerit dolu: N/1' when Acil > 1."""
        for i in range(1, 3):
            self.write_task(
                f"task-{i}.md",
                f"---\nid: TASK-{i}\ntitle: Acil {i}\nstatus: Active\nlabels: [acil]\n---\n",
            )

        result = self.run_board("--tasks", str(self.tasks_dir), "--today", "2026-09-22")

        self.assertEqual(result.returncode, 0)
        self.assertIn(
            "WIP: 0/7 · Acil: 2/1 · Devam ediyor: 2 · İncelemede: 0 · Sahip kontrolü: 0 · Sırada: 0 · Biten: 0",
            result.stdout,
        )
        self.assertIn("⚠️ Acil şerit dolu: 2/1", result.stdout)
        self.assertNotIn("WIP sınırı aşıldı", result.stdout)

    def test_both_warnings_appear_in_stated_order(self):
        """AC #3: Warnings appear right after counts and before Hazır, in order: WIP then Acil."""
        for i in range(1, 9):
            self.write_task(
                f"task-act-{i}.md",
                f"---\nid: TASK-{i}\ntitle: Active {i}\nstatus: Active\nlabels: []\n---\n",
            )
        for i in range(9, 11):
            self.write_task(
                f"task-acl-{i}.md",
                f"---\nid: TASK-{i}\ntitle: Acil {i}\nstatus: Active\nlabels: [acil]\n---\n",
            )

        result = self.run_board("--tasks", str(self.tasks_dir), "--today", "2026-09-22")

        self.assertEqual(result.returncode, 0)
        self.assertIn("⚠️ WIP sınırı aşıldı: 8/7", result.stdout)
        self.assertIn("⚠️ Acil şerit dolu: 2/1", result.stdout)

        pos_counts = result.stdout.index("WIP: 8/7 · Acil: 2/1")
        pos_wip = result.stdout.index("⚠️ WIP sınırı aşıldı: 8/7")
        pos_acil = result.stdout.index("⚠️ Acil şerit dolu: 2/1")
        pos_hazir = result.stdout.index("Hazır: 0 (< 2) → planlama zamanı")

        self.assertTrue(pos_counts < pos_wip < pos_acil < pos_hazir)

    def test_three_wip_lanes_three_total_no_warning(self):
        """CHANGES #4: one non-urgent task in Active, In review and Owner check is WIP 3/3, no warning."""
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
            "WIP: 3/7 · Acil: 0/1 · Devam ediyor: 1 · İncelemede: 1 · Sahip kontrolü: 1 · Sırada: 0 · Biten: 0",
            result.stdout,
        )
        self.assertNotIn("WIP sınırı aşıldı", result.stdout)
        self.assertNotIn("Acil şerit dolu", result.stdout)

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
            "WIP: 8/7 · Acil: 0/1 · Devam ediyor: 6 · İncelemede: 1 · Sahip kontrolü: 1 · Sırada: 0 · Biten: 0",
            result.stdout,
        )
        self.assertIn("⚠️ WIP sınırı aşıldı: 8/7", result.stdout)
        self.assertNotIn("Acil şerit dolu", result.stdout)

    def test_sub_tasks_do_not_count_toward_wip(self):
        """Only top-level work counts; any number of sub-tasks under an Epic may be open."""
        self.write_task("task-1.md", "---\nid: TASK-1\ntitle: Epic\nstatus: Active\nlabels: []\n---\n")
        for i in range(1, 10):
            self.write_task(
                f"task-1.{i}.md",
                f"---\nid: TASK-1.{i}\ntitle: Leaf {i}\nstatus: Active\nparent_task_id: TASK-1\nlabels: []\n---\n",
            )

        result = self.run_board("--tasks", str(self.tasks_dir), "--today", "2026-09-22")

        self.assertIn("WIP: 1/7 · Acil: 0/1 · Devam ediyor: 10 ·", result.stdout)
        self.assertNotIn("WIP sınırı aşıldı", result.stdout)


class HazirLineTest(PmBoardTestCase):
    def test_hazir_line_shown_when_sirada_is_0(self):
        """AC #4: 'Hazır: N (< 2) → planlama zamanı' appears when Sırada == 0."""
        result = self.run_board("--tasks", str(self.tasks_dir), "--today", "2026-09-22")
        self.assertEqual(result.returncode, 0)
        self.assertIn("Hazır: 0 (< 2) → planlama zamanı", result.stdout)

    def test_hazir_line_shown_when_sirada_is_1(self):
        """AC #4: 'Hazır: N (< 2) → planlama zamanı' appears when Sırada == 1."""
        self.write_task(
            "task-1.md",
            "---\nid: TASK-1\ntitle: One todo\nstatus: Ready\nlabels: []\n---\n",
        )
        result = self.run_board("--tasks", str(self.tasks_dir), "--today", "2026-09-22")
        self.assertEqual(result.returncode, 0)
        self.assertIn("Hazır: 1 (< 2) → planlama zamanı", result.stdout)

    def test_hazir_line_not_shown_when_sirada_is_2(self):
        """AC #4: Hazır line does not appear when Sırada == 2."""
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
        self.assertNotIn("planlama zamanı", result.stdout)
        self.assertNotIn("Hazır:", result.stdout)

    def test_hazir_line_not_shown_when_sirada_greater_than_2(self):
        """AC #4: Hazır line does not appear when Sırada > 2."""
        for i in range(1, 4):
            self.write_task(
                f"task-{i}.md",
                f"---\nid: TASK-{i}\ntitle: Todo {i}\nstatus: Ready\nlabels: []\n---\n",
            )
        result = self.run_board("--tasks", str(self.tasks_dir), "--today", "2026-09-22")
        self.assertEqual(result.returncode, 0)
        self.assertNotIn("planlama zamanı", result.stdout)


class SortingTest(PmBoardTestCase):
    def test_sorting_by_id_number_not_text(self):
        """AC #5: Tasks inside each section are sorted by the number in their id (TASK-2 before TASK-10)."""
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
        """AC #6: Inline list format labels: [a, b] is read, unknown fields are ignored."""
        self.write_task(
            "task-1.md",
            (
                "---\n"
                "id: TASK-1\n"
                "title: Inline Acil\n"
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
            "WIP: 1/7 · Acil: 1/1 · Devam ediyor: 2 · İncelemede: 0 · Sahip kontrolü: 0 · Sırada: 0 · Biten: 0",
            result.stdout,
        )
        self.assertIn("- TASK-1 · Inline Acil (acil)", result.stdout)
        self.assertIn("- TASK-2 · Inline Empty", result.stdout)

    def test_block_labels_format(self):
        """AC #6: Block list format labels: followed by lines '  - item' is read."""
        self.write_task(
            "task-1.md",
            ("---\nid: TASK-1\ntitle: Block Acil\nstatus: Active\nlabels:\n  - pilot\n  - acil\n---\n"),
        )
        self.write_task(
            "task-2.md",
            ("---\nid: TASK-2\ntitle: Block Non-Acil\nstatus: Active\nlabels:\n  - pilot\n---\n"),
        )

        result = self.run_board("--tasks", str(self.tasks_dir), "--today", "2026-09-22")

        self.assertEqual(result.returncode, 0)
        self.assertIn(
            "WIP: 1/7 · Acil: 1/1 · Devam ediyor: 2 · İncelemede: 0 · Sahip kontrolü: 0 · Sırada: 0 · Biten: 0",
            result.stdout,
        )
        self.assertIn("- TASK-1 · Block Acil (acil)", result.stdout)
        self.assertIn("- TASK-2 · Block Non-Acil", result.stdout)

    def test_urgent_label_counts_as_acil(self):
        """CHANGES #3: the 'urgent' label counts as acil; the title suffix stays ' (acil)'."""
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
            "WIP: 0/7 · Acil: 2/1 · Devam ediyor: 2 · İncelemede: 0 · Sahip kontrolü: 0 · Sırada: 0 · Biten: 0",
            result.stdout,
        )
        self.assertIn("- TASK-1 · Urgent label (acil)", result.stdout)
        self.assertIn("- TASK-2 · Acil label (acil)", result.stdout)
        self.assertIn("⚠️ Acil şerit dolu: 2/1", result.stdout)


class FrontmatterAndExitCodeTest(PmBoardTestCase):
    def test_files_without_frontmatter_skipped_silently_and_exits_0(self):
        """AC #7: Files without frontmatter are skipped silently; exit code is 0."""
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
            "WIP: 0/7 · Acil: 0/1 · Devam ediyor: 0 · İncelemede: 0 · Sahip kontrolü: 0 · Sırada: 0 · Biten: 1",
            result.stdout,
        )
        self.assertIn("- TASK-1 · Valid", result.stdout)
        self.assertNotIn("no_frontmatter", result.stdout)
        self.assertNotIn("Meeting Notes", result.stdout)

    def test_empty_tasks_directory_exits_0(self):
        """Empty DIR produces empty board with empty sections showing '- (yok)'."""
        result = self.run_board("--tasks", str(self.tasks_dir), "--today", "2026-09-22")

        self.assertEqual(result.returncode, 0)
        self.assertIn(
            "WIP: 0/7 · Acil: 0/1 · Devam ediyor: 0 · İncelemede: 0 · Sahip kontrolü: 0 · Sırada: 0 · Biten: 0",
            result.stdout,
        )
        self.assertIn("Hazır: 0 (< 2) → planlama zamanı", result.stdout)
        self.assertIn("## Devam ediyor\n- (yok)", result.stdout)
        self.assertIn("## Sırada\n- (yok)", result.stdout)
        self.assertIn("## Bitti\n- (yok)", result.stdout)
        self.assertNotIn("## Diğer", result.stdout)


class CommandLineInterfaceTest(PmBoardTestCase):
    def test_today_flag_overrides_date(self):
        result = self.run_board("--tasks", str(self.tasks_dir), "--today", "2025-01-15")
        self.assertEqual(result.returncode, 0)
        self.assertTrue(result.stdout.startswith("# Durum panosu (2025-01-15)"))

    def test_default_today_uses_local_date(self):
        result = self.run_board("--tasks", str(self.tasks_dir))
        self.assertEqual(result.returncode, 0)
        expected_header = f"# Durum panosu ({date.today().isoformat()})"
        self.assertTrue(
            result.stdout.startswith(expected_header),
            f"Expected header starting with {expected_header!r}, got: {result.stdout[:50]!r}",
        )

    def test_default_tasks_dir_reads_pm_backlog(self):
        """CHANGES #2: without --tasks, pm_board reads <root>/.pm/backlog/tasks."""
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
        """Review finding: a file that opens --- but never closes it has no frontmatter."""
        self.write_task("task-1.md", "---\nid: TASK-1\ntitle: Real\nstatus: Ready\nlabels: []\n---\n")
        self.write_task("broken.md", "---\nid: TASK-9\ntitle: Broken\nstatus: Ready\n")
        result = self.run_board("--tasks", str(self.tasks_dir), "--today", "2026-09-22")
        self.assertEqual(result.returncode, 0)
        self.assertIn("TASK-1 · Real", result.stdout)
        self.assertNotIn("TASK-9", result.stdout)

    def test_exact_output_with_both_warnings(self):
        """Review finding: pin the full layout when both warnings are present."""
        for i in range(1, 9):
            self.write_task(f"task-{i}.md", f"---\nid: TASK-{i}\ntitle: A{i}\nstatus: Active\nlabels: []\n---\n")
        for i in (9, 10):
            self.write_task(f"task-{i}.md", f"---\nid: TASK-{i}\ntitle: E{i}\nstatus: Active\nlabels: [acil]\n---\n")
        result = self.run_board("--tasks", str(self.tasks_dir), "--today", "2026-09-22")
        expected = (
            "# Durum panosu (2026-09-22)\n\n"
            "WIP: 8/7 · Acil: 2/1 · Devam ediyor: 10 · İncelemede: 0 · Sahip kontrolü: 0 · Sırada: 0 · Biten: 0\n\n"
            "⚠️ WIP sınırı aşıldı: 8/7\n\n"
            "⚠️ Acil şerit dolu: 2/1\n\n"
            "Hazır: 0 (< 2) → planlama zamanı\n\n"
            "## Devam ediyor\n"
            "- TASK-1 · A1\n- TASK-2 · A2\n- TASK-3 · A3\n- TASK-4 · A4\n"
            "- TASK-5 · A5\n- TASK-6 · A6\n- TASK-7 · A7\n- TASK-8 · A8\n"
            "- TASK-9 · E9 (acil)\n- TASK-10 · E10 (acil)\n\n"
            "## İncelemede\n- (yok)\n\n"
            "## Sahip kontrolü\n- (yok)\n\n"
            "## Sırada\n- (yok)\n\n"
            "## Bitti\n- (yok)\n"
        )
        self.assertEqual(result.stdout, expected)


if __name__ == "__main__":
    unittest.main()
