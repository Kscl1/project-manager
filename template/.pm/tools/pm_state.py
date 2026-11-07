"""Print one project's live state as JSON, for the project window and any other reader. Standard library only.

Usage: python .pm/tools/pm_board.py --state
       python .pm/tools/pm_state.py
       python .pm/tools/pm_state.py --task REQ-1      one task in full, for the window's detail view
       python .pm/tools/pm_state.py --job run/job     one job in full: its brief, result and attempts
       python .pm/tools/pm_state.py --pane w1:p1      one Herdr agent of this project, with what its pane shows

The state is computed on each call from what is already there, and the call writes nothing:
- Backlog task files: the open tasks (Active, In review, Owner check) with their live block, and what waits on the owner;
- pm_run receipts under .pm/local/runs: jobs not ended yet, and jobs that ended in the last 24 hours. Only run
  folders whose receipts.json changed in that time are read: an older run has nothing recent to show, and reading
  every run folder of a long-lived project takes most of a second;
- Herdr's live snapshot (`herdr api snapshot`): the agents working in this project's folder or below it;
- git: branch, changed files, last commits.
`waiting` is what waits on a person, stuck work first and then the oldest: a job that ended without its result, a
worker Herdr shows as blocked, a task's `Needs owner:` line, a task in Owner check. `board` is every open task, most
important first, then the last closed ones; a task's `waiting` says it is in that list. `soon` is the `Review by:`
dates of the open tasks, nearest first.
A job's `started_by` is what pm_run recorded about who started the run: the tool, and a `lead` line a job may name in
jobs.json, since no tool tells a program which model is driving it. A run started from a Herdr pane that holds another
job of this project names that job in `by_job`. Runs older than the field have none.
`events` lists today's commits (by commit time), closed tasks and ended jobs, newest first, all in local time. A job's
optional `task` field in jobs.json names the task it works for; `workers_by_task` groups the jobs by it. A job's `lease`
is how fresh its run's pm_run.lease is: `fresh` when the loop rewrote it in the last LEASE_FRESH_S, else `stale`. It is
a hint, not proof: a loop that just died stays fresh for a while, and a live loop that starts several slow workers in
one tick can look stale until the tick ends. A not-ended job under a lease stale for long is left over. A Herdr agent
is matched to a job by the agent name pm_run gave the job's current attempt (unique per attempt and run folder), never
by its pane, which a later session may reuse; the match holds whatever the lease says.
A source that cannot be read is null, never a guess: `agents` when Herdr is not installed or does not answer, `git`
outside a repository or when one of its git calls fails or does not answer in GIT_TIMEOUT (then `events` carries no
commits), a job's `state` when its run's receipts.json cannot be read. An ended job that never started a worker (a failed preflight, a blocked successor) has no end time; its
`why` says what stopped it.
"""

import itertools
import json
import os
import re
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
VERSION = 2  # the shape of the JSON; a reader checks it before it trusts the keys
RECENT_S = 24 * 3600
# pm_run's ended states (pm_run.ENDED; a test keeps the two in step). Any other state is not ended yet.
ENDED = ("verified", "artifact-present", "check-failed", "handed-over", "failed", "blocked", "stopped")
# pm_run's loop rewrites pm_run.lease once a tick (PM_RUN_TICK, 15 s) and treats it as silent after three ticks; a
# tick that starts a worker may also wait up to 60 s for it to be ready.
LEASE_FRESH_S = 3 * float(os.environ.get("PM_RUN_TICK", 15)) + 60
NO_TASK = "(none)"
STUCK = ("handed-over", "blocked", "failed", "check-failed")  # pm_run's ended states that need someone to look
PRIORITIES = {"high": 0, "medium": 1, "low": 2}  # a task without one comes after these
BOARD_CLOSED = 5  # how many closed tasks the board shows
SOON = 5  # how many review dates
# Herdr as pm_run finds it: PM_RUN_HERDR (tests pass a JSON command list), else `herdr` on PATH.
HERDR = os.environ.get("PM_RUN_HERDR") or shutil.which("herdr") or "herdr"
HERDR_CMD = json.loads(HERDR) if HERDR.startswith("[") else [HERDR]
HERDR_TIMEOUT = 5
DETAIL_CHARS = 60000  # how much of one brief, result or log a detail view shows; the rest is said to be cut
SCREEN_LINES = 60  # how much of a running agent's pane a detail view shows
HIDDEN_FIELDS = ("id", "title", "status", "ordinal")  # the first three head the view; ordinal is only board order
LOG_LINES = 400  # how far back in a run's log a job's own lines are looked for
GIT_TIMEOUT = 10  # a hung git (a network drive, a held lock) must not hold up the screen that waits for this answer


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


