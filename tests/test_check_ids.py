"""Tests for tools/check_ids.py: which ID-shaped strings block, and that the product passes its own check.

The cases build their IDs from parts, so this file never holds one the check would report.
"""

import io
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import check_ids  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DECISION = "D-" + "86"
TASK = "REQ-" + "94.4"


class Findings(unittest.TestCase):
    def test_a_cited_id_blocks_in_code_and_docs(self):
        cases = {
            "tools/x.py": f"x = 1  # see ({DECISION})\n",
            "template/README.md": f"intro\n\nThe board ({TASK}) shows it.\n",
            ".githooks/commit-msg": f"# the trailer ({DECISION})\n",
            "template/.pm/tools/pm_init.py": f'HEADER = "# package ({DECISION})"\n',
        }
        for name, text in cases.items():
            self.assertTrue(check_ids.findings(name, text), name)

    def test_the_line_of_the_finding_is_reported(self):
        self.assertEqual(check_ids.findings("a.md", f"one\ntwo\nthree {TASK}\n"), [(3, TASK)])

    def test_template_examples_pass_but_longer_ids_do_not(self):
        self.assertEqual(check_ids.findings("a.md", "`.pm/decisions/D-01.md`, `depends_on: [D-01]`, REQ-1\n"), [])
        self.assertEqual([found for _, found in check_ids.findings("a.md", "REQ-12 and D-011\n")], ["REQ-12", "D-011"])

    def test_test_data_passes_in_a_test_file(self):
        source = (
            "def test_x(self):\n"
            f'    self.write("t.md", "id: {DECISION}\\n")\n'
            f'    self.assertIn(f"{{name}} needs {TASK}", out)\n'
        )
        self.assertEqual(check_ids.findings("tests/test_x.py", source), [])

    def test_comments_and_docstrings_of_a_test_file_block(self):
        source = (
            f'"""Tests for the board ({TASK})."""\n'
            "\n"
            "class T:\n"
            "    def test_x(self):\n"
            f'        """Shown at the start ({DECISION})."""\n'
            f"        # {DECISION}: an open task records it\n"
            "        pass\n"
        )
        found = check_ids.findings("template/.pm/swarm/test_pm_run.py", source)
        self.assertEqual(found, [(1, TASK), (5, DECISION), (6, DECISION)])

    def test_every_docstring_form_blocks(self):
        cases = {
            "concatenated": f'"""Reason: """ "{DECISION}"\n',
            "same line": f'def test_x(): """{DECISION}"""; pass\n',
            "parenthesized": f'(\n    "{DECISION}"\n)\n',
        }
        for label, source in cases.items():
            found = [hit for _, hit in check_ids.findings("tests/test_x.py", source)]
            self.assertEqual(found, [DECISION], label)

    def test_a_lone_f_string_is_data_not_a_docstring(self):
        source = f'def test_x(self):\n    f"{{self}} {DECISION}"\n'
        self.assertEqual(check_ids.findings("tests/test_x.py", source), [])


class Files(unittest.TestCase):
    """main() over a fake checkout: binary files are skipped, text that is not UTF-8 is reported."""

    def run_main(self, files):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, data in files.items():
                (root / name).write_bytes(data)
            listing = subprocess.CompletedProcess([], 0, stdout="\0".join(files) + "\0")
            out = io.StringIO()
            with patch.object(check_ids, "ROOT", root), patch.object(check_ids.subprocess, "run", return_value=listing):
                with redirect_stdout(out):
                    code = check_ids.main()
            return code, out.getvalue()

    def test_binary_is_skipped_but_latin_1_text_is_reported(self):
        code, out = self.run_main({"logo.png": b"\x89PNG\0" + DECISION.encode(), "notes.md": b"caf\xe9\n"})
        self.assertEqual(code, 1)
        self.assertIn("notes.md: not UTF-8", out)
        self.assertNotIn("logo.png", out)

    def test_a_utf_8_file_with_a_bom_is_checked(self):
        code, out = self.run_main({"notes.md": b"\xef\xbb\xbf" + f"see {DECISION}\n".encode()})
        self.assertEqual(code, 1)
        self.assertIn(f"notes.md:1: {DECISION}", out)


class Product(unittest.TestCase):
    def test_the_product_carries_no_private_id(self):
        result = subprocess.run([sys.executable, str(ROOT / "tools" / "check_ids.py")], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout)


if __name__ == "__main__":
    unittest.main()
