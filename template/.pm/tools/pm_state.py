"""Print one project's live state as JSON, for the project window and any other reader. Standard library only.

Usage: python .pm/tools/pm_board.py --state
       python .pm/tools/pm_state.py

The state is computed on each call from what is already there, and the call writes nothing:
- Backlog task files: the open tasks (Active, In review, Owner check) with their live block, and what waits on the owner;
- pm_run receipts under .pm/local/runs: jobs not ended yet, and jobs that ended in the last 24 hours. Only run
  folders whose receipts.json changed in that time are read: an older run has nothing recent to show, and reading
  every run folder of a long-lived project takes most of a second;
- Herdr's live snapshot (`herdr api snapshot`): the agents working in this project's folder or below it;
- git: branch, changed files, last commits.
`events` lists today's commits, closed tasks and ended jobs, newest first. A job's optional `task` field in jobs.json
names the task it works for; `workers_by_task` groups the jobs by it. A job's `loop` says whether its pm_run loop is
still alive (its lease is fresh): a job that is not ended under a stopped loop is left over, not running.
A source that cannot be read is null (`agents` when Herdr is not installed or not running, `git` outside a repo),
never a guess.
"""

import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pm_resume  # noqa: E402  (a sibling script, which already reads the tasks and git)

ROOT = pm_resume.ROOT
RUNS_DIR = ROOT / ".pm" / "local" / "runs"
VERSION = 1  # the shape of the JSON; a reader checks it before it trusts the keys
RECENT_S = 24 * 3600
# pm_run's ended states (pm_run.ENDED; a test keeps the two in step). Any other state is not ended yet.
ENDED = ("verified", "artifact-present", "check-failed", "handed-over", "failed", "blocked", "stopped")
# pm_run's loop rewrites pm_run.lease every tick (PM_RUN_TICK, 15 s) and treats it as silent after three ticks.
LEASE_FRESH_S = 3 * float(os.environ.get("PM_RUN_TICK", 15))
NO_TASK = "(none)"
# Herdr as pm_run finds it: PM_RUN_HERDR (tests pass a JSON command list), else `herdr` on PATH.
HERDR = os.environ.get("PM_RUN_HERDR") or shutil.which("herdr") or "herdr"
HERDR_CMD = json.loads(HERDR) if HERDR.startswith("[") else [HERDR]
HERDR_TIMEOUT = 5


def stamp(seconds):
    """Seconds since the epoch as local ISO time, or None."""
    if not isinstance(seconds, (int, float)):
        return None
    return datetime.fromtimestamp(seconds).astimezone().isoformat(timespec="seconds")