def read_json(path):
    """The file's JSON, or None when it cannot be read; utf-8-sig, as pm_run reads it."""
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None


def lease_fresh(run_dir, now):
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
        listed = read_json(run / "jobs.json")
        if not isinstance(listed, list):
            continue  # without its job list a run cannot be shown
        state = read_json(path)
        readable = isinstance(state, dict)
        fresh = lease_fresh(run, now)
        for job in listed:
            if not isinstance(job, dict) or not isinstance(job.get("id"), str):
                continue
            receipt = state.get(job["id"]) if readable and isinstance(state.get(job["id"]), dict) else {}
            attempts = [a for a in receipt.get("attempts") or [] if isinstance(a, dict)]
            last = attempts[-1] if attempts else {}
            # a job the receipts do not name yet is pending, as pm_run counts it; unreadable receipts say nothing
            job_state = receipt.get("state", "pending") if readable else None
            ended = last.get("ended") if isinstance(last.get("ended"), (int, float)) else None
            if job_state in ENDED and ended is not None and now - ended > RECENT_S:
                continue
            artifact = last.get("artifact") if isinstance(last.get("artifact"), dict) else {}
            jobs.append(
                {
                    "run": run.name,
                    "job": job["id"],
                    "task": job["task"] if isinstance(job.get("task"), str) and job["task"].strip() else None,
                    "state": job_state,
                    "lease": "fresh" if fresh else "stale",
                    "model": last.get("model") or job.get("model"),
                    "harness": job.get("harness", "pi"),
                    "thinking": job.get("thinking"),
                    "attempts": len(attempts),
                    "started": stamp(last.get("started")),
                    "ended": stamp(ended) if job_state in ENDED else None,
                    "why": receipt.get("why") or last.get("why"),
                    "words": artifact.get("words"),
                    "check_exit": last.get("verify_rc"),
                    "pane": last.get("pane"),
                    "agent_name": last.get("name"),
                    "brief": brief_title(job),
                    **used(attempts),
                    "started_by": started_by(state, job) if readable else None,
                }
            )
    for job in jobs:  # a run started from a pane that holds another job was started by that job
        pane = job["started_by"]["pane"] if job["started_by"] else None
        if pane:
            job["started_by"]["by_job"] = next(
                (f"{other['run']}/{other['job']}" for other in jobs if other is not job and other["pane"] == pane), None
            )
    return jobs


def used(attempts):
    """What a job's attempts used, added up. `usage_partial` says an attempt is missing, so the sum is a floor."""
    known = [a["usage"] for a in attempts if isinstance(a.get("usage"), dict)]
    costs = [u["cost_usd"] for u in known if isinstance(u.get("cost_usd"), (int, float))]
    return {
        "tokens": sum(u.get("total_tokens") or 0 for u in known) or None,
        "turns": sum(u.get("turns") or 0 for u in known) or None,
        "cost_usd": round(sum(costs), 4) if costs else None,
        "usage_partial": bool(known) and len(costs) < len(attempts),
    }


def started_by(receipts, job):
    """Who started this job's run, as pm_run recorded it, or None for a run older than that record."""
    who = receipts.get("_started_by")
    lead = job.get("lead") if isinstance(job.get("lead"), str) else None
    if not isinstance(who, dict) and not lead:
        return None
    who = who if isinstance(who, dict) else {}
    return {"tool": who.get("tool"), "lead": lead, "pane": who.get("pane"), "by_job": None}


