"""Tests for ``python .pm/tools/pm_open.py``.

A throwaway project holds only a ``.pm/`` folder and, in the tests that need it, a ``.claude/launch.json``. The port
check, ``Popen``, ``shutil.which``, ``webbrowser.open`` and the ``npx --no-install`` check are fakes, so nothing is
started, no browser opens and no port is touched. Standard library only.
"""

import importlib.util
import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parent.parent / "tools" / "pm_open.py"
spec = importlib.util.spec_from_file_location("pm_open", SCRIPT)
pm_open = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pm_open)

BOARD = {
    "name": "board",
    "runtimeExecutable": "backlog",
    "runtimeArgs": ["browser", "--no-open", "--port", "6420"],
    "port": 6420,
}
MAP = {
    "name": "map",
    "runtimeExecutable": "npx",
    "runtimeArgs": ["-y", "likec4@1.60.0", "start", "--port", "5173"],
    "port": 5173,
}


class FakeProcess:
    """Stands in for a started server: its process id, and whether it has stopped (None while it runs)."""

    pid = 4321
    returncode = None

    def poll(self):
        return self.returncode


class OpenTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / ".pm").mkdir()
        self.answers = []  # the port check's answers, in order; the last one repeats
        self.ports = []  # every port the check was asked about
        self.runs = []  # (command, kwargs) of each start
        self.checks = []  # every npx download check
        self.opened = []  # every address handed to the browser
        self.programs = {"backlog": "/bin/backlog", "npx": "/bin/npx"}
        self.check_code = 0
        self.exit_code = None  # the started server's exit code; None while it runs
        for patch in (
            mock.patch.object(pm_open, "ROOT", self.root),
            mock.patch.object(pm_open, "WAIT_SECONDS", 0.05),
            mock.patch.object(pm_open, "POLL_SECONDS", 0),
            mock.patch.object(pm_open, "listening", self.listen),
            mock.patch.object(pm_open.subprocess, "Popen", self.spawn),
            mock.patch.object(pm_open.subprocess, "run", self.check),
            mock.patch.object(pm_open.shutil, "which", self.which),
            mock.patch.object(pm_open.webbrowser, "open", self.opened.append),
        ):
            patch.start()
            self.addCleanup(patch.stop)

    def listen(self, port):
        self.ports.append(port)
        if len(self.answers) > 1:
            return self.answers.pop(0)
        return self.answers[0] if self.answers else False

    def spawn(self, command, **kwargs):
        self.runs.append((command, kwargs))
        process = FakeProcess()
        process.returncode = self.exit_code
        return process

    def check(self, command, **kwargs):
        self.checks.append(command)
        return subprocess.CompletedProcess(command, self.check_code)

    def which(self, name):
        return self.programs.get(name)

    def run_tool(self, *args):
        out = io.StringIO()
        with redirect_stdout(out):
            code = pm_open.main(list(args))
        return code, out.getvalue()

    def write_launch(self, *configs):
        path = self.root / ".claude" / "launch.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"version": "0.0.1", "configurations": list(configs)}), encoding="utf-8")

    def test_board_that_is_already_open_is_opened_and_nothing_starts(self):
        self.answers = [True]
        code, out = self.run_tool("board")
        self.assertEqual(code, 0)
        self.assertIn("Something already answers", out)
        self.assertIn("another program holds port 6420", out)
        self.assertIn("http://127.0.0.1:6420", out)
        self.assertEqual(self.opened, ["http://127.0.0.1:6420"])
        self.assertEqual(self.runs, [])

    def test_board_without_backlog_says_how_to_get_it(self):
        self.programs = {}
        code, out = self.run_tool("board")
        self.assertEqual(code, 1)
        self.assertIn("npm i -g backlog.md", out)
        self.assertNotIn("Traceback", out)
        self.assertEqual(self.runs, [])
        self.assertEqual(self.opened, [])

    def test_board_starts_a_window_waits_for_the_port_and_reports_how_to_stop(self):
        self.answers = [False, False, True]
        code, out = self.run_tool("board")
        self.assertEqual(code, 0)
        command, kwargs = self.runs[0]
        self.assertEqual(command, ["/bin/backlog", "browser", "--no-open", "--port", "6420"])
        self.assertEqual(kwargs["cwd"], self.root)
        if os.name == "nt":
            self.assertEqual(kwargs["creationflags"], subprocess.CREATE_NEW_CONSOLE)
            self.assertIn("close the window", out)
        else:
            self.assertTrue(kwargs["start_new_session"])
            self.assertIn("4321", out)
        self.assertTrue((self.root / ".pm" / "local" / "open-board.log").exists())
        self.assertEqual(self.opened, ["http://127.0.0.1:6420"])
        self.assertEqual(self.ports, [6420, 6420, 6420])
        self.assertIn("http://127.0.0.1:6420", out)
        self.assertIn("backlog browser --no-open --port 6420", out)

    def test_board_that_never_answers_names_the_command_and_the_log(self):
        self.answers = [False]
        code, out = self.run_tool("board")
        self.assertEqual(code, 1)
        self.assertIn("did not answer", out)
        self.assertIn("backlog browser --no-open --port 6420", out)
        self.assertIn(".pm/local/open-board.log", out)
        self.assertEqual(self.opened, [])

    def test_map_without_the_layer_is_reported_as_not_installed(self):
        code, out = self.run_tool("map")
        self.assertEqual(code, 1)
        self.assertIn("not installed", out)
        self.assertIn("--map", out)
        self.assertEqual(self.runs, [])
        self.assertEqual(self.checks, [])
        self.assertEqual(self.opened, [])

    def test_board_that_stops_at_once_is_reported_without_the_full_wait(self):
        self.answers = [False]
        self.exit_code = 3
        code, out = self.run_tool("board")
        self.assertEqual(code, 1)
        self.assertIn("stopped before it answered", out)
        self.assertIn("exit code 3", out)
        self.assertIn(".pm/local/open-board.log", out)
        self.assertEqual(self.opened, [])

    def test_map_layer_without_its_entry_points_to_the_upgrade(self):
        (self.root / ".agents" / "skills" / "pm-likec4-dsl").mkdir(parents=True)
        code, out = self.run_tool("map")
        self.assertEqual(code, 1)
        self.assertIn("map layer is installed", out)
        self.assertIn("upgrading the package adds the entry", out)
        self.assertEqual(self.runs, [])

    def test_map_that_is_not_downloaded_stops_before_starting(self):
        self.write_launch(MAP)
        self.check_code = 1
        code, out = self.run_tool("map")
        self.assertEqual(code, 2)
        self.assertIn("likec4@1.60.0", out)
        self.assertIn("npm", out)
        self.assertIn("--download", out)
        self.assertEqual(self.checks, [["/bin/npx", "--no-install", "likec4@1.60.0", "--version"]])
        self.assertEqual(self.runs, [])

    def test_map_starts_the_entry_command_after_a_download_yes(self):
        self.write_launch(MAP)
        self.check_code = 1
        self.answers = [False, True]
        code, out = self.run_tool("map", "--download")
        self.assertEqual(code, 0)
        self.assertEqual(self.checks, [])
        self.assertEqual(self.runs[0][0], ["/bin/npx", "-y", "likec4@1.60.0", "start", "--port", "5173"])
        self.assertEqual(self.opened, ["http://127.0.0.1:5173"])
        self.assertIn("http://127.0.0.1:5173", out)

    def test_map_starts_without_the_flag_when_the_package_is_already_there(self):
        self.write_launch(MAP)
        self.answers = [False, True]
        code, _ = self.run_tool("map")
        self.assertEqual(code, 0)
        self.assertEqual(self.checks, [["/bin/npx", "--no-install", "likec4@1.60.0", "--version"]])
        self.assertEqual(
            self.runs[0][0],
            ["/bin/npx", "--no-install", "likec4@1.60.0", "start", "--port", "5173"],
            "without --download the start itself may not download, so -y becomes --no-install",
        )

    def test_launch_file_wins_over_the_built_in_defaults(self):
        self.write_launch(
            {
                "name": "board",
                "runtimeExecutable": "backlog",
                "runtimeArgs": ["browser", "--no-open", "--port", "7001"],
                "port": 7001,
            }
        )
        self.answers = [False, True]
        code, out = self.run_tool("board")
        self.assertEqual(code, 0)
        self.assertEqual(self.runs[0][0], ["/bin/backlog", "browser", "--no-open", "--port", "7001"])
        self.assertIn("http://127.0.0.1:7001", out)

    def test_the_port_field_counts_when_the_arguments_carry_no_port(self):
        self.write_launch({"name": "board", "runtimeExecutable": "backlog", "runtimeArgs": ["browser"], "port": 7002})
        self.answers = [True]
        code, _ = self.run_tool("board")
        self.assertEqual(code, 0)
        self.assertEqual(self.ports, [7002])

    def test_help_explains_both_names_and_the_download_flag(self):
        out = io.StringIO()
        with redirect_stdout(out), self.assertRaises(SystemExit) as raised:
            pm_open.main(["--help"])
        self.assertEqual(raised.exception.code, 0)
        text = out.getvalue()
        for word in ("board", "map", "--download"):
            self.assertIn(word, text)


if __name__ == "__main__":
    unittest.main()
