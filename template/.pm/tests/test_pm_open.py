"""Tests for ``python .pm/tools/pm_open.py``.

A throwaway project holds only a ``.pm/`` folder and, in the tests that need it, a ``.claude/launch.json``; the
project list lives in a throwaway ``PM_HOME``. The port check, ``Popen``, ``shutil.which``, ``webbrowser.open``, the
``npx --no-install`` check, the board's ``/api/status`` answer, the names a running map serves on each loopback, the process check, the process start time and the stop
call are fakes, so nothing is started, no browser opens and no port or process is touched. The project list, its
temporary files and its lock are real, in the throwaway folder. Standard library only.
"""

import contextlib
import importlib.util
import io
import json
import os
import signal
import socket
import subprocess
import tempfile
import threading
import time
import types
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parent.parent / "tools" / "pm_open.py"
spec = importlib.util.spec_from_file_location("pm_open", SCRIPT)
pm_open = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pm_open)
REAL_ALIVE, REAL_START_TIME = pm_open.alive, pm_open.start_time  # before setUp puts its fakes in their place

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
DEFAULT_BOARD = ["/bin/backlog", "browser", "--no-open", "--port", "6420", "--non-interactive"]


class FakeProcess:
    """Stands in for a started server: its process id, and whether it has stopped (None while it runs)."""

    def __init__(self, pid, returncode=None):
        self.pid = pid
        self.returncode = returncode

    def poll(self):
        return self.returncode


class LauncherTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name)
        self.root = self.project("shop")  # the project this command runs in
        self.other = self.project("other")  # a second project, for the shared port list
        self.store = self.work / "home" / "projects.json"
        self.lock = self.store.parent / "projects.lock"
        environment = mock.patch.dict(os.environ, {"PM_HOME": str(self.store.parent)})
        environment.start()
        self.addCleanup(environment.stop)
        self.answers = {}  # port -> the port check's answers, in order; the last one repeats
        self.after_start = set()  # the ports that answer once a server was started on them
        self.ports = []  # every port the check was asked about
        self.statuses = []  # every port the board status was asked about
        self.maps = {}  # address -> the LikeC4 project names the map there serves
        self.status = {}  # port -> the folder the board there says it serves
        self.owners = {}  # port -> the project root of the server that was started there
        self.runs = []  # (command, kwargs) of each start
        self.checks = []  # every npx download check
        self.opened = []  # every address handed to the browser
        self.programs = {"backlog": "/bin/backlog", "npx": "/bin/npx"}
        self.check_code = 0  # the npx check's answer: 0 when the package is already downloaded
        self.exit_code = None  # the started server's exit code; None while it runs
        self.pids = []  # every process id a start handed out
        self.starts = {}  # process id -> the start time the check reads now; the default is one per id
        self.serving = self.root  # the project the board under test belongs to
        self.live = set()  # the process ids the check calls alive
        self.ended = []  # every process id a stop asked to end
        self.guard = threading.Lock()  # the lock test runs two of these at once
        for patch in (
            mock.patch.object(pm_open, "WAIT_SECONDS", 0.1),
            mock.patch.object(pm_open, "POLL_SECONDS", 0.01),
            mock.patch.object(pm_open, "answers", self.listen),
            mock.patch.object(pm_open.subprocess, "Popen", self.spawn),
            mock.patch.object(pm_open.subprocess, "run", self.check),
            mock.patch.object(pm_open, "project_of", self.project_of),
            mock.patch.object(pm_open, "served_maps", lambda base: self.maps.get(base, [])),
            mock.patch.object(pm_open, "alive", self.is_alive),
            mock.patch.object(pm_open, "start_time", self.start_of),
            mock.patch.object(pm_open, "terminate", self.terminate),
            mock.patch.object(pm_open.shutil, "which", self.which),
            mock.patch.object(pm_open.webbrowser, "open", self.opened.append),
        ):
            patch.start()
            self.addCleanup(patch.stop)

    def project(self, name):
        """A throwaway project root: a folder with a .pm/ folder in it."""
        root = self.work / name
        (root / ".pm").mkdir(parents=True)
        return root

    def opened_port(self, port):
        """Whether something answers there now: a busy port, or one whose started server holds it."""
        if port in self.after_start and any(str(port) in command for command, _ in list(self.runs)):
            return True
        said = self.answers.get(port)
        return bool(said) and (said.pop(0) if len(said) > 1 else said[0])

    def listen(self, port):
        self.ports.append(port)
        return self.opened_port(port)

    def spawn(self, command, **kwargs):
        with self.guard:
            pid = 4321 + len(self.pids)
            self.pids.append(pid)
            self.runs.append((command, kwargs))
            self.owners[int(command[command.index("--port") + 1])] = kwargs["cwd"]
        return FakeProcess(pid, self.exit_code)

    def check(self, command, **kwargs):
        self.checks.append(command)
        return subprocess.CompletedProcess(command, self.check_code)

    def project_of(self, port):
        self.statuses.append(port)
        if port in self.status:
            return self.status[port]  # what the test says, including None
        if not self.opened_port(port):
            return None  # nothing answers there, so nothing names a folder
        return self.owners.get(port, self.serving.as_posix())

    def is_alive(self, pid):
        return pid in self.live

    def start_of(self, pid):
        return self.starts.get(pid, f"start-of-{pid}")

    def terminate(self, pid):
        self.ended.append(pid)
        return True

    def which(self, name):
        return self.programs.get(name)

    def run_tool(self, *args, root=None):
        self.serving = root or self.root
        out = io.StringIO()
        with mock.patch.object(pm_open, "ROOT", self.serving), redirect_stdout(out):
            code = pm_open.main(list(args))
        return code, out.getvalue()

    def open_in(self, root):
        """One `board` run in that project, the way a second command runs it: the root is passed in, not patched."""
        return pm_open.open_server("board", root=root)

    def write_launch(self, *configs, root=None):
        path = (root or self.root) / ".claude" / "launch.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"version": "0.0.1", "configurations": list(configs)}), encoding="utf-8")
        return path

    def write_store(self, data):
        self.store.parent.mkdir(parents=True, exist_ok=True)
        self.store.write_text(json.dumps(data), encoding="utf-8")

    def read_store(self):
        return json.loads(self.store.read_text(encoding="utf-8"))

    def key(self, root=None):
        return pm_open.folder_key(root or self.root)

    def record(self, root=None):
        return self.read_store()["projects"][self.key(root)]

    def write_map_config(self, name, folder=None, file="likec4.config.json"):
        path = (folder or self.root) / file
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"name": name}), encoding="utf-8")

    def busy(self, *ports):
        """Make those ports answer, for good."""
        for port in ports:
            self.answers[port] = [True]

    def answering_after_a_start(self, *ports):
        """Those ports are free until a server starts on them, then they answer."""
        self.after_start.update(ports)

    # -- the board ---------------------------------------------------------------------------------------------

    def test_board_starts_without_a_console_window_and_says_how_to_stop(self):
        self.answering_after_a_start(6420)
        code, out = self.run_tool("board")
        self.assertEqual(code, 0)
        command, kwargs = self.runs[0]
        self.assertEqual(command, DEFAULT_BOARD, "a `backlog browser` server gets --non-interactive")
        self.assertEqual(kwargs["cwd"], self.root)
        if os.name == "nt":
            self.assertEqual(
                kwargs["creationflags"],
                subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP,
                "no console window: its output goes to the log alone",
            )
        else:
            self.assertTrue(kwargs["start_new_session"])
        self.assertTrue((self.root / ".pm" / "local" / "open-board.log").exists())
        self.assertEqual(self.opened, ["http://127.0.0.1:6420"])
        self.assertIn("The board is open at http://127.0.0.1:6420", out)
        self.assertIn("python .pm/tools/pm_open.py stop board", out)
        self.assertNotIn("close the window", out)
        self.assertEqual(
            self.record()["board"],
            {"port": 6420, "pid": 4321, "started": "start-of-4321"},
            "the port, the process id and the time it started are recorded",
        )

    def test_a_second_open_while_ours_is_still_starting_starts_nothing(self):
        started = REAL_START_TIME(os.getpid())
        if not started:
            self.skipTest("this machine cannot read the start time of a process")
        self.write_store(
            {
                "projects": {
                    self.key(): {"name": "shop", "board": {"port": 6420, "pid": os.getpid(), "started": started}}
                }
            }
        )
        # The port stays silent, as it does while the server that was just started boots.
        with mock.patch.object(pm_open, "alive", REAL_ALIVE), mock.patch.object(pm_open, "start_time", REAL_START_TIME):
            code, out = self.run_tool("board")
        self.assertEqual(code, 0)
        self.assertEqual(
            out,
            "The board is still starting at http://127.0.0.1:6420; run this command again in a few seconds.\n",
        )
        self.assertEqual(self.runs, [], "the server that is still starting is not started a second time")
        self.assertEqual(self.opened, [], "the browser opens once the server answers, not before")

    def test_a_board_that_is_ours_already_is_opened_and_nothing_starts(self):
        self.busy(6420)
        code, out = self.run_tool("board")
        self.assertEqual(code, 0)
        self.assertIn("The board is already running at http://127.0.0.1:6420", out)
        self.assertEqual(self.opened, ["http://127.0.0.1:6420"])
        self.assertEqual(self.runs, [])
        self.assertEqual(self.statuses, [6420], "an answering port is asked who it serves")
        self.assertEqual(self.record()["board"], {"port": 6420}, "a board this tool did not start keeps no process id")

    def test_a_recorded_port_is_used_again_though_a_lower_one_is_free(self):
        self.write_store({"projects": {self.key(): {"name": "shop", "board": {"port": 7050, "pid": 999}}}})
        self.answering_after_a_start(7050)
        code, _ = self.run_tool("board")
        self.assertEqual(code, 0)
        self.assertEqual(self.runs[0][0][-2], "7050", "the address of a project stays the same")
        self.assertEqual(
            self.record()["board"],
            {"port": 7050, "pid": 4321, "started": "start-of-4321"},
            "the new process id replaces the old one",
        )

    def test_a_port_that_answers_for_another_folder_is_foreign_and_ours_starts_above(self):
        self.busy(6420)
        self.status[6420] = self.other.as_posix()
        self.answering_after_a_start(6421)
        code, out = self.run_tool("board")
        self.assertEqual(code, 0)
        self.assertIn(f"Port 6420 answers for another project ({self.other.as_posix()})", out)
        self.assertEqual(
            self.runs[0][0], ["/bin/backlog", "browser", "--no-open", "--port", "6421", "--non-interactive"]
        )
        self.assertEqual(self.opened, ["http://127.0.0.1:6421"])
        self.assertEqual(self.record()["board"]["port"], 6421, "ours is recorded on its own port")

    def test_a_port_that_answers_without_a_board_status_is_foreign(self):
        self.busy(6420)
        self.status[6420] = None  # it answers, but with nothing we can read
        self.answering_after_a_start(6421)
        code, out = self.run_tool("board")
        self.assertEqual(code, 0)
        self.assertIn("Port 6420 answers for another program", out)
        self.assertEqual(self.runs[0][0][-2:], ["6421", "--non-interactive"])
        self.assertEqual(self.opened, ["http://127.0.0.1:6421"])
        self.assertEqual(self.statuses, [6420, 6421], "the board that was started is asked too")

    def test_a_board_that_starts_but_serves_another_project_is_not_reported_open(self):
        self.answering_after_a_start(6420)
        self.status[6420] = self.other.as_posix()
        code, out = self.run_tool("board")
        self.assertEqual(code, 1)
        self.assertIn("it is not this project's board", out)
        self.assertNotIn("is open at", out)
        self.assertEqual(self.opened, [])

    def test_a_board_that_never_answers_names_the_command_and_the_log(self):
        code, out = self.run_tool("board")
        self.assertEqual(code, 1)
        self.assertIn("did not answer", out)
        self.assertIn("backlog browser --no-open --port 6420 --non-interactive", out)
        self.assertIn(".pm/local/open-board.log", out)
        self.assertEqual(self.opened, [])

    def test_board_that_stops_at_once_is_reported_without_the_full_wait(self):
        self.exit_code = 3
        code, out = self.run_tool("board")
        self.assertEqual(code, 1)
        self.assertIn("stopped before it answered", out)
        self.assertIn("exit code 3", out)
        self.assertIn(".pm/local/open-board.log", out)
        self.assertEqual(self.opened, [])

    def test_a_port_that_answers_after_the_started_server_quit_is_not_reported_open(self):
        self.answering_after_a_start(6420)  # free before the start, then something answers
        self.exit_code = 1  # but what was started has already quit
        code, out = self.run_tool("board")
        self.assertEqual(code, 1)
        self.assertIn("Another program may hold port 6420", out)
        self.assertNotIn("is open", out)
        self.assertEqual(self.opened, [])

    def test_board_without_backlog_says_how_to_get_it(self):
        self.programs = {}
        code, out = self.run_tool("board")
        self.assertEqual(code, 1)
        self.assertIn("npm i -g backlog.md", out)
        self.assertNotIn("Traceback", out)
        self.assertEqual(self.runs, [])
        self.assertEqual(self.opened, [])

    def test_launch_file_wins_over_the_built_in_defaults(self):
        self.write_launch(
            {
                "name": "board",
                "runtimeExecutable": "backlog",
                "runtimeArgs": ["browser", "--port", "7001"],
                "port": 7001,
            }
        )
        self.answering_after_a_start(7001)
        code, out = self.run_tool("board")
        self.assertEqual(code, 0)
        self.assertEqual(self.runs[0][0], ["/bin/backlog", "browser", "--port", "7001", "--non-interactive"])
        self.assertIn("http://127.0.0.1:7001", out)

    def test_a_board_command_that_is_already_non_interactive_is_left_alone(self):
        self.write_launch(
            {
                "name": "board",
                "runtimeExecutable": "backlog",
                "runtimeArgs": ["browser", "--non-interactive"],
                "port": 7002,
            }
        )
        self.answering_after_a_start(7002)
        code, _ = self.run_tool("board")
        self.assertEqual(code, 0)
        self.assertEqual(self.runs[0][0], ["/bin/backlog", "browser", "--non-interactive", "--port", "7002"])

    # -- the map -----------------------------------------------------------------------------------------------

    def test_the_map_gets_a_local_listen_address_and_its_own_hmr_port(self):
        self.write_launch(MAP)
        self.answering_after_a_start(5173)
        code, out = self.run_tool("map")
        self.assertEqual(code, 0)
        self.assertEqual(
            self.runs[0][0],
            [
                "/bin/npx",
                "--no-install",
                "likec4@1.60.0",
                "start",
                "--port",
                "5173",
                "--listen",
                "127.0.0.1",
                "--hmr-port",
                "24678",
            ],
        )
        self.assertEqual(
            self.record()["map"], {"port": 5173, "hmr_port": 24678, "pid": 4321, "started": "start-of-4321"}
        )
        self.assertEqual(self.opened, ["http://127.0.0.1:5173"])
        self.assertIn("--listen 127.0.0.1 --hmr-port 24678", out)

    def test_map_command_listens_on_ipv4_whatever_the_entry_says(self):
        for given in ("0.0.0.0", "::1", "localhost"):  # the launcher speaks IPv4 only
            command = pm_open.map_command(["/bin/npx", "likec4", "start", "--listen", given], 24678)
            self.assertEqual(command[command.index("--listen") + 1], "127.0.0.1")
            self.assertNotIn(given, command)
            self.assertEqual(command.count("--listen"), 1, "the value is replaced, not a second flag added")

    def test_the_map_takes_an_hmr_port_no_other_project_holds(self):
        self.write_store(
            {"projects": {self.key(self.other): {"name": "other", "map": {"port": 5174, "hmr_port": 24678, "pid": 9}}}}
        )
        self.write_launch(MAP)
        self.answering_after_a_start(5173)
        code, _ = self.run_tool("map")
        self.assertEqual(code, 0)
        self.assertIn("24679", self.runs[0][0])
        self.assertNotIn("24678", self.runs[0][0])
        self.assertEqual(self.record()["map"]["hmr_port"], 24679)

    def test_an_hmr_port_the_entry_names_moves_when_another_project_holds_it(self):
        self.write_store(
            {"projects": {self.key(self.other): {"name": "other", "map": {"port": 5174, "hmr_port": 24678, "pid": 9}}}}
        )
        self.write_launch(
            dict(MAP, runtimeArgs=["-y", "likec4@1.60.0", "start", "--port", "5173", "--hmr-port", "24678"])
        )
        self.answering_after_a_start(5173)
        code, out = self.run_tool("map")
        self.assertEqual(code, 0)
        command = self.runs[0][0]
        self.assertEqual(command[command.index("--hmr-port") + 1], "24679", "the command runs the chosen HMR port")
        self.assertEqual(command.count("--hmr-port"), 1)
        self.assertIn("--hmr-port 24679", out, "the line shows exactly what runs")
        self.assertEqual(self.record()["map"]["hmr_port"], 24679)

    def test_an_hmr_port_the_entry_names_is_kept_while_it_is_free(self):
        self.write_launch(
            dict(MAP, runtimeArgs=["-y", "likec4@1.60.0", "start", "--port", "5173", "--hmr-port", "25000"])
        )
        self.answering_after_a_start(5173)
        code, _ = self.run_tool("map")
        self.assertEqual(code, 0)
        command = self.runs[0][0]
        self.assertEqual(command[command.index("--hmr-port") + 1], "25000")
        self.assertEqual(self.record()["map"]["hmr_port"], 25000)

    def test_a_map_with_no_free_hmr_port_does_not_start(self):
        self.write_launch(MAP)
        self.busy(*range(pm_open.HMR_FIRST, pm_open.HMR_FIRST + pm_open.PORTS_TRIED))
        code, out = self.run_tool("map")
        self.assertEqual(code, 1)
        self.assertIn("HMR port was not found", out)
        self.assertEqual(self.runs, [], "nothing starts without an HMR port of its own")

    def test_a_map_whose_recorded_process_still_runs_is_opened_and_nothing_starts(self):
        self.write_launch(MAP)
        self.write_store(
            {"projects": {self.key(): {"name": "shop", "map": {"port": 5173, "pid": 4321, "started": "start-of-4321"}}}}
        )
        self.live = {4321}
        self.busy(5173)
        code, out = self.run_tool("map")
        self.assertEqual(code, 0)
        self.assertIn("The map is already running at http://127.0.0.1:5173", out)
        self.assertEqual(self.runs, [])
        self.assertEqual(self.opened, ["http://127.0.0.1:5173"])

    def test_a_map_whose_recorded_process_is_gone_is_foreign_even_though_the_port_answers(self):
        self.write_launch(MAP)
        self.write_store(
            {"projects": {self.key(): {"name": "shop", "map": {"port": 5173, "pid": 999, "started": "start-of-999"}}}}
        )
        self.busy(5173)
        self.answering_after_a_start(5174)
        code, out = self.run_tool("map")
        self.assertEqual(code, 0)
        self.assertIn(
            "Port 5173 answers for another program", out, "a running map of ours would have a live process id"
        )
        self.assertEqual(self.runs[0][0][:6], ["/bin/npx", "--no-install", "likec4@1.60.0", "start", "--port", "5174"])
        self.assertEqual(self.record()["map"]["port"], 5174)

    def test_a_process_id_that_belongs_to_another_process_is_not_ours(self):
        self.write_launch(MAP)
        self.write_store(
            {"projects": {self.key(): {"name": "shop", "map": {"port": 5173, "pid": 999, "started": "then"}}}}
        )
        self.live = {999}
        self.starts = {999: "now"}  # the id runs, but it is another process now
        self.busy(5173)
        self.answering_after_a_start(5174)
        code, out = self.run_tool("map")
        self.assertEqual(code, 0)
        self.assertIn("Port 5173 answers for another program", out, "a reused process id is not our map")
        self.assertEqual(self.runs[0][0][:6], ["/bin/npx", "--no-install", "likec4@1.60.0", "start", "--port", "5174"])
        self.assertEqual(self.record()["map"]["started"], "start-of-4321", "the new process replaces the stale one")

    def test_a_record_without_a_start_time_is_not_ours(self):
        self.write_launch(MAP)
        self.write_store({"projects": {self.key(): {"name": "shop", "map": {"port": 5173, "pid": 999}}}})
        self.live = {999}
        self.busy(5173)
        self.answering_after_a_start(5174)
        code, out = self.run_tool("map")
        self.assertEqual(code, 0)
        self.assertIn("Port 5173 answers for another program", out, "without a start time nothing proves it is ours")
        self.assertEqual(self.runs[0][0][4:6], ["--port", "5174"])

    def test_a_running_map_that_serves_this_projects_name_is_opened_and_left_running(self):
        self.write_launch(MAP)
        self.write_map_config("shop-map")  # a name the user chose
        self.busy(5173)  # started by the Claude preview or a terminal, on ::1 only
        self.maps["http://[::1]:5173"] = ["shop-map"]
        code, out = self.run_tool("map")
        self.assertEqual(code, 0)
        self.assertIn("The map is already running at http://[::1]:5173", out)
        self.assertEqual(self.runs, [], "no second map beside it")
        self.assertEqual(self.opened, ["http://[::1]:5173"], "the browser goes where the name was served")
        self.assertEqual(self.record()["map"], {"port": 5173}, "not started here, so no process id")
        code, out = self.run_tool("stop", "map")
        self.assertEqual(code, 0)
        self.assertIn("was not started by this tool, so I left it running", out)
        self.assertEqual(self.ended, [])

    def test_the_map_is_ours_on_the_loopback_that_serves_its_name_not_on_the_other(self):
        self.write_launch(MAP)
        self.write_map_config("shop-map")
        self.busy(5173)
        self.maps["http://127.0.0.1:5173"] = ["other-map"]  # another program holds the port on IPv4
        self.maps["http://[::1]:5173"] = ["shop-map"]
        code, out = self.run_tool("map")
        self.assertEqual(code, 0)
        self.assertEqual(self.opened, ["http://[::1]:5173"], "never the IPv4 program")
        self.assertEqual(self.runs, [])

    def test_a_running_map_of_another_likec4_project_is_foreign(self):
        self.write_launch(MAP)
        self.write_map_config("shop-map")
        self.busy(5173)
        self.maps["http://127.0.0.1:5173"] = ["other-9f8e7d"]
        self.answering_after_a_start(5174)
        code, out = self.run_tool("map")
        self.assertEqual(code, 0)
        self.assertIn("Port 5173 answers for another project (the LikeC4 project other-9f8e7d)", out)
        self.assertNotIn("no name I can read", out)
        self.assertEqual(self.runs[0][0][4:6], ["--port", "5174"])

    def test_a_made_name_with_this_folders_code_is_recognised(self):
        self.write_launch(MAP)
        name = f"shop-{pm_open.path_code(self.root)}"
        self.write_map_config(name)
        self.busy(5173)
        self.maps["http://127.0.0.1:5173"] = [name]
        code, out = self.run_tool("map")
        self.assertEqual(code, 0)
        self.assertEqual(self.runs, [])
        self.assertEqual(self.opened, ["http://127.0.0.1:5173"])

    def test_a_made_name_copied_from_another_folder_does_not_claim_its_map(self):
        self.write_launch(MAP)
        copied = f"shop-{pm_open.path_code(self.other)}"  # the other folder's config, copied here
        self.write_map_config(copied)
        self.busy(5173)
        self.maps["http://127.0.0.1:5173"] = [copied]  # that folder's map
        self.answering_after_a_start(5174)
        code, out = self.run_tool("map")
        self.assertEqual(code, 0)
        self.assertIn(f"The map name {copied} was made for another folder", out)
        self.assertEqual(self.runs[0][0][4:6], ["--port", "5174"], "the other folder's map is not taken for ours")

    def test_a_map_on_the_entrys_port_is_found_when_the_record_names_another(self):
        self.write_launch(MAP)
        self.write_map_config("shop-map")
        # `stop map` ended our map on 5174 and kept that port; the Claude preview's map still runs on 5173.
        self.write_store({"projects": {self.key(): {"name": "shop", "map": {"port": 5174, "hmr_port": 24679}}}})
        self.busy(5173)
        self.maps["http://[::1]:5173"] = ["shop-map"]
        code, out = self.run_tool("map")
        self.assertEqual(code, 0)
        self.assertEqual(self.runs, [], "no new map on the recorded port")
        self.assertEqual(self.opened, ["http://[::1]:5173"])
        self.assertEqual(self.record()["map"], {"port": 5173}, "the project now points at the running map")

    def test_a_foreign_map_on_the_entrys_port_leaves_the_recorded_port_in_use(self):
        self.write_launch(MAP)
        self.write_map_config("shop-map")
        self.write_store({"projects": {self.key(): {"name": "shop", "map": {"port": 5174, "hmr_port": 24679}}}})
        self.busy(5173)
        self.maps["http://127.0.0.1:5173"] = ["other-map"]
        self.answering_after_a_start(5174)
        code, out = self.run_tool("map")
        self.assertEqual(code, 0)
        self.assertEqual(self.runs[0][0][4:6], ["--port", "5174"], "the recorded port, as before")

    def test_a_made_name_is_checked_by_its_code_whatever_the_folders_are_called(self):
        for name in ("other", "project", "x"):  # a copy into shop-copy, a renamed folder, an empty slug's fallback
            with self.subTest(made_for=name):
                self.assertFalse(pm_open.made_here(self.root, f"{name}-{pm_open.path_code(self.other)}"))
        self.assertTrue(pm_open.made_here(self.root, f"other-{pm_open.path_code(self.root)}"), "a renamed made name")
        self.assertTrue(pm_open.made_here(self.root, "shop-map"), "a name the user chose has no code to check")

    def test_a_map_without_a_config_name_starts_beside_a_running_one_and_says_why(self):
        self.write_launch(MAP)
        self.busy(5173)
        self.maps["http://127.0.0.1:5173"] = ["default"]  # LikeC4's name for a project without a config
        self.answering_after_a_start(5174)
        code, out = self.run_tool("map")
        self.assertEqual(code, 0)
        self.assertIn("Port 5173 answers for another project (the LikeC4 project default)", out)
        self.assertIn("This project's map has no name I can read", out)
        self.assertEqual(self.runs[0][0][4:6], ["--port", "5174"])

    def test_the_map_name_comes_from_the_folder_the_map_serves(self):
        entry = dict(MAP, runtimeArgs=["-y", "likec4@1.60.0", "start", "docs/map", "--port", "5173"])
        self.write_launch(entry)
        self.write_map_config("at-the-root")
        self.write_map_config("in-docs", folder=self.root / "docs" / "map", file=".likec4rc")
        self.assertEqual(pm_open.map_name(self.root), "in-docs")

    def test_a_code_config_or_a_broken_one_gives_no_map_name(self):
        self.write_launch(MAP)
        (self.root / "likec4.config.ts").write_text("export default {}", encoding="utf-8")
        self.assertIsNone(pm_open.map_name(self.root), "a code config cannot be read here")
        (self.root / "likec4.config.json").write_text("{ // JSON5, which LikeC4 reads\n name: 'x' }", encoding="utf-8")
        self.assertIsNone(pm_open.map_name(self.root))

    def test_a_first_config_that_cannot_be_read_is_not_skipped_for_the_next(self):
        self.write_launch(MAP)
        (self.root / ".likec4rc").write_text("{ name: 'json5' }", encoding="utf-8")
        self.write_map_config("not-the-maps")
        self.assertIsNone(pm_open.map_name(self.root), "the next file's name may not be the map's")

    def test_keep_does_not_carry_a_process_id_to_another_port(self):
        self.write_store(
            {"projects": {self.key(): {"name": "shop", "board": {"pid": 4321, "started": "start-of-4321"}}}}
        )
        self.live = {4321}
        self.busy(6420)
        code, out = self.run_tool("board")
        self.assertEqual(code, 0)
        self.assertIn("The board is already running at http://127.0.0.1:6420", out)
        self.assertEqual(
            self.record()["board"], {"port": 6420}, "a board found on another port brings no process id with it"
        )

    def test_map_without_the_layer_is_reported_as_not_installed(self):
        code, out = self.run_tool("map")
        self.assertEqual(code, 1)
        self.assertIn("not installed", out)
        self.assertIn("--map", out)
        self.assertEqual(self.runs, [])
        self.assertEqual(self.checks, [])
        self.assertEqual(self.opened, [])

    def test_map_layer_without_its_entry_points_to_the_upgrade(self):
        (self.root / ".agents" / "skills" / "pm-likec4-dsl").mkdir(parents=True)
        code, out = self.run_tool("map")
        self.assertEqual(code, 1)
        self.assertIn("map layer is installed", out)
        self.assertIn("upgrading the package adds the entry", out)
        self.assertEqual(self.runs, [])

    def test_the_npx_download_check_runs_before_the_lock_is_taken(self):
        self.write_launch(MAP)
        self.store.parent.mkdir(parents=True, exist_ok=True)
        seen = []

        def check(package):
            seen.append(self.lock.exists())  # the npx check may take 120 seconds: no other run should wait for it
            return True

        self.answering_after_a_start(5173)
        with mock.patch.object(pm_open, "downloaded", check):
            code, _ = self.run_tool("map")
        self.assertEqual(code, 0)
        self.assertEqual(seen, [False], "the download check runs before the lock is taken")
        self.assertEqual(len(self.runs), 1, "the map still starts")
        self.assertFalse(self.lock.exists(), "the lock is released at the end")

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
        self.answering_after_a_start(5173)
        code, out = self.run_tool("map", "--download")
        self.assertEqual(code, 0)
        self.assertEqual(self.checks, [])
        self.assertEqual(
            self.runs[0][0],
            [
                "/bin/npx",
                "-y",
                "likec4@1.60.0",
                "start",
                "--port",
                "5173",
                "--listen",
                "127.0.0.1",
                "--hmr-port",
                "24678",
            ],
        )
        self.assertEqual(self.opened, ["http://127.0.0.1:5173"])
        self.assertIn("http://127.0.0.1:5173", out)

    def test_map_starts_without_the_flag_when_the_package_is_already_there(self):
        self.write_launch(MAP)
        self.answering_after_a_start(5173)
        code, _ = self.run_tool("map")
        self.assertEqual(code, 0)
        self.assertEqual(self.checks, [["/bin/npx", "--no-install", "likec4@1.60.0", "--version"]])
        self.assertEqual(
            self.runs[0][0][:2],
            ["/bin/npx", "--no-install"],
            "without --download the start itself may not download, so -y becomes --no-install",
        )

    def test_a_map_entry_without_a_pinned_version_still_asks_before_a_download(self):
        self.write_launch(dict(MAP, runtimeArgs=["-y", "likec4", "start", "--port", "5173"]))
        self.check_code = 1
        code, out = self.run_tool("map")
        self.assertEqual(code, 2)
        self.assertIn("--download", out)
        self.assertEqual(self.checks, [["/bin/npx", "--no-install", "likec4", "--version"]])
        self.assertEqual(self.runs, [])

    # -- entry names, files and the project list ----------------------------------------------------------------

    def test_both_entry_name_pairs_work(self):
        self.write_launch(
            dict(BOARD, name="backlog-board"),
            dict(MAP, name="likec4"),
        )
        self.answering_after_a_start(6420, 5173)
        board_code, _ = self.run_tool("board")
        map_code, _ = self.run_tool("map")
        self.assertEqual(board_code, 0)
        self.assertEqual(map_code, 0)
        self.assertEqual(self.runs[0][0][-2:], ["6420", "--non-interactive"])
        self.assertIn("likec4@1.60.0", self.runs[1][0])

    def test_the_launch_file_is_byte_identical_after_a_run(self):
        path = self.root / ".claude" / "launch.json"
        path.parent.mkdir(parents=True)
        original = '{"version":"0.0.1",  "configurations":[{"name":"board","runtimeExecutable":"backlog",\n "runtimeArgs":["browser","--port","7003"],"port":7003}]}'
        path.write_text(original, encoding="utf-8")
        self.answering_after_a_start(7003)
        code, _ = self.run_tool("board")
        self.assertEqual(code, 0)
        self.assertEqual(path.read_text(encoding="utf-8"), original, "launch.json is tracked in git: it is only read")

    def test_a_project_joins_the_list_the_first_time_its_board_opens(self):
        self.assertFalse(self.store.exists())
        self.answering_after_a_start(6420)
        self.run_tool("board")
        line = self.record()
        self.assertEqual(line["name"], "shop")
        self.assertEqual(line["board"]["port"], 6420)

    def test_two_projects_get_different_board_ports(self):
        self.answering_after_a_start(6420, 6421)
        first, _ = self.run_tool("board")
        second, out = self.run_tool("board", root=self.other)
        self.assertEqual((first, second), (0, 0))
        self.assertEqual(self.runs[0][0][-2], "6420")
        self.assertEqual(self.runs[1][0][-2], "6421", "another project already holds 6420")
        self.assertIn("http://127.0.0.1:6421", out)
        data = self.read_store()
        self.assertEqual(data["projects"][self.key()]["board"]["port"], 6420)
        self.assertEqual(data["projects"][self.key(self.other)]["board"]["port"], 6421)

    def test_two_runs_that_read_the_list_at_once_keep_both_records_and_different_ports(self):
        real_read, reads, guard = pm_open.read_store, [], threading.Lock()

        def read_at_once():
            data = real_read()
            with guard:
                reads.append(1)
                first = len(reads) <= 2
            if first:  # give the other run the same list to read, unless the lock holds it back
                time.sleep(0.3)
            return data

        self.answering_after_a_start(6420, 6421)
        with redirect_stdout(io.StringIO()), mock.patch.object(pm_open, "read_store", read_at_once):
            runs = [threading.Thread(target=self.open_in, args=(root,)) for root in (self.root, self.other)]
            for run in runs:
                run.start()
            for run in runs:
                run.join(30)
        data = self.read_store()["projects"]
        self.assertIn(self.key(), data, "the first run keeps its record")
        self.assertIn(self.key(self.other), data, "the second run keeps its record")
        ports = {data[self.key()]["board"]["port"], data[self.key(self.other)]["board"]["port"]}
        self.assertEqual(len(ports), 2, "two runs that read the list at once must not choose the same port")

    def test_the_lock_is_held_while_the_list_is_chosen_and_released_before_the_wait(self):
        probes = []

        def probe(port):
            probes.append((self.lock.exists(), bool(self.runs)))  # (holding the lock, a server already started)
            return self.listen(port)

        self.answering_after_a_start(6420)
        with mock.patch.object(pm_open, "answers", probe):
            code, _ = self.run_tool("board")
        self.assertEqual(code, 0)
        self.assertTrue(probes[0][0], "the port is chosen while the lock is held")
        self.assertFalse(probes[-1][0], "the wait for the server runs without the lock")
        self.assertFalse(self.lock.exists(), "the lock is released at the end")

    def test_a_lock_left_behind_by_a_run_that_died_is_removed(self):
        self.lock.parent.mkdir(parents=True, exist_ok=True)
        self.lock.write_text("", encoding="utf-8")
        old = time.time() - 2 * pm_open.LOCK_STALE
        os.utime(self.lock, (old, old))
        with mock.patch.object(pm_open, "LOCK_WAIT", 0.5):
            code, out = self.run_tool("opening", "always")
        self.assertEqual(code, 0)
        self.assertNotIn("Another run is using the project list", out)
        self.assertFalse(self.lock.exists())
        self.assertEqual(self.read_store()["opening"], "always")

    def test_a_lock_open_that_windows_refuses_is_waited_for_not_skipped(self):
        real_open, refused = os.open, []

        def open_while_deleted(path, flags, mode=0o777):
            if len(refused) < 3:  # Windows says this while another run's lock file is being deleted
                refused.append(path)
                raise PermissionError(13, "the file is being deleted")
            return real_open(path, flags, mode)

        with mock.patch.object(pm_open.os, "open", open_while_deleted), pm_open.locked():
            self.assertTrue(self.lock.exists(), "a refused open is a busy lock: it is waited for, not skipped")
        self.assertEqual(len(refused), 3)
        self.assertFalse(self.lock.exists(), "the lock is released at the end")

    def test_a_lock_that_is_never_free_ends_after_the_wait_with_one_line(self):
        waits, real_sleep = [], time.sleep

        def wait(seconds):
            waits.append(seconds)
            if len(waits) > 2000:
                raise AssertionError("the wait never ended: the deadline is not checked on every path")
            real_sleep(0.001)  # the deadline still passes, only sooner

        out = io.StringIO()
        with mock.patch.object(pm_open, "LOCK_WAIT", 0.2), mock.patch.object(pm_open.time, "sleep", wait):
            with mock.patch.object(pm_open.os, "open", side_effect=PermissionError(13, "busy")):
                with redirect_stdout(out), pm_open.locked() as held:
                    self.assertFalse(held, "a run without the lock says so through the yielded value")
                    self.assertFalse(self.lock.exists())
        lines = out.getvalue().splitlines()
        self.assertEqual(len(lines), 1, "one plain line says the lock was not held")
        self.assertIn(f"Another run is using the project list at {self.store}", lines[0])
        self.assertIn("nothing was changed", lines[0])
        self.assertTrue(waits, "a busy lock is waited for")

    def test_a_lock_that_cannot_be_made_at_all_ends_with_one_plain_line(self):
        out = io.StringIO()
        # A PermissionError is the Windows busy answer and is waited for; any other failure cannot be waited away.
        with mock.patch.object(pm_open.os, "open", side_effect=OSError(28, "no space left on that folder")):
            with redirect_stdout(out), pm_open.locked() as held:
                self.assertFalse(held, "no lock file means no lock")
        lines = out.getvalue().splitlines()
        self.assertEqual(len(lines), 1, "one plain line says the lock could not be made")
        self.assertIn(f"could not make the lock file at {self.lock}", lines[0])
        self.assertIn("nothing was changed", lines[0])

    def test_a_run_that_cannot_take_the_lock_changes_nothing(self):
        self.write_store({"projects": {self.key(): {"name": "shop", "board": {"port": 6420}}}})
        self.lock.parent.mkdir(parents=True, exist_ok=True)
        self.lock.write_text("", encoding="utf-8")  # another run holds a fresh lock: never stale
        before = self.store.read_bytes()
        self.answering_after_a_start(6420, 6421)
        with mock.patch.object(pm_open, "LOCK_WAIT", 0.05):
            codes = [
                self.run_tool("board")[0],
                self.run_tool("stop", "board")[0],
                self.run_tool("opening", "always")[0],
            ]
            _, out = self.run_tool("board")
        self.assertEqual(codes, [1, 1, 1], "every write waits for the lock or ends with 1")
        self.assertEqual(self.store.read_bytes(), before, "the other run's list is not touched without the lock")
        self.assertEqual(self.runs, [], "nothing is started without the list")
        self.assertIn(f"Another run is using the project list at {self.store}", out)
        self.assertTrue(self.lock.exists(), "the other run's lock is left alone")

    def test_the_project_list_is_written_to_a_temporary_file_and_moved(self):
        moves = []
        replace = os.replace

        def record_move(source, target):
            moves.append((Path(source), Path(target)))
            replace(source, target)

        with mock.patch.object(pm_open.os, "replace", record_move):
            code, _ = self.run_tool("opening", "always")
        self.assertEqual(code, 0)
        self.assertEqual(len(moves), 1)
        source, target = moves[0]
        self.assertEqual(target, self.store)
        self.assertEqual(source.parent, self.store.parent, "the temporary file sits next to its final name")
        self.assertEqual(sorted(path.name for path in self.store.parent.iterdir()), ["projects.json"])

    def test_a_broken_project_list_reads_as_empty_and_is_rewritten(self):
        self.store.parent.mkdir(parents=True, exist_ok=True)
        self.store.write_text("{ this is not json", encoding="utf-8")
        self.assertEqual(pm_open.opening(), "ask", "a broken file means the default")
        self.answering_after_a_start(6420)
        code, _ = self.run_tool("board")
        self.assertEqual(code, 0)
        self.assertEqual(self.record()["board"], {"port": 6420, "pid": 4321, "started": "start-of-4321"})

    def test_a_broken_project_list_is_copied_before_it_is_rewritten(self):
        self.store.parent.mkdir(parents=True, exist_ok=True)
        self.store.write_text("{ this is not json", encoding="utf-8")
        code, out = self.run_tool("opening", "always")
        self.assertEqual(code, 0)
        self.assertIn(str(self.store) + ".broken", out, "one plain line names the copy")
        self.assertIn("could not be read", out)
        self.assertEqual(
            (self.store.parent / "projects.json.broken").read_text(encoding="utf-8"),
            "{ this is not json",
            "the old list is kept before the new one is written",
        )
        self.assertEqual(self.read_store()["opening"], "always")

    def test_a_broken_project_list_that_is_not_utf8_is_copied_and_replaced(self):
        self.store.parent.mkdir(parents=True, exist_ok=True)
        broken = b'{"opening": "\xff\xfe"}'  # not UTF-8: reading it as text fails, as a list it is broken
        self.store.write_bytes(broken)
        code, out = self.run_tool("opening", "always")
        self.assertEqual(code, 0)
        self.assertIn("could not be read", out)
        self.assertEqual(
            (self.store.parent / "projects.json.broken").read_bytes(), broken, "the copy holds the very bytes"
        )
        self.assertEqual(self.read_store()["opening"], "always")

    def test_a_broken_list_whose_copy_fails_is_left_as_it_was(self):
        self.store.parent.mkdir(parents=True, exist_ok=True)
        self.store.write_text("{ this is not json", encoding="utf-8")
        with mock.patch.object(pm_open.shutil, "copyfile", side_effect=OSError(28, "no space left")):
            code, out = self.run_tool("opening", "always")
        self.assertEqual(code, 1, "a list that could not be kept is never replaced")
        self.assertEqual(self.store.read_text(encoding="utf-8"), "{ this is not json", "the only copy still stands")
        self.assertFalse((self.store.parent / "projects.json.broken").exists())
        self.assertIn("I left the list as it was", out)
        self.assertNotIn("I kept a copy", out, "the line about a kept copy waits for the copy")

    def test_a_list_that_cannot_be_read_is_left_as_it_was(self):
        # Sol, 3 Nov: a list the run may not read (a Windows ACL) was replaced without a copy.
        self.store.parent.mkdir(parents=True, exist_ok=True)
        self.store.write_text('{"opening": "never"}', encoding="utf-8")
        real = Path.read_bytes

        def refuse(path):
            if path == self.store:
                raise PermissionError(13, "Permission denied")
            return real(path)

        with mock.patch.object(pm_open.Path, "read_bytes", refuse):
            code, out = self.run_tool("opening", "always")
        self.assertEqual(code, 1, "a list that could not be read is never replaced")
        self.assertEqual(self.store.read_text(encoding="utf-8"), '{"opening": "never"}')
        self.assertIn("is there but could not be read (Permission denied); I left it as it was.", out)

    # -- stop and list ------------------------------------------------------------------------------------------

    def test_stop_with_no_record_does_nothing(self):
        code, out = self.run_tool("stop", "board")
        self.assertEqual(code, 0)
        self.assertIn("No board is recorded for this project, so I stopped nothing.", out)
        self.assertEqual(self.ended, [])

    def test_stop_ends_the_recorded_server_and_keeps_the_address(self):
        self.answering_after_a_start(6420)
        self.run_tool("board")
        self.live = {self.pids[-1]}
        code, out = self.run_tool("stop", "board")
        self.assertEqual(code, 0)
        self.assertEqual(self.ended, [4321])
        self.assertIn("Stopped the board (process id 4321).", out)
        self.assertEqual(self.record()["board"], {"port": 6420}, "the port stays, the claim to a process goes")
        self.assertEqual(self.record()["name"], "shop", "the project itself stays in the list")
        self.after_start.clear()  # the stopped server no longer answers there
        _, listed = self.run_tool("list")
        self.assertIn("board http://127.0.0.1:6420 stopped", listed)

    def test_stop_of_a_server_that_is_gone_says_so_and_does_nothing(self):
        self.write_store({"projects": {self.key(): {"name": "shop", "board": {"port": 6420, "pid": 999}}}})
        code, out = self.run_tool("stop", "board")
        self.assertEqual(code, 0)
        self.assertIn("The board recorded for this project is not running, so I stopped nothing.", out)
        self.assertEqual(self.ended, [])

    def test_stop_leaves_a_server_this_tool_did_not_start(self):
        self.write_store({"projects": {self.key(): {"name": "shop", "board": {"port": 6420}}}})
        self.busy(6420)  # this project's own board, started by hand
        code, out = self.run_tool("stop", "board")
        self.assertEqual(code, 0)
        self.assertEqual(self.ended, [], "nothing is ended: this tool cannot tell whose process it is")
        self.assertIn("was not started by this tool, so I left it running", out)
        self.assertNotIn("is not running", out, "the board answers, so saying it is not running would be wrong")

    def test_stop_does_not_end_a_process_that_is_not_ours(self):
        self.write_store(
            {"projects": {self.key(): {"name": "shop", "map": {"port": 5173, "pid": 999, "started": "then"}}}}
        )
        self.live = {999}
        self.starts = {999: "now"}  # the recorded id was handed to another process
        self.busy(5173)
        code, out = self.run_tool("stop", "map")
        self.assertEqual(code, 0)
        self.assertEqual(self.ended, [], "a process id that now belongs to another process is never ended")
        self.assertIn("was not started by this tool, so I left it running", out)
        self.assertEqual(self.record()["map"], {"port": 5173}, "the stale process id is dropped from the list")

    def test_stop_reads_the_process_once_right_before_it_ends_it(self):
        self.write_store(
            {"projects": {self.key(): {"name": "shop", "map": {"port": 5173, "pid": 999, "started": "then"}}}}
        )
        self.live = {999}
        self.busy(5173)
        reads = iter(["then", "now"])  # ours for the ownership check, another process by the time it is ended
        with mock.patch.object(pm_open, "start_time", lambda pid: next(reads, "now")):
            code, out = self.run_tool("stop", "map")
        self.assertEqual(code, 0)
        self.assertEqual(self.ended, [], "only the process read right before the end is ended")
        self.assertIn("was not started by this tool, so I left it running", out)
        self.assertNotIn("Stopped the map", out)
        self.assertEqual(self.record()["map"], {"port": 5173}, "the stale process id is dropped from the list")

    def test_stop_needs_to_know_which_server(self):
        code, out = self.run_tool("stop")
        self.assertEqual(code, 1)
        self.assertIn("stop board", out)

    def test_list_calls_a_map_that_serves_this_projects_name_running(self):
        self.write_launch(MAP)
        self.write_map_config("shop-map")
        self.write_store({"projects": {self.key(): {"name": "shop", "map": {"port": 5173}}}})
        self.busy(5173)
        self.maps["http://[::1]:5173"] = ["shop-map"]
        code, out = self.run_tool("list")
        self.assertEqual(code, 0)
        self.assertIn("map http://[::1]:5173 running", out)

    def test_list_names_each_project_with_its_board_and_map(self):
        self.write_store(
            {
                "projects": {
                    self.key(): {"name": "shop", "board": {"port": 6421, "pid": 4321}, "map": {"port": 5173}},
                    self.key(self.other): {"name": "other", "map": {"port": 5174, "pid": 9, "hmr_port": 24678}},
                }
            }
        )
        self.live = {4321}
        self.busy(6421, 5173)
        code, out = self.run_tool("list")
        self.assertEqual(code, 0)
        lines = out.splitlines()
        self.assertEqual(len(lines), 2, "one line per project")
        shop = next(line for line in lines if line.startswith("shop"))
        self.assertIn("board http://127.0.0.1:6421 running", shop)
        other = next(line for line in lines if line.startswith("other"))
        self.assertIn("board not started yet", other)
        self.assertIn("map http://127.0.0.1:5174 stopped", other, "a dead process id is not a running map")

    def test_list_calls_a_server_running_only_when_it_is_this_projects_own(self):
        self.write_store(
            {
                "projects": {
                    self.key(): {
                        "name": "shop",
                        "board": {"port": 6421, "pid": 4321, "started": "start-of-4321"},
                        "map": {"port": 5173, "pid": 4322, "started": "start-of-4322"},
                    },
                    self.key(self.other): {"name": "other", "board": {"port": 6422}, "map": {"port": 5174}},
                }
            }
        )
        self.status[6421] = self.other.as_posix()  # the board there serves another project
        self.live = {4322}
        self.busy(6421, 5173, 5174)
        code, out = self.run_tool("list")
        self.assertEqual(code, 0)
        shop = next(line for line in out.splitlines() if line.startswith("shop"))
        other = next(line for line in out.splitlines() if line.startswith("other"))
        self.assertIn("board http://127.0.0.1:6421 answers for another program", shop)
        self.assertIn("map http://127.0.0.1:5173 running", shop)
        self.assertIn("board http://127.0.0.1:6422 stopped", other)
        self.assertIn("map http://127.0.0.1:5174 answers for another program", other)

    def test_list_with_nothing_registered_says_how_to_add_a_project(self):
        code, out = self.run_tool("list")
        self.assertEqual(code, 0)
        self.assertIn("No project is registered yet", out)
        self.assertIn("pm_open.py board", out)

    # -- the opening setting -------------------------------------------------------------------------------------

    def test_opening_stores_the_choice_and_says_what_it_means(self):
        code, out = self.run_tool("opening", "always")
        self.assertEqual(code, 0)
        self.assertEqual(self.read_store()["opening"], "always")
        self.assertIn("The project window is now 'always'", out)
        self.assertIn("opens the board without asking", out)

    def test_opening_without_a_word_is_refused(self):
        code, out = self.run_tool("opening", "sometimes")
        self.assertEqual(code, 1)
        self.assertIn("ask`, `always` or `never`", out)
        self.assertFalse(self.store.exists(), "a refused choice writes nothing")

    def test_the_window_lines_read_as_plain_words(self):
        self.assertEqual(
            pm_open.WINDOW_LINES["ask"],
            "Project window: ask the user once whether to open the board (python .pm/tools/pm_open.py board).",
        )
        self.assertEqual(
            pm_open.WINDOW_LINES["always"],
            "Project window: the user chose always; open the board now with python .pm/tools/pm_open.py board.",
        )
        self.assertEqual(pm_open.WINDOW_LINES["never"], "")

    def test_help_explains_every_command(self):
        out = io.StringIO()
        with redirect_stdout(out), self.assertRaises(SystemExit) as raised:
            pm_open.main(["--help"])
        self.assertEqual(raised.exception.code, 0)
        text = out.getvalue()
        for word in ("board", "map", "--download", "stop", "list", "opening"):
            self.assertIn(word, text)


