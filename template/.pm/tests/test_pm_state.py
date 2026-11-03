"""Tests for ``python .pm/tools/pm_state.py``, the project's live state as JSON.

Every test builds a throwaway git repository with Backlog task files, pm_run run folders under .pm/local/runs and,
where Herdr matters, a fake ``herdr`` that prints a fixed snapshot. The scripts are copied into the fixture and run
with ``subprocess`` from its root. Standard library only.
"""

import ast
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent / "tools"
PM_RUN = Path(__file__).resolve().parent.parent / "swarm" / "pm_run.py"
HOUR = 3600


def run_git(repo, *args):
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, encoding="utf-8", check=False)
    if result.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def write_task(root, task_id, title, status, notes=None, updated=None):
    tasks = root / ".pm" / "backlog" / "tasks"
    tasks.mkdir(parents=True, exist_ok=True)
    lines = ["---", f"id: {task_id}", f"title: {title}", f"status: {status}", "created_date: '2026-06-01 09:00'"]
    if updated:
        lines.append(f"updated_date: '{updated}'")
    lines += ["---", "", "## Description", "", f"Fixture task {task_id}.", ""]
    if notes is not None:
        lines += [
            "## Implementation Notes",
            "",
            "<!-- SECTION:NOTES:BEGIN -->",
            notes,
            "<!-- SECTION:NOTES:END -->",
            "",
        ]
    (tasks / f"{task_id.lower()} - fixture.md").write_text("\n".join(lines), encoding="utf-8")


def tree_digest(folder):
    """One hash over every file name and its bytes under a folder."""
    digest = hashlib.sha256()
    for path in sorted(p for p in folder.rglob("*") if p.is_file()):
        digest.update(path.relative_to(folder).as_posix().encode("utf-8") + b"\0" + path.read_bytes())
    return digest.hexdigest()


class StateTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        run_git(self.root, "init", "-b", "main")
        run_git(self.root, "config", "user.name", "Test")
        run_git(self.root, "config", "user.email", "test@example.com")
        (self.root / "backlog.config.yml").write_text("# test fixture\n", encoding="utf-8")
        tools = self.root / ".pm" / "tools"
        tools.mkdir(parents=True)
        for name in ("pm_state.py", "pm_resume.py", "pm_board.py", "pm_open.py"):
            shutil.copy(TOOLS / name, tools / name)
        self.runs = self.root / ".pm" / "local" / "runs"
        self.herdr = json.dumps([sys.executable, str(self.root / "no-herdr-here.py")])  # fails: Herdr not running

    def state(self, *args):
        env = dict(os.environ, PM_RUN_HERDR=self.herdr, PYTHONUTF8="1")
        result = subprocess.run(
            [sys.executable, *args],
            cwd=self.root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def snapshot(self):
        return self.state(".pm/tools/pm_state.py")

    def commit(self, message, name="history.txt"):
        (self.root / name).write_text(message + "\n", encoding="utf-8")
        run_git(self.root, "add", name)
        run_git(self.root, "commit", "-q", "-m", message)

    def run_folder(self, name, jobs, receipts, lease_age=None, written_ago=0):
        run = self.runs / name
        run.mkdir(parents=True)
        (run / "jobs.json").write_text(json.dumps(jobs), encoding="utf-8")
        (run / "receipts.json").write_text(json.dumps(receipts), encoding="utf-8")
        if lease_age is not None:
            (run / "pm_run.lease").write_text(f"4242 {time.time() - lease_age}", encoding="utf-8")
        if written_ago:
            moment = time.time() - written_ago
            os.utime(run / "receipts.json", (moment, moment))
        return run

    def fake_herdr(self, agents):
        script = self.root / "fake_herdr.py"
        reply = {"id": "cli:api:snapshot", "result": {"snapshot": {"agents": agents}, "type": "session_snapshot"}}
        script.write_text(f"import sys\nsys.stdout.write({json.dumps(json.dumps(reply))})\n", encoding="utf-8")
        self.herdr = json.dumps([sys.executable, str(script)])

    def test_open_tasks_carry_their_live_block_and_owner_waits_are_listed(self):
        write_task(self.root, "REQ-1", "Build the thing", "Active", "Next: write it\nBlocker: none\nNeeds owner: none")
        write_task(self.root, "REQ-2", "Ask the owner", "Owner check", "Next: wait\nNeeds owner: try it on Windows")
        write_task(self.root, "REQ-3", "Later", "Ready", "Next: nothing yet")
        self.commit("feat: start\n\nRefs: REQ-1")
        state = self.snapshot()
        self.assertEqual(state["version"], 1)
        self.assertEqual([task["id"] for task in state["tasks"]], ["REQ-1", "REQ-2"])
        first = state["tasks"][0]
        self.assertEqual((first["next"], first["blocker"], first["evidence"]), ("write it", "none", None))
        self.assertEqual(
            state["owner_waits"], [{"task": "REQ-2", "status": "Owner check", "needs": "try it on Windows"}]
        )
        self.assertEqual(state["git"]["branch"], "main")
        self.assertEqual(state["git"]["last_commits"][0]["tasks"], ["REQ-1"])
        self.assertIsNone(state["agents"])  # Herdr did not answer: unknown, not empty

    def test_the_snapshot_writes_nothing_in_the_records(self):
        write_task(self.root, "REQ-1", "Build the thing", "Active", "Next: write it")
        decisions = self.root / ".pm" / "decisions"
        decisions.mkdir(parents=True)
        (decisions / "D-01.md").write_text("---\nid: D-01\n---\n", encoding="utf-8")
        self.commit("feat: start")
        self.run_folder("r1", [{"id": "a", "task": "REQ-1"}], {"a": {"state": "pending", "attempts": []}}, lease_age=1)
        before = [tree_digest(self.root / ".pm" / name) for name in ("backlog", "decisions", "local")]
        status = run_git(self.root, "status", "--porcelain")
        self.snapshot()
        self.state(".pm/tools/pm_board.py", "--state")
        after = [tree_digest(self.root / ".pm" / name) for name in ("backlog", "decisions", "local")]
        self.assertEqual(before, after)
        self.assertEqual(run_git(self.root, "status", "--porcelain"), status)

    def test_jobs_running_and_recently_ended_are_grouped_by_their_task(self):
        write_task(self.root, "REQ-1", "Build the thing", "Active", "Next: write it")
        now = time.time()
        self.commit("feat: start")
        jobs = [
            {"id": "work", "task": "REQ-1", "model": "m1", "harness": "pi", "thinking": "high"},
            {"id": "review", "task": "REQ-1", "model": "m2"},
            {"id": "old", "task": "REQ-1", "model": "m3"},
            {"id": "loose", "model": "m4"},
        ]
        receipts = {
            "_herdr_workspace": "w1",
            "work": {"state": "started", "attempts": [{"started": now - 600, "pane": "w1:p2", "model": "m1"}]},
            "review": {
                "state": "verified",
                "attempts": [
                    {
                        "started": now - HOUR,
                        "ended": now - 60,
                        "artifact": {"words": 812},
                        "verify_rc": 0,
                        "pane": "w1:p3",
                    }
                ],
            },
            "old": {"state": "verified", "attempts": [{"started": now - 50 * HOUR, "ended": now - 49 * HOUR}]},
            "loose": {"state": "pending", "attempts": []},
        }
        self.run_folder("live-run", jobs, receipts, lease_age=5)
        self.run_folder("old-run", [{"id": "x", "task": "REQ-1"}], {"x": {"state": "started"}}, written_ago=48 * HOUR)
        state = self.snapshot()
        found = {job["job"]: job for job in state["jobs"]}
        self.assertEqual(sorted(found), ["loose", "review", "work"])  # the long-ended job and the old run are out
        self.assertEqual(
            (found["work"]["state"], found["work"]["loop"], found["work"]["model"]), ("started", "running", "m1")
        )
        self.assertIsNone(found["work"]["ended"])
        self.assertEqual((found["review"]["words"], found["review"]["check_exit"]), (812, 0))
        self.assertEqual(
            state["workers_by_task"], {"REQ-1": ["live-run/work", "live-run/review"], "(none)": ["live-run/loose"]}
        )
        self.assertEqual(state["tasks"][0]["workers"], ["live-run/work", "live-run/review"])
        ended = [event for event in state["events"] if event["kind"] == "job-ended"]
        if datetime.fromtimestamp(now - 60).date() == datetime.fromtimestamp(now).date():
            self.assertEqual([event["ref"] for event in ended], ["live-run/review"])

    def test_a_job_left_over_by_a_stopped_loop_says_so(self):
        self.commit("feat: start")
        receipts = {"a": {"state": "started", "attempts": [{"started": time.time() - 600}]}}
        self.run_folder("dead-run", [{"id": "a"}], receipts, lease_age=10 * 60)
        self.assertEqual(self.snapshot()["jobs"][0]["loop"], "stopped")

    def test_herdr_agents_in_this_project_are_listed_and_matched_to_their_job(self):
        self.commit("feat: start")
        receipts = {"a": {"state": "started", "attempts": [{"started": time.time() - 60, "pane": "w1:p2"}]}}
        self.run_folder("r1", [{"id": "a", "task": "REQ-9"}], receipts, lease_age=1)
        elsewhere = self.root.parent / "another-project"
        self.fake_herdr(
            [
                {"pane_id": "w1:p2", "agent": "pi", "agent_status": "working", "cwd": str(self.root)},
                {"pane_id": "w1:p3", "agent": "claude", "agent_status": "done", "cwd": str(self.root / "src")},
                {"pane_id": "w2:p1", "agent": "pi", "agent_status": "working", "cwd": str(elsewhere)},
            ]
        )
        agents = self.snapshot()["agents"]
        self.assertEqual(
            [(a["pane"], a["status"], a["job"]) for a in agents],
            [("w1:p2", "working", "r1/a"), ("w1:p3", "done", None)],
        )

    def test_todays_commits_and_closed_tasks_are_events_newest_first(self):
        closed_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        write_task(self.root, "REQ-5", "Finished today", "Done", updated=closed_at.strftime("%Y-%m-%dT%H:%M:00Z"))
        write_task(self.root, "REQ-6", "Finished long ago", "Done", updated="2026-01-02T10:00:00Z")
        self.commit("feat: first")
        self.commit("fix: second", name="other.txt")
        events = self.snapshot()["events"]
        kinds = [(event["kind"], event["ref"] if event["kind"] == "task-closed" else event["what"]) for event in events]
        self.assertIn(("task-closed", "REQ-5"), kinds)
        self.assertNotIn(("task-closed", "REQ-6"), kinds)
        commits = [what for kind, what in kinds if kind == "commit"]
        self.assertEqual(commits, ["fix: second", "feat: first"])
        times = [event["time"] for event in events]
        self.assertEqual(times, sorted(times, reverse=True))

    def test_a_folder_without_git_or_runs_still_answers(self):
        shutil.rmtree(self.root / ".git")
        state = self.snapshot()
        self.assertIsNone(state["git"])
        self.assertEqual((state["tasks"], state["jobs"], state["events"]), ([], [], []))

    @unittest.skipUnless(PM_RUN.exists(), "the swarm layer is not installed")
    def test_ended_states_match_pm_run(self):
        sys.path.insert(0, str(TOOLS))
        try:
            import pm_state
        finally:
            sys.path.remove(str(TOOLS))
        text = PM_RUN.read_text(encoding="utf-8")
        line = next(line for line in text.splitlines() if line.startswith("ENDED = "))
        self.assertEqual(pm_state.ENDED, ast.literal_eval(line.split("=", 1)[1].strip()))


if __name__ == "__main__":
    unittest.main()
