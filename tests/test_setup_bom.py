"""Tests for tools/setup/bom.py: version parsing, the status rules, real command probes and the shipped bom.toml.

Standard library only. The probe tests run real processes (this Python, a .cmd or shell script on PATH), so they
exercise the operating system they run on; the rest are plain functions.
"""

import os
import platform
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools" / "setup"))

import bom  # noqa: E402

PY = sys.executable


class ParseVersion(unittest.TestCase):
    def test_real_outputs(self):
        cases = {
            "Python 3.11.9": "3.11.9",
            "Python 3.11": "3.11",
            "git version 2.54.0.windows.1": "2.54.0",
            "git version 2.55.0": "2.55.0",
            "v24.14.0": "24.14.0",
            "2.1.300 (Claude Code)": "2.1.300",
            "1.52.0\n": "1.52.0",
        }
        for text, version in cases.items():
            self.assertEqual(bom.parse_version(text), version, text)

    def test_suffix_is_kept_so_it_cannot_be_compared(self):
        self.assertEqual(bom.parse_version("Python 3.15.0rc1"), "3.15.0rc1")
        self.assertEqual(bom.parse_version("tool 1.2.3-beta.4"), "1.2.3-beta.4")

    def test_no_version(self):
        for text in ("", None, "command not found", "build 7"):
            self.assertIsNone(bom.parse_version(text), text)


class Compare(unittest.TestCase):
    def test_numbers_not_text(self):
        self.assertEqual(bom.compare("2.10.0", "2.9.0"), 1)
        self.assertEqual(bom.compare("1.9", "1.10"), -1)

    def test_missing_parts_count_as_zero(self):
        self.assertEqual(bom.compare("3.11", "3.11.0"), 0)
        self.assertEqual(bom.compare("3.11", "3.11.9"), -1)


class Status(unittest.TestCase):
    def test_rules(self):
        cases = [
            ((None, False, None), bom.MISSING),
            (("/bin/x", False, None), bom.FAILED),
            (("/bin/x", True, None), bom.UNREADABLE),
            (("/bin/x", True, "3.15.0rc1"), bom.CANNOT_COMPARE),
            (("/bin/x", True, "3.10.14"), bom.BELOW),
            (("/bin/x", True, "3.11"), bom.OK),
            (("/bin/x", True, "3.11.9"), bom.OK),
            (("/bin/x", True, "3.14.8"), bom.UNTESTED),
        ]
        for probed, expected in cases:
            self.assertEqual(bom.status(*probed, "3.11", "3.11.9"), expected, probed)


class Probe(unittest.TestCase):
    def test_missing_command(self):
        self.assertEqual(bom.probe(["pm-no-such-command-xyz", "--version"]), (None, False, None))

    def test_python_is_the_running_interpreter(self):
        self.assertEqual(bom.probe(["python", "--version"]), (PY, True, platform.python_version()))

    def test_version_on_non_zero_exit_is_not_taken(self):
        result = bom.probe([PY, "-c", "print('1.2.3'); raise SystemExit(3)"])
        self.assertEqual(result, (PY, False, None))

    def test_timeout(self):
        result = bom.probe([PY, "-c", "import time; time.sleep(10)"], timeout=0.5)
        self.assertEqual(result, (PY, False, None))

    def test_script_found_on_path(self):
        """A tool installed as a script on PATH: npm's .cmd shims on Windows, a shell script on Linux."""
        with tempfile.TemporaryDirectory() as folder:
            if os.name == "nt":
                script = Path(folder) / "pm-fake-tool.cmd"
                script.write_text("@echo pm-fake-tool 1.2.3\r\n")
            else:
                script = Path(folder) / "pm-fake-tool"
                script.write_text("#!/bin/sh\necho pm-fake-tool 1.2.3\n")
                script.chmod(0o755)
            with patch.dict(os.environ, {"PATH": folder + os.pathsep + os.environ["PATH"]}):
                path, ran_ok, version = bom.probe(["pm-fake-tool", "--version"])
        self.assertEqual(Path(path).name.lower(), script.name.lower())
        self.assertEqual((ran_ok, version), (True, "1.2.3"))


