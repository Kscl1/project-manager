"""Scenario tests for .pm/swarm/pm_run.py with a fake Herdr (no model, no terminal, no Herdr server).

The fake Herdr keeps its state in a JSON file and reads each worker's behaviour from the job's `model` field:
  ok        writes a finished artifact on the first prompt, then settles
  nothing   writes nothing and settles
  lazy      writes an unfinished skeleton first, finishes only after the resume nudge
  ask       shows a question (Herdr state `blocked`) forever
  hang      keeps working forever
  vanish    the agent disappears mid-turn without writing anything
  crash     writes an unfinished skeleton, then the agent disappears
  nostart   `agent start` fails
  lost      loses the first brief without working; the resent brief finishes
"""

import contextlib
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
PM_RUN = HERE / "pm_run.py"
_PM_RUN_SPEC = importlib.util.spec_from_file_location("pm_run", PM_RUN)
pm_run = importlib.util.module_from_spec(_PM_RUN_SPEC)
_PM_RUN_SPEC.loader.exec_module(pm_run)

FAKE_HERDR = r"""
import json, os, re, sys, time
from pathlib import Path

STATE = Path(os.environ["FAKE_HERDR_STATE"])
REPO = Path(os.environ["PM_RUN_REPO"])
state = json.loads(STATE.read_text()) if STATE.exists() else {"n": 0, "workspaces": [], "agents": {}, "gone": {},
                                                                "closed": []}
args = sys.argv[1:]

def opt(name):
    return args[args.index(name) + 1]

def reply(result):
    STATE.write_text(json.dumps(state))
    print(json.dumps({"id": "1", "result": result}))
    sys.exit(0)

def fail(code, message):
    STATE.write_text(json.dumps(state))
    sys.stderr.write(json.dumps({"id": "1", "error": {"code": code, "message": message}}))
    sys.exit(1)

def finished():
    return "word " * 60 + "\n<!-- done -->\n"

def status(agent):
    if not agent["prompts"] and agent.get("prompt_rejected"):
        return "idle"
    if not agent["prompts"] and agent.get("startup_states"):
        states = agent["startup_states"]
        return states.pop(0) if len(states) > 1 else states[0]
    if not agent["prompts"] or agent["behaviour"] == "lost" and len(agent["prompts"]) == 1:
        return "idle"
    if agent["behaviour"] == "ask":
        return "blocked"
    if agent["behaviour"] == "hang":
        return "working"
    return "working" if time.time() - agent["prompted"] < 0.5 else "done"

state["n"] += 1
n = state["n"]
cmd = args[:2]
state.setdefault("calls", []).append(args)
if os.environ.get("FAKE_WORKSPACE_ERROR") == " ".join(cmd):
    fail("server_not_running", "connection refused")
if cmd == ["workspace", "list"]:
    reply({"type": "workspace_list", "workspaces": state["workspaces"]})
if cmd == ["workspace", "create"]:
    ws = {"workspace_id": f"w{n}", "label": opt("--label"), "panes": [f"w{n}:p1"]}
    state["workspaces"].append(ws)
    reply({"type": "workspace_created", "workspace": ws, "tab": {"tab_id": f"w{n}:t1"},
           "root_pane": {"pane_id": f"w{n}:p1"}})
if cmd == ["tab", "create"]:
    ws = next(w for w in state["workspaces"] if w["workspace_id"] == opt("--workspace"))
    ws["panes"].append(f"{ws['workspace_id']}:p{n}")
    reply({"type": "tab_created", "tab": {"tab_id": f"{ws['workspace_id']}:t{n}"}, "root_pane": {"pane_id": ws["panes"][-1]}})
if cmd == ["agent", "start"]:
    name, behaviour = args[2], opt("--model")
    if os.environ.get("FAKE_TRUST"):
        state.setdefault("pane_screens", {})[opt("--pane")] = "Do you trust the contents of this project?"
        if os.environ["FAKE_TRUST"] == "read_error":
            state["pane_screens"][opt("--pane")] = {"error": "read failed"}
        fail("agent_blocked", "agent blocked during startup")
    if behaviour == "nostart":
        fail("agent_not_ready", "pi did not become ready")
    if os.environ.get("FAKE_TRUST_AFTER_START"):
        state.setdefault("pane_screens", {})[opt("--pane")] = "Do you trust the contents of this project?"
    state["agents"][name] = {"pane": opt("--pane"), "behaviour": behaviour, "argv": args, "prompts": [], "prompted": 0,
                             "startup_states": json.loads(os.environ.get("FAKE_START_STATES", "[]"))}
    reply({"type": "agent_started", "agent": {"name": name, "agent_status": "idle"}})
if cmd == ["agent", "prompt"]:
    name, text = args[2], args[3]
    agent = state["agents"].get(name)
    if not agent:
        fail("agent_not_found", name)
    if os.environ.get("FAKE_PROMPT_ERROR") and not agent.get("prompt_rejected"):
        agent["prompt_rejected"] = True
        fail("prompt_failed", "agent did not accept the prompt")
    agent["prompts"].append(text)
    agent["prompted"] = time.time()
    found = re.search(r"output file is (.+?)\. Create", text)
    if found:
        agent["out"] = found.group(1)
    out = REPO / agent["out"]
    out.parent.mkdir(parents=True, exist_ok=True)
    if os.environ.get("FAKE_PI_STOP"):
        sessions = Path(os.environ["PM_RUN_PI_SESSIONS"]) / ("--" + re.sub(r"[/\\:]", "-", str(REPO).lstrip("/\\")) + "--")
        sessions.mkdir(parents=True, exist_ok=True)
        entries = [
            {"type": "session", "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + ".999Z", "cwd": str(REPO)},
            {"type": "session_info", "name": name},
            {"type": "message", "message": {"role": "assistant", "stopReason": "stop"}},
            {"type": "message", "message": {"role": "assistant", "stopReason": os.environ["FAKE_PI_STOP"],
                                             "errorMessage": "provider request timed out"}},
            {"type": "message", "message": {"role": "toolResult", "content": "not an assistant"}},
        ]
        (sessions / (name + ".jsonl")).write_text("\n".join(json.dumps(e) for e in entries) + '\n{"partial":', encoding="utf-8")
    if os.environ.get("FAKE_PI_USAGE"):
        # Two assistant messages with the same usage: one from an hour before this attempt, one from it. Only the
        # second counts, so a doubled sum shows up at once.
        sessions = Path(os.environ["PM_RUN_PI_SESSIONS"]) / ("--" + re.sub(r"[/\\:]", "-", str(REPO).lstrip("/\\")) + "--")
        sessions.mkdir(parents=True, exist_ok=True)
        now = time.time()
        def stamp(when):
            return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(when)) + ".%03dZ" % (int(when * 1000) % 1000)
        entries = [
            {"type": "session", "timestamp": stamp(now), "cwd": str(REPO)},
            {"type": "session_info", "name": name},
            {"type": "message", "timestamp": stamp(now - 3600),
             "message": {"role": "assistant", "stopReason": "stop", "usage": json.loads(os.environ["FAKE_PI_USAGE"])}},
            {"type": "message", "timestamp": stamp(now),
             "message": {"role": "assistant", "stopReason": "stop", "usage": json.loads(os.environ["FAKE_PI_USAGE"])}},
        ]
        (sessions / (name + ".jsonl")).write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")
    if agent["behaviour"] != "lost" or len(agent["prompts"]) > 1:
        agent["completion_seq"] = agent.get("completion_seq", 0) + 1
    if agent["behaviour"] == "ok" or agent["behaviour"] == "lost" and len(agent["prompts"]) > 1:
        out.write_text(finished())
    elif agent["behaviour"] == "lazy":
        out.write_text(finished() if len(agent["prompts"]) > 1 else "skeleton\n")
    elif agent["behaviour"] == "vanish":
        state["gone"][name] = state["agents"].pop(name)
    elif agent["behaviour"] == "crash":
        out.write_text("skeleton\n")
        state["gone"][name] = state["agents"].pop(name)
    reply({"type": "agent_prompted"})
if cmd == ["agent", "read"]:
    reads = state.get("reads", ["working"])
    screen = reads.pop(0) if len(reads) > 1 else reads[0]
    if isinstance(screen, dict):
        fail("read_failed", screen["error"])
    STATE.write_text(json.dumps(state))
    sys.stdout.write(screen)
    sys.exit(0)
if cmd == ["agent", "get"]:
    if os.environ.get("FAKE_GET_ERROR"):
        state["get_errors"] = state.get("get_errors", 0) + 1
        if state["get_errors"] <= int(os.environ["FAKE_GET_ERROR"]):
            fail("server_timeout", "query timed out")
    agent = state["agents"].get(args[2])
    if not agent:
        fail("agent_not_found", args[2])
    info = {"name": args[2], "agent_status": status(agent)}
    if not os.environ.get("FAKE_NO_SEQ"):
        info["completion_seq"] = agent.get("completion_seq", 0)
    reply({"type": "agent_info", "agent": info})
if cmd == ["pane", "read"]:
    screen = state.get("pane_screens", {}).get(args[2], "")
    if isinstance(screen, dict):
        fail("read_failed", screen["error"])
    STATE.write_text(json.dumps(state))
    sys.stdout.write(screen)
    sys.exit(0)
if cmd == ["pane", "close"]:
    if os.environ.get("FAKE_STOP_ERROR"):
        fail("server_timeout", "close timed out")
    for name in [k for k, a in state["agents"].items() if a["pane"] == args[2]]:
        state["gone"][name] = state["agents"].pop(name)
    for ws in state["workspaces"]:
        if args[2] in ws["panes"]:
            ws["panes"].remove(args[2])
    state["workspaces"] = [w for w in state["workspaces"] if w["panes"]]  # Herdr closes a workspace with its last pane
    reply({"type": "ok"})
if cmd == ["pane", "run"]:
    state.setdefault("ran", []).append([args[2], args[3]])
    reply({"type": "ok"})
if cmd == ["workspace", "close"]:
    state["workspaces"] = [w for w in state["workspaces"] if w["workspace_id"] != args[2]]
    state["closed"].append(args[2])
    reply({"type": "ok"})
sys.stderr.write("fake herdr: unknown command " + " ".join(args))
sys.exit(2)
"""


def end_process(proc):
    """Clean up a check process a test started; killing the shell is enough for the fake checks here."""
    if proc.poll() is None:
        proc.kill()
        proc.wait()


def process_runs(pid):
    """True while a process with this id runs (tasklist on Windows, where os.kill would end it)."""
    if os.name == "nt":
        listed = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True).stdout
        return f" {pid} " in f" {listed} "
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def repo_for_in_process_runs(test, repo):
    """A Run made inside the test process writes its failure log under PM_RUN_REPO, never into the checkout."""
    patcher = patch.dict(os.environ, {"PM_RUN_REPO": str(repo)})
    patcher.start()
    test.addCleanup(patcher.stop)