def project_file(name):
    """The file a job's list names, only when it sits inside this project: a detail view reads nothing else."""
    try:
        path = (ROOT / name).resolve()
        path.relative_to(ROOT.resolve())
    except (OSError, ValueError):
        return None
    return path if path.is_file() else None


def brief_title(job):
    """The first line of the job's first brief, the plainest name for what the job does; None when unreadable."""
    briefs = job.get("briefs")
    if not isinstance(briefs, list) or not briefs or not isinstance(briefs[0], str):
        return None
    path = project_file(briefs[0])
    if path is None:
        return None
    try:
        with path.open(encoding="utf-8-sig", errors="replace") as lines:
            for line in itertools.islice(lines, 40):
                text = line.strip().lstrip("#").strip()
                if text and text != "---":
                    return text[:160]
    except OSError:
        return None
    return None


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
    # pm_run names each attempt's Herdr agent; a job that has ended no longer owns one
    owners = {
        job["agent_name"]: f"{job['run']}/{job['job']}"
        for job in jobs
        if job["agent_name"] and job["state"] not in ENDED
    }
    agents = []
    for agent in listed:
        cwd = agent.get("cwd") if isinstance(agent, dict) else None
        if not cwd or not inside(cwd, root_key):
            continue
        agents.append(
            {
                "pane": agent.get("pane_id"),
                "name": agent.get("name"),
                "agent": agent.get("display_agent") or agent.get("agent"),
                "status": agent.get("agent_status"),
                "title": agent.get("title") or agent.get("terminal_title_stripped"),
                "cwd": cwd,
                "job": owners.get(agent.get("name")),
            }
        )
    return agents


def iso_local(text):
    """An ISO time with any offset as local ISO time, or None."""
    try:
        return datetime.fromisoformat(text).astimezone().isoformat(timespec="seconds")
    except (TypeError, ValueError):
        return None


def commit_entry(commit):
    tasks = sorted(ref for ref in commit["refs"] if ref.lower() != "none")  # `Refs: none` names no task
    return {"sha": commit["sha"], "time": iso_local(commit["time"]), "subject": commit["subject"], "tasks": tasks}


def git_state():
    """(git, today's commits): branch line, changed files and the last five commits, then today's commits.

    Both are None outside a git repository or when one of the calls fails or does not answer: an empty list must
    mean no commits, never "could not ask"."""
    # --no-optional-locks: a reader that runs often must not rewrite the index
    status = pm_resume.git_stdout(["--no-optional-locks", "status", "--porcelain=v1", "-b"], None, GIT_TIMEOUT)
    if status is None:
        return None, None
    lines = status.splitlines()
    branch = lines[0][3:] if lines and lines[0].startswith("## ") else None
    if branch and branch.startswith("No commits yet"):
        last, todays = [], []  # git log fails in a new repository; there is nothing to list
    else:
        last = pm_resume.commits("-5", timeout=GIT_TIMEOUT, failed=None)
        todays = pm_resume.commits("--since=midnight", timeout=GIT_TIMEOUT, failed=None)
    if last is None or todays is None:
        return None, None
    changed = [line for line in lines if not line.startswith("## ")]
    return {"branch": branch, "changed": changed, "last_commits": [commit_entry(c) for c in last]}, todays


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
    found = [
        {"time": iso_local(c["time"]), "kind": "commit", "what": c["subject"], "ref": c["sha"]} for c in todays_commits
    ]
    for task in tasks:
        if task["status"] == "Done" and pm_resume.local_day(task["updated"]) == today:
            found.append(
                {"time": local_time(task["updated"]), "kind": "task-closed", "what": task["title"], "ref": task["id"]}
            )
    for job in jobs:
        if job["ended"] and job["ended"][:10] == today.isoformat():
            what = f"{job['job']}: {job['state']}"
            found.append({"time": job["ended"], "kind": "job-ended", "what": what, "ref": f"{job['run']}/{job['job']}"})
    # by the moment itself: ISO text with different offsets does not sort as text
    return sorted(found, key=lambda event: moment(event["time"]), reverse=True)


