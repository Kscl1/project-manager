"""Tests for ``python .pm/tools/pm_bridge.py``, the project window's local server.

A real server runs on a free port with a throwaway ``PM_HOME`` and a throwaway project, whose ``pm_state.py`` is a small
script written here. Starting and stopping a map is a fake ``run`` in these tests, so nothing is started; the map's
ownership check is a fake too. The red-line tests read the program's own source. Standard library only.
"""

import ast
import hashlib
import http.client
import importlib.util
import json
import os
import shutil
import socket
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

TOOLS = Path(__file__).resolve().parent.parent / "tools"
SCRIPT = TOOLS / "pm_bridge.py"
spec = importlib.util.spec_from_file_location("pm_bridge", SCRIPT)
pm_bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pm_bridge)
pm_open = pm_bridge.pm_open

STATE = 'import json\nprint(json.dumps({"version": %d, "project": {"name": "ç"}}, ensure_ascii=False))\n'
LAUNCH = {"configurations": [{"name": "map", "runtimeExecutable": "npx", "runtimeArgs": ["likec4"], "port": 5173}]}


class Case(unittest.TestCase):
    def setUp(self):
        self.temp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.temp, ignore_errors=True)
        self.project = self.temp / "demo"
        (self.project / ".pm" / "tools").mkdir(parents=True)
        (self.project / ".pm" / "backlog" / "tasks").mkdir(parents=True)
        (self.project / ".pm" / "decisions").mkdir()
        (self.project / ".pm" / "backlog" / "tasks" / "req-1.md").write_text("task", encoding="utf-8")
        (self.project / ".pm" / "decisions" / "D-1.md").write_text("decision", encoding="utf-8")
        (self.project / ".claude").mkdir()
        (self.project / ".claude" / "launch.json").write_text(json.dumps(LAUNCH), encoding="utf-8")
        self.write_state(STATE % 1)
        home = self.temp / "home"
        home.mkdir()
        self.key = pm_open.folder_key(self.project)
        store = {"projects": {self.key: {"name": "demo", "map": {"port": 5200}}}}
        (home / "projects.json").write_text(json.dumps(store), encoding="utf-8")
        patch = mock.patch.dict(os.environ, {"PM_HOME": str(home)})
        patch.start()
        self.addCleanup(patch.stop)
        self.id = pm_open.path_code(self.key)
        self.server = pm_bridge.Bridge(0)
        thread = threading.Thread(target=self.server.serve_forever, args=(0.02,), daemon=True)
        thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.origin = f"http://127.0.0.1:{self.server.port}"

    def write_state(self, text):
        (self.project / ".pm" / "tools" / "pm_state.py").write_text(text, encoding="utf-8")

    def ask(self, method, path, body=None, **headers):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.port, timeout=10)
        self.addCleanup(connection.close)
        names = {"Host": headers.pop("host", f"127.0.0.1:{self.server.port}")}
        names.update({key.replace("_", "-"): value for key, value in headers.items()})
        connection.putrequest(method, path, skip_host=True)
        for key, value in names.items():
            connection.putheader(key, value)
        data = body if isinstance(body, bytes) else (json.dumps(body).encode() if body is not None else b"")
        connection.putheader("Content-Length", str(len(data)))
        connection.endheaders(data)
        answer = connection.getresponse()
        return answer, answer.read()

    def post(self, path, body, **headers):
        sent = {"Origin": self.origin, "Content_Type": "application/json", **headers}
        return self.ask("POST", path, body, **sent)


class Serving(Case):
    def test_it_listens_on_loopback_only_and_offers_no_other_address(self):
        self.assertEqual(self.server.server_address[0], "127.0.0.1")
        self.assertEqual(pm_bridge.HOST, "127.0.0.1")
        self.assertNotIn("--host", SCRIPT.read_text(encoding="utf-8"))

    def test_the_page_comes_with_its_policy(self):
        answer, body = self.ask("GET", "/")
        self.assertEqual(answer.status, 200)
        self.assertIn(b"Project window", body)
        self.assertIn("frame-ancestors 'none'", answer.getheader("Content-Security-Policy"))

    def test_health_names_the_bridge(self):
        answer, body = self.ask("GET", "/api/health")
        self.assertEqual(answer.status, 200)
        self.assertEqual(json.loads(body)["name"], "pm-bridge")
        self.assertTrue(pm_bridge.is_bridge(self.server.port))

    def test_a_second_start_finds_the_first(self):
        with mock.patch("builtins.print") as said:
            self.assertEqual(pm_bridge.main(["--port", str(self.server.port)]), 0)
        self.assertIn("already runs", said.call_args[0][0])

    def test_a_port_held_by_another_program_is_said(self):
        other = socket.create_server(("127.0.0.1", 0))
        self.addCleanup(other.close)
        with mock.patch("builtins.print") as said:
            self.assertEqual(pm_bridge.main(["--port", str(other.getsockname()[1])]), 1)
        self.assertIn("another program", said.call_args[0][0])