class PmRunFixture:
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="pm_run_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.run_dir = self.tmp / "run"
        self.run_dir.mkdir()
        (self.tmp / "brief.md").write_text("A worker brief.\n", encoding="utf-8")
        repo_for_in_process_runs(self, self.tmp)
        fake = self.tmp / "fake_herdr.py"
        fake.write_text(FAKE_HERDR, encoding="utf-8")
        self.fake_state = self.tmp / "herdr.json"
        (self.run_dir / "caps.json").write_text('{"default": 4}', encoding="utf-8")
        self.env = {
            **os.environ,
            "PM_RUN_HERDR": json.dumps([sys.executable, str(fake)]),
            "PM_RUN_REPO": str(self.tmp),
            "FAKE_HERDR_STATE": str(self.fake_state),
            "PYTHONIOENCODING": "utf-8",
            "PM_RUN_TICK": "0.2",
            "PM_RUN_SETTLE_S": "1",
            "PM_RUN_SETUP_S": "0",
            "PM_RUN_HARD_S": "60",
            "PM_RUN_MAX_TRIES": "2",
            "PM_RUN_MAX_NUDGES": "2",
            "PM_RUN_QUIET_S": "0",
            "PM_RUN_OVERTIME_S": "1",
            "PM_RUN_HERDR_TIMEOUT": "30",
            "PM_RUN_VERIFY_S": "600",
            "PM_RUN_PI_SESSIONS": str(self.tmp / "sessions"),
        }

    @property
    def a1(self):
        """The Herdr agent name of job a's first attempt in this test's run."""
        return pm_run.agent_name("a", 1, self.run_dir.resolve())

    def jobs(self, *jobs):
        (self.run_dir / "jobs.json").write_text(json.dumps(list(jobs)), encoding="utf-8")

    def job(self, jid, behaviour, **extra):
        job = {
            "id": jid,
            "model": behaviour,
            "out": f"out/{jid}.md",
            "briefs": ["brief.md"],
            "min_words": 50,
            "verify": f'"{sys.executable}" -c "import sys; sys.exit(0)"',
        }
        job.update(extra)
        # A real run's report folder already exists: preflight never starts a worker into a folder that is not there.
        (self.tmp / job["out"]).parent.mkdir(parents=True, exist_ok=True)
        return job

    def run_pm(self, *args, timeout=60):
        result = subprocess.run(
            [sys.executable, str(PM_RUN), str(self.run_dir), *args],
            env=self.env,
            timeout=timeout,
            capture_output=True,
            text=True,
        )
        return result

    def start_pm(self):
        """Start a loop in the background, for scenarios that change the run while it is live."""
        proc = subprocess.Popen(
            [sys.executable, str(PM_RUN), str(self.run_dir)],
            env=self.env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.addCleanup(proc.kill)
        return proc

    def wait_for_log(self, text):
        log, deadline = self.run_dir / "pm_run.log", time.time() + 30
        while not (log.exists() and text in log.read_text(encoding="utf-8")):
            self.assertLess(time.time(), deadline, f"no {text} in pm_run.log")
            time.sleep(0.1)

    def wait_for_state(self, jid, expected):
        """Wait until the saved receipt of `jid` says `expected`: a log line is written a moment before the save."""
        deadline = time.time() + 30
        while True:
            try:
                if self.receipts().get(jid, {}).get("state") == expected:
                    return
            except (OSError, ValueError):
                pass
            self.assertLess(time.time(), deadline, f"{jid} never reached {expected}")
            time.sleep(0.05)

    def receipts(self):
        return json.loads((self.run_dir / "receipts.json").read_text(encoding="utf-8"))

    def herdr_state(self):
        return json.loads(self.fake_state.read_text(encoding="utf-8"))


class PmRunTest(PmRunFixture, unittest.TestCase):
    def test_finished_artifact_and_passing_check_is_verified(self):
        self.jobs(self.job("a", "ok", thinking="medium"))
        self.run_pm()
        state = self.receipts()
        self.assertEqual(state["a"]["state"], "verified")
        attempt = state["a"]["attempts"][-1]
        self.assertEqual(attempt["verify_rc"], 0)
        self.assertTrue(attempt["stopped_confirmed"])
        self.assertIn("sha256", attempt["artifact"])
        self.assertIn("seen_hash", attempt)
        self.assertFalse(attempt["stall"])
        self.assertFalse(attempt["loop"])
        herdr = self.herdr_state()
        self.assertEqual(herdr["agents"], {}, "the worker's pane must be closed")
        started = herdr["gone"][self.a1]
        self.assertIn("--kind", started["argv"])
        self.assertEqual(started["argv"][started["argv"].index("--thinking") + 1], "medium")
        self.assertIn("brief.md", started["prompts"][0])
        self.assertEqual(herdr["workspaces"], [], "the run's workspace is closed at the end")

    def test_claude_harness_runs_the_setup_line_then_starts_claude_code(self):
        self.jobs(self.job("a", "ok", harness="claude", setup="$env:X=1", args=["--permission-mode", "acceptEdits"]))
        self.run_pm()
        self.assertEqual(self.receipts()["a"]["state"], "verified")
        herdr = self.herdr_state()
        argv = herdr["gone"][self.a1]["argv"]
        self.assertEqual(argv[argv.index("--kind") + 1], "claude")
        settings = argv[argv.index("--settings") + 1]
        self.assertEqual(
            argv[argv.index("--") + 1 :],
            ["--model", "ok", "--disallowedTools", "Agent,Workflow", "--settings", settings]
            + ["--permission-mode", "acceptEdits"],
        )
        # The project's MCP servers start without the approval dialog that would swallow the brief, and Claude Code's
        # bundled skills are off. No allow rules: Claude Code's own read-only check is stricter than a prefix.
        self.assertEqual(
            json.loads(Path(settings).read_text(encoding="utf-8")),
            {"enableAllProjectMcpServers": True, "disableBundledSkills": True},
        )
        self.assertEqual(herdr["ran"], [[herdr["gone"][self.a1]["pane"], "$env:X=1"]])

    def test_pi_is_the_default_harness_and_runs_no_setup(self):
        self.jobs(self.job("a", "ok"))
        self.run_pm()
        herdr = self.herdr_state()
        argv = herdr["gone"][self.a1]["argv"]
        self.assertEqual(argv[argv.index("--kind") + 1], "pi")
        self.assertEqual(argv[argv.index("--exclude-tools") + 1], "Agent,SubagentWorkflow")
        self.assertEqual(self.receipts()["a"]["attempts"][0]["model"], "ok")
        self.assertNotIn("ran", herdr)
        self.assertIn("Write only that file. ", herdr["gone"][self.a1]["prompts"][0])

    def seed_reads(self, *screens):
        empty = {"n": 0, "workspaces": [], "agents": {}, "gone": {}, "closed": []}
        self.fake_state.write_text(json.dumps({**empty, "reads": list(screens)}), encoding="utf-8")

    def test_agy_harness_waits_for_its_screen_then_gets_the_brief(self):
        # Herdr reports agy ready before agy draws: the first read shows only the launch line.
        self.seed_reads("PS> agy --model ok", "> Type a message")
        self.jobs(self.job("a", "ok", harness="agy", thinking="high", args=["--mode", "accept-edits"]))
        self.run_pm()
        self.assertEqual(self.receipts()["a"]["state"], "verified")
        started = self.herdr_state()["gone"][self.a1]
        argv = started["argv"]
        self.assertEqual(argv[argv.index("--kind") + 1], "agy")
        self.assertEqual(argv[argv.index("--") + 1 :], ["--model", "ok", "--mode", "accept-edits"])
        self.assertIn("brief.md", started["prompts"][0])

    def test_agy_first_run_screen_is_handed_over_without_the_brief(self):
        self.seed_reads("PS> agy --model ok", "Welcome to Antigravity CLI!\n\nChoose your color scheme:\n  > terminal")
        self.jobs(self.job("a", "ok", harness="agy"), self.job("b", "ok", after=["a"]))
        result = self.run_pm()
        self.assertEqual(result.returncode, 0, result.stderr)
        state = self.receipts()
        self.assertEqual(state["a"]["state"], "handed-over")
        self.assertEqual(len(state["a"]["attempts"]), 1, "the same screen would stop every retry")
        self.assertIn("first-run screen", state["a"]["attempts"][0]["why"])
        self.assertEqual(state["b"]["state"], "blocked")
        herdr = self.herdr_state()
        self.assertEqual(herdr["agents"][self.a1]["prompts"], [], "the brief must not land in the menu")
        self.assertTrue(herdr["workspaces"], "the run's workspace stays open with the handed-over tab")

    def test_missing_brief_is_checked_again_before_a_retry(self):
        out = self.tmp / "out" / "a.md"
        out.parent.mkdir()
        out.write_text("previous attempt's output", encoding="utf-8")
        (self.tmp / "brief.md").unlink()
        run, job = pm_run.Run(self.run_dir), self.job("a", "ok")
        state = {"a": {"state": "pending", "attempts": [{"started": 0}]}}
        with patch.object(run, "launch") as launch:
            run.tick([job], state, {})
        launch.assert_not_called()
        self.assertEqual(state["a"]["state"], "failed")
        self.assertEqual(len(state["a"]["attempts"]), 1)
        self.assertEqual(out.read_text(encoding="utf-8"), "previous attempt's output")
        self.assertFalse(out.with_name("a.attempt1.md").exists())

    def test_agy_folder_trust_screen_is_handed_over_like_the_other_first_run_screens(self):
        # Herdr showed the trust question as an idle agy, so pm_run used to send the brief into it; after five retries
        # the same screen was still there. Only the owner can answer it, once per folder.
        self.seed_reads(
            "PS> agy --model ok", "Do you trust the contents of this project?\n  > Yes, I trust this folder"
        )
        self.jobs(self.job("a", "ok", harness="agy"), self.job("b", "ok", after=["a"]))
        result = self.run_pm()
        self.assertEqual(result.returncode, 0, result.stderr)
        state = self.receipts()
        self.assertEqual(state["a"]["state"], "handed-over")
        self.assertEqual(len(state["a"]["attempts"]), 1, "a retry would show the same screen again")
        self.assertIn("first-run screen", state["a"]["attempts"][0]["why"])
        self.assertIn("Do you trust the contents of this project?", state["a"]["attempts"][0]["why"])
        self.assertEqual(state["b"]["state"], "blocked")
        herdr = self.herdr_state()
        self.assertEqual(herdr["agents"][self.a1]["prompts"], [], "the brief must not land in the trust question")
        self.assertTrue(herdr["workspaces"], "the run's workspace stays open with the handed-over tab")
        self.assertNotIn("RETRY a", (self.run_dir / "pm_run.log").read_text(encoding="utf-8"))

    def test_first_prompt_waits_for_ready_agent_state(self):
        self.env["FAKE_START_STATES"] = json.dumps(["starting", "working", "ready"])
        self.jobs(self.job("a", "ok"))
        result = self.run_pm()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.receipts()["a"]["state"], "verified")
        calls = self.herdr_state()["calls"]
        first_prompt = next(i for i, c in enumerate(calls) if c[:2] == ["agent", "prompt"])
        self.assertEqual(sum(c[:2] == ["agent", "get"] for c in calls[:first_prompt]), 3)
        self.assertEqual(self.receipts()["a"]["attempts"][0]["seq0"], 0)

    def test_no_agent_state_uses_the_fixed_wait(self):
        run = pm_run.Run(self.run_dir)
        attempt = {"name": "worker"}
        with patch.object(run, "status_of", return_value="unknown"), patch.object(
            pm_run.time, "sleep"
        ) as sleep, patch.object(pm_run, "SETUP_S", 2):
            self.assertTrue(run.wait_ready(attempt))
        sleep.assert_called_once_with(2)

    def test_a_query_timeout_at_the_deadline_does_not_fall_back_to_prompting(self):
        run = pm_run.Run(self.run_dir)
        attempt = {"name": "worker"}
        with patch.object(run, "status_of", return_value="unknown"), patch.object(pm_run, "READY_S", 1), patch.object(
            pm_run.time, "monotonic", side_effect=[0, 0, 1]
        ):
            self.assertFalse(run.wait_ready(attempt))
        self.assertIn("not ready", attempt["launch_error"])

    def test_not_ready_at_the_ceiling_does_not_receive_a_brief(self):
        self.env.update(FAKE_START_STATES=json.dumps(["working"]), PM_RUN_READY_S="0.2", PM_RUN_MAX_TRIES="1")
        self.jobs(self.job("a", "ok"))
        result = self.run_pm()
        self.assertEqual(result.returncode, 0, result.stderr)
        state = self.receipts()["a"]
        self.assertEqual(state["state"], "failed")
        self.assertIn("not ready", state["attempts"][0]["why"])
        calls = self.herdr_state()["calls"]
        self.assertFalse(any(c[:2] == ["agent", "prompt"] for c in calls))

    def test_agy_trust_keeps_previous_attempt_output_once(self):
        out = self.tmp / "out" / "a.md"
        out.parent.mkdir()
        out.write_text("first attempt output", encoding="utf-8")
        run, job = pm_run.Run(self.run_dir), self.job("a", "ok", harness="agy")
        state = {"a": {"state": "pending", "attempts": [{"started": 0}]}}
        with patch.dict(os.environ, {**self.env, "FAKE_TRUST": "1"}), patch.object(
            pm_run, "HERDR_CMD", json.loads(self.env["PM_RUN_HERDR"])
        ), patch.object(pm_run.time, "sleep"):
            run.tick([job], state, {})
            pane = state["a"]["trust_wait"]["pane"]
            self.assertEqual((out.parent / "a.attempt1.md").read_text(encoding="utf-8"), "first attempt output")
            herdr = self.herdr_state()
            herdr["pane_screens"][pane] = "Trust accepted"
            self.fake_state.write_text(json.dumps(herdr), encoding="utf-8")
            os.environ.pop("FAKE_TRUST")
            with patch.object(run, "first_run", return_value=False):
                run.tick([job], state, {})
        self.assertEqual(state["a"]["state"], "started")
        self.assertEqual(len(state["a"]["attempts"]), 2)
        self.assertFalse((out.parent / "a.attempt1-2.md").exists())

    def test_agy_trust_does_not_count_old_output_as_a_new_attempt_each_tick(self):
        out = self.tmp / "out" / "a.md"
        out.parent.mkdir()
        out.write_text("earlier report", encoding="utf-8")
        run, job, state = pm_run.Run(self.run_dir), self.job("a", "ok", harness="agy"), {}
        with patch.dict(os.environ, {**self.env, "FAKE_TRUST": "1"}), patch.object(
            pm_run, "HERDR_CMD", json.loads(self.env["PM_RUN_HERDR"])
        ), patch.object(pm_run.time, "sleep"):
            run.tick([job], state, {})
            pane = state["a"]["trust_wait"]["pane"]
            herdr = self.herdr_state()
            herdr["pane_screens"][pane] = "Trust accepted"
            self.fake_state.write_text(json.dumps(herdr), encoding="utf-8")
            os.environ.pop("FAKE_TRUST")
            with patch.object(run, "first_run", return_value=False):
                run.tick([job], state, {})
        self.assertEqual(state["a"]["state"], "started")
        self.assertEqual((out.parent / "a.kept.md").read_text(encoding="utf-8"), "earlier report")
        self.assertFalse((out.parent / "a.kept-2.md").exists())

    def test_agy_folder_trust_waits_without_tries_then_starts_after_answer(self):
        run, job, state = pm_run.Run(self.run_dir), self.job("a", "ok", harness="agy"), {}
        env = {**self.env, "FAKE_TRUST": "1"}
        with patch.dict(os.environ, env), patch.object(
            pm_run, "HERDR_CMD", json.loads(self.env["PM_RUN_HERDR"])
        ), patch.object(pm_run.time, "sleep"):
            run.tick([job], state, {})
            self.assertEqual(state["a"]["state"], "pending")
            self.assertEqual(state["a"]["attempts"], [], "a trust screen must not use an attempt")
            pane = state["a"]["trust_wait"]["pane"]
            self.assertIn(f"agy asks to trust {self.tmp}", run.log_path.read_text(encoding="utf-8"))
            with patch("builtins.print") as printed:
                run.status([job], state)
            self.assertIn(f"waiting for blocked agy pane {pane}", str(printed.call_args_list))
            run.save(state)
            state = run.load("receipts.json", {})  # restarting the scheduler must keep the same wait
            for _ in range(3):
                run.tick([job], state, {})
            self.assertEqual(len([c for c in self.herdr_state()["calls"] if c[:2] == ["agent", "start"]]), 1)
            self.assertEqual(run.log_path.read_text(encoding="utf-8").count("agy asks to trust"), 1)
            herdr = self.herdr_state()
            herdr["pane_screens"][pane] = {"error": "read failed"}
            self.fake_state.write_text(json.dumps(herdr), encoding="utf-8")
            run.tick([job], state, {})
            self.assertEqual(state["a"]["attempts"], [], "a failed pane read is not an answer")
            herdr = self.herdr_state()
            herdr["pane_screens"][pane] = "Trust accepted. Type a message."
            self.fake_state.write_text(json.dumps(herdr), encoding="utf-8")
            os.environ.pop("FAKE_TRUST")
            with patch.object(run, "first_run", return_value=False):
                run.tick([job], state, {})
            self.assertEqual(state["a"]["state"], "started")
            self.assertEqual(len(state["a"]["attempts"]), 1)
            self.assertEqual(state["a"]["attempts"][0]["name"], self.a1)
            calls = self.herdr_state()["calls"]
            self.assertIn(["pane", "close", pane], calls)
            self.assertEqual(sum(c[:2] == ["agent", "prompt"] for c in calls), 1)
            self.assertNotIn("RETRY a", run.log_path.read_text(encoding="utf-8"))

    def test_deleting_a_job_waiting_on_folder_trust_leaves_and_names_its_pane(self):
        run, job, state = pm_run.Run(self.run_dir), self.job("a", "ok", harness="agy"), {}
        with patch.dict(os.environ, {**self.env, "FAKE_TRUST": "1"}), patch.object(
            pm_run, "HERDR_CMD", json.loads(self.env["PM_RUN_HERDR"])
        ), patch.object(pm_run.time, "sleep"):
            run.tick([job], state, {})
            pane = state["a"]["trust_wait"]["pane"]
            run.tick([], state, {})
        self.assertEqual(state["a"]["state"], "removed")
        self.assertIn(f"Herdr pane {pane}", run.log_path.read_text(encoding="utf-8"))
        self.assertNotIn(["pane", "close", pane], self.herdr_state()["calls"])

    def test_stop_closes_an_agy_trust_pane_without_counting_a_try(self):
        run, job, state = pm_run.Run(self.run_dir), self.job("a", "ok", harness="agy"), {}
        with patch.dict(os.environ, {**self.env, "FAKE_TRUST": "1"}), patch.object(
            pm_run, "HERDR_CMD", json.loads(self.env["PM_RUN_HERDR"])
        ), patch.object(pm_run.time, "sleep"):
            run.tick([job], state, {})
            pane = state["a"]["trust_wait"]["pane"]
            run.tick([{**job, "stop": True}], state, {})
        self.assertEqual(state["a"]["state"], "stopped")
        self.assertEqual(state["a"]["attempts"], [])
        self.assertIn(["pane", "close", pane], self.herdr_state()["calls"])

    def test_agy_trust_screen_after_successful_start_also_waits_without_a_try(self):
        run, job, state = pm_run.Run(self.run_dir), self.job("a", "ok", harness="agy"), {}
        env = {**self.env, "FAKE_TRUST_AFTER_START": "1", "FAKE_START_STATES": '["blocked"]'}
        with patch.dict(os.environ, env), patch.object(
            pm_run, "HERDR_CMD", json.loads(self.env["PM_RUN_HERDR"])
        ), patch.object(run, "first_run", return_value=False), patch.object(pm_run.time, "sleep"):
            run.tick([job], state, {})
            run.tick([job], state, {})
        self.assertEqual(state["a"]["state"], "pending")
        self.assertEqual(state["a"]["attempts"], [])
        self.assertIn("agy asks to trust", run.log_path.read_text(encoding="utf-8"))
        self.assertFalse(any(c[:2] == ["agent", "prompt"] for c in self.herdr_state()["calls"]))

    def test_agy_trust_close_failure_does_not_start_a_second_worker(self):
        run, job, state = pm_run.Run(self.run_dir), self.job("a", "ok", harness="agy"), {}
        with patch.dict(os.environ, {**self.env, "FAKE_TRUST": "1"}), patch.object(
            pm_run, "HERDR_CMD", json.loads(self.env["PM_RUN_HERDR"])
        ), patch.object(pm_run.time, "sleep"):
            run.tick([job], state, {})
            herdr = self.herdr_state()
            herdr["pane_screens"][state["a"]["trust_wait"]["pane"]] = "Trust accepted"
            self.fake_state.write_text(json.dumps(herdr), encoding="utf-8")
            with patch.object(run, "stop", return_value=False):
                run.tick([job], state, {})
        self.assertEqual(state["a"]["state"], "failed")
        self.assertFalse(state["a"]["trust_stopped_confirmed"])
        self.assertEqual(len([c for c in self.herdr_state()["calls"] if c[:2] == ["agent", "start"]]), 1)

    def test_agy_blocked_start_with_unreadable_pane_is_not_retried_blindly(self):
        run, job, state = pm_run.Run(self.run_dir), self.job("a", "ok", harness="agy"), {}
        with patch.dict(os.environ, {**self.env, "FAKE_TRUST": "read_error"}), patch.object(
            pm_run, "HERDR_CMD", json.loads(self.env["PM_RUN_HERDR"])
        ), patch.object(pm_run.time, "sleep"):
            run.tick([job], state, {})
            for _ in range(3):
                run.tick([job], state, {})
        self.assertEqual(state["a"]["state"], "pending")
        self.assertEqual(state["a"]["attempts"], [])
        self.assertEqual(len([c for c in self.herdr_state()["calls"] if c[:2] == ["agent", "start"]]), 1)
        self.assertIn("could not read", run.log_path.read_text(encoding="utf-8"))

    def test_writes_lets_the_worker_write_more_than_its_output(self):
        self.jobs(self.job("a", "ok", writes=["site/", "notes/x.md"]))
        self.run_pm()
        prompt = self.herdr_state()["gone"][self.a1]["prompts"][0]
        self.assertIn("Write only that file and the paths site/, notes/x.md. ", prompt)

    def test_failures_of_every_run_go_to_one_shared_log_one_line_each(self):
        self.jobs(
            self.job("a", "ok", verify=f'"{sys.executable}" -c "import sys; sys.exit(1)"'),
            self.job("b", "ok", verify=None),
        )
        self.run_pm()
        lines = (self.tmp / ".pm" / "local" / "failures.log").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 2, "LAUNCH and the start and done lines are routine")
        for line in lines:
            self.assertRegex(line, r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d run ")
        # a's check runs in the background, so b's line may be written first
        self.assertEqual(sorted(line.split()[3:5] for line in lines), [["ARTIFACT", "b"], ["CHECK-FAILED", "a"]])

    def test_status_tally_counts_shared_failures_in_order_and_ignores_other_words(self):
        failures = self.tmp / ".pm" / "local" / "failures.log"
        failures.parent.mkdir(parents=True)
        failures.write_text(
            "2026-11-01 00:00:00 run-a PROMPT a: sent again\n"
            "2026-11-01 00:00:01 run-b WAITING b: answer PROMPT here\n"
            "2026-11-01 00:00:02 run-b PROMPT b: sent again\n"
            "2026-11-01 00:00:03 run-a RETRY c: later\n"
            "2026-11-01 00:00:04 run-b WAITING c: answer here\n"
            "2026-11-01 00:00:05 run-b LAUNCH d: routine\n"
            "bad line PROMPT d: not a failure-log record\n",
            encoding="utf-8",
        )
        self.jobs(self.job("a", "ok"))
        status = self.run_pm("--status")
        self.assertNotIn("tried again (pm_run on its own, or a --retry)", status.stdout)
        result = self.run_pm("--status", "--tally")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("tried again (pm_run on its own, or a --retry): PROMPT=2, RETRY=1", result.stdout)
        self.assertIn("needed a person or a look: WAITING=2", result.stdout)
        self.assertEqual(result.stdout.count("tried again (pm_run on its own, or a --retry):"), 1)
        self.assertNotIn("LAUNCH=", result.stdout)
        self.assertFalse(self.fake_state.exists())

    def test_status_tally_keeps_the_two_groups_apart_and_orders_each(self):
        failures = self.tmp / ".pm" / "local" / "failures.log"
        failures.parent.mkdir(parents=True)
        failures.write_text(
            "2026-11-01 00:00:00 run QUOTA-WAIT a: waited out a reset\n"
            "2026-11-01 00:00:01 run RESUME a: nudged\n"
            "2026-11-01 00:00:02 run RESUME a: nudged\n"
            "2026-11-01 00:00:03 run BLOCKED b: a dependency failed\n"
            "2026-11-01 00:00:04 run CHECK-FAILED c: the check failed\n"
            "2026-11-01 00:00:05 run CHECK-FAILED c: the check failed\n"
            "2026-11-01 00:00:06 run CHECK-FAILED c: the check failed\n",
            encoding="utf-8",
        )
        result = self.run_pm("--status", "--tally")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("tried again (pm_run on its own, or a --retry): RESUME=2, QUOTA-WAIT=1", result.stdout)
        self.assertIn("needed a person or a look: CHECK-FAILED=3, BLOCKED=1", result.stdout)
        self.assertLess(
            result.stdout.index("tried again (pm_run on its own, or a --retry):"),
            result.stdout.index("needed a person or a look:"),
            "the line a person must read comes second",
        )
        person_line = result.stdout.split("needed a person or a look:", 1)[1].splitlines()[0]
        self.assertNotIn("RESUME=", person_line, "what pm_run fixed itself is not a person's work")
        self.assertNotIn("QUOTA-WAIT=", person_line)

    def test_status_tally_reports_an_unreadable_log_without_stopping(self):
        run = pm_run.Run(self.run_dir)
        with patch.object(Path, "open", side_effect=PermissionError("access denied")), patch(
            "builtins.print"
        ) as printed:
            run.failure_tally()
        self.assertIn("could not read", str(printed.call_args_list))
        self.assertIn("--status --tally", str(printed.call_args_list))

    def test_status_tally_with_no_failure_log_says_none(self):
        result = self.run_pm("--status", "--tally")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("tried again (pm_run on its own, or a --retry): none", result.stdout)
        self.assertIn("needed a person or a look: none", result.stdout)
        self.assertFalse((self.tmp / ".pm" / "local" / "failures.log").exists())

    def test_a_held_failure_log_never_stops_the_logging_loop(self):
        run = pm_run.Run(self.run_dir)
        run.repo = self.tmp
        real = Path.open

        def held(path, *args, **kwargs):
            if path.name == "failures.log":
                raise PermissionError(13, "Permission denied", str(path))
            return real(path, *args, **kwargs)

        with patch.object(Path, "open", held), patch("sys.stdout", io.StringIO()):
            run.log("TICK-ERROR KeyError: 'x'; the loop goes on")  # must not raise
            run.log("RETRY a: worker is gone")
        log = run.log_path.read_text(encoding="utf-8")
        self.assertIn("TICK-ERROR", log)
        self.assertEqual(log.count("could not append"), 1, "warned once")

    def test_failing_check_keeps_the_report_and_never_relaunches(self):
        self.jobs(
            self.job("a", "ok", verify=f'"{sys.executable}" -c "import sys; sys.exit(1)"'),
            self.job("b", "ok", after=["a"]),
        )
        result = self.run_pm()
        self.assertEqual(result.returncode, 0, result.stderr)
        state = self.receipts()
        self.assertEqual(state["a"]["state"], "check-failed")
        self.assertEqual(len(state["a"]["attempts"]), 1, "a finished report must not be paid for twice")
        self.assertEqual(state["a"]["attempts"][0]["why"], "artifact present but check exited 1")
        self.assertIn(pm_run.MARKER, (self.tmp / "out" / "a.md").read_text(encoding="utf-8"))
        self.assertFalse((self.tmp / "out" / "a.attempt1.md").exists())
        self.assertIn("CHECK-FAILED a", result.stdout)
        self.assertIn("no relaunch", result.stdout)
        self.assertNotIn("RETRY a", result.stdout)
        self.assertEqual(state["b"]["state"], "blocked")
        self.assertEqual(self.herdr_state()["agents"], {}, "the worker's pane is still closed")

    def test_missing_brief_fails_before_launch_and_blocks_dependants(self):
        out = self.tmp / "out" / "a.md"
        out.parent.mkdir()
        out.write_text("old output", encoding="utf-8")
        self.jobs(self.job("a", "ok", briefs=["brief.md", "missing.md"]), self.job("b", "ok", after=["a"]))
        result = self.run_pm()
        self.assertEqual(result.returncode, 0, result.stderr)
        state = self.receipts()
        self.assertEqual(state["a"]["state"], "failed")
        self.assertEqual(state["a"]["attempts"], [])
        self.assertIn("brief not found: missing.md", state["a"]["why"])
        self.assertEqual(state["b"]["state"], "blocked")
        self.assertFalse(self.fake_state.exists(), "Herdr must not be called")
        self.assertIn(
            "PREFLIGHT a: brief not found: missing.md; fix jobs.json, then --retry a",
            (self.run_dir / "pm_run.log").read_text(encoding="utf-8"),
        )
        failures = (self.tmp / ".pm" / "local" / "failures.log").read_text(encoding="utf-8")
        self.assertRegex(failures, r"run PREFLIGHT a: brief not found: missing.md")
        self.assertEqual(out.read_text(encoding="utf-8"), "old output")
        self.assertFalse(out.with_name("a.kept.md").exists())
        self.assertIn("brief not found: missing.md", self.run_pm("--status").stdout)

    def test_missing_brief_with_json_escapes_explains_backslashes(self):
        # A JSON writer used single backslashes, so \\r, \\n and \\b became control characters.
        bad_path = json.loads(r'"C:\run\new\brief.md"')
        self.jobs(self.job("a", "ok", briefs=[bad_path]))
        result = self.run_pm()
        self.assertEqual(result.returncode, 0, result.stderr)
        state = self.receipts()["a"]
        self.assertEqual(state["state"], "failed")
        self.assertEqual(state["attempts"], [])
        self.assertIn(r"brief not found: C:\run\new\brief.md", state["why"])
        self.assertIn(r"a backslash in jobs.json was read as an escape: write \\ or /", state["why"])
        self.assertNotRegex(state["why"], r"[\x00-\x1f\x7f-\x9f]")
        self.assertFalse(self.fake_state.exists())

    def test_preflight_does_not_read_a_file_path_out_of_verify(self):
        # Text between quotes is not reliably a file: echo prints it. The path check was dropped for this, and the
        # glitch that started it (a Windows path in a non-raw string) is caught by the control-character check.
        self.jobs(self.job("a", "ok", verify='echo "Z:/this-is-a-literal-not-a-file"'))
        self.run_pm()
        self.assertEqual(self.receipts()["a"]["state"], "verified")

    def test_preflight_finds_a_control_character_in_verify_and_setup(self):
        # The Windows path of the glitch: \r, \n and \v became control characters, so the shell could not find its
        # own script. Plain words, and the character is shown as it would be written in JSON.
        cases = (
            ("verify", 'python -c "import sys\r; sys.exit(0)"'),
            ("setup", "set X=1\v"),
        )
        for key, line in cases:
            with self.subTest(key=key):
                run, job, state = pm_run.Run(self.run_dir), self.job("a", "ok"), {}
                run.repo = self.tmp
                (self.tmp / "out").mkdir(exist_ok=True)
                job[key] = line
                with patch.object(run, "launch") as launch:
                    run.tick([job], state, {})
                launch.assert_not_called()
                self.assertEqual(state["a"]["state"], "failed")
                self.assertIn(f"{key} holds a control character", state["a"]["why"])
                self.assertIn("write \\ or / in jobs.json", state["a"]["why"])
                self.assertNotRegex(state["a"]["why"], r"[\x00-\x1f\x7f-\x9f]")

    def test_preflight_lets_a_tab_through_in_setup(self):
        # A tab separates words in a shell line, so it is not a broken Windows path; the job starts.
        self.jobs(self.job("a", "ok", setup="echo\tready"))
        self.run_pm()
        self.assertEqual(self.receipts()["a"]["state"], "verified")

    def test_preflight_fails_a_command_that_is_not_text(self):
        # A number is not a command line, so the job ends PREFLIGHT before a worker is paid for.
        for key in ("verify", "setup"):
            with self.subTest(key=key):
                run, job, state = pm_run.Run(self.run_dir), self.job("a", "ok"), {}
                run.repo = self.tmp
                job[key] = 17
                with patch.object(run, "launch") as launch:
                    run.tick([job], state, {})
                launch.assert_not_called()
                self.assertEqual(state["a"]["state"], "failed")
                self.assertIn(f"{key} must be one command line (text)", state["a"]["why"])
                self.assertIn(f"PREFLIGHT a: {key} must be one command line (text)", run.log_path.read_text("utf-8"))

    def test_preflight_fails_a_task_field_that_is_not_a_task_id(self):
        # The optional task field names the task a job works for; a number or a blank cannot name one.
        for value in (12, "  "):
            with self.subTest(task=value):
                run, job, state = pm_run.Run(self.run_dir), self.job("a", "ok"), {}
                run.repo = self.tmp
                job["task"] = value
                with patch.object(run, "launch") as launch:
                    run.tick([job], state, {})
                launch.assert_not_called()
                self.assertEqual(state["a"]["state"], "failed")
                self.assertIn("task must be a task ID (text)", state["a"]["why"])

    def test_a_job_with_a_task_field_runs_as_before(self):
        self.jobs(self.job("a", "ok", task="REQ-12"))
        self.run_pm()
        self.assertEqual(self.receipts()["a"]["state"], "verified")

    def test_preflight_requires_the_folder_that_will_hold_the_report(self):
        run, job, state = pm_run.Run(self.run_dir), self.job("a", "ok"), {}
        run.repo = self.tmp
        job["out"] = "reports/a.md"  # a typo in jobs.json: the folder is not there
        with patch.object(run, "launch") as launch:
            run.tick([job], state, {})
            launch.assert_not_called()
        self.assertEqual(state["a"]["state"], "failed")
        self.assertIn(f"output folder not found: {self.tmp / 'reports'}", state["a"]["why"])

    def test_preflight_never_runs_the_verify_command(self):
        # A verify command may run whole test suites, so preflight only reads its text.
        marker = self.tmp / "ran.txt"
        verify = f'"{sys.executable}" -c "import pathlib; pathlib.Path(r\'{marker}\').touch()"'
        run, job, state = pm_run.Run(self.run_dir), self.job("a", "ok", verify=verify), {}
        run.repo = self.tmp
        job["out"] = "reports/a.md"
        with patch.object(run, "launch") as launch:
            run.tick([job], state, {})
            launch.assert_not_called()
        self.assertEqual(state["a"]["state"], "failed")
        self.assertFalse(marker.exists(), "a pre-flight must never run the check itself")

    def test_preflight_runs_again_before_a_retry_launches_the_job(self):
        job = self.job("a", "ok", verify="echo\x0b", retry=1)
        state = {"a": {"state": "failed", "attempts": [{"started": 0}], "why": "old reason"}}
        run = pm_run.Run(self.run_dir)
        run.repo = self.tmp

        def started(job, attempt, state):
            attempt["pane"] = "p1"
            return True

        with patch.object(run, "launch", side_effect=started) as launch:
            run.tick([job], state, {})
            launch.assert_not_called()
            self.assertEqual(state["a"]["state"], "failed")
            self.assertIn("verify holds a control character", state["a"]["why"])
            job.update(retry=2, verify=f'"{sys.executable}" -c "import sys; sys.exit(0)"')
            run.tick([job], state, {})
        self.assertEqual(state["a"]["state"], "started")
        launch.assert_called_once()
        log = run.log_path.read_text(encoding="utf-8")
        self.assertIn("PREFLIGHT a:", log)
        self.assertIn("RETRY a: failed cleared, back to pending for a new attempt", log)

    def test_jobs_file_with_a_byte_order_mark_is_read(self):
        (self.run_dir / "jobs.json").write_text(json.dumps([self.job("a", "ok")]), encoding="utf-8-sig")
        self.run_pm()
        self.assertEqual(self.receipts()["a"]["state"], "verified")

    def test_invalid_jobs_file_stops_with_the_parse_error(self):
        (self.run_dir / "jobs.json").write_text('[{"id": "a",]', encoding="utf-8")
        result = self.run_pm(timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("jobs.json is not valid JSON", result.stderr)
        self.assertNotIn("pm_run start", result.stdout)
        self.assertFalse(self.fake_state.exists(), "no worker may start")

    def test_a_bad_tick_and_a_half_saved_jobs_file_do_not_stop_the_loop(self):
        log = self.run_dir / "pm_run.log"
        broken = self.job("b", "ok", after=5)  # not a list: the tick raises TypeError
        self.jobs(self.job("a", "ok"), broken)
        proc = self.start_pm()
        self.wait_for_log("TICK-ERROR TypeError")
        (self.run_dir / "jobs.json").write_text('[{"id": "a",', encoding="utf-8")
        self.wait_for_log("SKIPPED jobs.json")
        self.jobs(self.job("a", "ok"))
        self.assertEqual(proc.wait(timeout=30), 0)
        self.assertEqual(self.receipts()["a"]["state"], "verified")
        self.assertIn("Traceback", log.read_text(encoding="utf-8"))
        self.assertEqual(log.read_text(encoding="utf-8").count("SKIPPED jobs.json"), 1, "logged once per error")

    def test_stop_closes_one_live_worker_and_blocks_its_successor(self):
        self.jobs(self.job("a", "hang"), self.job("b", "ok", after=["a"]), self.job("c", "ok"))
        proc = self.start_pm()
        self.wait_for_log("LAUNCH a")
        result = self.run_pm("--stop", "a")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(proc.wait(timeout=30), 0)
        state = self.receipts()
        self.assertEqual([state[j]["state"] for j in "abc"], ["stopped", "blocked", "verified"])
        self.assertTrue(state["a"]["attempts"][0]["stopped_confirmed"])
        self.assertEqual(len(state["a"]["attempts"]), 1, "a stopped job is not retried")
        self.assertEqual(self.herdr_state()["agents"], {}, "the stopped worker's pane is closed")
        self.assertNotEqual(self.run_pm("--stop", "nope").returncode, 0)
        self.assertIn("already ended (verified)", self.run_pm("--stop", "c").stdout)

    def test_a_job_deleted_while_it_runs_is_reported_once_and_its_pane_left_open(self):
        self.jobs(self.job("a", "hang"))
        proc = self.start_pm()
        self.wait_for_log("LAUNCH a")
        self.jobs(self.job("c", "ok"))
        self.assertEqual(proc.wait(timeout=30), 0)
        log = (self.run_dir / "pm_run.log").read_text(encoding="utf-8")
        self.assertEqual(log.count("REMOVED a"), 1)
        self.assertEqual(self.receipts()["a"]["state"], "removed")
        herdr = self.herdr_state()
        self.assertIn(self.a1, herdr["agents"], "nobody stopped it, so its pane stays")
        self.assertTrue(herdr["workspaces"], "closing the workspace would kill the unwatched worker")
        self.assertIn("a               removed (not in jobs.json)", self.run_pm("--status").stdout)

    def test_agent_names_differ_between_runs_and_keep_the_attempt_number(self):
        one, two = pm_run.agent_name("a", 1, Path("runs/one")), pm_run.agent_name("a", 1, Path("runs/two"))
        self.assertNotEqual(one, two, "Herdr agent names are global; two runs must not share one")
        long = pm_run.agent_name("A very_long job id that goes on and on", 12, Path("runs/one"))
        self.assertLessEqual(len(long), 32)
        self.assertRegex(long, r"^[a-z][a-z0-9_-]{0,31}$")
        self.assertRegex(long, r"-12-[0-9a-f]{4}$")

    def test_an_output_from_another_run_is_copied_before_the_first_attempt(self):
        out = self.tmp / "out" / "a.md"
        out.parent.mkdir()
        out.write_text("a verified report from another run\n", encoding="utf-8")
        (self.tmp / "out" / "a.kept.md").write_text("an older copy\n", encoding="utf-8")
        self.jobs(self.job("a", "ok"))
        self.run_pm()
        self.assertEqual(self.receipts()["a"]["state"], "verified")
        self.assertEqual(
            (self.tmp / "out" / "a.kept-2.md").read_text(encoding="utf-8"), "a verified report from another run\n"
        )
        self.assertEqual((self.tmp / "out" / "a.kept.md").read_text(encoding="utf-8"), "an older copy\n")
        self.assertIn(
            "KEPT a: a.md existed before this run; a copy is at a.kept-2.md",
            (self.run_dir / "pm_run.log").read_text(encoding="utf-8"),
        )

    def test_a_brief_changed_while_the_worker_ran_is_flagged(self):
        brief = self.tmp / "brief.md"
        brief.write_text("item one\n", encoding="utf-8")
        self.jobs(self.job("a", "lazy"))  # finishes only after a nudge, so the brief can change in between
        real_launch = pm_run.Run.launch

        def launch_then_edit(run, job, attempt, state):
            sent = real_launch(run, job, attempt, state)
            brief.write_text("item two\n", encoding="utf-8")
            return sent

        state = {}
        run = pm_run.Run(self.run_dir)
        run.repo = self.tmp
        with patch.dict(os.environ, self.env), patch.object(
            pm_run, "HERDR_CMD", json.loads(self.env["PM_RUN_HERDR"])
        ), patch.object(pm_run.Run, "launch", launch_then_edit), patch.object(pm_run, "SETTLE_S", 0), patch.object(
            pm_run, "QUIET_S", 0
        ):
            for _ in range(20):
                run.tick([self.job("a", "lazy")], state, {})
                if state["a"]["state"] in pm_run.ENDED:
                    break
                time.sleep(0.6)
        self.assertEqual(state["a"]["state"], "verified")
        self.assertTrue(state["a"]["attempts"][-1]["brief_changed"])
        self.assertIn("BRIEF-CHANGED a", run.log_path.read_text(encoding="utf-8"))

    def test_old_artifact_from_before_the_attempt_does_not_count(self):
        out = self.tmp / "out" / "a.md"
        out.parent.mkdir(parents=True)
        out.write_text(" ".join(["old"] * 80) + "\n<!-- done -->\n", encoding="utf-8")
        past = time.time() - 3600
        os.utime(out, (past, past))
        self.jobs(self.job("a", "nothing"))
        self.run_pm()
        state = self.receipts()
        self.assertEqual(state["a"]["state"], "handed-over")
        self.assertEqual(len(state["a"]["attempts"]), 1)
        self.assertIn("older than this attempt", state["a"]["attempts"][0]["why"])
        self.assertTrue(out.exists())
        self.assertFalse(out.with_name("a.attempt1.md").exists())

    def test_unfinished_turn_gets_a_resume_nudge_in_the_same_session(self):
        self.jobs(self.job("a", "lazy"))
        self.run_pm()
        state = self.receipts()
        self.assertEqual(state["a"]["state"], "verified")
        self.assertEqual(len(state["a"]["attempts"]), 1)
        self.assertEqual(state["a"]["attempts"][0]["nudges"], 1)
        prompts = self.herdr_state()["gone"][self.a1]["prompts"]
        self.assertEqual(len(prompts), 2)
        self.assertIn("previous turn ended", prompts[1])
        self.assertIn("brief file(s) brief.md", prompts[1])

    def test_lost_brief_is_resent_in_full_with_the_same_nudge_budget(self):
        self.jobs(self.job("a", "lost", writes=["code/"]))
        result = self.run_pm()
        self.assertEqual(result.returncode, 0, result.stderr)
        attempt = self.receipts()["a"]["attempts"][0]
        self.assertEqual(self.receipts()["a"]["state"], "verified")
        self.assertEqual(attempt["seq0"], 0)
        self.assertEqual(attempt["nudges"], 1)
        prompts = self.herdr_state()["gone"][self.a1]["prompts"]
        self.assertEqual(prompts[0], prompts[1])
        self.assertIn("Read the brief file(s) brief.md", prompts[1])
        self.assertIn("and the paths code/", prompts[1])
        self.assertIn("PROMPT a: no turn ran after the brief was sent; brief resent", result.stdout)
        self.assertNotIn("RESUME a:", result.stdout)
        calls = self.herdr_state()["calls"]
        first_prompt = next(i for i, c in enumerate(calls) if c[:2] == ["agent", "prompt"])
        self.assertEqual(calls[first_prompt - 1][:2], ["agent", "get"])

    def test_failed_initial_prompt_is_retried_in_the_same_session_without_a_new_attempt(self):
        self.env["FAKE_PROMPT_ERROR"] = "1"
        self.jobs(self.job("a", "ok"))
        result = self.run_pm()
        self.assertEqual(result.returncode, 0, result.stderr)
        state = self.receipts()["a"]
        self.assertEqual(state["state"], "verified")
        self.assertEqual(len(state["attempts"]), 1)
        calls = self.herdr_state()["calls"]
        self.assertEqual(sum(c[:2] == ["agent", "start"] for c in calls), 1)
        prompts = [c[3] for c in calls if c[:2] == ["agent", "prompt"]]
        self.assertEqual(len(prompts), 2)
        self.assertEqual(prompts[0], prompts[1])
        self.assertIn("PROMPT a", result.stdout)

    def test_lost_brief_behind_a_used_up_quota_is_not_resent(self):
        screen = "> Read the brief file(s) brief.md\n  API Error: 429 usage limit reached for cx/gpt-6-astra\n"
        empty = {"n": 0, "workspaces": [], "agents": {}, "gone": {}, "closed": []}
        self.fake_state.write_text(json.dumps({**empty, "reads": [screen]}), encoding="utf-8")
        self.jobs(self.job("a", "lost", harness="claude"))
        result = self.run_pm()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.receipts()["a"]["state"], "handed-over")
        self.assertEqual(len(self.herdr_state()["agents"][self.a1]["prompts"]), 1)
        self.assertIn("HANDED-OVER a: provider quota or usage limit", result.stdout)
        self.assertNotIn("brief resent", result.stdout)

    def test_retry_keeps_fresh_output_without_overwriting_a_kept_name(self):
        out = self.tmp / "out" / "a.md"
        out.parent.mkdir()
        kept = out.with_name("a.attempt1.md")
        kept.write_text("already kept", encoding="utf-8")
        self.jobs(self.job("a", "crash"))  # the worker is gone, so a fresh session is allowed
        result = self.run_pm()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(kept.read_text(encoding="utf-8"), "already kept")
        saved = out.with_name("a.attempt1-2.md")
        self.assertEqual(saved.read_text(encoding="utf-8"), "skeleton\n")
        self.assertTrue(out.exists(), "the next attempt writes a separate output")
        self.assertIn("KEPT a: previous output saved as a.attempt1-2.md", result.stdout)
        self.assertLess(result.stdout.index("KEPT a:"), result.stdout.index("LAUNCH a attempt 2"))

    def test_worker_that_disappears_without_output_is_retried(self):
        self.jobs(self.job("a", "vanish"))
        self.run_pm()
        state = self.receipts()
        self.assertEqual(state["a"]["state"], "failed")
        attempt = state["a"]["attempts"][0]
        self.assertIn("worker is gone and no output file", attempt["why"])
        self.assertIn("session log not found", attempt["turn_end"])
        self.assertTrue(attempt["stopped_confirmed"])

    def test_launch_failure_fails_and_blocks_the_successor(self):
        self.jobs(self.job("a", "nostart"), self.job("b", "ok", after=["a"]))
        self.run_pm()
        state = self.receipts()
        self.assertEqual(state["a"]["state"], "failed")
        self.assertIn("pi did not become ready", state["a"]["attempts"][0]["why"])
        self.assertEqual(state["b"]["state"], "blocked")
        self.assertEqual(state["b"]["attempts"], [])

    def test_successor_starts_only_after_its_dependency_is_verified(self):
        self.jobs(self.job("a", "ok"), self.job("b", "ok", after=["a"]))
        self.run_pm()
        state = self.receipts()
        self.assertEqual(state["b"]["state"], "verified")
        self.assertGreater(state["b"]["attempts"][0]["started"], state["a"]["attempts"][0]["ended"])
        workspaces = {state[j]["attempts"][0]["pane"].split(":")[0] for j in ("a", "b")}
        self.assertEqual(workspaces, {state["_herdr_workspace"]}, "both jobs run in the run's one workspace")
        self.assertEqual(self.herdr_state()["closed"], [state["_herdr_workspace"]])

    def test_without_a_check_the_job_is_only_artifact_present_and_blocks_successors(self):
        self.jobs(self.job("a", "ok", verify=None), self.job("b", "ok", after=["a"]))
        self.run_pm()
        state = self.receipts()
        self.assertEqual(state["a"]["state"], "artifact-present")
        self.assertEqual(state["b"]["state"], "blocked")

    def test_hung_worker_gets_extra_time_once_then_is_handed_over_open(self):
        self.env["PM_RUN_HARD_S"] = "2"
        self.jobs(self.job("a", "hang"), self.job("b", "ok", after=["a"]))
        result = self.run_pm()
        state = self.receipts()
        self.assertEqual(state["a"]["state"], "handed-over")
        self.assertEqual(len(state["a"]["attempts"]), 1, "no fresh session while the worker lives")
        self.assertEqual(state["a"]["attempts"][0]["why"], "still working after the hard limit and the extra time")
        self.assertIn("OVERTIME a:", result.stdout)
        self.assertLess(result.stdout.index("OVERTIME a:"), result.stdout.index("HANDED-OVER a:"))
        self.assertIn(self.a1, self.herdr_state()["agents"], "the session stays open for the lead")
        self.assertEqual(self.herdr_state()["closed"], [], "the workspace stays open too")
        self.assertEqual(state["b"]["state"], "blocked")

    def test_query_error_keeps_worker_unknown_even_past_hard_timeout(self):
        self.env.update(FAKE_GET_ERROR="9999", PM_RUN_HARD_S="0")
        self.jobs(self.job("a", "ok"))
        with self.assertRaises(subprocess.TimeoutExpired):
            self.run_pm(timeout=4)
        attempt = self.receipts()["a"]["attempts"][0]
        self.assertEqual(self.receipts()["a"]["state"], "started")
        self.assertEqual(attempt["herdr"], "unknown")
        self.assertIn("query timed out", attempt["herdr_error"])
        self.assertEqual(len(self.receipts()["a"]["attempts"]), 1)
        calls = self.herdr_state()["calls"]
        self.assertGreater(sum(c[:2] == ["agent", "get"] for c in calls), 1)
        self.assertFalse(any(c[:2] == ["pane", "close"] for c in calls))

    def test_transient_query_error_recovers_on_a_later_tick(self):
        self.env["FAKE_GET_ERROR"] = "2"
        self.jobs(self.job("a", "ok"))
        self.run_pm()
        self.assertEqual(self.receipts()["a"]["state"], "verified")
        self.assertEqual(len(self.receipts()["a"]["attempts"]), 1)

    def test_server_down_during_workspace_setup_has_one_clear_error(self):
        for command in ("workspace list", "workspace create"):
            with self.subTest(command=command):
                self.env["FAKE_WORKSPACE_ERROR"] = command
                self.jobs(self.job("a", "ok"))
                result = self.run_pm()
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stderr.strip(), "Herdr server not running: connection refused")
                self.assertNotIn("Traceback", result.stderr)
                self.assertFalse((self.run_dir / "pm_run.lease").exists())

    def test_missing_herdr_says_how_to_fix_it(self):
        self.env["PM_RUN_HERDR"] = str(self.run_dir / "no-herdr-here.exe")
        self.jobs(self.job("a", "ok"))
        result = self.run_pm()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("install Herdr or set PM_RUN_HERDR", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_verify_timeout_is_a_failed_check_with_a_receipt_reason(self):
        self.env["PM_RUN_VERIFY_S"] = "0.1"
        self.jobs(self.job("a", "ok", verify=f'"{sys.executable}" -c "import time; time.sleep(1)"'))
        self.run_pm()
        state = self.receipts()["a"]
        self.assertEqual(state["state"], "check-failed")
        self.assertEqual(len(state["attempts"]), 1)
        self.assertIn("verify timed out after 0.1 s", state["attempts"][0]["why"])
        self.assertNotEqual(state["attempts"][0]["verify_rc"], 0)

    def test_check_command_reports_verify_timeout_without_herdr(self):
        self.env["PM_RUN_VERIFY_S"] = "0.1"
        out = self.tmp / "out" / "a.md"
        out.parent.mkdir()
        out.write_text("word " * 60 + "\n<!-- done -->\n", encoding="utf-8")
        self.jobs(self.job("a", "ok", verify=f'"{sys.executable}" -c "import time; time.sleep(1)"'))
        result = self.run_pm("--check", "a")
        self.assertEqual(result.returncode, 1)
        self.assertIn("verify timed out after 0.1 s", result.stdout)
        self.assertFalse(self.fake_state.exists())

    def test_pi_provider_error_is_recorded_from_the_last_assistant_message(self):
        self.env["FAKE_PI_STOP"] = "error"
        self.jobs(self.job("a", "nothing"))
        self.run_pm()
        for attempt in self.receipts()["a"]["attempts"]:
            self.assertEqual(attempt["stopReason"], "error")
            self.assertEqual(attempt["errorMessage"], "provider request timed out")
            self.assertIn("provider error: provider request timed out", attempt["why"])
            self.assertTrue(Path(attempt["session_log"]).is_file())
        self.assertIn("provider error: provider request timed out", (self.run_dir / "pm_run.log").read_text())

    def test_missing_pi_session_log_is_explicit_in_receipt(self):
        self.env["PM_RUN_MAX_TRIES"] = "1"
        self.jobs(self.job("a", "nothing"))
        self.run_pm()
        self.assertIn("session log not found", self.receipts()["a"]["attempts"][0]["why"])

    def test_worker_asking_a_question_waits_and_is_never_killed(self):
        self.env["PM_RUN_HARD_S"] = "1"
        self.jobs(self.job("a", "ask"))
        with self.assertRaises(subprocess.TimeoutExpired):
            self.run_pm(timeout=5)
        state = self.receipts()
        self.assertEqual(state["a"]["state"], "started")
        self.assertIn("asked", state["a"]["attempts"][0])
        self.assertIn(self.a1, self.herdr_state()["agents"])
        self.assertIn("WAITING a", (self.run_dir / "pm_run.log").read_text(encoding="utf-8"))

    def test_brief_tells_the_worker_to_ask_the_lead_for_a_helper(self):
        prompt = pm_run.launch_prompt(self.job("a", "ok"))
        self.assertIn("Do not start a helper", prompt)
        self.assertIn("Helper needed:", prompt)

    def test_a_job_with_helper_models_may_start_them_as_pm_run_jobs(self):
        prompt = pm_run.launch_prompt(self.job("a", "ok", writes=["sub/"], helpers=["cheap-a", "cheap-b"]))
        self.assertNotIn("Do not start a helper", prompt)
        self.assertIn("only as jobs of your own pm_run run", prompt)
        self.assertIn("on these models: cheap-a, cheap-b.", prompt)
        self.assertIn("a skill that runs its own agent", prompt, "the ban is as wide as without helpers")
        self.assertIn("Name the run directory a-helpers", prompt)
        self.assertIn("wait until it has ended", prompt)
        self.assertIn("Your output file is out/a.md. Create", prompt, "the output sentence is unchanged")

    def test_a_helper_object_tells_the_worker_its_harness_and_thinking(self):
        helper = {"model": "big", "harness": "claude", "thinking": "low"}
        job = self.job("a", "ok", writes=["sub/"], helpers=["cheap-a", helper])
        prompt = pm_run.launch_prompt(job)
        self.assertIn("on these models: cheap-a, big (harness claude, thinking low).", prompt)
        self.assertNotIn("Do not start a helper", prompt)

    def test_a_job_with_helper_objects_passes_preflight_and_starting_it(self):
        helper = {"model": "big", "harness": "claude", "thinking": "low"}
        self.jobs(self.job("a", "ok", writes=["sub/"], helpers=["cheap-a", helper]))
        result = self.run_pm()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.receipts()["a"]["state"], "verified")
        prompt = self.herdr_state()["gone"][self.a1]["prompts"][0]
        self.assertIn("on these models: cheap-a, big (harness claude, thinking low).", prompt)

    def test_preflight_rejects_a_helper_object_that_misses_one_of_its_three(self):
        for helper in ({"model": "big", "harness": "pi"}, {"model": "big", "thinking": "low"}, 7):
            with self.subTest(helper=helper):
                run, job, state = pm_run.Run(self.run_dir), self.job("a", "ok", helpers=[helper]), {}
                run.repo = self.tmp
                with patch.object(run, "launch") as launch:
                    run.tick([job], state, {})
                launch.assert_not_called()
                self.assertEqual(state["a"]["state"], "failed")
                self.assertEqual(state["a"]["why"], "helper 1 needs model, harness and thinking, or a plain model name")

    def test_second_scheduler_refuses_to_run(self):
        self.jobs(self.job("a", "ok"))
        (self.run_dir / "pm_run.lease").write_text(f"{os.getpid()} {time.time()}")
        result = self.run_pm(timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("holds", result.stderr + result.stdout)

    def test_check_command_judges_one_job_without_herdr(self):
        out = self.tmp / "out" / "a.md"
        out.parent.mkdir(parents=True)
        out.write_text("word " * 60 + "\n<!-- done -->\n", encoding="utf-8")
        self.jobs(
            self.job("a", "ok"),
            self.job("b", "ok", out="out/a.md", verify=f'"{sys.executable}" -c "import sys; sys.exit(4)"'),
        )
        passed = self.run_pm("--check", "a")
        self.assertEqual(passed.returncode, 0, passed.stdout + passed.stderr)
        self.assertIn("a: verified", passed.stdout)
        failed = self.run_pm("--check", "b")
        self.assertEqual(failed.returncode, 1)
        self.assertIn("check exited 4", failed.stdout)
        self.assertFalse(self.fake_state.exists(), "--check must not call Herdr")


class CheckAndRetryTest(PmRunFixture, unittest.TestCase):
    """A check runs in the background (state `checking`), and `--retry` starts an ended job again."""

    def test_a_slow_check_does_not_hold_the_next_launch(self):
        (self.run_dir / "caps.json").write_text('{"default": 1}', encoding="utf-8")  # one job per bucket
        self.jobs(
            self.job("a", "ok", verify=f'"{sys.executable}" -c "import time; time.sleep(1)"'),
            self.job("b", "ok"),
        )
        result = self.run_pm()
        self.assertEqual(result.returncode, 0, result.stderr)
        state = self.receipts()
        self.assertEqual([state[j]["state"] for j in "ab"], ["verified", "verified"])
        log = (self.run_dir / "pm_run.log").read_text(encoding="utf-8")
        self.assertIn("CHECK a", log)
        self.assertLess(
            log.index("LAUNCH b"),
            log.index("VERIFIED a"),
            "a slow check must not hold the next job, and a checking job keeps no bucket slot",
        )

    def test_a_check_that_runs_past_the_limit_is_killed_and_fails_the_job(self):
        out = self.tmp / "out" / "a.md"
        out.parent.mkdir()
        out.write_text("word " * 60 + "\n<!-- done -->\n", encoding="utf-8")
        job = self.job("a", "ok", verify=f'"{sys.executable}" -c "import time; time.sleep(30)"')
        attempt = {"name": "worker", "started": 1, "worked": True, "session_log": str(self.tmp / "no.jsonl")}
        state = {"a": {"state": "started", "attempts": [attempt]}}
        run = pm_run.Run(self.run_dir)
        run.repo = self.tmp
        with patch.object(run, "status_of", return_value=None), patch.object(pm_run, "VERIFY_S", 1):
            run.tick([job], state, {})
            self.assertEqual(state["a"]["state"], "checking")
            self.assertIn("a", run.checks, "a running check is kept, not waited for")
            with patch.object(pm_run.time, "time", return_value=time.time() + 5):
                run.tick([job], state, {})
        self.assertEqual(state["a"]["state"], "check-failed")
        self.assertEqual(attempt["verify_rc"], -1)
        self.assertIn("verify timed out after 1 s", attempt["why"])
        self.assertNotIn("a", run.checks, "the killed check is forgotten")

    def test_a_restart_loses_the_check_result_and_retry_checks_again(self):
        out = self.tmp / "out" / "a.md"
        out.parent.mkdir()
        out.write_text("word " * 60 + "\n<!-- done -->\n", encoding="utf-8")
        attempt = {"name": "worker", "started": 1, "artifact": {"words": 60}, "checking_since": 0, "check_pid": 4242}
        state = {"a": {"state": "checking", "attempts": [attempt]}}
        run = pm_run.Run(self.run_dir)
        run.repo = self.tmp
        self.assertEqual(run.checks, {}, "a fresh loop has no check process in memory")
        no_worker = patch.object(run, "launch")  # a regression must not start a real, paid worker
        launch = no_worker.start()
        self.addCleanup(no_worker.stop)
        run.tick([self.job("a", "ok")], state, {})
        self.assertEqual(state["a"]["state"], "check-failed", "an old check is never adopted or started twice")
        self.assertIn("result was lost", attempt["why"])
        self.assertEqual(run.checks, {})
        job = self.job("a", "ok", retry=1)
        run.tick([job], state, {})
        self.assertEqual(state["a"]["state"], "checking", "--retry checks the same report again")
        deadline = time.time() + 10
        while state["a"]["state"] == "checking" and time.time() < deadline:
            run.tick([job], state, {})
            time.sleep(0.1)
        self.assertEqual(state["a"]["state"], "verified")
        launch.assert_not_called()

    def test_a_check_that_passes_after_its_report_went_away_fails(self):
        out = self.tmp / "out" / "a.md"
        out.parent.mkdir()
        out.write_text("word " * 60 + "\n<!-- done -->\n", encoding="utf-8")
        job = self.job("a", "ok")
        attempt = {"name": "worker", "started": 1, "artifact": {"words": 60}}
        state = {"a": {"state": "pending", "attempts": [attempt]}}
        run = pm_run.Run(self.run_dir)
        run.repo = self.tmp
        run.start_check(job, state["a"])
        out.unlink()  # the report goes away while the check runs
        deadline = time.time() + 10
        while state["a"]["state"] == "checking" and time.time() < deadline:
            run.tick([job], state, {})
            time.sleep(0.1)
        self.assertEqual(state["a"]["state"], "check-failed", "a passed check proves nothing about a missing report")
        self.assertIn("no longer complete", attempt["why"])

    def test_a_check_that_passes_after_its_report_changed_fails(self):
        out = self.tmp / "out" / "a.md"
        out.parent.mkdir()
        out.write_text("word " * 60 + "\n<!-- done -->\n", encoding="utf-8")
        art, _ = pm_run.check_artifact(out, 1, 0)
        job = self.job("a", "ok")
        attempt = {"name": "worker", "started": 1, "artifact": art}
        state = {"a": {"state": "pending", "attempts": [attempt]}}
        run = pm_run.Run(self.run_dir)
        run.repo = self.tmp
        run.start_check(job, state["a"])
        out.write_text("other " * 60 + "\n<!-- done -->\n", encoding="utf-8")  # complete, but not what was checked
        deadline = time.time() + 10
        while state["a"]["state"] == "checking" and time.time() < deadline:
            run.tick([job], state, {})
            time.sleep(0.1)
        self.assertEqual(state["a"]["state"], "check-failed", "the check result belongs to the report it read")
        self.assertIn("changed while the check ran", attempt["why"])

    def test_a_restart_during_a_retried_check_ends_check_failed_without_a_new_worker(self):
        attempt = {"name": "worker", "started": 1, "artifact": {"words": 60}, "checking_since": 0, "check_retry": True}
        state = {"a": {"state": "checking", "attempts": [attempt]}}
        run = pm_run.Run(self.run_dir)
        run.repo = self.tmp
        with patch.object(run, "launch") as launch:  # a regression must not start a real, paid worker
            run.tick([self.job("a", "ok")], state, {})
        launch.assert_not_called()
        self.assertEqual(state["a"]["state"], "check-failed", "a lost result is not a failed retry: no paid attempt")
        self.assertIn("result was lost", attempt["why"])

    def test_stop_ends_a_job_whose_check_runs_and_kills_the_check(self):
        out = self.tmp / "out" / "a.md"
        out.parent.mkdir()
        out.write_text("word " * 60 + "\n<!-- done -->\n", encoding="utf-8")
        job = self.job("a", "ok", verify=f'"{sys.executable}" -c "import time; time.sleep(30)"', stop=True)
        attempt = {"name": "worker", "started": 1, "artifact": {"words": 60}}
        state = {"a": {"state": "pending", "attempts": [attempt]}}
        run = pm_run.Run(self.run_dir)
        run.repo = self.tmp
        run.start_check(job, state["a"])
        proc = run.checks["a"]
        self.addCleanup(end_process, proc)
        run.tick([job], state, {})
        self.assertEqual(state["a"]["state"], "stopped", "a stopped job must not end verified")
        self.assertNotIn("a", run.checks)
        self.assertIsNotNone(proc.poll(), "the check is killed, not left to finish")
        self.assertIn("STOPPED a: on request, its check was stopped", run.log_path.read_text(encoding="utf-8"))

    def test_a_timed_out_check_kills_its_whole_process_tree(self):
        out = self.tmp / "out" / "a.md"
        out.parent.mkdir()
        out.write_text("word " * 60 + "\n<!-- done -->\n", encoding="utf-8")
        job = self.job("a", "ok", verify=f'"{sys.executable}" -c "import time; time.sleep(5)"')
        attempt = {"name": "worker", "started": 1, "worked": True, "session_log": str(self.tmp / "no.jsonl")}
        state = {"a": {"state": "started", "attempts": [attempt]}}
        run = pm_run.Run(self.run_dir)
        run.repo = self.tmp
        with patch.object(run, "status_of", return_value=None), patch.object(pm_run, "VERIFY_S", 1), patch.object(
            pm_run, "kill_check"
        ) as kill:
            run.tick([job], state, {})
            self.assertEqual(state["a"]["state"], "checking")
            proc = run.checks["a"]
            self.addCleanup(end_process, proc)
            with patch.object(pm_run.time, "time", return_value=time.time() + 5):
                run.tick([job], state, {})
        kill.assert_called_once_with(proc)
        self.assertEqual(state["a"]["state"], "check-failed")

    def start_shell_tree(self):
        """A real check shape: a shell, a Python parent under it and a Python child under that; returns the shell and the child's id."""
        pid_file = self.tmp / "child.pid"
        child = "import time; time.sleep(60)"
        parent = (
            "import subprocess, sys, time; "
            f"p = subprocess.Popen([sys.executable, '-c', '{child}']); "
            f"open(r'{pid_file}', 'w').write(str(p.pid)); time.sleep(60)"
        )
        proc = subprocess.Popen(f'"{sys.executable}" -c "{parent}"', shell=True, start_new_session=os.name != "nt")
        self.addCleanup(end_process, proc)
        deadline = time.time() + 20
        while not pid_file.exists() and time.time() < deadline:
            time.sleep(0.1)
        return proc, int(pid_file.read_text(encoding="utf-8"))

    def assert_gone(self, pid, message):
        gone_by = time.time() + 10
        while process_runs(pid) and time.time() < gone_by:
            time.sleep(0.2)
        self.assertFalse(process_runs(pid), message)

    def test_kill_check_ends_the_real_child_of_the_shell(self):
        proc, child_pid = self.start_shell_tree()
        self.assertTrue(pm_run.kill_check(proc))
        self.assert_gone(child_pid, "the real command under the shell is killed too")

    @unittest.skipUnless(os.name == "nt", "the shell is the only handle to the tree on Windows")
    def test_after_a_failed_tree_kill_the_command_to_stop_it_by_hand_still_works(self):
        proc, child_pid = self.start_shell_tree()
        self.addCleanup(subprocess.run, ["taskkill", "/PID", str(child_pid), "/F"], capture_output=True)
        failed = subprocess.CompletedProcess([], 1)
        with patch.object(pm_run.subprocess, "run", return_value=failed):
            self.assertFalse(pm_run.kill_check(proc))
        self.assertIsNone(proc.poll(), "the shell is left running, so the tree can still be found through it")
        done = subprocess.run(pm_run.stop_by_hand(proc.pid), shell=True, capture_output=True)
        self.assertEqual(done.returncode, 0, done.stdout)
        self.assert_gone(child_pid, "the printed command stops the real command")

    def test_a_check_whose_tree_cannot_be_killed_names_the_command_to_stop_it(self):
        out = self.tmp / "out" / "a.md"
        out.parent.mkdir()
        out.write_text("word " * 60 + "\n<!-- done -->\n", encoding="utf-8")
        job = self.job("a", "ok", verify=f'"{sys.executable}" -c "import time; time.sleep(5)"')
        attempt = {"name": "worker", "started": 1, "artifact": {"words": 60}}
        state = {"a": {"state": "pending", "attempts": [attempt]}}
        run = pm_run.Run(self.run_dir)
        run.repo = self.tmp
        run.start_check(job, state["a"])
        proc = run.checks["a"]
        self.addCleanup(end_process, proc)
        with patch.object(pm_run, "VERIFY_S", 1), patch.object(pm_run, "kill_check", return_value=False), patch.object(
            pm_run.time, "time", return_value=time.time() + 5
        ):
            run.tick([job], state, {})
        self.assertEqual(state["a"]["state"], "check-failed")
        self.assertTrue(attempt["check_left_running"])
        self.assertIn(pm_run.stop_by_hand(proc.pid), attempt["why"])

    def test_stop_after_a_restart_says_the_old_check_is_not_stopped_from_here(self):
        attempt = {"name": "worker", "started": 1, "artifact": {"words": 60}, "checking_since": time.time()}
        state = {"a": {"state": "checking", "attempts": [attempt]}}
        run = pm_run.Run(self.run_dir)
        run.repo = self.tmp
        run.tick([self.job("a", "ok", stop=True)], state, {})
        self.assertEqual(state["a"]["state"], "stopped")
        self.assertIn("earlier loop", run.log_path.read_text(encoding="utf-8"))

    def test_a_retried_check_failed_job_checks_the_report_again_first(self):
        job = self.job("a", "ok")
        job["retry"] = 1
        run = pm_run.Run(self.run_dir)
        run.repo = self.tmp
        out = self.tmp / "out" / "a.md"
        cases = [
            ("a deleted report", None, "pending"),
            ("a report without the done marker", "word " * 60 + "\n", "pending"),
            ("a fixed report", "word " * 60 + "\n<!-- done -->\n", "checking"),
        ]
        for case, text, expected in cases:
            out.unlink(missing_ok=True)
            if text is not None:
                out.write_text(text, encoding="utf-8")
            attempt = {
                "name": "worker",
                "started": 1,
                "artifact": {"words": 3},
                "verify_rc": 1,
                "stopped_confirmed": True,
            }
            state = {"a": {"state": "check-failed", "attempts": [attempt]}}
            run.tick([job], state, {"default": 0})
            self.assertEqual(state["a"]["state"], expected, f"{case} must not end verified")
            if expected == "pending":
                self.assertNotIn("a", run.checks, f"{case}: no check runs on a report that does not pass")
                self.assertNotIn("check_retry", attempt)
            else:
                run.drop_check("a")
                self.assertTrue(attempt["check_retry"])
                self.assertEqual(attempt["artifact"]["words"], 63, "the fresh result is stored")
        log = run.log_path.read_text(encoding="utf-8")
        self.assertIn("RETRY a: check-failed cleared, back to pending for a new attempt: no output file", log)
        self.assertIn("back to pending for a new attempt: no done marker", log)

    def test_a_retry_closes_the_old_worker_before_the_reset(self):
        job = self.job("a", "ok")
        job["retry"] = 1
        attempt = {"name": "worker", "started": 1, "pane": "p1", "stopped_confirmed": False}
        state = {"a": {"state": "handed-over", "attempts": [attempt]}}
        run = pm_run.Run(self.run_dir)
        run.repo = self.tmp
        with patch.object(run, "stop", return_value=True) as stop:
            run.tick([job], state, {"default": 0})
        stop.assert_called_once_with(attempt)
        self.assertEqual(state["a"]["state"], "pending")
        self.assertTrue(attempt["stopped_confirmed"], "the closed worker is confirmed stopped")

    def test_a_retry_is_refused_when_the_old_worker_cannot_be_closed(self):
        job = self.job("a", "ok")
        job["retry"] = 1
        attempt = {"name": "worker", "started": 1, "pane": "p7", "stopped_confirmed": False}
        state = {"a": {"state": "handed-over", "attempts": [attempt]}}
        run = pm_run.Run(self.run_dir)
        run.repo = self.tmp
        with patch.object(run, "stop", return_value=False):
            run.tick([job], state, {"default": 0})
            run.tick([job], state, {"default": 0})  # the same request, again
        self.assertEqual(state["a"]["state"], "handed-over", "the job keeps its state")
        self.assertEqual(len(state["a"]["attempts"]), 1, "no new attempt runs beside the old worker")
        self.assertEqual(state["a"]["retries"], 1, "the handled request is not fired again")
        log = run.log_path.read_text(encoding="utf-8")
        self.assertIn(
            "RETRY-REFUSED a: could not close the old worker in Herdr pane p7; close it, then --retry a again", log
        )
        self.assertEqual(log.count("RETRY-REFUSED"), 1)

    def test_a_retry_that_arrives_while_the_job_runs_never_fires_later(self):
        job = self.job("a", "ok")
        job["retry"] = 1
        attempt = {"name": "worker", "started": 1, "pane": "p1"}
        state = {"a": {"state": "started", "attempts": [attempt]}}
        run = pm_run.Run(self.run_dir)
        run.repo = self.tmp
        with patch.object(run, "status_of", return_value="unknown"):
            run.tick([job], state, {})
        self.assertEqual(state["a"]["state"], "started", "a running job is not reset")
        self.assertEqual(state["a"]["retries"], 1, "the request is recorded as handled")
        state["a"]["state"] = "stopped"  # the job ends later, normally
        attempt["stopped_confirmed"] = True
        run.tick([job], state, {"default": 0})
        self.assertEqual(state["a"]["state"], "stopped", "the old request does not fire after the job ends")
        self.assertEqual(len(state["a"]["attempts"]), 1)
        self.assertIn(
            "RETRY-IGNORED a: it was started when the request arrived",
            run.log_path.read_text(encoding="utf-8"),
        )

    def test_retry_refuses_a_verified_job_and_a_running_one(self):
        self.jobs(self.job("a", "ok"), self.job("b", "hang"))
        proc = self.start_pm()
        self.wait_for_state("b", "started")
        running = self.run_pm("--retry", "b")
        self.assertNotEqual(running.returncode, 0)
        self.assertIn("stop it first with --stop b, then --retry b", running.stderr)
        self.wait_for_state("a", "verified")
        verified = self.run_pm("--retry", "a")
        self.assertNotEqual(verified.returncode, 0)
        self.assertIn("already verified", verified.stderr)
        missing = self.run_pm("--retry", "nope")
        self.assertNotEqual(missing.returncode, 0)
        self.assertIn("no job nope", missing.stderr)
        jobs = json.loads((self.run_dir / "jobs.json").read_text(encoding="utf-8"))
        self.assertNotIn("retry", jobs[0], "a refused --retry changes nothing")
        self.run_pm("--stop", "b")
        self.assertEqual(proc.wait(timeout=30), 0)
        self.assertEqual(self.receipts()["b"]["state"], "stopped")

    def test_retry_on_a_stopped_job_restarts_it_and_its_blocked_follower(self):
        self.jobs(self.job("a", "hang"), self.job("b", "ok", after=["a"]))
        proc = self.start_pm()
        self.wait_for_state("a", "started")
        self.run_pm("--stop", "a")
        self.assertEqual(proc.wait(timeout=30), 0, "a stopped job and its blocked follower end the loop")
        self.assertEqual([self.receipts()[j]["state"] for j in "ab"], ["stopped", "blocked"])
        jobs = json.loads((self.run_dir / "jobs.json").read_text(encoding="utf-8"))
        next(j for j in jobs if j["id"] == "a")["model"] = "ok"  # the retried attempt can finish this time
        (self.run_dir / "jobs.json").write_text(json.dumps(jobs), encoding="utf-8")
        result = self.run_pm("--retry", "a")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("go back to pending", result.stdout)
        proc = self.start_pm()
        self.assertEqual(proc.wait(timeout=60), 0)
        state = self.receipts()
        self.assertEqual([state[j]["state"] for j in "ab"], ["verified", "verified"])
        self.assertEqual(len(state["a"]["attempts"]), 2, "the retry is a new attempt")
        self.assertEqual(state["a"]["retries"], 1)
        jobs = json.loads((self.run_dir / "jobs.json").read_text(encoding="utf-8"))
        self.assertNotIn("stop", jobs[0], "--retry clears the stop request")
        self.assertEqual(jobs[0]["retry"], 1)
        log = (self.run_dir / "pm_run.log").read_text(encoding="utf-8")
        self.assertIn("RETRY a: stopped cleared, back to pending", log)

    def test_retry_on_a_check_failed_job_checks_again_without_a_new_worker(self):
        flag, script = self.tmp / "pass.flag", self.tmp / "check.py"
        script.write_text(
            "import sys\nfrom pathlib import Path\nsys.exit(0 if Path('pass.flag').exists() else 1)\n", encoding="utf-8"
        )
        self.jobs(self.job("a", "ok", verify=f'"{sys.executable}" "{script}"'))
        self.run_pm()
        self.assertEqual(self.receipts()["a"]["state"], "check-failed")
        flag.touch()
        result = self.run_pm("--retry", "a")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("its check runs again on the existing report", result.stdout)
        proc = self.start_pm()
        self.assertEqual(proc.wait(timeout=60), 0)
        state = self.receipts()
        self.assertEqual(state["a"]["state"], "verified")
        self.assertEqual(len(state["a"]["attempts"]), 1, "no new worker was paid for")
        self.assertEqual(state["a"]["attempts"][0]["verify_rc"], 0)
        self.assertEqual(state["a"]["retries"], 1)
        self.assertIn(
            "RETRY a: check again on the existing report, no new worker",
            (self.run_dir / "pm_run.log").read_text(encoding="utf-8"),
        )
        self.assertEqual(self.herdr_state()["agents"], {}, "a re-check starts no worker")


class PromptRecoveryTest(PmRunFixture, unittest.TestCase):
    def test_retry_keeps_output_before_launch_and_skips_all_kept_names(self):
        run = pm_run.Run(self.run_dir)
        run.repo = self.tmp
        out = self.tmp / "a.md"
        job = self.job("a", "nothing", out="a.md")
        for n in (1, 2):
            out.write_text(f"attempt {n}", encoding="utf-8")
            state = {"a": {"state": "pending", "attempts": [{"started": 0}] * n}}
            if n == 1:
                for name in ("a.attempt1.md", "a.attempt1-2.md"):
                    (self.tmp / name).write_text("kept", encoding="utf-8")
            expected = self.tmp / ("a.attempt1-3.md" if n == 1 else "a.attempt2.md")

            def launch(job, attempt, state):
                self.assertFalse(out.exists())
                self.assertEqual(expected.read_text(encoding="utf-8"), f"attempt {n}")
                attempt["pane"] = "p1"
                return True

            with patch.object(run, "launch", side_effect=launch):
                run.tick([job], state, {})
            self.assertEqual(state["a"]["state"], "started")
        self.assertEqual((self.tmp / "a.attempt1.md").read_text(encoding="utf-8"), "kept")
        self.assertEqual((self.tmp / "a.attempt1-2.md").read_text(encoding="utf-8"), "kept")

    def test_failed_output_retention_does_not_launch_the_retry(self):
        run = pm_run.Run(self.run_dir)
        run.repo = self.tmp
        out = self.tmp / "a.md"
        out.write_text("previous output", encoding="utf-8")
        state = {"a": {"state": "pending", "attempts": [{"started": 0}]}}
        with patch.object(Path, "rename", side_effect=OSError("permission denied")), patch.object(
            run, "launch"
        ) as launch:
            run.tick([self.job("a", "nothing", out="a.md")], state, {})
        launch.assert_not_called()
        self.assertEqual(state["a"]["state"], "failed")
        self.assertEqual(len(state["a"]["attempts"]), 1)
        self.assertEqual(out.read_text(encoding="utf-8"), "previous output")
        self.assertIn("KEPT-FAILED a: could not keep the previous output", run.log_path.read_text(encoding="utf-8"))

    def test_a_briefly_locked_output_is_kept_after_a_retry(self):
        run = pm_run.Run(self.run_dir)
        run.repo = self.tmp
        (self.tmp / "a.md").write_text("previous output", encoding="utf-8")
        state = {"a": {"state": "pending", "attempts": []}}
        copy = shutil.copy2
        calls = []

        def locked_once(src, dst):
            calls.append(src)
            if len(calls) == 1:
                raise PermissionError("held by a scanner")
            return copy(src, dst)

        with patch.object(pm_run.shutil, "copy2", side_effect=locked_once), patch.object(
            pm_run.time, "sleep"
        ), patch.object(run, "launch", side_effect=lambda job, attempt, state: attempt.update(pane="p1") or True):
            run.tick([self.job("a", "nothing", out="a.md")], state, {})
        self.assertEqual(state["a"]["state"], "started")
        self.assertEqual((self.tmp / "a.kept.md").read_text(encoding="utf-8"), "previous output")

    def settled_worker(self, error="500", screen="working"):
        """A Pi worker whose turn looks settled, with a session log that ends in a provider error."""
        self.fake_state.write_text(
            json.dumps(
                {
                    "n": 0,
                    "reads": [screen],
                    "agents": {
                        "worker": {"behaviour": "nothing", "prompts": ["brief"], "prompted": 0, "out": "out/a.md"}
                    },
                }
            ),
            encoding="utf-8",
        )
        log = self.tmp / "sessions" / "worker.jsonl"
        log.parent.mkdir(parents=True, exist_ok=True)
        entries = [
            {"type": "session", "timestamp": "1970-01-01T00:00:05Z"},
            {"type": "session_info", "name": "worker"},
            {"type": "message", "message": {"role": "assistant", "stopReason": "error", "errorMessage": error}},
        ]
        log.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")
        os.utime(log, (1000, 1000))
        attempt = {"name": "worker", "started": 1, "prompted": 1, "worked": True, "session_log": str(log)}
        run = pm_run.Run(self.run_dir)
        run.repo = self.tmp
        return run, log, attempt, {"a": {"state": "started", "attempts": [attempt]}}

    def tick_at(self, run, state, now, **consts):
        patches = [
            patch.dict(os.environ, self.env),
            patch.object(pm_run, "HERDR_CMD", json.loads(self.env["PM_RUN_HERDR"])),
        ]
        patches += [patch.object(pm_run, k, v) for k, v in consts.items()]
        patches += [
            patch.object(pm_run.time, "time", return_value=now),
            patch.object(run, "status_of", return_value="done"),
        ]
        with contextlib.ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            run.tick([self.job("a", "nothing")], state, {})
        return self.herdr_state()["agents"]["worker"]["prompts"]

    def test_without_a_session_log_the_pane_must_stay_unchanged_before_a_nudge(self):
        run, log, attempt, state = self.settled_worker()
        log.unlink()
        del attempt["session_log"]  # another harness, or a Pi folder the setup line moved
        herdr = self.herdr_state()
        self.fake_state.write_text(json.dumps({**herdr, "reads": ["thinking A", "thinking A B"]}), encoding="utf-8")
        for now, prompts in ((1100, 1), (1150, 1), (1200, 1), (1239, 1), (1241, 2)):
            with self.subTest(now=now):
                self.assertEqual(len(self.tick_at(run, state, now, QUIET_S=90, MAX_NUDGES=3)), prompts)
        log_text = run.log_path.read_text(encoding="utf-8")
        self.assertIn("HOLD a: turn looks settled but its pane last changed 0 s ago", log_text)
        self.assertIn("RESUME a", log_text)
        self.assertIsNone(attempt["settled_hash"], "a nudge starts a fresh quiet window")

    def test_log_line_with_claude_marks_survives_a_cp1252_console(self):
        console = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
        with patch.object(sys, "stdout", console):
            pm_run.Run(self.run_dir).log("HANDED-OVER a: ● Login expired ⎿")
        self.assertIn("● Login expired ⎿", (self.run_dir / "pm_run.log").read_text(encoding="utf-8"))

    def test_settled_turn_inside_pis_retry_wait_is_held_not_nudged(self):
        run, _, attempt, state = self.settled_worker()
        consts = {"QUIET_S": 90, "MAX_NUDGES": 3}
        self.assertEqual(len(self.tick_at(run, state, 1030, **consts)), 1, "Pi wrote its log 30 s ago: no nudge")
        self.assertEqual(state["a"]["state"], "started")
        self.assertIn("HOLD a: turn looks settled but Pi wrote its log 30 s ago", run.log_path.read_text("utf-8"))
        self.assertIn("; pm_run nudges it in the same session", run.log_path.read_text("utf-8"))
        prompts = self.tick_at(run, state, 1100, **consts)
        self.assertEqual(len(prompts), 2, "quiet for 100 s: Pi has stopped, so the same session is nudged")
        self.assertIn("previous turn ended", prompts[-1])
        self.assertEqual(attempt["nudges"], 1)

    def test_hold_line_says_the_brief_is_resent_and_when(self):
        run, _, attempt, state = self.settled_worker()
        attempt.update(worked=False, seq0=0, completion_seq=0)  # the worker never took the brief
        self.assertEqual(
            len(self.tick_at(run, state, 1030, QUIET_S=90, MAX_NUDGES=3)), 1, "a held turn is not sent yet"
        )
        log = run.log_path.read_text(encoding="utf-8")
        self.assertIn("HOLD a: turn looks settled but Pi wrote its log 30 s ago; ", log)
        self.assertIn("; if Pi's log stays quiet for 90 s, pm_run resends the brief", log)
        self.assertNotIn("pm_run nudges it in the same session", log)

    def test_hold_line_names_the_pane_as_the_source_it_watches(self):
        # No session log, so the pane is the clock: the condition must say so, not name Pi's log.
        run, log, attempt, state = self.settled_worker()
        log.unlink()
        del attempt["session_log"]
        attempt.update(worked=False, seq0=0, completion_seq=0)  # the worker never took the brief
        self.assertEqual(len(self.tick_at(run, state, 1100, QUIET_S=90, MAX_NUDGES=3)), 1)
        log_text = run.log_path.read_text(encoding="utf-8")
        self.assertIn("its pane last changed 0 s ago", log_text)
        self.assertIn("; if the pane stays quiet for 90 s, pm_run resends the brief", log_text)

    def test_no_turn_yet_needs_a_quiet_sequence_and_no_working_state(self):
        self.assertTrue(pm_run.no_turn_yet({}), "an attempt without a sequence ran no turn")
        self.assertTrue(pm_run.no_turn_yet({"seq0": 1, "completion_seq": 1}))
        self.assertFalse(pm_run.no_turn_yet({"seq0": 1, "completion_seq": 2}), "the sequence advanced")
        self.assertFalse(pm_run.no_turn_yet({"worked": True}), "the worker was seen working")

    def test_used_up_quota_is_handed_over_without_a_nudge(self):
        claude_pane = 'some earlier output\n  API Error: 429 {"error":{"message":"usage limit reached"}}\n\n'
        for error, screen, sign in (
            ("429 You have hit your usage limit", "working", "429 You have hit your usage limit"),
            (None, claude_pane, 'API Error: 429 {"error":{"message":"usage limit reached"}}'),
        ):
            with self.subTest(error=error):
                run, log, attempt, state = self.settled_worker(error, screen)
                prompts = self.tick_at(run, state, 1100, QUIET_S=0, MAX_NUDGES=3)
                self.assertEqual(len(prompts), 1, "the brief is not resent into a used-up quota")
                self.assertEqual(state["a"]["state"], "handed-over")
                self.assertIn(sign, attempt["quota"])
                self.assertIn("provider quota or usage limit", attempt["why"])
                self.assertIn("rerun the job after it resets", run.log_path.read_text(encoding="utf-8"))
                self.assertIn("worker", self.herdr_state()["agents"], "the session is left open")
                run.log_path.unlink()

    def test_a_quota_that_resets_soon_is_waited_out_then_nudged(self):
        run, log, attempt, state = self.settled_worker("429 The usage limit has been reached (reset after 2m 0s)")
        for now, prompts in ((1100, 1), (1200, 1), (1249, 1), (1251, 2)):
            with self.subTest(now=now):
                self.assertEqual(len(self.tick_at(run, state, now, QUIET_S=0, MAX_NUDGES=3)), prompts)
                self.assertEqual(state["a"]["state"], "started")
        self.assertIn("QUOTA-WAIT a", run.log_path.read_text(encoding="utf-8"))
        self.assertIn("RESUME a", run.log_path.read_text(encoding="utf-8"))

    def test_a_quota_is_waited_out_once_per_attempt_and_never_past_the_hard_limit(self):
        run, log, attempt, state = self.settled_worker("429 usage limit reached (reset after 2m 0s)")
        self.tick_at(run, state, 1100, QUIET_S=0, MAX_NUDGES=3)
        self.assertTrue(attempt["quota_waited"])
        entry = {"type": "message", "message": {"role": "assistant", "stopReason": "error", "errorMessage": ""}}
        entry["message"]["errorMessage"] = "429 usage limit reached (reset after 3m 0s)"  # a countdown that restarted
        log.write_text(log.read_text(encoding="utf-8") + json.dumps(entry) + "\n", encoding="utf-8")
        os.utime(log, (1200, 1200))
        self.tick_at(run, state, 1300, QUIET_S=0, MAX_NUDGES=3)
        self.assertEqual(state["a"]["state"], "handed-over", "a second wait in one attempt is not allowed")

        run, log, attempt, state = self.settled_worker("429 usage limit reached (reset after 20m 0s)")
        self.tick_at(run, state, 1100, QUIET_S=0, MAX_NUDGES=3, HARD_S=1500)
        self.assertEqual(state["a"]["state"], "handed-over", "the wait would end after the hard limit")

    def test_a_quota_that_resets_late_or_never_says_is_still_handed_over(self):
        for error in ("429 usage limit reached, resets in 5h", '429 {"message":"Go usage limit exceeded"}'):
            with self.subTest(error=error):
                run, log, attempt, state = self.settled_worker(error)
                self.assertEqual(len(self.tick_at(run, state, 1100, QUIET_S=0, MAX_NUDGES=3)), 1)
                self.assertEqual(state["a"]["state"], "handed-over")
                run.log_path.unlink()

    def test_reset_times_are_read_from_the_message(self):
        for text, seconds in (("(reset after 15m 19s)", 919), ("Resets in 2h", 7200), ("reset after 44s)", 44)):
            self.assertEqual(pm_run.reset_seconds(text), seconds)
        self.assertIsNone(pm_run.reset_seconds("limit reached, try later"))

    def test_bare_429_throttling_and_worker_prose_are_still_nudged(self):
        outage = '429: {"type":"server_error","message":"Upstream request failed: Endpoint is unavailable."}'
        throttled = "API Error: 429 rate_limit_error: this request would exceed your rate limit"
        prose = "## Next\n\nDocument the quota handling; the usage limit test passed.\n"
        for error, screen in ((outage, "working"), ("500", throttled), ("500", prose)):
            with self.subTest(error=error, screen=screen):
                run, log, attempt, state = self.settled_worker(error, screen)
                self.assertEqual(len(self.tick_at(run, state, 1100, QUIET_S=0, MAX_NUDGES=3)), 2)
                self.assertEqual(state["a"]["state"], "started")
                self.assertNotIn("quota", attempt)

    def test_expired_sign_in_is_handed_over_without_a_nudge(self):
        for error, screen in (
            (None, "Not logged in · Please run /login\n"),
            (None, "some earlier output\n● Login expired · Please run /login\n"),
            (None, '  ⎿  API Error: 401 {"type":"authentication_error","message":"OAuth token has expired"}\n'),
            ("401 Unauthorized: invalid api key", "working"),
        ):
            with self.subTest(screen=screen, error=error):
                run, log, attempt, state = self.settled_worker(error, screen)
                prompts = self.tick_at(run, state, 1100, QUIET_S=0, MAX_NUDGES=3)
                self.assertEqual(len(prompts), 1, "the brief is not resent before the owner signs in again")
                self.assertEqual(state["a"]["state"], "handed-over")
                self.assertIn("sign-in needed", attempt["why"])
                self.assertIn("/login", run.log_path.read_text(encoding="utf-8"))
                self.assertNotIn("quota", attempt)
                run.log_path.unlink()

    def test_prose_about_logins_and_a_key_signed_status_line_are_still_nudged(self):
        prose = "## Next\n\nHand over on a 401 and on an expired OAuth token; document it.\n"
        # The reviewer's own cases (16 Oct): prose that names the banner or quotes the error mid-sentence.
        named = "Document the Login expired banner.\nThe old API Error: 401 test passed: please run /login first.\n"
        quoted = "> API Error: 401 (example only; authentication is healthy)\n`Please run /login` is the hint.\n"
        # A Claude Code pane on a profile signed in with a key or token, as Herdr read it on 16 Oct: the hint above
        # the input box.
        status_line = (
            "● Write(R-sol.md)\n\n✽ Whisking… (11s)\n" + " " * 60 + "Not logged in · Run /login\n" + "─" * 90 + "\n❯\n"
        )
        for screen in (prose, named, quoted, status_line):
            with self.subTest(screen=screen):
                run, log, attempt, state = self.settled_worker("500", screen)
                self.assertEqual(len(self.tick_at(run, state, 1100, QUIET_S=0, MAX_NUDGES=3)), 2)
                self.assertEqual(state["a"]["state"], "started")
                self.assertNotIn("login", attempt)

    def blocked_worker(self, screen, worked=False):
        """A worker Herdr shows as blocked since t=1000, on this screen."""
        run, log, attempt, state = self.settled_worker(None, screen)
        attempt.update(asking=True, asked=1000, ask_kind="blocked", asks=1, seq0=None, worked=worked)
        return run, attempt, state

    def tick_blocked(self, run, state, now):
        with patch.dict(os.environ, self.env), patch.object(
            pm_run, "HERDR_CMD", json.loads(self.env["PM_RUN_HERDR"])
        ), patch.object(pm_run.time, "time", return_value=now), patch.object(run, "status_of", return_value="blocked"):
            run.tick([self.job("a", "nothing")], state, {})

    def test_a_paid_wall_before_the_first_turn_ends_the_job_at_once(self):
        # The screen of 6 Nov: Claude Code stopped Fable below a rule line and pm_run waited for 36 minutes.
        rule = "─" * 60
        for text in (
            "Fable 5.1 now uses usage credits",
            "Your payment is past due",
            "Your subscription does not include this model",
        ):
            with self.subTest(text=text):
                screen = f"> Read the brief\n{rule}\n  {text}\n  > Switch model and continue\n  Enter to confirm\n"
                run, attempt, state = self.blocked_worker(screen)
                self.tick_blocked(run, state, 1001)
                self.assertEqual(state["a"]["state"], "handed-over")
                self.assertIn(text, attempt["why"], "the reason quotes the screen")
                self.assertIn("worker", self.herdr_state()["agents"], "the session is left open")

    def test_an_unknown_screen_before_the_first_turn_ends_after_the_short_limit(self):
        run, attempt, state = self.blocked_worker("Pick a theme\n> dark\n")
        self.tick_blocked(run, state, 1100)
        self.assertEqual(state["a"]["state"], "started", "a start-up screen gets its short time")
        self.tick_blocked(run, state, 1121)
        self.assertEqual(state["a"]["state"], "handed-over")
        self.assertIn("Pick a theme", attempt["why"])

    def test_a_question_after_real_work_waits_for_the_long_limit(self):
        run, attempt, state = self.blocked_worker("I wrote about the billing page.\nAllow this edit?\n", worked=True)
        self.tick_blocked(run, state, 2000)
        self.assertEqual(state["a"]["state"], "started", "worker prose naming billing is no wall")
        self.tick_blocked(run, state, 2801)
        self.assertEqual(state["a"]["state"], "handed-over")

    def test_a_herdr_that_stops_answering_cannot_hold_a_run_for_ever(self):
        run, log, attempt, state = self.settled_worker()
        for now, ended in ((1000, "started"), (2000, "started"), (2801, "handed-over")):
            with patch.dict(os.environ, self.env), patch.object(pm_run.time, "time", return_value=now), patch.object(
                run, "status_of", return_value="unknown"
            ):
                run.tick([self.job("a", "nothing")], state, {})
            self.assertEqual(state["a"]["state"], ended)

    def test_every_question_in_one_session_is_reported(self):
        run, log, attempt, state = self.settled_worker()
        job = self.job("a", "nothing")
        # (Herdr state, its state counter): a question seen twice, an answer seen working, a second question, then
        # an answer and a third question that both fell between two ticks (16 Oct, Sol's review run).
        for status, seq in (("blocked", 3), ("blocked", 3), ("working", 4), ("blocked", 5), ("blocked", 7)):

            def status_of(attempt, status=status, seq=seq):
                attempt["state_seq"] = seq
                return status

            with patch.dict(os.environ, self.env), patch.object(
                pm_run, "HERDR_CMD", json.loads(self.env["PM_RUN_HERDR"])
            ), patch.object(run, "status_of", side_effect=status_of):
                run.tick([job], state, {})
        waiting = [line for line in run.log_path.read_text(encoding="utf-8").splitlines() if "WAITING a" in line]
        self.assertEqual(len(waiting), 3, "one line per question, not per tick, the later questions too")
        self.assertIn("question 3 in this session", waiting[-1])
        self.assertEqual(state["a"]["state"], "started")

    def test_agy_permission_questions_wait_once_past_the_hard_limit_and_resume_after_answer(self):
        questions = (
            "Allow access to this file?",
            "Run this command?",
            "Requesting permission for: read report.md",
        )
        for question in questions:
            with self.subTest(question=question):
                run, _, attempt, state = self.settled_worker(screen=question)
                attempt["pane"] = "w1:p7"
                job = self.job("a", "nothing", harness="agy")
                with patch.dict(os.environ, self.env), patch.object(
                    pm_run, "HERDR_CMD", json.loads(self.env["PM_RUN_HERDR"])
                ), patch.object(run, "status_of", return_value="done"), patch.object(
                    pm_run, "QUIET_S", 0
                ), patch.object(pm_run, "HARD_S", 1):
                    for now in (1100, 1200, 1300, 1400):
                        with patch.object(pm_run.time, "time", return_value=now):
                            run.tick([job], state, {})
                    self.assertEqual(state["a"]["state"], "started")
                    self.assertNotIn("nudges", attempt)
                    self.assertEqual(len(self.herdr_state()["agents"]["worker"]["prompts"]), 1)
                    herdr = self.herdr_state()
                    self.fake_state.write_text(json.dumps({**herdr, "reads": [{"error": "read failed"}]}))
                    with patch.object(pm_run.time, "time", return_value=1400):
                        run.tick([job], state, {})
                    self.assertEqual(state["a"]["state"], "started", "a failed read is not an answer")
                    waiting = run.log_path.read_text(encoding="utf-8")
                    self.assertEqual(waiting.count("WAITING a"), 1)
                    self.assertIn("w1:p7", waiting)
                    with patch("builtins.print") as printed:
                        run.status([job], state)
                    self.assertIn("waiting for an answer in pane w1:p7", str(printed.call_args_list))
                    herdr = self.herdr_state()
                    self.fake_state.write_text(
                        json.dumps({**herdr, "reads": ["Answer accepted. Working on the task."]})
                    )
                    with patch.object(pm_run.time, "time", return_value=1401):
                        run.tick([job], state, {})
                    self.assertNotIn("asking", attempt)
                    self.assertEqual(len(self.herdr_state()["agents"]["worker"]["prompts"]), 2)
                run.log_path.unlink()

    def test_agy_new_permission_target_is_logged_even_if_answers_fall_between_ticks(self):
        run, _, attempt, state = self.settled_worker(screen="Requesting permission for: read first.md")
        job = self.job("a", "nothing", harness="agy")
        with patch.dict(os.environ, self.env), patch.object(
            pm_run, "HERDR_CMD", json.loads(self.env["PM_RUN_HERDR"])
        ), patch.object(run, "status_of", return_value="done"):
            run.tick([job], state, {})
            herdr = self.herdr_state()
            self.fake_state.write_text(json.dumps({**herdr, "reads": ["Requesting permission for: read second.md"]}))
            run.tick([job], state, {})
            run.tick([job], state, {})
        self.assertEqual(run.log_path.read_text(encoding="utf-8").count("WAITING a"), 2)
        self.assertEqual(attempt["asks"], 2)
        self.assertEqual(state["a"]["state"], "started")

    def test_agy_permission_detection_uses_last_lines(self):
        run, _, attempt, state = self.settled_worker(screen="Allow access to this file?\n" + "new output\n" * 11)
        job = self.job("a", "nothing", harness="agy")
        with patch.dict(os.environ, self.env), patch.object(
            pm_run, "HERDR_CMD", json.loads(self.env["PM_RUN_HERDR"])
        ), patch.object(run, "status_of", return_value="done"), patch.object(
            pm_run.time, "time", return_value=1100
        ), patch.object(pm_run, "QUIET_S", 0):
            run.tick([job], state, {})
        self.assertEqual(attempt["nudges"], 1, "an old permission question is not a current one")

    def test_agy_permission_question_waits_even_with_a_completed_artifact(self):
        run, _, attempt, state = self.settled_worker(screen="Allow access to this file?")
        out = self.tmp / "out" / "a.md"
        out.parent.mkdir(exist_ok=True)
        out.write_text("word " * 60 + "\n<!-- done -->\n", encoding="utf-8")
        with patch.dict(os.environ, self.env), patch.object(
            pm_run, "HERDR_CMD", json.loads(self.env["PM_RUN_HERDR"])
        ), patch.object(run, "status_of", return_value="done"), patch.object(
            run, "stop", return_value=True
        ) as stop, patch.object(pm_run, "SETTLE_S", 0):
            run.tick([self.job("a", "nothing", harness="agy")], state, {})
        self.assertEqual(state["a"]["state"], "started")
        self.assertTrue(attempt["asking"])
        stop.assert_not_called()

    def test_limit_banner_with_a_reset_time_is_a_used_up_quota(self):
        run, log, attempt, state = self.settled_worker("500", "You've hit your limit · resets 3am (Europe/Istanbul)\n")
        self.assertEqual(len(self.tick_at(run, state, 1100, QUIET_S=0, MAX_NUDGES=3)), 1)
        self.assertEqual(state["a"]["state"], "handed-over")

    def test_an_earlier_turns_quota_error_is_not_reused_when_the_log_is_gone(self):
        run, log, attempt, state = self.settled_worker()
        attempt.update(stopReason="error", errorMessage="429 usage limit reached")  # cached from an earlier turn
        log.unlink()
        attempt.pop("session_log")
        self.assertEqual(len(self.tick_at(run, state, 1100, QUIET_S=0, MAX_NUDGES=3)), 2)
        self.assertEqual(state["a"]["state"], "started")
        self.assertIsNone(attempt["errorMessage"])

    def test_nudges_that_bring_new_work_do_not_use_the_idle_budget(self):
        run, log, attempt, state = self.settled_worker()
        consts = {"QUIET_S": 0, "MAX_NUDGES": 1}
        self.assertEqual(len(self.tick_at(run, state, 1100, **consts)), 2)
        with log.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"type": "message", "message": {"role": "assistant", "stopReason": "error"}}) + "\n")
        os.utime(log, (1000, 1000))  # the clock is patched; keep the write in its past
        out = self.tmp / "out" / "a.md"
        out.parent.mkdir(exist_ok=True)
        out.write_text("# a\n\nhalf done\n", encoding="utf-8")
        self.assertEqual(len(self.tick_at(run, state, 1200, **consts)), 3, "log and output changed: not idle")
        self.assertEqual(len(self.tick_at(run, state, 1300, **consts)), 3, "no growth: the budget of one is used")
        self.assertEqual(state["a"]["state"], "handed-over")
        self.assertEqual(len(state["a"]["attempts"]), 1)
        self.assertIn("1 nudges in a row brought no new work", attempt["why"])
        self.assertIn("worker", self.herdr_state()["agents"], "the session is left open")

    def test_nudges_that_leave_the_output_unchanged_use_the_idle_budget(self):
        run, log, attempt, state = self.settled_worker()
        consts = {"QUIET_S": 0, "MAX_NUDGES": 1}
        self.assertEqual(len(self.tick_at(run, state, 1100, **consts)), 2)
        with log.open("a", encoding="utf-8") as f:  # the worker answers the nudge but does not touch its output
            f.write(json.dumps({"type": "message", "message": {"role": "assistant", "stopReason": "stop"}}) + "\n")
        os.utime(log, (1000, 1000))
        self.assertEqual(len(self.tick_at(run, state, 1200, **consts)), 2, "the log grew but the output did not")
        self.assertEqual(state["a"]["state"], "handed-over")
        self.assertIn("1 nudges in a row brought no new work", attempt["why"])

    def test_settled_turn_selects_full_brief_or_self_contained_resume(self):
        for seq, worked, no_seq, expected in (
            (7, False, False, "PROMPT"),
            (8, False, False, "RESUME"),
            (7, True, False, "RESUME"),
            (7, False, True, "PROMPT"),
            (7, True, True, "RESUME"),
        ):
            with self.subTest(seq=seq, worked=worked, no_seq=no_seq):
                self.fake_state.write_text(
                    json.dumps(
                        {
                            "n": 0,
                            "agents": {
                                "worker": {
                                    "behaviour": "nothing",
                                    "prompts": ["brief"],
                                    "prompted": 0,
                                    "out": "out/a.md",
                                    "completion_seq": seq,
                                }
                            },
                        }
                    ),
                    encoding="utf-8",
                )
                attempt = {
                    "name": "worker",
                    "started": 1,
                    "prompted": 1,
                    "seq0": 7,
                    "completion_seq": 99,
                    "worked": worked,
                }
                state = {"a": {"state": "started", "attempts": [attempt]}}
                run = pm_run.Run(self.run_dir)
                run.repo = self.tmp
                with patch.dict(os.environ, {**self.env, "FAKE_NO_SEQ": "1" if no_seq else ""}), patch.object(
                    pm_run, "HERDR_CMD", json.loads(self.env["PM_RUN_HERDR"])
                ), patch.object(pm_run.time, "time", return_value=100), patch.object(
                    pm_run, "MAX_NUDGES", 1
                ), patch.object(pm_run, "QUIET_S", 0):
                    run.tick([self.job("a", "nothing")], state, {})
                    prompts = self.herdr_state()["agents"]["worker"]["prompts"]
                    self.assertEqual(len(prompts), 2)
                    self.assertIn(
                        "Read the brief file(s)" if expected == "PROMPT" else "previous turn ended", prompts[-1]
                    )
                    self.assertIn("brief.md", prompts[-1])
                    self.assertIn("out/a.md", prompts[-1])
                    self.assertEqual(attempt["nudges"], 1)
                    with patch.object(run, "stop", return_value=True), patch.object(
                        run, "status_of", return_value="done"
                    ), patch.object(pm_run.time, "time", return_value=200):
                        run.tick([self.job("a", "nothing")], state, {"default": 0})
                    self.assertEqual(state["a"]["state"], "handed-over", "one idle nudge used the budget")
                    self.assertEqual(len(self.herdr_state()["agents"]["worker"]["prompts"]), 2)
                log = run.log_path.read_text(encoding="utf-8")
                self.assertIn(expected + " a:", log)
                run.log_path.unlink()