class CommandTest(unittest.TestCase):
    """The command a server runs: the flag's value replaced where it is, or the flag added once."""

    def test_an_option_is_replaced_in_place_or_added_once(self):
        self.assertEqual(
            pm_open.with_port(["/bin/backlog", "browser", "--port", "6420"], 6421),
            ["/bin/backlog", "browser", "--port", "6421"],
        )
        self.assertEqual(
            pm_open.with_port(["/bin/backlog", "browser"], 6421), ["/bin/backlog", "browser", "--port", "6421"]
        )
        self.assertEqual(
            pm_open.map_command(["/bin/npx", "likec4", "start", "--listen", "0.0.0.0"], 24679),
            ["/bin/npx", "likec4", "start", "--listen", "127.0.0.1", "--hmr-port", "24679"],
        )
        self.assertEqual(
            pm_open.map_command(["/bin/npx", "likec4", "start", "--hmr-port", "25000"], 24679),
            ["/bin/npx", "likec4", "start", "--hmr-port", "24679", "--listen", "127.0.0.1"],
        )


class Answer:
    """What urlopen hands back: a body to read, in a with block."""

    def __init__(self, text):
        self.text = text

    def __enter__(self):
        return self

    def __exit__(self, *problem):
        return False

    def read(self):
        return self.text.encode("utf-8")


