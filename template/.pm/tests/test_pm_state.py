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
from unittest.mock import patch

TOOLS = Path(__file__).resolve().parent.parent / "tools"
PM_RUN = Path(__file__).resolve().parent.parent / "swarm" / "pm_run.py"
HOUR = 3600


def run_git(repo, *args):
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, encoding="utf-8", check=False)
    if result.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def write_task(root, task_id, title, status, notes=None, updated=None, priority=None):
    tasks = root / ".pm" / "backlog" / "tasks"
    tasks.mkdir(parents=True, exist_ok=True)
    lines = ["---", f"id: {task_id}", f"title: {title}", f"status: {status}", "created_date: '2026-06-01 09:00'"]
    if updated:
        lines.append(f"updated_date: '{updated}'")
    if priority:
        lines.append(f"priority: {priority}")
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


def skip_near_midnight(test, minutes=10):
    """A test about "today" cannot hold while the day turns between its setup and the snapshot."""
    clock = datetime.now()
    if clock.hour == 0 and clock.minute < minutes or clock.hour == 23 and clock.minute >= 60 - minutes:
        test.skipTest("too close to midnight for a test about today")


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

    def commit(self, message, name="history.txt", when=None, authored=None):
        """A commit; `when` and `authored` are git dates ('@<epoch> <offset>') for the committer and the author."""
        (self.root / name).write_text(message + "\n", encoding="utf-8")
        run_git(self.root, "add", name)
        env = dict(os.environ)
        if when:
            env["GIT_COMMITTER_DATE"] = when
        if authored:
            env["GIT_AUTHOR_DATE"] = authored
        result = subprocess.run(
            ["git", "commit", "-q", "-m", message], cwd=self.root, capture_output=True, text=True, env=env, check=False
        )
        self.assertEqual(result.returncode, 0, result.stderr)

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

    def detail(self, *args):
        return self.state(".pm/tools/pm_state.py", *args)["found"]

    def test_a_task_opens_in_full_and_a_closed_one_too(self):
        tasks = self.root / ".pm" / "backlog" / "tasks"
        tasks.mkdir(parents=True)
        (tasks / "req-7 - x.md").write_text(
            "---\nid: REQ-7\ntitle: Seven\nstatus: Active\npriority: high\nparent_task_id: REQ-1\n---\n\n"
            "## Description\n\n<!-- SECTION:DESCRIPTION:BEGIN -->\nWhy it exists\n<!-- SECTION:DESCRIPTION:END -->\n\n"
            "## Acceptance Criteria\n<!-- AC:BEGIN -->\n- [x] #1 Done one\n- [ ] #2 Open one\n<!-- AC:END -->\n\n"
            "## Implementation Notes\n\n<!-- SECTION:NOTES:BEGIN -->\nNext: go\n<!-- SECTION:NOTES:END -->\n\n"
            "## Final Summary\n\n<!-- SECTION:FINAL_SUMMARY:BEGIN -->\nEnded well\n<!-- SECTION:FINAL_SUMMARY:END -->\n",
            encoding="utf-8",
        )
        closed = self.root / ".pm" / "backlog" / "completed"
        closed.mkdir(parents=True)
        (closed / "req-8 - x.md").write_text("---\nid: REQ-8\ntitle: Eight\nstatus: Done\n---\n", encoding="utf-8")
        task = self.detail("--task", "req-7")
        self.assertEqual((task["id"], task["priority"], task["parent"]), ("REQ-7", "high", "REQ-1"))
        self.assertEqual(task["description"], "Why it exists")
        self.assertEqual(task["notes"], "Next: go")
        self.assertEqual(task["summary"], "Ended well")
        self.assertEqual(task["criteria"], [{"done": True, "text": "Done one"}, {"done": False, "text": "Open one"}])
        self.assertEqual(self.detail("--task", "REQ-8")["status"], "Done")
        self.assertIsNone(self.detail("--task", "REQ-9"))

    def test_a_job_says_what_it_does_who_started_it_and_what_it_used(self):
        brief = self.runs / "r" / "brief.md"
        jobs = [
            {
                "id": "a",
                "model": "m/sol",
                "lead": "Claude Opus 5.5",
                "briefs": [".pm/local/runs/r/brief.md"],
                "out": ".pm/local/runs/r/out.md",
            }
        ]
        attempt = {"name": "n", "started": time.time() - 60, "ended": time.time(), "pane": "w1:p1"}
        attempt["usage"] = {"total_tokens": 10, "turns": 2, "cost_usd": 0.5}
        run = self.run_folder(
            "r",
            jobs,
            {"_started_by": {"tool": "Claude Code", "pane": None}, "a": {"state": "verified", "attempts": [attempt]}},
        )
        brief.write_text("---\n\n# Review the page\n\nBody\n", encoding="utf-8")
        (run / "out.md").write_text("Findings", encoding="utf-8")
        (run / "pm_run.log").write_text("01:00 a: started\n01:01 other: started\n", encoding="utf-8")
        job = self.snapshot()["jobs"][0]
        self.assertEqual(job["brief"], "Review the page")
        self.assertEqual((job["tokens"], job["turns"], job["cost_usd"]), (10, 2, 0.5))
        self.assertEqual(job["started_by"]["tool"], "Claude Code")
        self.assertEqual(job["started_by"]["lead"], "Claude Opus 5.5")
        found = self.detail("--job", "r/a")
        self.assertEqual(found["title"], "Review the page")
        self.assertEqual(found["result"], {"text": "Findings", "cut": False})
        self.assertIn("Body", found["briefs"][0]["text"])
        self.assertEqual(found["log"], "01:00 a: started")
        self.assertEqual(found["tokens"], 10)

    def test_a_helper_names_the_job_whose_pane_started_it(self):
        def job(name):
            return [{"id": name, "model": "m", "briefs": [], "out": "x"}]

        now = time.time()
        self.run_folder("lead", job("w"), {"w": {"state": "working", "attempts": [{"started": now, "pane": "w1:p2"}]}})
        self.run_folder(
            "help",
            job("h"),
            {"_started_by": {"tool": "pi", "pane": "w1:p2"}, "h": {"state": "working", "attempts": [{"started": now}]}},
        )
        jobs = {item["job"]: item for item in self.snapshot()["jobs"]}
        self.assertEqual(jobs["h"]["started_by"]["by_job"], "lead/w")
        self.assertIsNone(jobs["w"]["started_by"])

    def test_a_detail_reads_nothing_outside_the_project(self):
        outside = Path(self._tmp.name).parent / f"outside-{os.getpid()}.md"
        outside.write_text("secret", encoding="utf-8")
        self.addCleanup(outside.unlink)
        jobs = [{"id": "a", "model": "m", "briefs": [str(outside)], "out": f"../../../../{outside.name}"}]
        self.run_folder("r", jobs, {})
        found = self.detail("--job", "r/a")
        self.assertEqual(found["briefs"], [])
        self.assertIsNone(found["result"])
        self.assertIsNone(self.detail("--job", "../r/a"))
        self.assertIsNone(self.detail("--job", "r/none"))

    def link_folder(self, link, target):
        """A folder link: a junction on Windows, which needs no special right, else a symlink."""
        if os.name == "nt":
            subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True, check=True)
            self.addCleanup(os.rmdir, link)  # removes the junction only, never what it points to
        else:
            link.symlink_to(target, target_is_directory=True)

    def test_a_linked_run_folder_that_leaves_the_project_is_not_read(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as outside:
            away = Path(outside)
            (away / "jobs.json").write_text(json.dumps([{"id": "a", "model": "secret"}]), encoding="utf-8")
            (away / "receipts.json").write_text("{}", encoding="utf-8")
            self.runs.mkdir(parents=True)
            self.link_folder(self.runs / "linked", away)
            self.assertIsNone(self.detail("--job", "linked/a"))

    def test_usage_adds_up_the_attempts_and_says_when_one_is_missing(self):
        paid = {
            "started": time.time() - 90,
            "ended": time.time() - 60,
            "usage": {"total_tokens": 10, "turns": 2, "cost_usd": 0.5},
        }
        jobs = [{"id": "a", "model": "m", "briefs": [], "out": "x"}]
        self.run_folder("r", jobs, {"a": {"state": "failed", "attempts": [paid, {"started": time.time() - 30}, paid]}})
        found = self.detail("--job", "r/a")
        self.assertEqual((found["tokens"], found["cost_usd"], found["usage_partial"]), (20, 1.0, True))
        listed = self.snapshot()["jobs"][0]
        self.assertEqual((listed["tokens"], listed["cost_usd"], listed["usage_partial"]), (20, 1.0, True))

    def test_open_tasks_carry_their_live_block_and_owner_waits_are_listed(self):
        write_task(self.root, "REQ-1", "Build the thing", "Active", "Next: write it\nBlocker: none\nNeeds owner: none")
        write_task(self.root, "REQ-2", "Ask the owner", "Owner check", "Next: wait\nNeeds owner: try it on Windows")
        write_task(self.root, "REQ-3", "Later", "Ready", "Next: nothing yet")
        self.commit("feat: start\n\nRefs: REQ-1")
        state = self.snapshot()
        self.assertEqual(state["version"], 2)
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

    def test_waiting_puts_stuck_work_first_then_the_oldest(self):
        write_task(self.root, "REQ-1", "Decide later", "Active", "Needs owner: pick one", "2026-10-02 10:00")
        write_task(self.root, "REQ-2", "Decide first", "Ready", "Needs owner: pick two", "2026-10-01 10:00")
        write_task(self.root, "REQ-3", "Look at this", "Owner check", "Next: try it", "2026-10-03 10:00")
        write_task(self.root, "REQ-4", "Just work", "Active", "Next: go on\nNeeds owner: none")
        attempt = {"started": time.time() - 60, "ended": time.time() - 30, "why": "stuck on a plan screen"}
        self.run_folder("r1", [{"id": "a", "task": "REQ-1"}], {"a": {"state": "handed-over", "attempts": [attempt]}})
        self.fake_herdr(
            [
                {
                    "pane_id": "p",
                    "name": "x",
                    "agent": "pi",
                    "agent_status": "blocked",
                    "title": "Allow?",
                    "cwd": str(self.root),
                }
            ]
        )
        cards = self.snapshot()["waiting"]
        self.assertEqual(
            [(c["kind"], c["ref"]) for c in cards],
            [("stuck", "REQ-1"), ("stuck", None), ("decision", "REQ-2"), ("decision", "REQ-1"), ("review", "REQ-3")],
        )
        self.assertEqual(cards[0]["text"], "stuck on a plan screen")
        self.assertEqual(cards[0]["tool"], "agents")
        self.assertEqual(cards[2]["text"], "pick two")
        self.assertEqual(cards[4]["text"], "try it")
        self.assertEqual(cards[4]["tool"], "board")

    def test_a_job_that_ended_well_waits_for_nobody(self):
        attempt = {"started": time.time() - 60, "ended": time.time() - 30}
        self.run_folder("r1", [{"id": "a"}], {"a": {"state": "verified", "attempts": [attempt]}})
        self.assertEqual(self.snapshot()["waiting"], [])

    def test_the_board_is_every_open_task_by_priority_then_the_last_closed(self):
        write_task(self.root, "REQ-1", "No priority", "Ready", "Blocker: none")
        write_task(self.root, "REQ-2", "Low", "Ready", priority="low")
        write_task(self.root, "REQ-3", "High", "Active", "Blocker: the tool is down\nNeeds owner: say", priority="high")
        write_task(self.root, "REQ-4", "Medium", "Ready", priority="medium")
        for number in range(5, 12):
            write_task(self.root, f"REQ-{number}", f"Closed {number}", "Done", updated=f"2026-10-{number:02d} 10:00")
        rows = self.snapshot()["board"]
        self.assertEqual(
            [r["id"] for r in rows],
            ["REQ-3", "REQ-4", "REQ-2", "REQ-1", "REQ-11", "REQ-10", "REQ-9", "REQ-8", "REQ-7"],
        )
        self.assertTrue(rows[0]["waiting"])
        self.assertFalse(rows[1]["waiting"])
        self.assertEqual(rows[0]["blocker"], "the tool is down")
        self.assertEqual(rows[0]["priority"], "high")
        self.assertIsNone(rows[3]["priority"])
        self.assertIsNone(rows[3]["blocker"], "`Blocker: none` blocks nothing")

    def test_soon_is_the_nearest_review_dates_of_open_tasks(self):
        write_task(self.root, "REQ-1", "Later", "Ready", "Review by: 2026-12-02 · the owner · a reason")
        write_task(self.root, "REQ-2", "Sooner", "Active", "Review by: 2026-12-01 · the owner · a reason")
        write_task(self.root, "REQ-3", "Closed", "Done", "Review by: 2026-11-01 · the owner · a reason")
        self.assertEqual(
            self.snapshot()["soon"],
            [
                {"date": "2026-12-01", "what": "Sooner", "ref": "REQ-2"},
                {"date": "2026-12-02", "what": "Later", "ref": "REQ-1"},
            ],
        )

    def test_jobs_running_and_recently_ended_are_grouped_by_their_task(self):
        write_task(self.root, "REQ-1", "Build the thing", "Active", "Next: write it")
        now = time.time()
        self.commit("feat: start")
        jobs = [
            {"id": "work", "task": "REQ-1", "model": "m1", "harness": "pi", "thinking": "high"},
            {"id": "review", "task": "REQ-1", "model": "m2"},
            {"id": "old", "task": "REQ-1", "model": "m3"},
            {"id": "loose", "model": "m4"},
            {"id": "early", "task": "REQ-1", "model": "m5"},
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
            "early": {"state": "failed", "why": "PREFLIGHT: brief not found", "attempts": []},
        }
        self.run_folder("live-run", jobs, receipts, lease_age=5)
        self.run_folder("old-run", [{"id": "x", "task": "REQ-1"}], {"x": {"state": "started"}}, written_ago=48 * HOUR)
        state = self.snapshot()
        found = {job["job"]: job for job in state["jobs"]}
        # the long-ended job and the old run are out; a job that failed before any worker started is in
        self.assertEqual(sorted(found), ["early", "loose", "review", "work"])
        self.assertEqual((found["early"]["ended"], found["early"]["why"]), (None, "PREFLIGHT: brief not found"))
        self.assertEqual(
            (found["work"]["state"], found["work"]["lease"], found["work"]["model"]), ("started", "fresh", "m1")
        )
        self.assertIsNone(found["work"]["ended"])
        self.assertEqual((found["review"]["words"], found["review"]["check_exit"]), (812, 0))
        self.assertEqual(
            state["workers_by_task"],
            {"REQ-1": ["live-run/work", "live-run/review", "live-run/early"], "(none)": ["live-run/loose"]},
        )
        self.assertEqual(state["tasks"][0]["workers"], ["live-run/work", "live-run/review", "live-run/early"])
        ended = [event for event in state["events"] if event["kind"] == "job-ended"]
        if datetime.fromtimestamp(now - 60).date() == datetime.fromtimestamp(now).date():
            self.assertEqual([event["ref"] for event in ended], ["live-run/review"])

    def test_unreadable_receipts_leave_the_state_unknown_and_a_bom_is_read(self):
        self.commit("feat: start")
        broken = self.run_folder("broken", [{"id": "a"}], {}, lease_age=1)
        (broken / "receipts.json").write_text('{"a": {"state": "star', encoding="utf-8")
        bom = self.run_folder("bom", [{"id": "b"}], {}, lease_age=1)
        (bom / "receipts.json").write_text('{"b": {"state": "verified"}}', encoding="utf-8-sig")
        found = {job["job"]: job["state"] for job in self.snapshot()["jobs"]}
        self.assertEqual(found, {"a": None, "b": "verified"})

    def test_a_job_left_over_by_a_dead_loop_has_a_stale_lease(self):
        self.commit("feat: start")
        receipts = {"a": {"state": "started", "attempts": [{"started": time.time() - 600}]}}
        self.run_folder("dead-run", [{"id": "a"}], receipts, lease_age=10 * 60)
        self.assertEqual(self.snapshot()["jobs"][0]["lease"], "stale")

    def test_herdr_agents_in_this_project_are_listed_and_matched_to_their_job(self):
        self.commit("feat: start")
        attempt = {"started": time.time() - 60, "pane": "w1:p2", "name": "run-a-1-ab12"}
        self.run_folder(
            "r1", [{"id": "a", "task": "REQ-9"}], {"a": {"state": "started", "attempts": [attempt]}}, lease_age=1
        )
        left = {"started": time.time() - 600, "pane": "w1:p4", "name": "run-b-1-cd34"}
        self.run_folder("dead", [{"id": "b"}], {"b": {"state": "started", "attempts": [left]}}, lease_age=10 * 60)
        elsewhere = self.root.parent / (self.root.name + "-copy")  # a sibling whose name starts with ours
        self.fake_herdr(
            [
                {
                    "pane_id": "w1:p2",
                    "name": "run-a-1-ab12",
                    "agent": "pi",
                    "agent_status": "working",
                    "cwd": str(self.root),
                },
                {"pane_id": "w1:p3", "agent": "claude", "agent_status": "done", "cwd": str(self.root / "src")},
                {
                    "pane_id": "w1:p4",
                    "name": "run-b-1-cd34",
                    "agent": "pi",
                    "agent_status": "idle",
                    "cwd": str(self.root),
                },
                {"pane_id": "w2:p1", "agent": "pi", "agent_status": "working", "cwd": str(elsewhere)},
            ]
        )
        agents = self.snapshot()["agents"]
        # the agent name is unique to the attempt, so it names its job even under a stale lease: a slow tick of a live
        # loop, or a worker left over by a dead one, which is still that job's worker
        self.assertEqual(
            [(a["pane"], a["status"], a["job"]) for a in agents],
            [("w1:p2", "working", "r1/a"), ("w1:p3", "done", None), ("w1:p4", "idle", "dead/b")],
        )

    def test_a_reused_pane_is_not_matched_to_the_old_job(self):
        self.commit("feat: start")
        attempt = {"started": time.time() - 60, "pane": "w1:p2", "name": "run-a-1-ab12"}
        self.run_folder("r1", [{"id": "a"}], {"a": {"state": "started", "attempts": [attempt]}}, lease_age=1)
        self.fake_herdr([{"pane_id": "w1:p2", "name": "someone-else", "agent": "claude", "cwd": str(self.root)}])
        self.assertIsNone(self.snapshot()["agents"][0]["job"])

    def test_todays_commits_and_closed_tasks_are_events_newest_first(self):
        skip_near_midnight(self)
        now = time.time()
        closed_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        write_task(self.root, "REQ-5", "Finished today", "Done", updated=closed_at.strftime("%Y-%m-%dT%H:%M:00Z"))
        write_task(self.root, "REQ-6", "Finished long ago", "Done", updated="2026-01-02T10:00:00Z")
        # Both committed today, the earlier in a far-west offset and the later in a far-east one: as text the west
        # one would sort as newer. The second was authored days ago and landed today, as a rebase does.
        self.commit("feat: first\n\nRefs: none", when=f"@{int(now - 120)} -0500")
        self.commit(
            "fix: second", name="other.txt", when=f"@{int(now - 60)} +0900", authored=f"@{int(now - 72 * HOUR)} +0300"
        )
        state = self.snapshot()
        events = state["events"]
        kinds = [(event["kind"], event["ref"] if event["kind"] == "task-closed" else event["what"]) for event in events]
        self.assertIn(("task-closed", "REQ-5"), kinds)
        self.assertNotIn(("task-closed", "REQ-6"), kinds)
        commits = [what for kind, what in kinds if kind == "commit"]
        self.assertEqual(commits, ["fix: second", "feat: first"])
        moments = [datetime.fromisoformat(event["time"]).timestamp() for event in events]
        self.assertEqual(moments, sorted(moments, reverse=True))
        offset = datetime.now().astimezone().isoformat()[-6:]
        self.assertTrue(all(event["time"].endswith(offset) for event in events))  # one clock for the reader
        self.assertEqual([c["tasks"] for c in state["git"]["last_commits"]], [[], []])  # `Refs: none` is no task

    def test_a_folder_without_git_or_runs_still_answers(self):
        shutil.rmtree(self.root / ".git")
        state = self.snapshot()
        self.assertIsNone(state["git"])
        self.assertEqual((state["tasks"], state["jobs"], state["events"]), ([], [], []))

    def test_a_new_repository_has_git_and_no_commits(self):
        state = self.snapshot()
        self.assertEqual((state["git"]["last_commits"], state["events"]), ([], []))

    def test_a_git_call_that_does_not_answer_leaves_git_unknown(self):
        sys.path.insert(0, str(TOOLS))
        try:
            import pm_resume
            import pm_state
        finally:
            sys.path.remove(str(TOOLS))

        def slow(hang):
            """git status answers; the git log call named by `hang` times out."""

            def run(command, **options):
                if "status" in command:
                    return subprocess.CompletedProcess(command, 0, "## main\n", "")
                if hang in command:
                    raise subprocess.TimeoutExpired(command, options["timeout"])
                return subprocess.CompletedProcess(command, 0, "", "")

            return run

        for hang in ("-5", "--since=midnight"):
            with self.subTest(hang=hang), patch.object(pm_resume.subprocess, "run", side_effect=slow(hang)) as run:
                self.assertEqual(pm_state.git_state(), (None, None))  # unknown, never an empty history
                self.assertTrue(all(call.kwargs["timeout"] == pm_state.GIT_TIMEOUT for call in run.call_args_list))
        hung = subprocess.TimeoutExpired(["git"], pm_state.GIT_TIMEOUT)
        with patch.object(pm_resume.subprocess, "run", side_effect=hung):
            self.assertEqual(pm_state.git_state(), (None, None))
            self.assertEqual(pm_resume.commits("-5"), [])  # the old callers still get an empty list

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