def local_time(updated):
    """Backlog's UTC updated_date ('2026-10-13 00:05' or '2026-10-13T00:05:00Z') as local ISO time, or None."""
    try:
        moment = datetime.strptime(updated[:16].replace("T", " "), "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return moment.astimezone().isoformat(timespec="seconds")


def live_value(value):
    """A live-block line the task does not carry, or carries empty, is null."""
    return None if value in (None, "?") else value


def read_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def loop_alive(run_dir, now):
    try:
        _pid, written = (run_dir / "pm_run.lease").read_text().split()
        return now - float(written) < LEASE_FRESH_S
    except (OSError, ValueError):
        return False


def recent_jobs(now):
    """Jobs not ended yet and jobs that ended in the last RECENT_S, from run folders written in that time."""
    jobs = []
    try:
        receipts = sorted(RUNS_DIR.glob("*/receipts.json"), key=lambda path: path.parent.name.casefold())
    except OSError:
        return jobs
    for path in receipts:
        try:
            if now - path.stat().st_mtime > RECENT_S:
                continue
        except OSError:
            continue
        run = path.parent
        state, listed = read_json(path, {}), read_json(run / "jobs.json", [])
        if not isinstance(state, dict) or not isinstance(listed, list):
            continue
        alive = loop_alive(run, now)
        for job in listed:
            if not isinstance(job, dict) or not isinstance(job.get("id"), str):
                continue
            receipt = state.get(job["id"]) if isinstance(state.get(job["id"]), dict) else {}
            attempts = [a for a in receipt.get("attempts") or [] if isinstance(a, dict)]
            last = attempts[-1] if attempts else {}
            job_state = receipt.get("state", "pending")
            ended = last.get("ended")
            if job_state in ENDED and not (isinstance(ended, (int, float)) and now - ended <= RECENT_S):
                continue
            artifact = last.get("artifact") if isinstance(last.get("artifact"), dict) else {}
            jobs.append(
                {
                    "run": run.name,
                    "job": job["id"],
                    "task": job["task"] if isinstance(job.get("task"), str) and job["task"].strip() else None,
                    "state": job_state,
                    "loop": "running" if alive else "stopped",
                    "model": last.get("model") or job.get("model"),
                    "harness": job.get("harness", "pi"),
                    "thinking": job.get("thinking"),
                    "attempts": len(attempts),
                    "started": stamp(last.get("started")),
                    "ended": stamp(ended) if job_state in ENDED else None,
                    "words": artifact.get("words"),
                    "check_exit": last.get("verify_rc"),
                    "pane": last.get("pane"),
                }
            )
    return jobs


def inside(path, root_key):
    key = pm_resume.path_key(Path(path))
    return key == root_key or key.startswith(root_key.rstrip(os.sep) + os.sep)


def herdr_agents(jobs):
    """The Herdr agents whose folder is this project or below it, or None when Herdr does not answer."""
    try:
        result = subprocess.run(
            [*HERDR_CMD, "api", "snapshot"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=HERDR_TIMEOUT,
            check=False,
        )
        snapshot = json.loads(result.stdout)["result"]["snapshot"]
        listed = snapshot.get("agents") or []
    except (OSError, subprocess.TimeoutExpired, ValueError, KeyError, TypeError, AttributeError):
        return None
    root_key = pm_resume.path_key(ROOT)
    # a pane that a job still uses names the job; an ended job's pane may hold someone else by now
    panes = {job["pane"]: f"{job['run']}/{job['job']}" for job in jobs if job["pane"] and job["state"] not in ENDED}
    agents = []
    for agent in listed:
        cwd = agent.get("cwd") if isinstance(agent, dict) else None
        if not cwd or not inside(cwd, root_key):
            continue
        agents.append(
            {
                "pane": agent.get("pane_id"),
                "agent": agent.get("display_agent") or agent.get("agent"),
                "status": agent.get("agent_status"),
                "title": agent.get("title"),
                "cwd": cwd,
                "job": panes.get(agent.get("pane_id")),
            }
        )
    return agents


def commit_entry(commit):
    return {"sha": commit["sha"], "time": commit["time"], "subject": commit["subject"], "tasks": sorted(commit["refs"])}


def git_state():
    """Branch line, changed files and the last five commits; None outside a git repository."""
    # --no-optional-locks: a reader that runs often must not rewrite the index
    status = pm_resume.git_stdout(["--no-optional-locks", "status", "--porcelain=v1", "-b"], None)
    if status is None:
        return None
    lines = status.splitlines()
    branch = lines[0][3:] if lines and lines[0].startswith("## ") else None
    return {
        "branch": branch,
        "changed": [line for line in lines if not line.startswith("## ")],
        "last_commits": [commit_entry(commit) for commit in pm_resume.commits("-5")],
    }


def task_entry(task, by_task):
    live = task["live"]
    return {
        "id": task["id"],
        "title": task["title"],
        "status": task["status"],
        "parent": task["parent"] or None,
        "next": live_value(live["Next"]),
        "evidence": live_value(live["Evidence"]),
        "blocker": live_value(live["Blocker"]),
        "needs_owner": live_value(live["Needs owner"]),
        "workers": by_task.get(task["id"], []),
    }


def events(today, tasks, jobs, todays_commits):
    """Today's commits, closed tasks and ended jobs, newest first."""
    found = [{"time": c["time"], "kind": "commit", "what": c["subject"], "ref": c["sha"]} for c in todays_commits]
    for task in tasks:
        if task["status"] == "Done" and pm_resume.local_day(task["updated"]) == today:
            found.append(
                {"time": local_time(task["updated"]), "kind": "task-closed", "what": task["title"], "ref": task["id"]}
            )
    for job in jobs:
        if job["ended"] and job["ended"][:10] == today.isoformat():
            what = f"{job['job']}: {job['state']}"
            found.append({"time": job["ended"], "kind": "job-ended", "what": what, "ref": f"{job['run']}/{job['job']}"})
    return sorted(found, key=lambda event: event["time"] or "", reverse=True)


def snapshot(now=None):
    now = time.time() if now is None else now
    today = datetime.fromtimestamp(now).date()
    open_tasks = pm_resume.load_tasks()
    drafts = pm_resume.load_tasks(pm_resume.DRAFTS_DIR)
    jobs = recent_jobs(now)
    by_task = {}
    for job in jobs:
        by_task.setdefault(job["task"] or NO_TASK, []).append(f"{job['run']}/{job['job']}")
    waits = [
        {"task": task["id"], "status": task["status"], "needs": task["live"]["Needs owner"]}
        for task in open_tasks + drafts
        if task["status"] != "Done" and pm_resume.asks_something(task["live"]["Needs owner"])
    ]
    return {
        "version": VERSION,
        "project": {"name": ROOT.name, "root": str(ROOT)},
        "generated": stamp(now),
        "tasks": [task_entry(t, by_task) for t in open_tasks if t["status"] in pm_resume.ACTIVE_STATUSES],
        "owner_waits": waits,
        "jobs": jobs,
        "workers_by_task": by_task,
        "agents": herdr_agents(jobs),
        "git": git_state(),
        "events": events(today, open_tasks + pm_resume.load_closed(), jobs, pm_resume.commits("--since=midnight")),
    }


def main():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except (OSError, ValueError):
            pass
    print(json.dumps(snapshot(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