class ServedMapsTest(unittest.TestCase):
    """A running LikeC4 map names the projects it serves in its likec4:projects module; nothing else is read."""

    HEAD = (
        'import { createHotContext as __vite__createHotContext } from "/@vite/client";'
        'import.meta.hot = __vite__createHotContext("likec4:plugin/projects.js");'
        'import { atom, useStore } from "/@fs/likec4_vite-plugin_internal.js";\n'
    )
    MODULE = HEAD + (
        "export const isSingleProject = false;\n"
        "export const projects = [{\n"
        '\tid: "shop-map",\n\ttitle: "Shop",\n\tpath: "",\n\texportFormats: [\n\t\t"png",\n\t\t"drawio"\n\t]\n'
        '}, {\n\tid: "lib",\n\ttitle: "Lib"\n}];\n'
        "export const $projects = atom([...projects]);\n"
    )

    def served(self, text, base="http://127.0.0.1:5173"):
        asked = []

        def urlopen(url, timeout):
            asked.append(url)
            return Answer(text)

        with mock.patch.object(pm_open.urllib.request, "urlopen", urlopen):
            with mock.patch.object(pm_open, "answers_on", return_value=True):
                return pm_open.served_maps(base), asked

    def test_the_names_come_from_likec4s_projects_module(self):
        names, asked = self.served(self.MODULE)
        self.assertEqual(names, ["shop-map", "lib"])
        self.assertEqual(asked, ["http://127.0.0.1:5173/@id/likec4:projects"])

    def test_an_id_inside_a_title_is_not_a_served_name(self):
        text = self.HEAD + 'export const projects = [{\n\tid: "other",\n\ttitle: "Project id: \'ours\'"\n}];\n'
        self.assertEqual(self.served(text)[0], ["other"])

    def test_a_page_that_only_quotes_the_module_names_nothing(self):
        page = '<html><pre>export const projects = [{\n\tid: "ours"\n}];</pre></html>'
        self.assertEqual(self.served(page)[0], [])
        self.assertEqual(self.served("<html>" + self.MODULE)[0], [], "the module's mark must be its first line")

    def test_a_silent_loopback_is_not_asked(self):
        with mock.patch.object(pm_open.urllib.request, "urlopen") as asked:
            with mock.patch.object(pm_open, "answers_on", return_value=False):
                self.assertEqual(pm_open.served_maps("http://127.0.0.1:5173"), [])
        asked.assert_not_called()

    def test_no_answer_names_nothing(self):
        def refused(url, timeout):
            raise OSError("connection refused")

        with mock.patch.object(pm_open.urllib.request, "urlopen", refused):
            self.assertEqual(pm_open.served_maps("http://[::1]:5173"), [])


