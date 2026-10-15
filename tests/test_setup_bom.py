"""Tests for tools/setup/bom.py: version parsing, the status rules, real command probes and the shipped bom.toml.

Standard library only. The probe tests run real processes (this Python, a .cmd or shell script on PATH), so they
exercise the operating system they run on; the rest are plain functions.
"""

import io
import json
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
            "All programs are installed. Worth a look: Claude Code (not tested yet).",
        )
        self.assertEqual(bom.next_step([self.row("Git", bom.OK)]), "All programs are ready.")
        self.assertEqual(
            bom.later_note(rows), 'The item marked "not checked" belongs to your project and is set up later.'
        )
        self.assertEqual(bom.later_note([self.row("Git", bom.OK)]), "")


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

    def test_install_lines_need_a_known_os(self):
        self.assertEqual(
            self.load_text(GOOD + 'install.linux = "sudo pacman -S git"\n')[0]["install"]["linux"], "sudo pacman -S git"
        )
        self.assert_rejected(GOOD + 'install.beos = "get git"\n', "install takes install.<os>")
        self.assert_rejected(GOOD + 'upgrade.windows = ""\n', "upgrade takes upgrade.<os>")
        self.assert_rejected(GOOD + 'install = "winget install git"\n', "install takes install.<os>")


def item(item_id, layer="core", **extra):
    return {"id": item_id, "name": item_id.title(), "kind": "command", "layer": layer, "check": [item_id], **extra}


def row(name, result, installed="-"):
    return (name, installed, "1.0", "1.2", result, "-")


class Plan(unittest.TestCase):
    def test_only_missing_and_below_minimum_become_steps(self):
        items = [
            item("git", install={"windows": "winget install git", "linux": "pacman -S git"}),
            item("node", install={"windows": "winget install node"}, upgrade={"windows": "winget upgrade node"}),
            item("ok", install={"windows": "winget install ok"}),
            item("new", install={"windows": "winget install new"}),
        ]
        rows = [row("Git", bom.MISSING), row("Node", bom.BELOW), row("Ok", bom.OK), row("New", bom.UNTESTED)]
        steps, notes = bom.plan(items, rows, system="windows")
        self.assertEqual(
            [(s["id"], s["why"], s["command"], s["needs"]) for s in steps],
            [
                ("git", bom.MISSING, "winget install git", "winget"),
                ("node", bom.BELOW, "winget upgrade node", "winget"),
            ],
        )
        self.assertEqual(steps[0]["shell"], ["powershell", "-NoProfile", "-Command", "winget install git"])
        self.assertEqual(steps[0]["check"], ["git"])
        self.assertEqual(notes, [])

    def test_missing_item_installs_even_when_an_upgrade_line_exists(self):
        items = [item("node", install={"windows": "winget install node"}, upgrade={"windows": "winget upgrade node"})]
        steps, _ = bom.plan(items, [row("Node", bom.MISSING)], system="windows")
        self.assertEqual(steps[0]["command"], "winget install node")

    def test_os_line_then_all(self):
        items = [
            item("backlog", install={"all": "npm i -g backlog.md"}),
            item("git", install={"linux": "pacman -S git"}),
        ]
        steps, _ = bom.plan(items, [row("Backlog", bom.MISSING), row("Git", bom.BELOW)], system="linux")
        self.assertEqual([s["command"] for s in steps], ["npm i -g backlog.md", "pacman -S git"])

    def test_no_command_and_failed_check_become_notes(self):
        items = [item("git", install={"linux": "pacman -S git"}, note="Get it from git-scm.com."), item("node")]
        steps, notes = bom.plan(items, [row("Git", bom.MISSING), row("Node", bom.FAILED)], system="windows")
        self.assertEqual(steps, [])
        self.assertEqual(len(notes), 2)
        self.assertIn("no install command for windows; Get it from git-scm.com.", notes[0])
        self.assertIn("version check failed; run node", notes[1])

    def test_unticked_layer_is_left_out(self):
        items = [item("likec4", layer="map", install={"all": "npm i -g likec4"})]
        self.assertEqual(bom.plan(items, [row("Likec4", bom.MISSING)], layers=("core",), system="linux"), ([], []))