class PaneWarningTest(PmRunFixture, unittest.TestCase):
    def watch(self, screens, times, **extra):
        job = self.job("a", "hang", **extra)
        self.fake_state.write_text(
            json.dumps({"n": 0, "reads": screens, "agents": {"worker": {"behaviour": "hang", "prompts": ["brief"]}}}),
            encoding="utf-8",
        )
        run = pm_run.Run(self.run_dir)
        run.repo = self.tmp
        run.log_path.unlink(missing_ok=True)
        attempt = {"name": "worker", "started": 1000, "prompted": 1000, "herdr": "working"}
        state = {"a": {"state": "started", "attempts": [attempt]}}
        snapshots = []
        with patch.dict(os.environ, self.env), patch.object(
            pm_run, "HERDR_CMD", json.loads(self.env["PM_RUN_HERDR"])
        ), patch.object(pm_run, "STALL_S", 300), patch.object(pm_run, "HARD_S", 10000):
            for now in times:
                with patch.object(pm_run.time, "time", return_value=now):
                    run.tick([job], state, {})
                snapshots.append(dict(attempt))
        run.save(state)
        calls = self.herdr_state()["calls"]
        self.assertTrue(all(c[:2] in (["agent", "get"], ["agent", "read"]) for c in calls), calls)
        for call in calls:
            if call[:2] == ["agent", "read"]:
                self.assertEqual(call[3:], ["--source", "visible"])
        log = run.log_path.read_text(encoding="utf-8") if run.log_path.exists() else ""
        return run, job, state, snapshots, log

    def test_stall_once_per_episode_and_receipt_status(self):
        run, job, state, snapshots, log = self.watch(
            ["first", "first", "first", "processed 200 files", "processed 200 files"],
            [1000, 1300, 1400, 1401, 1701],
        )
        self.assertEqual(log.count("STALLED a:"), 2)
        self.assertIn("no new output for 5 min", log)
        self.assertIn("no evidence yet: a long think, or a request hung at the provider", log)
        self.assertTrue(snapshots[1]["stall"])
        self.assertTrue(snapshots[0]["worked"])
        self.assertFalse(snapshots[3]["stall"])
        self.assertEqual(snapshots[3]["seen_at"], 1401)
        self.assertTrue(self.receipts()["a"]["attempts"][0]["stall"])
        with patch("builtins.print") as printed:
            run.status([job], state)
        shown = "\n".join(call.args[0] for call in printed.call_args_list)  # the table, then the totals
        self.assertIn("stall=True", shown)
        self.assertIn("loop=False", shown)

    def test_first_observation_uses_prompted_as_silence_start(self):
        _, _, _, _, log = self.watch(["quiet"], [1300])
        self.assertEqual(log.count("STALLED a:"), 1)

    def test_wrapped_wall_needs_new_output_and_rearms_after_one_clear_tick(self):
        line = "} " * 75
        first = "first\n" + (line + "\n") * 20
        second = "second\n" + (line + "\n") * 21
        third = "third\n" + (line + "\n") * 22
        _, _, _, snapshots, log = self.watch(
            [first, first, second, third, "normal output", first, second],
            [1000, 1010, 1020, 1030, 1040, 1050, 1060],
        )
        self.assertFalse(snapshots[0]["loop"])
        self.assertFalse(snapshots[1]["loop"])
        self.assertTrue(snapshots[2]["loop"])
        self.assertFalse(snapshots[4]["loop"])
        self.assertEqual(log.count("LOOP a:"), 2)
        self.assertIn('suspected loop, new output keeps repeating "' + line[:60] + '" (21 of the last 30 lines)', log)

    def test_frozen_wall_is_stalled_not_looping(self):
        wall = ("} " * 75 + "\n") * 30
        _, _, _, _, log = self.watch([wall], [1000, 1300, 1315])
        self.assertNotIn("LOOP", log)
        self.assertEqual(log.count("STALLED"), 1)

    def test_only_last_30_content_lines_count_and_chrome_does_not_change_the_hash(self):
        _, _, _, _, log = self.watch(["}\n" * 20 + "ok\n" * 30], [1000, 1010])
        self.assertNotIn("LOOP", log)
        first = "processed 100 files\n" + "─" * 25 + " ⠼ Working\n100 tokens TPS --"
        second = "processed 100 files\n" + "─" * 25 + " ⠋ Working\n200 tokens TPS 10"
        _, _, _, snapshots, log = self.watch([first, second], [1000, 1300])
        self.assertEqual(snapshots[0]["seen_hash"], snapshots[1]["seen_hash"])
        self.assertEqual(snapshots[1]["seen_at"], 1000)
        self.assertEqual(log.count("STALLED"), 1)

    def test_different_repeated_line_does_not_prove_a_loop(self):
        _, _, _, _, log = self.watch(["}\n" * 20, "]\n" * 20], [1000, 1010])
        self.assertNotIn("LOOP", log)

    def test_failed_read_changes_no_warning_state_and_emits_nothing(self):
        _, _, _, snapshots, log = self.watch([{"error": "query timed out"}], [1300])
        self.assertEqual(
            snapshots[0],
            {
                "name": "worker",
                "started": 1000,
                "prompted": 1000,
                "herdr": "working",
                "worked": True,
                "completion_seq": 0,
            },
        )
        self.assertEqual(log, "")

    def test_failed_read_preserves_an_existing_episode(self):
        _, _, _, snapshots, log = self.watch(["quiet", "quiet", {"error": "query timed out"}], [1000, 1300, 1400])
        self.assertEqual(snapshots[1], snapshots[2])
        self.assertEqual(log.count("STALLED"), 1)

    def test_pane_evidence_is_bounded_and_not_a_diagnosis(self):
        for pane, expected in (
            ("error 429", 'quota or rate limit: pane mentions "429"'),
            ("RATE LIMIT", 'quota or rate limit: pane mentions "RATE LIMIT"'),
            ("fetch failed", 'connection or server: pane mentions "fetch failed"'),
            ("1429 items\n" + "fine\n" * 10, "no evidence yet"),
            ("429\n" + "fine\n" * 10, "no evidence yet"),
            ("1503 items", "no evidence yet"),
        ):
            with self.subTest(pane=pane):
                _, _, _, _, log = self.watch([pane], [1300])
                self.assertIn(expected, log)

    def test_probe_only_at_warning_and_http_evidence(self):
        from urllib.error import HTTPError, URLError

        url = "http://127.0.0.1:8080/v1/models"
        for code, expected in (
            (200, "no evidence yet"),
            (429, "quota or rate limit"),
            (502, "connection or server"),
            (503, "connection or server"),
            (401, "probe inconclusive (check the probe URL)"),
            (403, "probe inconclusive (check the probe URL)"),
            (404, "probe inconclusive (check the probe URL)"),
        ):
            with self.subTest(code=code), patch.object(pm_run, "urlopen") as probe:
                if code == 200:
                    probe.return_value.__enter__.return_value.status = 200
                else:
                    probe.side_effect = HTTPError(url, code, "test", {}, None)
                _, _, _, _, log = self.watch(["quiet"], [1000, 1300, 1315], probe=url)
                self.assertIn(expected, log)
                probe.assert_called_once_with(url, timeout=5)
        for error in (URLError("connection refused"), TimeoutError("timed out")):
            with self.subTest(error=error), patch.object(pm_run, "urlopen", side_effect=error) as probe:
                _, _, _, _, log = self.watch(["quiet"], [1300], probe=url)
                self.assertIn("connection or server", log)
                probe.assert_called_once_with(url, timeout=5)
        with patch.object(pm_run, "urlopen", side_effect=HTTPError(url, 403, "test", {}, None)):
            _, _, _, _, log = self.watch(["error 429"], [1300], probe=url)
            self.assertIn('quota or rate limit: pane mentions "429"', log)
            self.assertIn("probe inconclusive", log)

    def test_resume_resets_observations_and_warning_flags(self):
        run, job, state, _, _ = self.watch(["quiet"], [1300])
        attempt = state["a"]["attempts"][0]
        attempt.update(loop=True, loop_line="}")
        with patch.object(run, "status_of", return_value="done"), patch.object(
            pm_run, "herdr", return_value={}
        ), patch.object(pm_run, "turn_end", return_value="no log"), patch.object(
            pm_run.time, "time", return_value=1400
        ):
            run.tick([job], state, {})
        self.assertIsNone(attempt["seen_hash"])
        self.assertEqual(attempt["seen_at"], 1400)
        self.assertFalse(attempt["stall"])
        self.assertFalse(attempt["loop"])
        self.assertIsNone(attempt["loop_line"])

    def test_normalization_removes_only_harness_chrome(self):
        content = "processed 100 files\n"
        for first, second in (
            (
                content + "─" * 25 + " ⠼ Working\n100 tokens TPS --",
                content + "─" * 25 + " ⠋ Working\n200 tokens TPS 10",
            ),
            (
                content + "✻ Thinking (1s)\n" + "─" * 30 + "\n100 tokens",
                content + "✶ Thinking (2s)\n" + "─" * 30 + "\n200 tokens",
            ),
        ):
            with self.subTest(first=first):
                self.assertEqual(pm_run.pane_content(first), pm_run.pane_content(second))
                self.assertIn("processed 100 files", pm_run.pane_content(first))
        self.assertNotEqual(pm_run.pane_content(content), pm_run.pane_content("processed 200 files\n"))
        self.assertIn("* bullet 123", pm_run.pane_content("* bullet 123\n"))

    def test_working_only_and_log_also_reaches_stdout(self):
        with patch("builtins.print") as printed:
            run, job, state, _, log = self.watch(["quiet"], [1300])
        self.assertTrue(any("STALLED a:" in str(c) for c in printed.call_args_list))
        before = len(self.herdr_state()["calls"])
        for status in ("unknown", "blocked", "idle"):
            with patch.object(run, "status_of", return_value=status), patch.object(
                pm_run.time, "time", return_value=1001
            ):
                run.tick([job], state, {})
        self.assertEqual(len(self.herdr_state()["calls"]), before)
        self.assertIn("STALLED", log)