class PortTest(unittest.TestCase):
    """A port counts as taken when something answers on 127.0.0.1 or ::1."""

    def test_a_port_that_answers_only_on_ipv6_counts_as_taken(self):
        try:
            server = socket.socket(socket.AF_INET6)
            server.bind(("::1", 0))
            server.listen(1)
        except OSError:
            self.skipTest("this machine has no IPv6 loopback")
        self.addCleanup(server.close)
        self.assertTrue(pm_open.answers(server.getsockname()[1]))

    def test_a_port_nobody_holds_is_free(self):
        probe = socket.socket()
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
        probe.close()
        self.assertFalse(pm_open.answers(port))

    def test_a_machine_without_ipv6_just_has_no_answer_there(self):
        tried = []

        class Probe:
            def __init__(self, family):
                if family == socket.AF_INET6:
                    raise OSError("no IPv6 on this machine")
                tried.append(family)

            def __enter__(self):
                return self

            def __exit__(self, *problem):
                return False

            def settimeout(self, seconds):
                pass

            def connect_ex(self, address):
                return 0 if address[0] == "127.0.0.1" else 111  # IPv4 answers, IPv6 could not be tried

        with mock.patch.object(pm_open.socket, "socket", Probe):
            self.assertTrue(pm_open.answers(6420))
        self.assertEqual(tried, [socket.AF_INET])

    def test_an_ipv6_answer_without_an_ipv4_one_still_counts(self):
        class Probe:
            def __init__(self, family):
                self.family = family

            def __enter__(self):
                return self

            def __exit__(self, *problem):
                return False

            def settimeout(self, seconds):
                pass

            def connect_ex(self, address):
                return 0 if (self.family == socket.AF_INET6 and address[0] == "::1") else 111

        with mock.patch.object(pm_open.socket, "socket", Probe):
            self.assertTrue(pm_open.answers(6420))