class Refusals(Case):
    def test_a_foreign_host_is_refused_everywhere(self):
        for host in ("evil.example", f"evil.example:{self.server.port}", "127.0.0.1:1"):
            for path in ("/", "/api/projects", f"/api/state?project={self.id}"):
                self.assertEqual(self.ask("GET", path, host=host)[0].status, 403, (host, path))
            with mock.patch.object(pm_bridge, "run") as ran:
                answer, _ = self.post("/api/map/start", {"project": self.id}, host=host)
            self.assertEqual(answer.status, 403)
            ran.assert_not_called()

    def test_a_post_needs_this_page_as_its_origin(self):
        for origin in ("", "http://evil.example", "http://127.0.0.1:1", "null"):
            with mock.patch.object(pm_bridge, "run") as ran:
                answer, _ = self.post("/api/map/stop", {"project": self.id}, Origin=origin)
            self.assertEqual(answer.status, 403, origin)
            ran.assert_not_called()

    def test_localhost_is_this_page_too(self):
        origin = f"http://localhost:{self.server.port}"
        with mock.patch.object(pm_bridge, "run", return_value=(0, "ok", "")) as ran:
            answer, _ = self.post(
                "/api/map/stop", {"project": self.id}, Origin=origin, host=f"localhost:{self.server.port}"
            )
        self.assertEqual(answer.status, 200)
        ran.assert_called_once()

    def test_a_post_must_be_json(self):
        with mock.patch.object(pm_bridge, "run") as ran:
            answer, _ = self.post("/api/map/start", {"project": self.id}, Content_Type="text/plain")
        self.assertEqual(answer.status, 415)
        ran.assert_not_called()

    def test_an_unknown_project_starts_nothing(self):
        for body in ({"project": "abcdef"}, {"project": str(self.project)}, {}, b"[1]", b"{broken", b"x" * 5000):
            with mock.patch.object(pm_bridge, "run") as ran:
                answer, _ = self.post("/api/map/start", body)
            self.assertEqual(answer.status, 404, body)
            ran.assert_not_called()
        self.assertEqual(self.ask("GET", "/api/state?project=abcdef")[0].status, 404)

    def test_only_the_map_can_be_started(self):
        for path in ("/api/board/start", "/api/agent/start", "/api/map/restart"):
            with mock.patch.object(pm_bridge, "run") as ran:
                self.assertEqual(self.post(path, {"project": self.id})[0].status, 404)
            ran.assert_not_called()


class Maps(Case):
    def test_start_and_stop_run_pm_open_for_that_folder_without_a_browser(self):
        tool = str(TOOLS / "pm_open.py")
        for path, words in (("/api/map/start", ["map"]), ("/api/map/stop", ["stop", "map"])):
            with mock.patch.object(pm_bridge, "run", return_value=(0, "said", "")) as ran:
                answer, body = self.post(path, {"project": self.id})
            self.assertEqual(answer.status, 200)
            self.assertEqual(ran.call_args[0][0][1:], [tool, *words, "--root", self.key, "--no-browser"])
            self.assertEqual(json.loads(body)["message"], "said")
            self.assertTrue(json.loads(body)["ok"])

    def test_a_failed_start_says_so(self):
        with mock.patch.object(pm_bridge, "run", return_value=(1, "the map stopped", "")):
            _, body = self.post("/api/map/start", {"project": self.id})
        self.assertFalse(json.loads(body)["ok"])
        self.assertEqual(json.loads(body)["message"], "the map stopped")

    def listed(self, ownership):
        with mock.patch.object(pm_open, "ownership", side_effect=ownership):
            return json.loads(self.ask("GET", "/api/projects")[1])["projects"][0]

    def test_a_url_is_given_only_for_this_projects_own_map(self):
        ours = self.listed(lambda f, n, s, port: (pm_open.OURS, None, f"http://127.0.0.1:{port}"))
        self.assertEqual(ours["map"], {"state": "running", "url": "http://localhost:5200/"})
        self.assertEqual(ours["name"], "demo")
        foreign = self.listed(lambda f, n, s, port: (pm_open.ANSWERS, None, f"http://127.0.0.1:{port}"))
        self.assertEqual(foreign["map"], {"state": "foreign"})
        stopped = self.listed(lambda f, n, s, port: (pm_open.STOPPED, None, f"http://127.0.0.1:{port}"))
        self.assertEqual(stopped["map"], {"state": "stopped"})

    def test_a_map_on_the_entrys_own_port_is_found(self):
        def only_5173(folder, name, server, port):
            return (pm_open.OURS, None, "http://[::1]:5173") if port == 5173 else (pm_open.STOPPED, None, "")

        self.assertEqual(self.listed(only_5173)["map"], {"state": "running", "url": "http://[::1]:5173/"})

    def test_a_project_without_a_map_layer_says_none(self):
        (self.project / ".claude" / "launch.json").unlink()
        self.assertEqual(json.loads(self.ask("GET", "/api/projects")[1])["projects"][0]["map"], {"state": "none"})

    def test_a_folder_that_is_gone_is_listed_as_not_found(self):
        moved = self.temp / "moved"
        self.project.rename(moved)
        listed = json.loads(self.ask("GET", "/api/projects")[1])["projects"][0]
        self.assertFalse(listed["found"])
        self.assertEqual(self.ask("GET", f"/api/state?project={self.id}")[0].status, 404)