# A Pi `usage` object as an assistant message carries it: 115 tokens for $0.12.
USAGE = {
    "input": 100,
    "output": 10,
    "cacheRead": 5,
    "cacheWrite": 0,
    "totalTokens": 115,
    "cost": {"input": 0.1, "output": 0.02, "cacheRead": 0, "cacheWrite": 0, "total": 0.12},
}
USED_115 = {
    "input": 100,
    "output": 10,
    "cache_read": 5,
    "cache_write": 0,
    "total_tokens": 115,
    "turns": 1,
    "cost_usd": 0.12,
}
THE_NOTE = "(at API prices; plans and free models cost less)"


def log_stamp(seconds):
    """A Pi log timestamp for a fixed epoch second, written as Pi writes it."""
    return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(seconds))


class UsageTest(PmRunFixture, unittest.TestCase):
    """What an attempt used, read from its Pi session log; a log is evidence, never a guess."""

    def folder(self):
        folder = self.tmp / "sessions" / ("--" + re.sub(r"[/\\:]", "-", str(self.tmp).lstrip("/\\")) + "--")
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def write_log(self, *entries, name="worker"):
        path = self.folder() / f"{name}.jsonl"
        path.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")
        return path

    def usage(self, started=1000, name="worker", log=None):
        job = {"id": "a", "model": "cheap-a", "out": "out/a.md"}
        with patch.dict(os.environ, {"PM_RUN_PI_SESSIONS": str(self.tmp / "sessions")}):
            return pm_run.usage_of(job, {"name": name, "started": started}, self.tmp, log)

    def session(self, *messages, started=1000):
        """A session header for an attempt that started at `started`, then the given message entries."""
        header = {"type": "session", "timestamp": log_stamp(started + 1)}
        return [header, {"type": "session_info", "name": "worker"}, *messages]

    def test_only_messages_written_after_the_attempt_started_count(self):
        self.write_log(
            *self.session(
                {"type": "message", "timestamp": log_stamp(900), "message": {"role": "assistant", "usage": USAGE}},
                {"type": "message", "timestamp": log_stamp(1100), "message": {"role": "assistant", "usage": USAGE}},
            )
        )
        self.assertEqual(self.usage(), USED_115)

    def test_a_message_without_a_cost_counts_its_tokens_and_leaves_the_money_null(self):
        no_cost = {"input": 10, "output": 2, "cacheRead": 0, "cacheWrite": 0, "totalTokens": 12}
        self.write_log(
            *self.session(
                {"type": "message", "message": {"role": "assistant", "usage": USAGE}},
                {"type": "message", "message": {"role": "assistant", "usage": no_cost}},
            )
        )
        self.assertEqual(
            self.usage(),
            {
                "input": 110,
                "output": 12,
                "cache_read": 5,
                "cache_write": 0,
                "total_tokens": 127,
                "turns": 2,
                "cost_usd": None,
            },
        )

    def test_turns_count_the_assistant_messages_summed_in_this_attempt(self):
        self.write_log(
            *self.session(
                {"type": "message", "timestamp": log_stamp(900), "message": {"role": "assistant", "usage": USAGE}},
                {"type": "message", "timestamp": log_stamp(1100), "message": {"role": "assistant", "usage": USAGE}},
                {"type": "message", "timestamp": log_stamp(1200), "message": {"role": "assistant", "usage": USAGE}},
                {"type": "message", "timestamp": log_stamp(1300), "message": {"role": "toolResult"}},
            )
        )
        self.assertEqual(self.usage()["turns"], 2, "one turn per assistant message inside this attempt; no tool result")

    def test_no_log_for_this_attempt_means_no_usage(self):
        self.assertIsNone(self.usage(), "no log is no evidence, not zero")
        self.write_log(
            *self.session(
                {"type": "message", "timestamp": log_stamp(1100), "message": {"role": "assistant", "usage": USAGE}}
            )
        )
        self.assertIsNone(self.usage(started=2000), "a session that began before the attempt is not this attempt's")
        self.assertEqual(self.usage(), USED_115, "the attempt that did start it reads it")

    def test_a_finished_run_without_a_session_log_keeps_no_usage(self):
        self.jobs(self.job("a", "ok"))
        self.run_pm()
        self.assertEqual(self.receipts()["a"]["state"], "verified")
        self.assertNotIn("usage", self.receipts()["a"]["attempts"][0])

    def test_an_unreadable_line_is_skipped_and_named_once(self):
        entries = self.session(
            {"type": "message", "message": {"role": "assistant", "usage": USAGE}},
            {"type": "message", "message": {"role": "assistant", "usage": USAGE}},
        )
        broken = '\n{"message": cut\n{"type": "message", cut again\n'
        (self.folder() / "worker.jsonl").write_text(
            "\n".join(json.dumps(e) for e in entries[:2]) + broken + "\n".join(json.dumps(e) for e in entries[2:]),
            encoding="utf-8",
        )
        said = []
        self.assertEqual(self.usage(log=said.append)["input"], 200, "both readable messages still count")
        self.assertEqual(len(said), 1, "one line, however many lines were unreadable")
        self.assertIn("skipped 2 unreadable line(s)", said[0])

    def test_totals_add_the_attempts_of_two_jobs_and_leave_an_unknown_cost_unknown(self):
        used = {
            "input": 1000,
            "output": 100,
            "cache_read": 0,
            "cache_write": 0,
            "total_tokens": 1100,
            "turns": 2,
            "cost_usd": 0.25,
        }
        jobs = [{"id": "a", "model": "cheap-a"}, {"id": "b", "model": "big-b"}]
        state = {
            "a": {"state": "verified", "attempts": [{"usage": used}, {"usage": {**used, "total_tokens": 900}}]},
            # An older receipt, written before turns were counted, says nothing about its turns.
            "b": {"state": "failed", "attempts": [{"usage": {**used, "turns": None, "cost_usd": None}}]},
            "_herdr_workspace": "w1",
        }
        per_model, per_job = pm_run.usage_tally(jobs, state)
        self.assertEqual(
            per_job["a"],
            {"tokens": 2000, "turns": 4, "cost": 0.5, "known": True, "turns_known": True, "counted": 2, "partial": 0},
            "both attempts were paid for",
        )
        self.assertEqual(
            per_job["b"],
            {"tokens": 1100, "turns": 0, "cost": 0.0, "known": False, "turns_known": False, "counted": 1, "partial": 0},
        )
        self.assertEqual(sorted(per_model), ["big-b", "cheap-a"])
        with patch("builtins.print") as printed:
            pm_run.Run(self.run_dir).print_totals(per_model)
        text = "\n".join(call.args[0] for call in printed.call_args_list)
        self.assertIn("cheap-a", text)
        self.assertIn(f"{'model':<24}{'tokens':>10}{'turns':>10}{'API est.':>10}", text)
        self.assertIn(f"{'cheap-a':<24}{'2.0k':>10}{'4':>10}{'$0.50':>10}", text)
        self.assertIn(
            f"{'big-b':<24}{'1.1k':>10}{'-':>10}{'-':>10}",
            text,
            "one attempt without a cost or a turn count leaves the row unknown",
        )
        self.assertIn(f"{'total':<24}{'3.1k':>10}{'-':>10}{'-':>10}", text)
        self.assertNotIn(THE_NOTE, text, "a total without money says nothing about API prices")
        self.assertNotIn("+?", text, "every attempt reported usage: no sum is marked partial")
        self.assertNotIn(pm_run.NO_USAGE, text)

    def totals_text(self, per_model):
        with patch("builtins.print") as printed:
            pm_run.Run(self.run_dir).print_totals(per_model)
        return "\n".join(call.args[0] for call in printed.call_args_list)

    def test_a_missing_usage_record_makes_the_job_model_and_total_partial(self):
        used = {"input": 100, "output": 10, "total_tokens": 115, "turns": 1, "cost_usd": 0.03}
        jobs = [{"id": "a", "model": "cheap-a"}]
        state = {"a": {"state": "verified", "attempts": [{"usage": used}, {"why": "log not found"}]}}
        per_model, per_job = pm_run.usage_tally(jobs, state)
        self.assertEqual(per_job["a"]["counted"], 1, "one attempt reported usage")
        self.assertEqual(per_job["a"]["partial"], 1, "one attempt was paid for without a usage record")
        self.assertEqual(per_job["a"]["tokens"], 115, "the known sum stays, it is only marked")
        text = self.totals_text(per_model)
        self.assertIn(f"{'cheap-a':<24}{'115+?':>10}{'1+?':>10}{'$0.03+?':>10}", text)
        self.assertIn(f"{'total':<24}{'115+?':>10}{'1+?':>10}{'$0.03+?':>10}", text, "a partial sum is not the whole")
        self.assertEqual(text.count(pm_run.NO_USAGE), 1, "the note appears once, under the totals")
        self.assertTrue(text.rstrip().endswith(pm_run.NO_USAGE), "the note sits under the total line")

    def test_status_marks_a_job_row_partial_when_an_attempt_reported_no_usage(self):
        used = {"input": 100, "output": 10, "total_tokens": 115, "turns": 1, "cost_usd": 0.03}
        jobs = [{"id": "a", "model": "cheap-a"}]
        state = {"a": {"state": "verified", "attempts": [{"usage": used}, {"why": "log not found"}]}}
        with patch("builtins.print") as printed:
            pm_run.Run(self.run_dir).status(jobs, state)
        text = "\n".join(call.args[0] for call in printed.call_args_list)
        self.assertRegex(text, r"(?m)^a +verified +2 +115\+\? +1\+\? +\$0\.03\+\? ", "the job row says it is partial")

    def test_a_mixed_harness_run_does_not_show_the_pi_sum_as_the_grand_total(self):
        used = {"input": 100, "output": 10, "total_tokens": 115, "turns": 1, "cost_usd": 0.03}
        jobs = [
            {"id": "a", "model": "pi-model", "harness": "pi"},
            {"id": "b", "model": "claude-model", "harness": "claude"},
        ]
        state = {
            "a": {"state": "verified", "attempts": [{"usage": used}]},
            "b": {"state": "verified", "attempts": [{"why": "Claude's log is not read"}]},
        }
        per_model, _ = pm_run.usage_tally(jobs, state)
        self.assertIn("claude-model", per_model, "a model whose attempts reported no usage still gets a row")
        self.assertEqual(per_model["claude-model"]["partial"], 1)
        self.assertEqual(per_model["pi-model"]["partial"], 0, "the Pi attempts themselves all reported usage")
        text = self.totals_text(per_model)
        self.assertIn(f"{'pi-model':<24}{'115':>10}{'1':>10}{'$0.03':>10}", text)
        self.assertIn(f"{'claude-model':<24}{'-':>10}{'-':>10}{'-':>10}", text, "nothing is known: dashes, no mark")
        total = next(line for line in text.splitlines() if line.startswith("total"))
        self.assertTrue(total.startswith(f"{'total':<24}{'115+?':>10}{'1+?':>10}{'$0.03+?':>10}"), total)
        self.assertEqual(text.count(pm_run.NO_USAGE), 1)

    def test_a_removed_job_without_usage_still_counts_against_the_total(self):
        used = {"input": 900, "output": 100, "total_tokens": 1000, "turns": 2, "cost_usd": 0.25}
        jobs = [{"id": "a", "model": "cheap-a"}]
        state = {
            "a": {"state": "verified", "attempts": [{"usage": used}]},
            "gone": {"state": "verified", "attempts": [{"model": "big-b", "why": "log not found"}]},
        }
        per_model, per_job = pm_run.usage_tally(jobs, state)
        self.assertIn("gone", per_job, "a job removed from jobs.json still counts: its attempts were paid for")
        self.assertEqual(per_job["gone"]["counted"], 0)
        self.assertIn("big-b", per_model, "its model keeps a row instead of disappearing")
        text = self.totals_text(per_model)
        self.assertIn(f"{'big-b':<24}{'-':>10}{'-':>10}{'-':>10}", text)
        total = next(line for line in text.splitlines() if line.startswith("total"))
        self.assertTrue(total.startswith(f"{'total':<24}{'1.0k+?':>10}{'2+?':>10}{'$0.25+?':>10}"), total)

    def test_status_shows_tokens_turns_and_the_api_estimate_for_a_job_and_the_same_total_per_model(self):
        self.env["FAKE_PI_USAGE"] = json.dumps(USAGE)
        self.jobs(self.job("a", "ok"))
        done = self.run_pm()
        self.assertEqual(self.receipts()["a"]["attempts"][0]["usage"], USED_115)
        self.assertRegex(done.stdout, r"(?m)^ok +115 +1 +\$0\.12$", "the loop prints the totals once when it ends")
        out = self.run_pm("--status").stdout
        self.assertRegex(out, r"(?m)^a +verified +1 +115 +1 +\$0\.12 +", "one row: tokens, turns, estimate")
        self.assertRegex(out, r"(?m)^ok +115 +1 +\$0\.12$")
        self.assertRegex(out, rf"(?m)^total +115 +1 +\$0\.12 +{re.escape(THE_NOTE)}$")
        self.assertNotIn("+?", out, "every attempt reported usage: the sums are the whole")
        self.assertNotIn(pm_run.NO_USAGE, out)

    def test_status_heads_the_money_column_api_estimate_and_says_the_note_once(self):
        self.env["FAKE_PI_USAGE"] = json.dumps(USAGE)
        self.jobs(self.job("a", "ok"))
        self.run_pm()
        out = self.run_pm("--status").stdout
        lines = out.splitlines()
        self.assertRegex(lines[0], r"^job\s+state\s+tries\s+tokens\s+turns\s+API est\.\s+last attempt$")
        self.assertIn(f"{'model':<24}{'tokens':>10}{'turns':>10}{'API est.':>10}", out)
        self.assertEqual(out.count(THE_NOTE), 1, "the note belongs on the total line, not on every row")
        total = next(line for line in lines if line.startswith("total"))
        self.assertTrue(total.endswith(THE_NOTE), f"the total line ends with the note: {total!r}")
        self.assertNotIn("cost", out.replace(THE_NOTE, ""), "no column is headed cost any more")

    def test_status_shows_a_dash_when_no_attempt_reported_usage(self):
        out = self.run_pm("--status").stdout
        self.assertRegex(out, r"(?m)^total +- +- +-$")
        self.assertNotIn(THE_NOTE, out)

    def test_a_run_whose_only_attempts_reported_no_usage_shows_dashes_not_a_partial_sum(self):
        self.jobs(self.job("a", "ok"))
        self.run_pm()
        self.assertNotIn("usage", self.receipts()["a"]["attempts"][0], "no session log, so nothing was reported")
        out = self.run_pm("--status").stdout
        self.assertIn(f"{'ok':<24}{'-':>10}{'-':>10}{'-':>10}", out, "a row where nothing is known stays a dash")
        self.assertRegex(out, r"(?m)^total +- +- +-$")
        self.assertNotIn("+?", out)
        self.assertNotIn(pm_run.NO_USAGE, out, "no sum carries the mark, so the note would explain nothing")