class FakeKernel32:
    """Stands in for the Windows kernel: an OpenProcess handle, the exit code and the creation time it writes."""

    def __init__(self, code=pm_open.STILL_ACTIVE, handle=1234, created=132000000000000000):
        self.code, self.handle, self.created, self.closed = code, handle, created, []
        self.OpenProcess = mock.Mock(return_value=handle)
        self.GetExitCodeProcess = mock.Mock(side_effect=self.exit_code)
        self.GetProcessTimes = mock.Mock(side_effect=self.times)
        self.CloseHandle = mock.Mock(side_effect=self.closed.append)

    def exit_code(self, handle, pointer):
        pointer._obj.value = self.code
        return 1

    def times(self, handle, created, exited, kernel, user):
        created._obj.value = self.created
        return 1


class PlatformTest(unittest.TestCase):
    """The Windows branches run on any system, and nothing real is signalled or started."""

    def setUp(self):
        self.kill = mock.Mock()

    def windows(self, kernel):
        """os.name says nt, os.kill is recorded, and ctypes.windll is this fake kernel; all restored afterwards."""
        stack = contextlib.ExitStack()
        stack.enter_context(mock.patch.object(pm_open.os, "name", "nt"))
        stack.enter_context(mock.patch.object(pm_open.os, "kill", self.kill))
        stack.enter_context(
            mock.patch.object(pm_open.ctypes, "windll", types.SimpleNamespace(kernel32=kernel), create=True)
        )
        return stack

    def test_the_alive_check_never_calls_os_kill_on_windows(self):
        kernel = FakeKernel32()
        with self.windows(kernel):
            self.assertTrue(pm_open.alive(4321))
        self.kill.assert_not_called()
        self.assertEqual(kernel.OpenProcess.call_args[0], (pm_open.QUERY_LIMITED, False, 4321))
        self.assertEqual(kernel.CloseHandle.call_count, 1, "the handle is closed again")

    def test_a_windows_process_that_has_exited_reads_as_gone(self):
        with self.windows(FakeKernel32(code=0)):
            self.assertFalse(pm_open.alive(4321))

    def test_a_windows_process_that_cannot_be_opened_reads_as_gone(self):
        with self.windows(FakeKernel32(handle=0)):
            self.assertFalse(pm_open.alive(4321))

    def test_the_windows_start_time_comes_from_get_process_times(self):
        kernel = FakeKernel32(created=132000000000000001)
        with self.windows(kernel):
            self.assertEqual(pm_open.start_time(4321), "132000000000000001")
        self.kill.assert_not_called()
        self.assertEqual(kernel.OpenProcess.call_args[0], (pm_open.QUERY_LIMITED, False, 4321))
        self.assertEqual(kernel.CloseHandle.call_count, 1, "the handle is closed again")

    def test_a_windows_process_whose_times_cannot_be_read_has_no_start_time(self):
        kernel = FakeKernel32()
        kernel.GetProcessTimes = mock.Mock(return_value=0)
        with self.windows(kernel):
            self.assertIsNone(pm_open.start_time(4321), "without a start time a process is not ours")

    def test_a_windows_process_that_cannot_be_opened_has_no_start_time(self):
        with self.windows(FakeKernel32(handle=0)):
            self.assertIsNone(pm_open.start_time(4321))

    def test_a_process_id_of_zero_has_no_start_time(self):
        self.assertIsNone(pm_open.start_time(0))
        self.assertIsNone(pm_open.start_time(None))

    def test_stop_on_windows_ends_the_whole_tree(self):
        run = mock.Mock(return_value=subprocess.CompletedProcess([], 0))
        with self.windows(FakeKernel32()), mock.patch.object(pm_open.subprocess, "run", run):
            self.assertTrue(pm_open.terminate(4321))
        self.assertEqual(run.call_args[0][0], ["taskkill", "/T", "/F", "/PID", "4321"])
        self.kill.assert_not_called()

    def test_stop_elsewhere_signals_the_process_group(self):
        killpg = mock.Mock()
        # A server starts in a session of its own, so its group id is its own process id.
        group = mock.patch.object(pm_open.os, "getpgid", lambda pid: pid, create=True)
        signal_group = mock.patch.object(pm_open.os, "killpg", killpg, create=True)
        with mock.patch.object(pm_open.os, "name", "posix"), group, signal_group:
            self.assertTrue(pm_open.terminate(4321))
        killpg.assert_called_once_with(4321, signal.SIGTERM)

    def test_stop_elsewhere_ends_nothing_when_the_group_is_another_one(self):
        killpg = mock.Mock()
        group = mock.patch.object(pm_open.os, "getpgid", lambda pid: 77, create=True)  # another program's group
        signal_group = mock.patch.object(pm_open.os, "killpg", killpg, create=True)
        with mock.patch.object(pm_open.os, "name", "posix"), group, signal_group:
            self.assertFalse(pm_open.terminate(4321))
        killpg.assert_not_called()  # the group holds programs this tool did not start

    def test_the_alive_check_elsewhere_only_asks(self):
        with mock.patch.object(pm_open.os, "name", "posix"), mock.patch.object(pm_open.os, "kill", self.kill):
            self.assertTrue(pm_open.alive(4321))
        self.kill.assert_called_once_with(4321, 0)

    def test_a_process_id_of_zero_is_never_checked(self):
        with mock.patch.object(pm_open.os, "name", "posix"), mock.patch.object(pm_open.os, "kill", self.kill):
            self.assertFalse(pm_open.alive(0))
            self.assertFalse(pm_open.alive(None))
        self.kill.assert_not_called()


