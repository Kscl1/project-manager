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

import importlib.util
import json
import os
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
    if behaviour == "nostart":
        fail("agent_not_ready", "pi did not become ready")
    state["agents"][name] = {"pane": opt("--pane"), "behaviour": behaviour, "argv": args, "prompts": [], "prompted": 0}
    reply({"type": "agent_started", "agent": {"name": name, "agent_status": "idle"}})
if cmd == ["agent", "prompt"]:
    name, text = args[2], args[3]
    agent = state["agents"].get(name)
    if not agent:
        fail("agent_not_found", name)
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


class PmRunFixture:
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="pm_run_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.run_dir = self.tmp / "run"
        self.run_dir.mkdir()
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
        started = herdr["gone"]["run-a-1"]
        self.assertIn("--kind", started["argv"])
        self.assertEqual(started["argv"][started["argv"].index("--thinking") + 1], "medium")
        self.assertIn("brief.md", started["prompts"][0])
        self.assertEqual(herdr["workspaces"], [], "the run's workspace is closed at the end")

    def test_claude_harness_runs_the_setup_line_then_starts_claude_code(self):
        self.jobs(self.job("a", "ok", harness="claude", setup="$env:X=1", args=["--permission-mode", "acceptEdits"]))
        self.run_pm()
        self.assertEqual(self.receipts()["a"]["state"], "verified")
        herdr = self.herdr_state()
        argv = herdr["gone"]["run-a-1"]["argv"]
        self.assertEqual(argv[argv.index("--kind") + 1], "claude")
        settings = argv[argv.index("--settings") + 1]
        self.assertEqual(
            argv[argv.index("--") + 1 :],
            ["--model", "ok", "--disallowedTools", "Agent,Workflow", "--settings", settings]
            + ["--permission-mode", "acceptEdits"],
        )
        # The project's MCP servers start without the approval dialog that would swallow the brief.
        self.assertEqual(json.loads(Path(settings).read_text(encoding="utf-8")), {"enableAllProjectMcpServers": True})
        self.assertEqual(herdr["ran"], [[herdr["gone"]["run-a-1"]["pane"], "$env:X=1"]])

    def test_pi_is_the_default_harness_and_runs_no_setup(self):
        self.jobs(self.job("a", "ok"))
        self.run_pm()
        herdr = self.herdr_state()
        argv = herdr["gone"]["run-a-1"]["argv"]
        self.assertEqual(argv[argv.index("--kind") + 1], "pi")
        self.assertEqual(argv[argv.index("--exclude-tools") + 1], "Agent,SubagentWorkflow")
        self.assertEqual(self.receipts()["a"]["attempts"][0]["model"], "ok")
        self.assertNotIn("ran", herdr)
        self.assertIn("Write only that file. ", herdr["gone"]["run-a-1"]["prompts"][0])

    def test_writes_lets_the_worker_write_more_than_its_output(self):
        self.jobs(self.job("a", "ok", writes=["site/", "notes/x.md"]))
        self.run_pm()
        prompt = self.herdr_state()["gone"]["run-a-1"]["prompts"][0]
        self.assertIn("Write only that file and the paths site/, notes/x.md. ", prompt)

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

    def test_invalid_jobs_file_stops_with_the_parse_error(self):
        (self.run_dir / "jobs.json").write_text('[{"id": "a",]', encoding="utf-8")
        result = self.run_pm(timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("jobs.json is not valid JSON", result.stderr)
        self.assertNotIn("pm_run start", result.stdout)
        self.assertFalse(self.fake_state.exists(), "no worker may start")

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
        prompts = self.herdr_state()["gone"]["run-a-1"]["prompts"]
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
        prompts = self.herdr_state()["gone"]["run-a-1"]["prompts"]
        self.assertEqual(prompts[0], prompts[1])
        self.assertIn("Read the brief file(s) brief.md", prompts[1])
        self.assertIn("and the paths code/", prompts[1])
        self.assertIn("PROMPT a: no turn ran after the brief was sent; brief resent", result.stdout)
        self.assertNotIn("RESUME a:", result.stdout)
        calls = self.herdr_state()["calls"]
        first_prompt = next(i for i, c in enumerate(calls) if c[:2] == ["agent", "prompt"])
        self.assertEqual(calls[first_prompt - 1][:2], ["agent", "get"])

    def test_lost_brief_behind_a_used_up_quota_is_not_resent(self):
        screen = "> Read the brief file(s) brief.md\n  API Error: 429 usage limit reached for cx/gpt-6-astra\n"
        empty = {"n": 0, "workspaces": [], "agents": {}, "gone": {}, "closed": []}
        self.fake_state.write_text(json.dumps({**empty, "reads": [screen]}), encoding="utf-8")
        self.jobs(self.job("a", "lost", harness="claude"))
        result = self.run_pm()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.receipts()["a"]["state"], "handed-over")
        self.assertEqual(len(self.herdr_state()["agents"]["run-a-1"]["prompts"]), 1)
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
        self.assertIn("run-a-1", self.herdr_state()["agents"], "the session stays open for the lead")
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
        self.assertIn("run-a-1", self.herdr_state()["agents"])
        self.assertIn("WAITING a", (self.run_dir / "pm_run.log").read_text(encoding="utf-8"))

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
        self.assertIn("could not keep previous output; no retry", run.log_path.read_text(encoding="utf-8"))

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
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            run.tick([self.job("a", "nothing")], state, {})
        return self.herdr_state()["agents"]["worker"]["prompts"]

    def test_settled_turn_inside_pis_retry_wait_is_held_not_nudged(self):
        run, _, attempt, state = self.settled_worker()
        consts = {"QUIET_S": 90, "MAX_NUDGES": 3}
        self.assertEqual(len(self.tick_at(run, state, 1030, **consts)), 1, "Pi wrote its log 30 s ago: no nudge")
        self.assertEqual(state["a"]["state"], "started")
        self.assertIn("HOLD a: turn looks settled but Pi wrote its log 30 s ago", run.log_path.read_text("utf-8"))
        prompts = self.tick_at(run, state, 1100, **consts)
        self.assertEqual(len(prompts), 2, "quiet for 100 s: Pi has stopped, so the same session is nudged")
        self.assertIn("previous turn ended", prompts[-1])
        self.assertEqual(attempt["nudges"], 1)

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
                ), patch.object(pm_run.time, "time", return_value=100), patch.object(pm_run, "MAX_NUDGES", 1):
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
        self.assertIn("stall=True", printed.call_args.args[0])
        self.assertIn("loop=False", printed.call_args.args[0])

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


class HerdrSafetyTest(unittest.TestCase):
    def test_only_agent_not_found_means_gone(self):
        run = pm_run.Run(".")
        for code, expected in (("agent_not_found", None), ("server_timeout", "unknown"), ("other", "unknown")):
            with self.subTest(code=code), patch.object(pm_run, "herdr", return_value={"error": {"code": code}}):
                self.assertEqual(run.status_of({"name": "worker"}), expected)

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