class LockedFileTest(unittest.TestCase):
    """On Windows a rename or a read fails while another process (a --status call, a watcher) holds the file."""

    def setUp(self):
        tmp = Path(tempfile.mkdtemp(prefix="pm_run_lock_"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        self.run = pm_run.Run(tmp)
        self.run.repo = tmp  # nothing a test writes may land in the checkout
        self.addCleanup(patch.stopall)
        patch.object(pm_run.time, "sleep").start()
        patch("sys.stdout", io.StringIO()).start()

    def test_save_waits_for_a_held_receipts_file(self):
        real, calls = os.replace, []

        def held_twice(src, dst):
            calls.append(dst)
            if len(calls) <= 2:
                raise PermissionError(13, "denied")
            real(src, dst)

        with patch.object(pm_run.os, "replace", held_twice):
            self.run.save({"a": {"state": "started"}})
        self.assertEqual(len(calls), 3)
        self.assertEqual(self.run.load("receipts.json", {}), {"a": {"state": "started"}})

    def test_save_that_stays_held_is_logged_and_kept_for_the_next_tick(self):
        with patch.object(pm_run.os, "replace", side_effect=PermissionError(13, "denied")):
            self.run.save({"a": {"state": "started"}})  # must not raise: the loop would die with it
        self.assertIn("SAVE-FAILED", self.run.log_path.read_text(encoding="utf-8"))
        self.run.save({"a": {"state": "verified"}})
        self.assertEqual(self.run.load("receipts.json", {}), {"a": {"state": "verified"}})

    def test_a_held_temporary_file_does_not_end_the_loop(self):
        tmp = self.run.root / "receipts.tmp"
        real = Path.write_text

        def held_tmp(path, *args, **kwargs):
            if path == tmp:
                raise PermissionError(13, "Permission denied", str(tmp))
            return real(path, *args, **kwargs)

        with patch.object(Path, "write_text", held_tmp), patch.object(self.run, "tick"):
            *_, saved = self.run.cycle([], {}, {"a": {"state": "started"}}, True)  # must not raise
        self.assertFalse(saved)
        self.assertIn("SAVE-FAILED receipts.tmp is held", self.run.log_path.read_text(encoding="utf-8"))

    def test_the_same_error_again_after_a_good_read_is_logged_again(self):
        jobs = self.run.root / "jobs.json"
        for text in ('[{"id": "a",', "[]", '[{"id": "a",'):
            jobs.write_text(text, encoding="utf-8")
            self.run.load("jobs.json", [], live=True)
        self.assertEqual(self.run.log_path.read_text(encoding="utf-8").count("SKIPPED jobs.json"), 2)

    def test_load_waits_for_a_file_being_replaced(self):
        (self.run.root / "receipts.json").write_text('{"a": 1}', encoding="utf-8")
        real, calls = Path.read_text, []

        def held_once(path, *args, **kwargs):
            calls.append(path)
            if len(calls) == 1:
                raise PermissionError(13, "the file is being replaced")
            return real(path, *args, **kwargs)

        with patch.object(Path, "read_text", held_once):
            self.assertEqual(self.run.load("receipts.json", {}), {"a": 1})
        self.assertEqual(len(calls), 2)

    def test_after_a_failed_save_the_state_in_memory_stays_the_truth(self):
        self.run.save({"a": {"state": "started"}})

        def finish(jobs, state, caps):
            state["a"]["state"] = "verified"

        with patch.object(self.run, "tick", finish), patch.object(
            pm_run.os, "replace", side_effect=PermissionError(13)
        ):
            jobs, caps, state, saved = self.run.cycle([], {}, {}, True)
        self.assertFalse(saved, "the main loop must not end the run on this pass")
        self.assertEqual(state, {"a": {"state": "verified"}})
        with patch.object(self.run, "tick"):
            jobs, caps, state, saved = self.run.cycle(jobs, caps, state, saved)
        self.assertTrue(saved)
        self.assertEqual(state, {"a": {"state": "verified"}}, "the older file on disk was not read back")
        self.assertEqual(self.run.load("receipts.json", {}), {"a": {"state": "verified"}})

    def test_a_run_file_that_stays_held_keeps_the_last_good_copy(self):
        (self.run.root / "jobs.json").write_text("[]", encoding="utf-8")
        with patch.object(Path, "read_text", side_effect=PermissionError(13, "held")), patch.object(
            self.run, "tick"
        ) as tick:
            jobs, caps, state, saved = self.run.cycle([{"id": "a"}], {"x": 1}, {"a": {}}, True)
            self.run.cycle(jobs, caps, state, saved)
        self.assertEqual((jobs, caps, state), ([{"id": "a"}], {"x": 1}, {"a": {}}))
        self.assertEqual(tick.call_count, 2, "the loop goes on")
        log = self.run.log_path.read_text(encoding="utf-8")
        self.assertEqual(log.count("SKIPPED jobs.json: held by another process"), 1, "logged once per error")
        with self.assertRaises(SystemExit), patch.object(Path, "read_text", side_effect=PermissionError(13)):
            self.run.load("jobs.json", [])  # at start and for --status a clear stop is right


class HerdrSafetyTest(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp(prefix="pm_run_safety_"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        repo_for_in_process_runs(self, tmp)

    def test_only_agent_not_found_means_gone(self):
        run = pm_run.Run(".")
        for code, expected in (("agent_not_found", None), ("server_timeout", "unknown"), ("other", "unknown")):
            with self.subTest(code=code), patch.object(pm_run, "herdr", return_value={"error": {"code": code}}):
                self.assertEqual(run.status_of({"name": "worker"}), expected)

    def test_stop_does_not_confirm_a_failed_pane_close_even_if_agent_is_gone(self):
        run = pm_run.Run(".")
        with patch.object(pm_run, "herdr", return_value={"error": {"code": "timeout"}}), patch.object(
            run, "status_of", return_value=None
        ):
            self.assertFalse(run.stop({"name": "worker", "pane": "p1"}))

    def test_stop_does_not_confirm_a_query_error(self):
        with patch.object(pm_run, "herdr", return_value={"error": {"code": "timeout"}}), patch.object(
            pm_run.time, "sleep"
        ):
            self.assertFalse(pm_run.Run(".").stop({"name": "worker", "pane": "p1"}))

    def test_herdr_timeout_returns_an_error(self):
        with patch.object(pm_run.subprocess, "run", side_effect=subprocess.TimeoutExpired("herdr", 30)) as call:
            result = pm_run.herdr("agent", "get", "worker")
        self.assertIn("timed out", result["error"]["message"])
        self.assertEqual(call.call_args.kwargs["timeout"], 30)

    def test_plain_read_preserves_json_like_output_and_uses_existing_timeout_errors(self):
        response = subprocess.CompletedProcess([], 0, '{"output": 123}', "")
        with patch.object(pm_run.subprocess, "run", return_value=response):
            self.assertEqual(pm_run.herdr("agent", "read", "worker", plain=True), response.stdout)
        response = subprocess.CompletedProcess([], 1, "", '{"error": {"code": "read_failed"}}')
        with patch.object(pm_run.subprocess, "run", return_value=response):
            self.assertEqual(pm_run.herdr("agent", "read", "worker", plain=True)["error"]["code"], "read_failed")
        for error in (subprocess.TimeoutExpired("herdr", 30), OSError("missing binary")):
            with self.subTest(error=error), patch.object(pm_run.subprocess, "run", side_effect=error):
                self.assertIn("error", pm_run.herdr("agent", "read", "worker", plain=True))

    def test_help_prints_the_usage_and_touches_no_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            for flag in ("--help", "-h"):
                result = subprocess.run(
                    [sys.executable, str(PM_RUN), flag], cwd=tmp, capture_output=True, text=True, timeout=10
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("Run worker jobs as visible Herdr agents", result.stdout)
                self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_a_missing_run_folder_is_named_not_a_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [sys.executable, str(PM_RUN), "no-such-run"], cwd=tmp, capture_output=True, text=True, timeout=10
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("pm_run: no run folder", result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_stall_env_overrides_default(self):
        result = subprocess.run(
            [sys.executable, "-c", "from pm_run import STALL_S; print(STALL_S)"],
            cwd=HERE,
            env={**os.environ, "PM_RUN_STALL_S": "12"},
            capture_output=True,
            text=True,
            timeout=3,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "12.0")

    def test_herdr_timeout_env_bounds_a_real_cli_call(self):
        env = {
            **os.environ,
            "PM_RUN_HERDR": json.dumps([sys.executable, "-c", "import time; time.sleep(5)"]),
            "PM_RUN_HERDR_TIMEOUT": "0.1",
        }
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import json; from pm_run import herdr; print(json.dumps(herdr('workspace', 'list')))",
            ],
            cwd=HERE,
            env=env,
            capture_output=True,
            text=True,
            timeout=3,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("timed out after 0.1 s", json.loads(result.stdout)["error"]["message"])

    def test_pi_log_lookup_ignores_old_sessions_and_other_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp).resolve()
            root = repo / "sessions"
            folder = root / ("--" + pm_run.re.sub(r"[/\\:]", "-", str(repo).lstrip("/\\")) + "--")
            folder.mkdir(parents=True)
            attempt = {"name": "worker", "started": time.time()}
            for filename, name, stamp in (
                ("old", "worker", attempt["started"] - 3600),
                ("other", "another-worker", attempt["started"] + 1),
                ("right", "worker", attempt["started"] + 1),
            ):
                entries = [
                    {"type": "session", "timestamp": pm_run.datetime.fromtimestamp(stamp).isoformat()},
                    {"type": "session_info", "name": name},
                    {"type": "message", "message": {"role": "assistant", "stopReason": "error", "errorMessage": "old"}},
                ]
                if filename == "right":
                    entries.append({"type": "message", "message": {"role": "assistant", "stopReason": "length"}})
                (folder / (filename + ".jsonl")).write_text("\n".join(json.dumps(e) for e in entries), encoding="utf-8")
            with patch.dict(os.environ, {"PM_RUN_PI_SESSIONS": str(root)}):
                self.assertEqual(pm_run.turn_end({}, attempt, repo), "Pi stopReason: length")
                self.assertTrue(attempt["session_log"].endswith("right.jsonl"))
                self.assertIsNone(attempt["errorMessage"])
                Path(attempt["session_log"]).unlink()
                self.assertIn("session log not found", pm_run.turn_end({}, attempt, repo))

    def test_every_retry_requires_a_confirmed_stop(self):
        run = pm_run.Run(".")
        for reason in ("hard timeout", "launch failed", "turn settled but no output file", "check exited 1"):
            state = {"state": "started", "attempts": [{"name": "worker"}]}
            with self.subTest(reason=reason), patch.object(run, "stop", return_value=False), patch.object(run, "log"):
                run.fail_or_retry({"id": "a"}, state, reason)
                self.assertEqual(state["state"], "failed")
                self.assertFalse(state["attempts"][0]["stopped_confirmed"])
                self.assertIn("could not be confirmed stopped", state["attempts"][0]["why"])


if __name__ == "__main__":
    unittest.main()