class CheckAll(unittest.TestCase):
    def test_rows_and_summary(self):
        items = [
            {"name": "A", "kind": "command", "check": ["a"], "min": "1.0", "tested": "1.2"},
            {"name": "B", "kind": "command", "check": ["b"], "min": "1.0", "tested": "1.2"},
            {"name": "C", "kind": "command", "check": ["c"], "min": "1.0", "tested": "1.2"},
            {"name": "D", "kind": "project-file", "path": ".pm"},
        ]
        found = {"a": ("/bin/a", True, "1.1"), "b": (None, False, None), "c": ("/bin/c", False, None)}
        rows = bom.check_all(items, lambda check: found[check[0]])
        self.assertEqual(
            rows,
            [
                ("A", "1.1", "1.0", "1.2", bom.OK, "/bin/a"),
                ("B", "-", "1.0", "1.2", bom.MISSING, "-"),
                ("C", "-", "1.0", "1.2", bom.FAILED, "/bin/c"),
                ("D", "-", "-", "-", bom.NOT_CHECKED, ".pm"),
            ],
        )
        self.assertEqual(bom.summary(rows), "4 items: 1 ok, 1 missing, 1 check failed, 1 not checked")


class NextStep(unittest.TestCase):
    def row(self, name, result):
        return (name, "-", "-", "-", result, "-")

    def test_every_status_has_a_level(self):
        statuses = {bom.MISSING, bom.FAILED, bom.UNREADABLE, bom.CANNOT_COMPARE, bom.NOT_CHECKED, bom.BELOW, bom.OK}
        self.assertEqual(set(bom.LEVEL), statuses | {bom.UNTESTED})

    def test_worst_level_wins(self):
        ok, new, gone, skip = (
            self.row("A", bom.OK),
            self.row("B", bom.UNTESTED),
            self.row("C", bom.MISSING),
            self.row("D", bom.NOT_CHECKED),
        )
        self.assertEqual(bom.worst([ok, new, gone, skip]), "bad")
        self.assertEqual(bom.worst([ok, new, skip]), "warn")
        self.assertEqual(bom.worst([ok, skip]), "good")
        self.assertEqual(bom.worst([skip]), "skip")
        self.assertEqual(bom.worst([]), "skip")

    def test_sentences(self):
        rows = [self.row("Git", bom.MISSING), self.row("Node.js", bom.BELOW), self.row("Claude Code", bom.UNTESTED)]
        self.assertEqual(
            bom.next_step(rows),
            "Next: install or update Git (missing), Node.js (below minimum), then check again.",
        )
        rows = [self.row("Git", bom.OK), self.row("Claude Code", bom.UNTESTED), self.row(".pm", bom.NOT_CHECKED)]
        self.assertEqual(
            bom.next_step(rows),
            "All programs are there and should work. Worth a look: Claude Code (not tested yet)."
            ' Items marked "not checked" are checked in a later step.',
        )
        self.assertEqual(bom.next_step([self.row("Git", bom.OK)]), "All programs are ready.")


GOOD = """
[[item]]
id = "git"
name = "Git"
kind = "command"
layer = "core"
check = ["git", "--version"]
min = "2.54.0"
tested = "2.54.0"
"""


class Load(unittest.TestCase):
    def load_text(self, text):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bom.toml"
            path.write_text(textwrap.dedent(text), encoding="utf-8")
            return bom.load(path)

    def assert_rejected(self, text, message):
        with self.assertRaises(ValueError) as caught:
            self.load_text(text)
        self.assertIn(message, str(caught.exception))

    def test_good(self):
        self.assertEqual(self.load_text(GOOD)[0]["id"], "git")

    def test_duplicate_id(self):
        self.assert_rejected(GOOD + GOOD, "duplicate id")

    def test_unknown_kind(self):
        self.assert_rejected(GOOD.replace('"command"', '"plugin"'), "kind must be one of")

    def test_min_above_tested(self):
        self.assert_rejected(GOOD.replace('min = "2.54.0"', 'min = "2.55.0"'), "min is above tested")

    def test_fake_version_string(self):
        self.assert_rejected(GOOD.replace('min = "2.54.0"', 'min = "not set"'), "min must look like")

    def test_npx_is_refused(self):
        self.assert_rejected(GOOD.replace('["git", "--version"]', '["npx", "likec4", "--version"]'), "npx")

    def test_command_needs_versions(self):
        self.assert_rejected(GOOD.replace('tested = "2.54.0"', ""), "needs min and tested")


class ShippedBom(unittest.TestCase):
    """The hand-edited bom.toml loads, and every shipped skill follows the pm- prefix."""

    def test_loads_and_names(self):
        items = bom.load()
        self.assertTrue(any(item["kind"] == "command" for item in items))
        for item in items:
            with self.subTest(item=item["id"]):
                if item["kind"] == "command":
                    self.assertTrue(item["install"]["windows"])
                    self.assertTrue(item["install"]["linux"])
                if "/skills/" in item.get("path", ""):
                    self.assertTrue(item["id"].startswith("pm-"))
                    self.assertTrue(Path(item["path"]).name.startswith("pm-"))


if __name__ == "__main__":
    unittest.main()