def waiting_cards(tasks, waits, jobs, agents):
    """What waits on a person: stuck jobs and workers first, then decisions and reviews, oldest first in each."""
    cards = [
        {
            "kind": "stuck",
            "title": job["brief"] or f"{job['run']}/{job['job']}",
            "text": job["why"] or job["state"],
            "since": job["ended"],
            "tool": "agents",
            "ref": job["task"],
            "job": f"{job['run']}/{job['job']}",
        }
        for job in jobs
        if job["state"] in STUCK
    ]
    for agent in agents or []:
        if agent["status"] == "blocked":
            title = agent["job"] or agent["name"] or agent["agent"]
            cards.append(
                {"kind": "stuck", "title": title, "text": agent["title"], "since": None, "tool": "agents", "ref": None}
            )
    by_id = {task["id"]: task for task in tasks}
    for wait in waits:
        task = by_id.get(wait["task"])
        if task:
            cards.append(card_of(task, "decision", wait["needs"]))
    asked = {wait["task"] for wait in waits}
    for task in tasks:
        if task["status"] == "Owner check" and task["id"] not in asked:
            cards.append(card_of(task, "review", live_value(task["live"]["Next"])))
    return sorted(cards, key=lambda card: (card["kind"] != "stuck", moment(card["since"]) or float("inf")))


def card_of(task, kind, text):
    return {
        "kind": kind,
        "title": task["title"],
        "text": text,
        "since": local_time(task["updated"] or task["created"]),
        "tool": "board",
        "ref": task["id"],
    }


def board_entry(task, waiting):
    blocker = live_value(task["live"]["Blocker"])
    return {
        "id": task["id"],
        "title": task["title"],
        "status": task["status"],
        "priority": task["priority"] or None,
        "milestone": task["milestone"] or None,
        "parent": task["parent"] or None,
        "blocker": blocker if pm_resume.asks_something(blocker) else None,  # `Blocker: none` blocks nothing
        "updated": local_time(task["updated"]),
        "waiting": task["id"] in waiting,
    }


def board(tasks, closed, cards):
    """Every open task, most important first, then the newest closed ones."""
    waiting = {card["ref"] for card in cards}
    live = [task for task in tasks if task["status"] != "Done"]
    live.sort(key=lambda task: PRIORITIES.get(task["priority"], len(PRIORITIES)))  # stable: task order within each
    ended = [task for task in tasks + closed if task["status"] == "Done"]
    ended.sort(key=lambda task: moment(local_time(task["updated"])), reverse=True)
    return [board_entry(task, waiting) for task in live + ended[:BOARD_CLOSED]]


def soon(tasks):
    """The nearest `Review by:` dates of the open tasks."""
    found = []
    for task in tasks:
        day = pm_resume.as_date(task["review_by"])
        if day and task["status"] != "Done":
            found.append({"date": day.isoformat(), "what": task["title"], "ref": task["id"]})
    return sorted(found, key=lambda item: item["date"])[:SOON]


def moment(text):
    try:
        return datetime.fromisoformat(text).timestamp()
    except (TypeError, ValueError):
        return 0.0