class State(Case):
    def state(self):
        answer, body = self.ask("GET", f"/api/state?project={self.id}")
        self.assertEqual(answer.status, 200)
        return json.loads(body)

    def test_it_is_the_projects_own_output(self):
        self.assertEqual(self.state()["state"]["project"]["name"], "ç")

    def test_a_failure_is_said_never_guessed(self):
        cases = {
            "boom": "import sys\nprint('boom', file=sys.stderr)\nsys.exit(3)\n",
            "JSON": "print('not json')\n",
            "shape": STATE % 99,
        }
        for word, text in cases.items():
            self.write_state(text)
            answer = self.state()
            self.assertIsNone(answer["state"], word)
            self.assertIn(word, answer["why"])

    def test_an_older_project_without_the_tool_says_upgrade(self):
        (self.project / ".pm" / "tools" / "pm_state.py").unlink()
        self.assertIn("upgrade", self.state()["why"])


class RedLines(Case):
    """D-134 clause 6: tested on what the program does, and on what its source could do."""

    def tree(self):
        return ast.parse(SCRIPT.read_text(encoding="utf-8"))

    def hashes(self):
        found = {}
        for folder in ("backlog", "decisions"):
            for path in sorted((self.project / ".pm" / folder).rglob("*")):
                found[path] = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else "folder"
        return found

    def test_serving_every_address_changes_no_task_or_decision(self):
        before = self.hashes()
        store = pm_open.store_path().read_bytes()
        for path in ("/", "/api/health", "/api/projects", f"/api/state?project={self.id}", "/api/nothing"):
            self.ask("GET", path)
        with mock.patch.object(pm_bridge, "run", return_value=(0, "", "")):
            self.post("/api/map/start", {"project": self.id})
            self.post("/api/map/stop", {"project": self.id})
        self.assertEqual(self.hashes(), before)
        self.assertEqual(pm_open.store_path().read_bytes(), store)

    def test_the_source_has_no_way_to_write_a_file(self):
        banned = {
            "write_text", "write_bytes", "unlink", "rmdir", "mkdir", "rename", "replace_file", "touch",
            "remove", "rmtree", "copy", "move", "open",
        }  # fmt: skip
        for node in ast.walk(self.tree()):
            if isinstance(node, ast.Attribute) and node.attr in banned:
                self.fail(f"line {node.lineno}: .{node.attr}")
            if isinstance(node, ast.Name) and node.id == "open":
                self.fail(f"line {node.lineno}: open")

    def test_it_calls_no_model_and_starts_no_agent(self):
        text = SCRIPT.read_text(encoding="utf-8")
        for word in ("anthropic", "openai", "pm_run", "herdr", "codex", "gemini"):
            self.assertNotIn(word, text.lower().split('"""', 2)[2])
        imported = set()
        for node in ast.walk(self.tree()):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            if isinstance(node, ast.ImportFrom):
                imported.add((node.module or "").split(".")[0])
        known = {
            "argparse",
            "concurrent",
            "http",
            "json",
            "os",
            "socketserver",
            "subprocess",
            "sys",
            "pathlib",
            "urllib",
            "pm_open",
        }
        self.assertEqual(imported, known)

    def test_a_process_starts_in_one_place_with_two_commands_only(self):
        calls = []
        for node in ast.walk(self.tree()):
            if isinstance(node, ast.Attribute) and getattr(node.value, "id", "") == "subprocess":
                if node.attr in ("run", "Popen", "call", "check_call", "check_output"):
                    calls.append(node.attr)
            if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "run":
                self.assertIn(node.args[0].func.id, ("map_command", "state_command"))
        self.assertEqual(calls, ["run"])
        for action in ("start", "stop"):
            self.assertEqual(Path(pm_bridge.map_command("x", action)[1]).name, "pm_open.py")
        self.assertEqual(Path(pm_bridge.state_command("x")[-1]).name, "pm_state.py")

    def test_the_map_is_the_only_thing_it_can_start(self):
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertEqual(text.count('"/api/map/start"'), 1)
        self.assertNotIn("backlog browser", text)


if __name__ == "__main__":
    unittest.main()