class Running(unittest.TestCase):
    def test_shell_per_os(self):
        self.assertEqual(
            bom.shell_args("irm x | iex", "windows"), ["powershell", "-NoProfile", "-Command", "irm x | iex"]
        )
        self.assertEqual(bom.shell_args("curl x | bash", "linux"), ["bash", "-c", "curl x | bash"])

    def test_outcome_from_exit_code_and_recheck(self):
        self.assertEqual(bom.outcome(0, row("Git", bom.OK, "2.54.0"))[0], "done")
        self.assertEqual(bom.outcome(0, row("Git", bom.UNTESTED, "2.60.0"))[0], "done")
        self.assertEqual(bom.outcome(0, row("Git", bom.MISSING))[0], "not-found")
        self.assertEqual(bom.outcome(0, row("Git", bom.BELOW, "0.9"))[0], "too-old")
        self.assertEqual(bom.outcome(0, row("Git", bom.UNREADABLE))[0], "unverified")
        self.assertEqual(bom.outcome(0, row("Git", bom.FAILED))[0], "unverified")
        state, message = bom.outcome(5, row("Git", bom.OK, "2.54.0"))
        self.assertEqual(state, "failed")
        self.assertIn("exit code 5", message)

    def test_needs_names_the_program_that_runs_the_line(self):
        self.assertEqual(bom.needs("winget install --id Git.Git", "windows"), "winget")
        self.assertEqual(bom.needs("sudo pacman -S --needed git", "linux"), "pacman")
        self.assertEqual(bom.needs("npm i -g backlog.md@1.52.0", "linux"), "npm")
        self.assertEqual(bom.needs("irm https://claude.ai/install.ps1 | iex", "windows"), "powershell")
        self.assertEqual(bom.needs("curl -fsSL https://claude.ai/install.sh | bash", "linux"), "curl")

    def test_path_refresh_keeps_this_process_first(self):
        before = os.environ["PATH"]
        try:
            os.environ["PATH"] = os.pathsep.join(["C:\\venv\\Scripts", before])
            bom.refresh_path()
            self.assertTrue(os.environ["PATH"].startswith("C:\\venv\\Scripts" + os.pathsep))
        finally:
            os.environ["PATH"] = before


class Main(unittest.TestCase):
    """The plain-text and JSON output an agent reads, and the exit codes it can trust."""

    def run_main(self, args, found):
        with patch("sys.stdout", new_callable=io.StringIO) as out:
            code = bom.main(args, lambda check: found.get(check[0], ("/bin/x", True, "999.0")))
        return code, out.getvalue()

    def test_steps_left_exit_1_and_list_commands(self):
        code, out = self.run_main([], {"git": (None, False, None)})
        self.assertEqual(code, 1)
        self.assertIn("To do on ", out)
        self.assertIn("1. Git (missing): ", out)

    def test_failed_check_is_a_note_and_exit_1(self):
        code, out = self.run_main(["--layers", "core"], {"git": ("/bin/git", False, None)})
        self.assertEqual(code, 1)
        self.assertIn("nothing can run automatically", out)
        self.assertIn("Note: Git: installed but its version check failed", out)

    def test_nothing_left_exit_0(self):
        code, out = self.run_main(["--layers", "core"], {})
        self.assertEqual(code, 0)
        self.assertIn("(core): nothing", out)

    def test_json(self):
        code, out = self.run_main(["--json"], {"git": (None, False, None)})
        data = json.loads(out)
        self.assertEqual(code, 1)
        self.assertEqual(data["steps"][0]["id"], "git")
        self.assertEqual(next(i for i in data["items"] if i["id"] == "git")["status"], bom.MISSING)

    def test_bad_layer_exit_2(self):
        with patch("sys.stderr"):
            self.assertEqual(bom.main(["--layers", "swarm"]), 2)


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