def snapshot(now=None):
    now = time.time() if now is None else now
    today = datetime.fromtimestamp(now).date()
    open_tasks = pm_resume.load_tasks()
    drafts = pm_resume.load_tasks(pm_resume.DRAFTS_DIR)
    jobs = recent_jobs(now)
    git, todays = git_state()
    by_task = {}
    for job in jobs:
        by_task.setdefault(job["task"] or NO_TASK, []).append(f"{job['run']}/{job['job']}")
    waits = [
        {"task": task["id"], "status": task["status"], "needs": task["live"]["Needs owner"]}
        for task in open_tasks + drafts
        if task["status"] != "Done" and pm_resume.asks_something(task["live"]["Needs owner"])
    ]
    agents = herdr_agents(jobs)
    closed = pm_resume.load_closed()
    cards = waiting_cards(open_tasks + drafts, waits, jobs, agents)
    return {
        "version": VERSION,
        "project": {"name": ROOT.name, "root": str(ROOT)},
        "generated": stamp(now),
        "tasks": [task_entry(t, by_task) for t in open_tasks if t["status"] in pm_resume.ACTIVE_STATUSES],
        "owner_waits": waits,
        "waiting": cards,
        "board": board(open_tasks, closed, cards),
        "soon": soon(open_tasks),
        "jobs": jobs,
        "workers_by_task": by_task,
        "agents": agents,
        "git": git,
        "events": events(today, open_tasks + closed, jobs, todays or []),
    }


def front_fields(text):
    """Every frontmatter field in file order, lists too, as [{"name", "value"}]; a custom field shows like any other."""
    lines = text.splitlines()
    fields = []
    if not lines or lines[0].strip() != "---":
        return fields
    for line in lines[1:]:
        if line.strip() == "---":
            break
        item = re.match(r"\s*-\s+(.*)$", line)
        if fields and item:
            value = fields[-1]["value"]
            fields[-1]["value"] = [*(value if isinstance(value, list) else []), pm_resume.scalar(item.group(1))]
        elif fields and line[:1] in (" ", "\t"):  # the next line of a folded value
            fields[-1]["value"] = f"{fields[-1]['value']} {line.strip()}".strip()
        else:
            name, separator, value = line.partition(":")
            value = value.strip()
            if separator:
                empty = value in ("[]", ">", ">-", ">+", "|", "|-", "|+")
                fields.append({"name": name.strip(), "value": "" if empty else pm_resume.scalar(value)})
    return [field for field in fields if field["value"] and field["name"] not in HIDDEN_FIELDS]


def task_sections(text):
    """Every `## ` section of a task file in order, the closing summary first, without Backlog's markers.

    A section of checklist lines alone also comes as `checks`. Text before the first heading is a section with no name.
    """
    body = re.split(r"^---\s*$", text, maxsplit=2, flags=re.M)[-1]
    parts = re.split(r"^##[ \t]+(.+?)[ \t]*#*[ \t]*$", body, flags=re.M)
    found = []
    for name, part in zip(["", *parts[1::2]], parts[0::2]):
        clean = re.sub(r"^\s*<!--\s*[A-Za-z]+:[A-Za-z0-9_:]+\s*-->\s*$", "", part, flags=re.M).strip()
        if clean:
            lines = [line for line in clean.splitlines() if line.strip()]
            items = checks(clean)
            found.append({"name": name, "text": clean, "checks": items if len(items) == len(lines) else None})
    return sorted(found, key=lambda item: item["name"] != "Final Summary")


def checks(text):
    """`- [x] #1 words` lines as [{"done": bool, "text": words}]."""
    items = re.findall(r"^\s*-\s*\[([ xX])\]\s*(?:#\d+\s*)?(.+)$", text, re.M)
    return [{"done": mark != " ", "text": words.strip()} for mark, words in items]


def task_detail(task_id):
    """One task in full from its file, or None when no open, closed or draft task has this id."""
    for directory in (pm_resume.TASKS_DIR, pm_resume.DRAFTS_DIR, *pm_resume.CLOSED_DIRS):
        for path in sorted(directory.glob("*.md")):
            try:
                text = path.read_text(encoding="utf-8-sig")
            except (OSError, UnicodeError):
                continue
            fields = pm_resume.read_frontmatter(text.splitlines()) or {}
            if fields.get("id", "").strip().casefold() != task_id.casefold():
                continue
            return {
                "id": fields["id"].strip(),
                "title": fields.get("title", "").strip(),
                "status": fields.get("status", "").strip(),
                "fields": front_fields(text),
                "sections": task_sections(text),
            }
    return None