class StartTimeTest(unittest.TestCase):
    """The start time of a process, read the way this system offers it; no process is started or ended."""

    @unittest.skipUnless(os.name == "nt", "the Windows creation time comes from GetProcessTimes")
    def test_on_windows_the_start_time_of_this_process_can_be_read(self):
        started = pm_open.start_time(os.getpid())
        self.assertTrue(started and started.isdigit())
        self.assertEqual(pm_open.start_time(os.getpid()), started, "a process keeps the time it started")

    @unittest.skipUnless(os.path.isdir("/proc"), "the Linux start time is the 22nd field of /proc/<pid>/stat")
    def test_on_linux_the_start_time_is_the_22nd_field_of_proc_stat(self):
        started = pm_open.start_time(os.getpid())
        self.assertTrue(started and started.isdigit())
        self.assertEqual(pm_open.start_time(os.getpid()), started, "a process keeps the time it started")
        self.assertIsNone(pm_open.start_time(999999999), "no such process, no start time")

    def test_elsewhere_the_start_time_comes_from_ps(self):
        run = mock.Mock(return_value=subprocess.CompletedProcess([], 0, stdout="Tue Nov  4 09:00:00 2025\n"))
        with mock.patch.object(pm_open.os, "name", "posix"):
            if os.path.isdir("/proc"):
                self.skipTest("this machine reads /proc instead")
            with mock.patch.object(pm_open.subprocess, "run", run):
                self.assertEqual(pm_open.start_time(4321), "Tue Nov  4 09:00:00 2025")
        self.assertEqual(run.call_args[0][0], ["ps", "-o", "lstart=", "-p", "4321"])

    def test_a_process_whose_ps_output_is_empty_has_no_start_time(self):
        run = mock.Mock(return_value=subprocess.CompletedProcess([], 0, stdout="  \n"))
        with mock.patch.object(pm_open.os, "name", "posix"):
            if os.path.isdir("/proc"):
                self.skipTest("this machine reads /proc instead")
            with mock.patch.object(pm_open.subprocess, "run", run):
                self.assertIsNone(pm_open.start_time(4321))

    def test_a_failing_ps_reads_as_no_start_time(self):
        run = mock.Mock(side_effect=OSError("no ps here"))
        with mock.patch.object(pm_open.os, "name", "posix"):
            if os.path.isdir("/proc"):
                self.skipTest("this machine reads /proc instead")
            with mock.patch.object(pm_open.subprocess, "run", run):
                self.assertIsNone(pm_open.start_time(4321))

    def test_a_record_without_a_start_time_is_never_ours(self):
        server = {"port": 5173, "pid": 4321}
        with mock.patch.object(pm_open, "alive", lambda pid: True), mock.patch.object(
            pm_open, "start_time", lambda pid: "start-of-4321"
        ):
            self.assertIsNone(pm_open.process_of(server), "a process id alone proves nothing")

    def test_a_record_whose_start_time_differs_is_not_ours(self):
        server = {"port": 5173, "pid": 4321, "started": "then"}
        with mock.patch.object(pm_open, "alive", lambda pid: True), mock.patch.object(
            pm_open, "start_time", lambda pid: "now"
        ):
            self.assertIsNone(pm_open.process_of(server), "the id was handed to another process")

    def test_a_record_whose_process_still_started_then_is_ours(self):
        server = {"port": 5173, "pid": 4321, "started": "start-of-4321"}
        with mock.patch.object(pm_open, "alive", lambda pid: True), mock.patch.object(
            pm_open, "start_time", lambda pid: "start-of-4321"
        ):
            self.assertEqual(pm_open.process_of(server), 4321)