def clipped(path):
    """{"text", "cut"} of a project file, or None when it cannot be read."""
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return None
    return {"text": text[:DETAIL_CHARS], "cut": len(text) > DETAIL_CHARS}


def pane_screen(pane):
    """What this pane shows now, or None; only a pane Herdr lists in this project is read."""
    if not pane or not any(agent["pane"] == pane for agent in herdr_agents([]) or []):
        return None
    try:
        command = [*HERDR_CMD, "pane", "read", pane, "--source", "recent", "--lines", str(SCREEN_LINES)]
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=HERDR_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.rstrip() if result.returncode == 0 else None


def pane_detail(pane):
    """One Herdr agent of this project with what it shows now, or None."""
    agent = next((a for a in herdr_agents([]) or [] if a["pane"] == pane), None)
    return {**agent, "screen": pane_screen(pane)} if agent else None


def job_log(run, job_id):
    """The lines of the run's log that name this job, newest last, or None."""
    path = project_file(run / "pm_run.log")
    if path is None:
        return None
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    named = re.compile(rf"(?<![\w-]){re.escape(job_id)}(?![\w-])")  # job `a` must not match the word `started`
    return "\n".join(line for line in lines[-LOG_LINES:] if named.search(line))[-DETAIL_CHARS:] or None


def job_detail(name):
    """One job of a run in full, from its own files, or None when `run/job` names none."""
    run_name, _, job_id = name.partition("/")
    if not job_id or not re.fullmatch(r"[\w.-]+", run_name) or run_name in (".", ".."):
        return None  # a run is one folder directly under the runs folder
    run = RUNS_DIR / run_name
    jobs_file, receipts_file = project_file(run / "jobs.json"), project_file(run / "receipts.json")
    if jobs_file is None:
        return None  # no such run, or a link that leaves the project
    listed = read_json(jobs_file)
    listed = listed if isinstance(listed, list) else []
    job = next((j for j in listed if isinstance(j, dict) and j.get("id") == job_id), None)
    if job is None:
        return None
    state = read_json(receipts_file) if receipts_file else None
    state = state if isinstance(state, dict) else {}
    receipt = state.get(job_id) if isinstance(state.get(job_id), dict) else {}
    attempts = [a for a in receipt.get("attempts") or [] if isinstance(a, dict)]
    briefs = []
    for brief in job.get("briefs") or []:
        path = project_file(brief) if isinstance(brief, str) else None
        read = clipped(path) if path else None
        if read:
            briefs.append({"name": brief, **read})
    out = project_file(job["out"]) if isinstance(job.get("out"), str) else None
    return {
        "run": run_name,
        "job": job_id,
        "title": brief_title(job),
        "task": job.get("task"),
        "model": (attempts[-1].get("model") if attempts else None) or job.get("model"),
        "harness": job.get("harness", "pi"),
        "thinking": job.get("thinking"),
        "state": receipt.get("state", "pending"),
        "why": receipt.get("why"),
        "started_by": started_by(state, job),
        "attempts": [
            {
                "model": a.get("model"),
                "started": stamp(a.get("started")),
                "ended": stamp(a.get("ended")),
                "why": a.get("why"),
            }
            for a in attempts
        ],
        **used(attempts),
        "out": job.get("out"),
        "briefs": briefs,
        "result": clipped(out) if out else None,
        "log": job_log(run, job_id),
        "screen": pane_screen(attempts[-1].get("pane")) if attempts and receipt.get("state") not in ENDED else None,
    }


def main():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except (OSError, ValueError):
            pass
    words = sys.argv[1:]
    details = {"--task": task_detail, "--job": job_detail, "--pane": pane_detail}
    if len(words) == 2 and words[0] in details:
        found = details[words[0]](words[1])
        print(json.dumps({"version": VERSION, "found": found}, indent=2, ensure_ascii=False))
        return 0
    print(json.dumps(snapshot(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