class StartTest(unittest.TestCase):
    """A started server outlives the command: no console window on Windows, its own session elsewhere."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.popen = mock.Mock(return_value="process")
        patch = mock.patch.object(pm_open.subprocess, "Popen", self.popen)
        patch.start()
        self.addCleanup(patch.stop)

    def start(self):
        log = self.root / ".pm" / "local" / "open-board.log"
        return pm_open.start(["/bin/backlog", "browser"], self.root, log)

    def test_elsewhere_the_server_gets_a_session_of_its_own(self):
        with mock.patch.object(pm_open.os, "name", "posix"):
            self.assertEqual(self.start(), "process")
        options = self.popen.call_args[1]
        self.assertTrue(options["start_new_session"])
        self.assertNotIn("creationflags", options)
        self.assertEqual(options["stderr"], subprocess.STDOUT, "the server's own output goes to the log")

    @unittest.skipUnless(os.name == "nt", "the two creation flags exist on Windows only")
    def test_on_windows_the_server_gets_no_console_window(self):
        self.start()
        options = self.popen.call_args[1]
        self.assertEqual(options["creationflags"], subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP)


class RootAndBrowserOptions(unittest.TestCase):
    """What the project window asks of this tool: another folder, and no browser."""

    def setUp(self):
        for name in ("ROOT", "BROWSER"):
            patch = mock.patch.object(pm_open, name, getattr(pm_open, name))
            patch.start()
            self.addCleanup(patch.stop)

    def test_root_points_the_tool_at_that_project(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / ".pm").mkdir()
            with mock.patch.object(pm_open, "stop_server", return_value=0) as stop:
                self.assertEqual(pm_open.main(["stop", "map", "--root", folder]), 0)
            stop.assert_called_once_with("map")
            self.assertEqual(pm_open.ROOT, Path(folder).resolve())

    def test_a_folder_without_pm_is_refused(self):
        with tempfile.TemporaryDirectory() as folder, redirect_stdout(io.StringIO()) as out:
            with mock.patch.object(pm_open, "open_server") as started:
                self.assertEqual(pm_open.main(["map", "--root", folder]), 1)
        started.assert_not_called()
        self.assertIn("no .pm folder", out.getvalue())

    def test_no_browser_opens_nothing(self):
        with mock.patch.object(pm_open, "open_server", return_value=0):
            pm_open.main(["map", "--no-browser"])
        with mock.patch.object(pm_open.webbrowser, "open") as opened:
            pm_open.show("http://127.0.0.1:1")
        opened.assert_not_called()

    def test_the_browser_opens_by_default(self):
        with mock.patch.object(pm_open, "open_server", return_value=0):
            pm_open.main(["map"])
        with mock.patch.object(pm_open.webbrowser, "open") as opened:
            pm_open.show("http://127.0.0.1:1")
        opened.assert_called_once()


if __name__ == "__main__":
    unittest.main()
