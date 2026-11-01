"""Run worker jobs as visible Herdr agents and keep a receipt per attempt (experimental).

Herdr starts and shows the workers (one Herdr workspace per run, one tab per attempt) and tells us when a turn
has settled. This tool only decides whether a job is done. A job is **verified** only when all of these hold:
  1. the artifact was written during this attempt (mtime after the attempt started),
  2. it ends with the done marker and has at least `min_words` words,
  3. Herdr shows the worker's turn settled and the tool closed its pane and confirmed the agent is gone,
  4. the job's `verify` command exits 0. A job without `verify` ends as **artifact-present**, never verified.
A finished artifact whose `verify` fails ends as **check-failed**: the report stays and the job is never relaunched,
because a rerun costs a whole job and the fault is often the check itself; fix the check or the report, then --check.
Herdr's own `done` badge proves nothing on its own: an aborted turn also ends as `done`.
Pi retries provider errors itself (retry.maxRetries in ~/.pi/agent/settings.json, at most 60 s between tries), and
Herdr may show its turn as done meanwhile. So pm_run nudges a settled Pi worker only after its session log has been
quiet for PM_RUN_QUIET_S, and never repeats Pi's own retry. When the log is not found (another harness, a Pi
folder moved by the setup line) the pane stands in for it: the nudge waits until the pane's content has stayed the
same for PM_RUN_QUIET_S, because Herdr can show a live turn as settled. A nudge goes to the same session: RESUME, or the
full brief again when no turn ran (no completion_seq advance and no observed working state).
A nudge counts as idle when the session log did not grow or the output file did not change since the previous one
(a worker that answers every nudge without touching its output is idle too); after PM_RUN_MAX_NUDGES idle nudges
in a row the job is **handed-over**: pm_run stops watching, leaves the session open in its Herdr tab and tells the lead.
A settled worker whose Pi error message or last pane lines name a used-up quota or usage limit, or a sign-in that ran
out ("Login expired", "Please run /login", a 401), is handed over at once, without a nudge: a resent brief would hit
the same wall until the limit resets or the owner signs in again. A bare 429 (an upstream outage answers with it too)
is nudged as before. A quota message that names a reset within PM_RUN_QUOTA_WAIT_S (1800 s) plus 30 s of slack,
written as "reset after 15m 19s" or "resets in 2h" (h, m, s units; other wordings are handed over as before), is
waited out instead (QUOTA-WAIT): once per attempt and only if the wait ends within the time limit (overtime already
granted included); then one nudge in the same session, or a hand-over if the limit is still shown.
At the hard limit a live worker gets PM_RUN_OVERTIME_S more, once (a settled one also gets a nudge), then is handed
over. A fresh session (a retry) starts only when the worker is gone or did not start, up to PM_RUN_MAX_TRIES attempts;
before it, this attempt's fresh output is kept as <stem>.attempt<n><suffix>, with -2, -3 on name clashes. An output
file that already exists when a job's first attempt starts (another run dir, or an earlier job with the same `out`)
is copied to <stem>.kept<suffix> first, so a finished report is never lost to a relaunch.
A brief that changes while its worker runs is logged as BRIEF-CHANGED when the job is judged, and the receipt keeps
brief_changed: the report answers the brief the worker read, which may no longer be the job's.
Each ended attempt keeps what it used: the attempt's `usage` holds "input", "output", "cache_read", "cache_write",
"total_tokens", "turns" (how many assistant messages were summed) and "cost_usd", summed from the assistant messages
the attempt's Pi session log wrote after the attempt started; a message without cost.total makes cost_usd null, and a
log that is not found leaves usage out altogether (never a guess). Claude Code's log is not read: it carries no cost and
pm_run does not know the file for a job. `--status` shows tokens and cost per job, then one line per model and a grand
total; the end of the loop prints the same totals.
A dependency that failed, was blocked, stopped, handed-over, check-failed or is only artifact-present blocks its
successors. Before each launch every brief must exist as a file; a missing one fails the job without starting a worker.
After startup pm_run waits up to 60 s for Herdr's ready/idle state before sending the brief; if no state is reported,
it uses PM_RUN_SETUP_S as the fallback. A known non-ready agent is not sent the brief at the ceiling.
A worker that asks a question (Herdr state `blocked`) is never killed for it; it waits until someone answers.
An agy permission question in the last pane lines also waits, even when Herdr reports the turn done. Each question
pm_run sees is logged as WAITING with the pane id, a later one in the same session too, even when the answer to the one
before fell between two ticks (Herdr's state counter shows it); questions asked and answered between two ticks are not.
If a blocked agy startup shows the folder trust question, the job stays pending without using a try. Answer Yes in
that pane; pm_run closes it and starts the job once the screen changes. A failed pane read does not count as an answer.

usage: python .pm/swarm/pm_run.py <run-dir>                 loop until every job has ended (see ENDED)
       python .pm/swarm/pm_run.py <run-dir> --status        print the receipt table with tokens and cost, then exit
       python .pm/swarm/pm_run.py <run-dir> --status --tally  also count shared failure-log events, most frequent first
       python .pm/swarm/pm_run.py <run-dir> --check <job>   check one job's current artifact and verify command, no Herdr
       python .pm/swarm/pm_run.py <run-dir> --stop <job>    stop one job of a live run: the loop closes its pane and
                                                            blocks its successors (never delete a live job from
                                                            jobs.json: its worker would run on unwatched); a stopped
                                                            job stays ended in this run dir: to run it again, put it
                                                            in a new run dir

<run-dir>/jobs.json: [{"id", "model", "out", "briefs": [...], "after": [...], "verify": "cmd", "min_words": 1000,
                       (verify runs through the system shell, cmd.exe on Windows: keep it a plain command, put logic in a script)
                       "bucket": "router", "thinking": "high",
                       "harness": "pi" | "claude" | "agy", "setup": "shell line run in the pane first", "args": [...],
                       "probe": "http://127.0.0.1:8080/v1/models",  (optional HTTP health probe; never include a secret)
                       "writes": ["site/"],    (paths the worker may write besides `out`, e.g. code it builds)
                       "helpers": ["model", ...],  (lets the worker start helpers as its own pm_run jobs, in a run
                                                    dir inside `writes`, on these models only; default: none)
                       "stop": true}]          (set by --stop; the job then stays ended here)
                       (harness "claude" starts Claude Code with --model and args, without its bundled skills
                        (CLAUDE_SETTINGS); harness "agy" starts the Antigravity CLI with --model and args (the model id
                        carries the thinking level, e.g. gemini-3.8-flash-low; pass "args": ["--mode", "accept-edits"]
                        or similar so file writes need no approval); thinking applies to Pi only;
                        Pi and Claude Code start without in-process sub-agent tools: a helper is its own pm_run job, so
                        it is visible too; a worker without "helpers" writes "Helper needed" in its output for the lead;
                        agy has no switch for its sub-agents, so there only the brief forbids them.
                        A first-run screen that only the owner can pass (agy: colour scheme, then its terms) is handed
                        over before the brief is sent: finish it once in that Herdr tab, then rerun the job)
<run-dir>/caps.json: {"<bucket>": max parallel}.
The loop re-reads jobs.json and caps.json every tick; a copy that is not valid JSON (an edit saved half-way) is
skipped with one log line. An error inside one tick is logged and the loop goes on.
Herdr binary: PM_RUN_HERDR, else `herdr` on PATH (where Herdr's installer puts it). The Herdr server must be running
(start `herdr` once).
Timeouts: PM_RUN_HERDR_TIMEOUT (30 seconds per CLI call), PM_RUN_VERIFY_S (600 seconds per check),
PM_RUN_START_S (10 seconds for agy to draw its screen after Herdr reports it ready).
Other env vars: PM_RUN_HARD_S (4500), PM_RUN_OVERTIME_S (900), PM_RUN_QUIET_S (90), PM_RUN_MAX_NUDGES (3),
PM_RUN_QUOTA_WAIT_S (1800),
PM_RUN_TICK (15), PM_RUN_SETTLE_S (20), PM_RUN_SETUP_S (2), PM_RUN_READY_S (60, capped at 60), PM_RUN_MAX_TRIES (5),
PM_RUN_REPO (the repo root; default the current folder).
Failure log: every event a person should look at later (a retry, a nudge, a hand-over, a check that failed, a job
without a check, a question, a stall...) is also appended, one line with date and run directory, to
<repo>/.pm/local/failures.log, shared by all runs of that repo root (each git worktree has its own), so
failures are recorded when they happen, not recalled later. Give run directories unique names: the line keeps only
the directory's own name.
PM_RUN_STALL_S (300 seconds): warn the caller once per inactivity episode; never stop or prompt the worker.
Working panes are also checked for suspected repeating output. Warnings reach stdout and pm_run.log; the receipt keeps stall/loop flags.
Delivery can lag the threshold by one tick plus Herdr/probe timeouts; probes run only for a new stall warning.
Pi diagnostics: PM_RUN_PI_SESSIONS overrides ~/.pi/agent/sessions; log lookup is best-effort, not completion evidence.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import time
import traceback
from collections import Counter
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

MARKER = "<!-- done -->"
# pm_run stops when every job is here
ENDED = ("verified", "artifact-present", "check-failed", "handed-over", "failed", "blocked", "stopped")


def _env(name, default):
    return float(os.environ.get(f"PM_RUN_{name}", default))


HARD_S, TICK, SETTLE_S = _env("HARD_S", 75 * 60), _env("TICK", 15), _env("SETTLE_S", 20)
STALL_S = _env("STALL_S", 300)
SETUP_S = _env("SETUP_S", 2)  # let the pane's setup line finish before the agent starts
START_S = _env("START_S", 10)
READY_S = min(60, max(0, _env("READY_S", 60)))  # never wait more than a minute for an agent's state
HERDR_TIMEOUT, VERIFY_S = _env("HERDR_TIMEOUT", 30), _env("VERIFY_S", 600)
MAX_TRIES = int(_env("MAX_TRIES", 5))
QUOTA_WAIT_S = _env("QUOTA_WAIT_S", 30 * 60)
QUIET_S, MAX_NUDGES, OVERTIME_S = _env("QUIET_S", 90), int(_env("MAX_NUDGES", 3)), _env("OVERTIME_S", 15 * 60)
# The pm_run.log words that also go to the shared failure log; LAUNCH, VERIFIED, HOLD and KEPT are routine.
FAILURES = {"FAILED", "RETRY", "HANDED-OVER", "CHECK-FAILED", "BLOCKED", "ARTIFACT", "RESUME", "PROMPT", "WAITING"}
FAILURES |= {"STALLED", "LOOP", "OVERTIME", "SAVE-FAILED", "TICK-ERROR", "SKIPPED", "REMOVED", "STOPPED"}
FAILURES |= {"BRIEF-CHANGED", "QUOTA-WAIT", "KEPT-FAILED"}
HERDR = os.environ.get("PM_RUN_HERDR") or shutil.which("herdr") or "herdr"
HERDR_CMD = json.loads(HERDR) if HERDR.startswith("[") else [HERDR]  # tests pass a JSON command list
SETTLED = ("done", "idle")
# A used-up allowance, not per-minute throttling ("rate limit" passes after a nudge). On a pane line it counts only
# beside an error sign: an API error, a 429, or a limit banner with its reset time.
QUOTA = re.compile(
    r"usage limit|quota|limit reached|(?:hit|reached) your (?:usage )?limit|out of (?:extra )?usage", re.I
)
ERROR_LINE = re.compile(r"\berror\b|\b429\b|\bresets?\b", re.I)
# A sign-in that ran out. Pi's own error message is trusted as it is (LOGIN). On the pane only a line that starts
# with the harness's answer counts (LOGIN_LINE): Claude Code answers "Not logged in · Please run /login" or
# "API Error: 401 ...", and its run still ends as a success. A worker's prose that names these words does not start
# with them, and the hint "Not logged in · Run /login" that a profile signed in with a key or token shows in its status
# line the whole time has no "Please".
LOGIN = re.compile(
    r"please run /login|login expired|oauth token (?:has )?expired|invalid (?:x-)?api[ -]key|authentication_error"
    r"|\b401\b",
    re.I,
)
# Only the marks Claude Code itself puts before a message (●, ⎿) may come first, so a quoted example ("> API Error:
# 401", "`Please run /login`") does not count. A bare example line that looks exactly like the error still does.
LOGIN_LINE = re.compile(
    r"^[\s●⎿]*(?:api error:? 401\b|(?:not logged in|login expired|invalid api key|oauth token has expired)\W+"
    r"please run /login|please run /login)",
    re.I,
)
PROMPT = (
    "Read the brief file(s) {briefs} and do the task. Your output file is {out}. Create it early and fill it "
    "section by section. Only when it is complete, append the exact last line <!-- done -->. Write only that file{also}. "
    "Do not ask questions: if something blocks you, write the blocker into the output file and finish. {helpers}"
)
NO_HELPER = (
    "Do not start a helper (a sub-agent, a background task, a skill that runs its own agent): if one would help, write "
    "'Helper needed: <what and why>' into the output file and go on with what you can; the lead decides."
)
# A job with "helpers" lets its worker run helpers the way the lead does: as pm_run jobs, each in its own Herdr tab.
HELPERS = (
    "You may start helpers, but only as jobs of your own pm_run run (python .pm/swarm/pm_run.py <run-dir>; the jobs.json "
    "format is at the top of that file), and only on these models: {models}. Name the run directory {job}-helpers, "
    "inside the paths you may write: Herdr shares workspace names between runs. Start the run, wait until it has "
    "ended (--status), then read and check each helper's output before you use it. Never start an in-process "
    "sub-agent, a background task or a skill that runs its own agent."
)
# Every helper runs in its own Herdr pane through pm_run, where the owner can watch it, so an agent started here
# gets no in-process sub-agent tools. Applies to this run only; the owner's own Pi and Claude Code setup is unchanged.
CLAUDE_SETTINGS = {
    "enableAllProjectMcpServers": True,  # the project's MCP servers (Context7...) start unasked
    # Claude Code's own skills (code-review, claude-api, dataviz...) fire on a brief's words, and code-review starts its
    # own background helper that --disallowedTools does not stop. The project's and plugins' skills stay.
    "disableBundledSkills": True,
}
# No allow rules for shell commands: Claude Code runs read-only commands (ls, cat, grep, Get-Content, read-only git)
# without a prompt in both shells and checks their arguments, so `git diff --output=x` still asks. A prefix rule
# would let that through.
NO_HELPERS = {
    "pi": ["--exclude-tools", "Agent,SubagentWorkflow"],
    "claude": ["--disallowedTools", "Agent,Workflow"],
    "agy": [],  # no switch for its sub-agents; the brief forbids them
}
# Screens a harness shows on its first run, before it takes a brief. Herdr reports agy idle there (its fallback when
# no detection rule matches), so a brief sent now would land in the menu. Only the owner should accept agy's terms.
FIRST_RUN = re.compile(r"Welcome to Antigravity CLI|Choose your color scheme|Terms of Service & Data Use")
PERMISSION = re.compile(
    r"allow\s+access\s+to\s+this\s+file\s*\?|run\s+this\s+command\s*\?|requesting\s+permission\s+for\s*:", re.I
)
TRUST = re.compile(r"do\s+you\s+trust\s+the\s+contents\s+of\s+this\s+project\s*\?", re.I)
RESUME = (
    "Your previous turn ended before the output was finished. Re-read the brief file(s) {briefs} and {out}, "
    "keep what is there, finish it, "
    "then append the exact last line <!-- done -->."
)


def held(action):
    """Run a file action; on Windows retry for about 3 s while another process (a --status call, a watcher) holds
    the file open, which makes a rename or a read fail with PermissionError. The last failure is raised."""
    for wait in (0.1, 0.2, 0.4, 0.8, 1.6):
        try:
            return action()
        except PermissionError:
            time.sleep(wait)
    return action()


def herdr(*args, plain=False, timeout=None):
    """Run one Herdr CLI command; return JSON (or {"error": ...}), or raw stdout for a successful pane read."""
    timeout = HERDR_TIMEOUT if timeout is None else min(HERDR_TIMEOUT, timeout)
    try:
        result = subprocess.run(
            [*HERDR_CMD, *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"error": {"code": "timeout", "message": f"Herdr call timed out after {timeout:g} s"}}
    except OSError as exc:  # not installed, or PM_RUN_HERDR names a file that is not there
        return {"error": {"message": f"cannot start {HERDR_CMD[0]} ({exc}); install Herdr or set PM_RUN_HERDR"}}
    if plain and result.returncode == 0:
        return result.stdout
    for text in (result.stdout, result.stderr):
        try:
            return json.loads(text)
        except ValueError:
            pass
    return {"error": {"message": (result.stdout + result.stderr).strip() or f"exit {result.returncode}"}}


def pane_content(text):
    """Trim the input/status footer and spinner lines, preserving digits in worker content."""
    lines = text.splitlines()
    for i in range(max(0, len(lines) - 12), len(lines)):
        if lines[i].count("─") >= 20 and lines[i].count("─") > len(lines[i].strip()) / 2:
            lines = lines[:i]
            break
    return "\n".join(line for line in lines if not re.search(r"[\u2800-\u28ff]|^\s*[✻✶✳✢✽·]", line))


def stall_cause(job, content):
    """Describe pane/probe evidence, not a diagnosis. Never probe outside a new stall warning."""
    tail = "\n".join(content.splitlines()[-10:])
    quota = re.search(r"\b429\b|rate limit|quota|usage limit", tail, re.I)
    connection = re.search(
        r"connection refused|ECONNRESET|fetch failed|timed out|\b50[23]\b|network|socket hang up", tail, re.I
    )
    probe_code, probe_failed = None, False
    if job.get("probe"):
        try:
            with urlopen(job["probe"], timeout=5) as response:
                probe_code = response.status
        except HTTPError as exc:
            probe_code = exc.code
            exc.close()
        except (URLError, OSError, ValueError):
            probe_failed = True
    inconclusive = (
        job.get("probe")
        and probe_code != 200
        and probe_code != 429
        and not (probe_failed or probe_code is not None and 500 <= probe_code < 600)
    )
    if quota:
        cause = f'quota or rate limit: pane mentions "{quota.group()}"'
    elif probe_code == 429:
        cause = "quota or rate limit: probe returned HTTP 429"
    elif connection:
        cause = f'connection or server: pane mentions "{connection.group()}"'
    elif probe_failed or probe_code is not None and 500 <= probe_code < 600:
        cause = "connection or server: " + (
            "probe did not answer" if probe_failed else f"probe returned HTTP {probe_code}"
        )
    else:
        cause = "no evidence yet: a long think, or a request hung at the provider"
    return cause + ("; probe inconclusive (check the probe URL)" if inconclusive else "")


def stop_sign(attempt, screen):
    """("login" or "quota", the message) when a settled turn hit a wall a resent brief cannot pass, else None.

    Pi's error from this turn is in its session log (turn_end); Claude Code prints the API error in its pane, so an
    error line among the last ten pane lines counts too. Worker prose that only mentions a quota does not, and neither
    does a bare 429: it also comes from an upstream outage, which a nudge can outlast.
    """
    error = attempt.get("errorMessage") or ""
    lines = (
        [line for line in pane_content(screen).splitlines() if line.strip()][-10:] if isinstance(screen, str) else []
    )
    for line in [error] + lines:
        if LOGIN_LINE.search(line) or line is error and LOGIN.search(line):
            return "login", " ".join(line.split())[:160]
        if (line is error or ERROR_LINE.search(line)) and QUOTA.search(line):
            return "quota", " ".join(line.split())[:160]
    return None


def reset_seconds(text):
    """Seconds until a limit resets when the message says so ("reset after 15m 19s", "resets in 2h"), else None."""
    found = re.search(r"\bresets? (?:after|in) ((?:\d+ ?[hms]\b ?)+)", text, re.I)
    if not found:
        return None
    units = {"h": 3600, "m": 60, "s": 1}
    return sum(int(n) * units[u.lower()] for n, u in re.findall(r"(\d+) ?([hms])", found.group(1), re.I))


def check_artifact(path, started, min_words):
    """Evidence 1 and 2: the artifact, or None with the reason."""
    if not path.exists():
        return None, "no output file"
    if path.stat().st_mtime < started:
        return None, "output is older than this attempt"
    text = path.read_text(encoding="utf-8", errors="replace")
    if MARKER not in text[-400:]:
        return None, "no done marker"
    if len(text.split()) < min_words:
        return None, f"only {len(text.split())} words"
    return {
        "sha256": sha256(text.encode("utf-8")).hexdigest()[:16],
        "words": len(text.split()),
        "mtime": path.stat().st_mtime,
    }, ""


def run_verify(job, repo):
    """Evidence 4: the job's own check."""
    if not job.get("verify"):
        return None, ""
    try:
        # No pipes: a shell child inheriting them can otherwise delay timeout cleanup on Windows.
        rc = subprocess.run(
            job["verify"], shell=True, cwd=repo, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=VERIFY_S
        ).returncode
        return rc, f"check exited {rc}" if rc else ""
    except subprocess.TimeoutExpired:
        return -1, f"verify timed out after {VERIFY_S:g} s"


def output_stamp(path):
    """Size and mtime of the output file as one string (it survives the JSON receipt), or None when missing."""
    try:
        st = path.stat()
        return f"{st.st_size}:{st.st_mtime_ns}"
    except OSError:
        return None


def short_tokens(count):
    """A token count as people read it: 950, 8.4k, 1.2M; "-" when no attempt reported one."""
    if count is None:
        return "-"
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M"
    if count >= 1_000:
        return f"{count / 1_000:.1f}k"
    return str(int(count))


def short_cost(money):
    """Money as people read it: $0.04, or $0.0013 for a cheap job; "-" when nothing is known."""
    if money is None:
        return "-"
    return f"${money:.4f}" if 0 < money < 0.01 else f"${money:.2f}"


def usage_tally(jobs, state):
    """Tokens, turns and cost per model and per job id, over every attempt in the receipts.

    A row's turns or cost are unknown when any attempt that counted for it did not report them, so a partial sum is
    never shown as the truth. A job that is no longer in jobs.json still counts: its attempts were paid for too.
    """
    models = {job["id"]: job.get("model") for job in jobs}
    per_model, per_job = {}, {}
    for jid, s in state.items():
        if jid.startswith("_"):
            continue
        for attempt in s.get("attempts", []):
            usage = attempt.get("usage")
            if not isinstance(usage, dict):
                continue
            model = attempt.get("model") or models.get(jid) or "unknown model"
            for key, bucket in ((model, per_model), (jid, per_job)):
                row = bucket.setdefault(key, {"tokens": 0, "turns": 0, "cost": 0.0, "known": True, "turns_known": True})
                row["tokens"] += usage.get("total_tokens") or 0
                if usage.get("turns") is None:  # a receipt written before turns were counted
                    row["turns_known"] = False
                else:
                    row["turns"] += usage["turns"]
                if usage.get("cost_usd") is None:
                    row["known"] = False
                else:
                    row["cost"] += usage["cost_usd"]
    return per_model, per_job


def session_log(attempt, now):
    """(size, seconds since last write) of the attempt's Pi session log, or (None, None) when unknown."""
    try:
        st = Path(attempt["session_log"]).stat()
        return st.st_size, now - st.st_mtime
    except (KeyError, OSError):
        return None, None


def keep_output(out, stem, move):
    """Move or copy the output file to <stem><suffix>, adding -2, -3 on name clashes; return the new path."""
    kept, extra = out.with_name(stem + out.suffix), 2
    while kept.exists():
        kept = out.with_name(f"{stem}-{extra}{out.suffix}")
        extra += 1
    if move:
        out.rename(kept)
    else:
        shutil.copy2(out, kept)
    return kept


def missing_brief(job, repo):
    """A missing brief's safe, one-line reason, or None when every path exists."""
    for brief in job["briefs"]:
        if not (repo / brief).is_file():
            control = any(ord(c) < 32 or 127 <= ord(c) <= 159 for c in brief)
            shown = "".join(
                json.dumps(c, ensure_ascii=False)[1:-1] if ord(c) < 32 or 127 <= ord(c) <= 159 else c for c in brief
            )
            hint = r" (a backslash in jobs.json was read as an escape: write \\ or /)" if control else ""
            return f"brief not found: {shown}{hint}"
    return None


def brief_digest(job, repo):
    """One hash over the job's brief files as they are now; a missing brief counts as its own content."""
    digest = sha256()
    for brief in job["briefs"]:
        try:
            digest.update((repo / brief).read_bytes())
        except OSError:
            digest.update(b"missing:" + brief.encode("utf-8"))
    return digest.hexdigest()[:16]


def agent_name(job_id, n, root):
    """Herdr agent names are global to the server: a tag from the run directory keeps two runs with the same job id
    apart. Herdr allows 32 characters, so the job id is cut, never the attempt number or the tag."""
    suffix = f"-{n}-{sha256(str(root).encode('utf-8')).hexdigest()[:4]}"
    return re.sub(r"[^a-z0-9-]", "-", f"run-{job_id}".lower())[: 32 - len(suffix)] + suffix


def launch_prompt(job):
    also = f" and the paths {', '.join(job['writes'])}" if job.get("writes") else ""
    helpers = HELPERS.format(models=", ".join(job["helpers"]), job=job["id"]) if job.get("helpers") else NO_HELPER
    return PROMPT.format(briefs=", ".join(job["briefs"]) or "(none)", out=job["out"], also=also, helpers=helpers)


def pi_log(job, attempt, repo):
    """This attempt's Pi session log as (path, a head/tail sample of its entries), or None.

    --name is a session_info entry near the start. Only files created for this attempt count; names repeat
    across runs. Large/missing/unreadable logs are diagnostic gaps, never proof that a worker stopped. The sample
    is enough for the last turn and its error, not for a usage sum: `usage_of` reads the whole file.
    """
    if job.get("harness", "pi") != "pi":
        return None
    root = Path(os.environ.get("PM_RUN_PI_SESSIONS", Path.home() / ".pi" / "agent" / "sessions"))
    folder = root / ("--" + re.sub(r"[/\\:]", "-", str(repo).lstrip("/\\")) + "--")
    try:
        paths = [Path(attempt["session_log"])] if attempt.get("session_log") else folder.glob("*.jsonl")
        for path in paths:
            try:
                if path.stat().st_mtime < attempt["started"]:
                    continue
                with path.open("rb") as f:
                    head = f.read(65536)
                    f.seek(max(len(head), path.stat().st_size - 1024 * 1024))
                    tail = f.read(1024 * 1024)
                entries = []
                for line in (head + b"\n" + tail).splitlines():
                    try:
                        entry = json.loads(line)
                        if isinstance(entry, dict):
                            entries.append(entry)
                    except (ValueError, UnicodeError):
                        pass  # a partial write or a cut line at a sample boundary
                header = next((e for e in entries if e.get("type") == "session"), {})
                stamp = datetime.fromisoformat(header.get("timestamp", "").replace("Z", "+00:00")).timestamp()
                if stamp < attempt["started"] or not any(
                    e.get("type") == "session_info" and e.get("name") == attempt["name"] for e in entries
                ):
                    continue
                attempt["session_log"] = str(path)
                return path, entries
            except (OSError, ValueError, TypeError):
                continue
    except OSError:
        pass
    return None


def turn_end(job, attempt, repo):
    """The last assistant message of this attempt's Pi session log: its stop reason or provider error."""
    if job.get("harness", "pi") != "pi":
        return "session log not found (only Pi logs supported)"
    attempt.update(stopReason=None, errorMessage=None)  # an earlier turn's error is no evidence for this one
    found = pi_log(job, attempt, repo)
    if not found:
        return "session log not found for this attempt (bounded Pi log lookup)"
    messages = [e.get("message") for e in found[1] if e.get("type") == "message"]
    last = next((m for m in reversed(messages) if isinstance(m, dict) and m.get("role") == "assistant"), {})
    attempt["stopReason"] = last.get("stopReason")
    attempt["errorMessage"] = last.get("errorMessage")
    if last.get("stopReason") == "error":
        return f"provider error: {last.get('errorMessage') or 'no error message in session log'}"
    return f"Pi stopReason: {last.get('stopReason') or 'not found in session log sample'}"


def log_time(entry):
    """Epoch seconds of a Pi log line, from its own timestamp or its message's (ms); None when it has neither."""
    stamp = entry.get("timestamp")
    if isinstance(stamp, str):
        try:
            return datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp()
        except ValueError:
            pass
    message = entry.get("message") if isinstance(entry.get("message"), dict) else {}
    for value in (stamp, message.get("timestamp")):
        if isinstance(value, (int, float)):
            return value / 1000 if value > 1e11 else float(value)  # Pi keeps message times in milliseconds
    return None


def usage_of(job, attempt, repo, log=None):
    """What this attempt's Pi session log says it used, or None when there is no log or nothing in it.

    Sums come from the assistant messages written after the attempt started, so a log that also holds earlier turns
    counts only this one; `turns` is how many of those messages were summed. cost_usd is null unless every message
    reported cost.total. A line that does not parse is skipped and named once through `log`, never raised: reading the
    log must not break a run.
    """
    found = pi_log(job, attempt, repo)
    if not found:
        return None
    path = found[0]
    keys = (("input", "input"), ("output", "output"), ("cache_read", "cacheRead"), ("cache_write", "cacheWrite"))
    sums = {name: 0 for name, _ in keys}
    sums["total_tokens"], totals_known, cost, cost_known, counted, skipped = 0, True, 0.0, True, 0, 0
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                except ValueError:
                    if line.strip():
                        skipped += 1
                    continue
                message = entry.get("message") if isinstance(entry, dict) else None
                usage = message.get("usage") if isinstance(message, dict) else None
                if not isinstance(usage, dict) or message.get("role") != "assistant":
                    continue
                written = log_time(entry)
                if written is not None and written < attempt["started"]:
                    continue
                counted += 1
                for name, key in keys:
                    value = usage.get(key)
                    if isinstance(value, (int, float)):
                        sums[name] += value
                total = usage.get("totalTokens")
                totals_known = totals_known and isinstance(total, (int, float))
                if isinstance(total, (int, float)):
                    sums["total_tokens"] += total
                part = usage.get("cost")
                reported = part.get("total") if isinstance(part, dict) else None
                cost_known = cost_known and isinstance(reported, (int, float))
                cost += reported if isinstance(reported, (int, float)) else 0
    except OSError:
        return None
    if skipped and log:
        log(f"USAGE {job['id']}: skipped {skipped} unreadable line(s) in {path.name}; the rest was counted")
    if not counted:
        return None
    if not totals_known:  # a message without the field: the parts still add up to what was used
        sums["total_tokens"] = sum(sums[name] for name, _ in keys)
    return {**sums, "turns": counted, "cost_usd": round(cost, 9) if cost_known else None}


class Run:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.repo = Path(os.environ.get("PM_RUN_REPO", Path.cwd())).resolve()
        self.state_path = self.root / "receipts.json"
        self.log_path = self.root / "pm_run.log"
        self.bad = {}  # file name -> the parse error last logged for it
        self.failures_warned = False  # the shared failure log could not be written; said once

    def log(self, text):
        line = f"{time.strftime('%H:%M:%S')} {text}"
        # A cp1252 console cannot print Claude Code's marks (●, ⎿); the console gets '?', the log file keeps them.
        enc = sys.stdout.encoding or "utf-8"
        print(line.encode(enc, "replace").decode(enc), flush=True)
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        if text.split(" ", 1)[0] in FAILURES:
            failures = self.repo / ".pm" / "local" / "failures.log"
            try:  # best effort: a held or unwritable shared log must never stop the loop that logs
                failures.parent.mkdir(parents=True, exist_ok=True)
                run, event = "-".join(self.root.name.split()), " ".join(text.split())[:400]  # one line each
                with failures.open("a", encoding="utf-8") as f:
                    f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {run} {event}\n")
            except OSError as exc:
                if not self.failures_warned:  # once, and without log(): that would recurse
                    self.failures_warned = True
                    warning = f"pm_run: could not append to {failures}: {exc}; failures stay in pm_run.log only"
                    print(warning, flush=True)
                    with self.log_path.open("a", encoding="utf-8") as f:
                        f.write(warning + "\n")

    def load(self, name, default, live=False):
        """A missing file gives the default; a file that is not valid JSON stops the run with the parse error.
        In the running loop (live) it gives the default instead, the last good copy, and logs the error once:
        a person editing jobs.json may save it half-written. A file another process keeps locked is handled the same.

        utf-8-sig also reads a file that starts with a byte order mark, as Windows PowerShell 5.1 writes it.
        """
        path = self.root / name
        try:
            data = json.loads(held(lambda: path.read_text(encoding="utf-8-sig")))
            self.bad.pop(name, None)  # a later error, even the same one, is logged again
            return data
        except FileNotFoundError:
            return default
        except (ValueError, PermissionError) as exc:
            what = "not valid JSON" if isinstance(exc, ValueError) else "held by another process"
            if not live:
                sys.exit(f"pm_run: {path} is {what}: {exc}")
            if str(exc) != self.bad.get(name):
                self.log(f"SKIPPED {name}: {what} ({exc}); the last good copy is used until it can be read")
            self.bad[name] = str(exc)
            return default

    def save(self, state):
        """Write the receipts; True when they reached the file. If another process keeps it locked, the caller keeps
        the state in memory as the truth and saves again next tick."""
        tmp = self.state_path.with_suffix(".tmp")
        try:
            held(lambda: tmp.write_text(json.dumps(state, indent=1), encoding="utf-8"))
            held(lambda: os.replace(tmp, self.state_path))
            return True
        except PermissionError as exc:
            held_file = Path(exc.filename).name if exc.filename else "receipts.json"
            self.log(f"SAVE-FAILED {held_file} is held by another process ({exc}); saved again next tick")
            return False

    def cycle(self, jobs, caps, state, saved):
        """One pass of the loop: re-read the run files, tick, save; returns (jobs, caps, state, saved).
        receipts.json is re-read only after a save that worked: otherwise it is older than the state in memory."""
        try:
            jobs, caps = self.load("jobs.json", jobs, live=True), self.load("caps.json", caps, live=True)
            if saved:
                state = self.load("receipts.json", state, live=True)
            self.tick(jobs, state, caps)
        except Exception as exc:  # noqa: BLE001 - one bad tick must not leave the workers unwatched
            error = f"{type(exc).__name__}: {exc}"
            if error != self.bad.get("tick"):  # once per distinct error, not every tick
                self.log(f"TICK-ERROR {error}; the loop goes on (traceback in pm_run.log)")
                with self.log_path.open("a", encoding="utf-8") as f:
                    f.write(traceback.format_exc())
            self.bad["tick"] = error
        return jobs, caps, state, self.save(state)

    # ---- lease: one scheduler per run directory -------------------------------------------------
    def take_lease(self):
        """Create the lease atomically; take over only a lease whose holder has gone silent."""
        lease = self.root / "pm_run.lease"
        for _ in range(2):
            try:
                fd = os.open(lease, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, f"{os.getpid()} {time.time()}".encode())
                os.close(fd)
                return
            except FileExistsError:
                try:
                    pid, stamp = lease.read_text().split()
                    alive = time.time() - float(stamp) < 3 * TICK
                except (OSError, ValueError):
                    alive = False
                if alive:
                    sys.exit(f"another pm_run (pid {pid}) holds {lease}; stop it first")
                lease.unlink(missing_ok=True)
        sys.exit(f"could not take {lease}")

    def refresh_lease(self):
        (self.root / "pm_run.lease").write_text(f"{os.getpid()} {time.time()}")

    # ---- Herdr: where and how a worker runs -------------------------------------------------------
    def workspace(self, state):
        """One Herdr workspace per run, labelled with the run directory's name. Its first pane stays an idle shell:
        closing a workspace's last pane closes the workspace, so workers always get their own tab."""
        ws = state.get("_herdr_workspace")
        response = herdr("workspace", "list")
        if "error" in response:
            (self.root / "pm_run.lease").unlink(missing_ok=True)
            message = " ".join(response["error"].get("message", "unknown error").split())
            sys.exit(f"Herdr server not running: {message}")
        listed = response.get("result", {}).get("workspaces", [])
        if ws and any(w["workspace_id"] == ws for w in listed):
            return ws
        for w in listed:
            if w.get("label") == self.root.name:
                state["_herdr_workspace"] = w["workspace_id"]
                return w["workspace_id"]
        made = herdr("workspace", "create", "--cwd", str(self.repo), "--label", self.root.name, "--no-focus")
        if "error" in made:
            (self.root / "pm_run.lease").unlink(missing_ok=True)
            message = " ".join(made["error"].get("message", "unknown error").split())
            sys.exit(f"Herdr server not running: {message}")
        ws = made["result"]["workspace"]["workspace_id"]
        state["_herdr_workspace"] = ws
        return ws

    def launch(self, job, attempt, state):
        """Open a worker tab and send the brief; True when a live session is ready to watch."""
        ws = self.workspace(state)
        tab = herdr("tab", "create", "--workspace", ws, "--label", job["id"], "--cwd", str(self.repo), "--no-focus")
        pane = tab.get("result", {}).get("root_pane", {}).get("pane_id")
        attempt["pane"] = pane
        if not pane:
            attempt["launch_error"] = tab.get("error", {}).get("message", "tab has no pane")
            return False
        if job.get("setup"):  # e.g. the env vars of a Claude Code profile; name env vars, never put a secret here
            herdr("pane", "run", str(pane), job["setup"])
            time.sleep(SETUP_S)
        harness = job.get("harness", "pi")
        agent_args = ["--kind", harness, "--pane", str(pane), "--", "--model", job["model"]]
        if harness == "pi":
            agent_args += ["--thinking", job.get("thinking", "high"), "--name", attempt["name"]]
        agent_args += NO_HELPERS[harness]
        if harness == "claude":
            # A project .mcp.json makes Claude Code ask which servers to enable before the first turn, and the brief
            # would land in that dialog. A settings file, not inline JSON: the pane's shell may strip the quotes.
            settings = self.root / "claude-settings.json"
            settings.write_text(json.dumps(CLAUDE_SETTINGS) + "\n", encoding="utf-8")
            agent_args += ["--settings", str(settings)]
        attempt["model"] = job["model"]  # the model asked for; the session log shows what actually ran
        start = herdr("agent", "start", attempt["name"], *agent_args, *job.get("args", []))
        if "error" in start:
            attempt["launch_error"] = start["error"].get("message", "")
            attempt["launch_code"] = start["error"].get("code", "")
            return False
        if harness == "agy" and self.first_run(attempt):
            return False
        if not self.wait_ready(attempt):
            return False
        attempt["seq0"] = attempt.get("completion_seq")
        sent = herdr("agent", "prompt", attempt["name"], launch_prompt(job))
        attempt["prompted"] = time.time()
        attempt["briefs_sha"] = brief_digest(job, self.repo)  # the text the worker was just pointed at
        self.reset_observation(attempt)
        if "error" in sent:
            self.log(
                f"HOLD {job['id']}: Herdr did not accept the brief; the same session is watched and the brief "
                "is sent again if the worker stays idle"
            )
        return True  # a live agent is watched even when Herdr rejected its first prompt

    def first_run(self, attempt):
        """True when agy shows its first-run screen. Herdr reports agy ready about 4 s before agy draws anything
        (Herdr 0.9.5, agy 1.4.2), so read until the screen changes from the bare launch line, for up to START_S."""
        before = None
        for _ in range(max(1, int(START_S))):
            screen = herdr("agent", "read", attempt["name"], "--source", "visible", plain=True)
            if isinstance(screen, str):
                found = FIRST_RUN.search(screen)
                if found:
                    attempt["first_run"] = found.group()
                    return True
                if before is not None and screen != before:
                    return False
                before = screen if before is None else before
            time.sleep(1)
        return False

    def trust_screen(self, attempt):
        """A blocked start may not have a registered agent, so read its pane directly."""
        if not attempt.get("pane"):
            return False
        screen = herdr("pane", "read", str(attempt["pane"]), "--source", "visible", plain=True)
        return bool(TRUST.search(screen)) if isinstance(screen, str) else None

    def wait_ready(self, attempt):
        """Wait for an idle input; use the old fixed delay only if Herdr reports no state."""
        deadline = time.monotonic() + READY_S
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                attempt["launch_error"] = f"agent not ready after {READY_S:g} s; brief not sent"
                return False
            status = self.status_of(attempt, timeout=remaining)
            if time.monotonic() >= deadline:
                attempt["launch_error"] = f"agent not ready after {READY_S:g} s; brief not sent"
                return False
            if status in ("ready", "idle"):
                return True
            if status == "unknown":
                delay = min(SETUP_S, max(0, deadline - time.monotonic()))
                if delay > 0:
                    time.sleep(delay)
                if time.monotonic() >= deadline:
                    attempt["launch_error"] = f"agent not ready after {READY_S:g} s; brief not sent"
                    return False
                return True
            if status is None or status == "blocked":
                attempt["launch_error"] = f"agent {'is gone' if status is None else 'is blocked'}; brief not sent"
                attempt["launch_code"] = status or "agent_not_found"
                return False
            time.sleep(min(1, max(0, deadline - time.monotonic())))

    def status_of(self, attempt, timeout=None):
        got = herdr("agent", "get", attempt["name"], timeout=timeout)
        if "error" in got:
            if got["error"].get("code") == "agent_not_found":
                return None
            attempt["herdr_error"] = got["error"].get("message", "unknown Herdr error")
            return "unknown"
        attempt.pop("herdr_error", None)
        agent = got["result"]["agent"]
        attempt["completion_seq"] = agent.get("completion_seq")
        if "state_change_seq" in agent:
            attempt["state_seq"] = agent["state_change_seq"]
        return agent.get("agent_status") or "unknown"

    def stop(self, attempt):
        """Close the worker's pane; True only when the close succeeded and Herdr no longer knows the agent."""
        if attempt.get("pane") and "error" in herdr("pane", "close", str(attempt["pane"])):
            return False
        for _ in range(5):
            if self.status_of(attempt) is None:
                return True
            time.sleep(1)
        return False

    def reset_observation(self, attempt):
        attempt.update(seen_hash=None, seen_at=attempt["prompted"], stall=False, loop=False, loop_line=None)
        attempt.update(settled_hash=None, settled_at=None)

    def pane_quiet(self, attempt, now):
        """Seconds the pane's content has stayed the same while the turn looks settled; None when it cannot be read.
        Herdr showed live turns as settled on 18 Oct (Claude Code mid-turn, Pi with its own agent folder), and
        without a session log nothing else tells such a turn from a finished one."""
        text = herdr("agent", "read", attempt["name"], "--source", "visible", plain=True)
        if not isinstance(text, str):
            return None
        digest = sha256(pane_content(text).encode("utf-8")).hexdigest()
        if digest != attempt.get("settled_hash"):
            attempt.update(settled_hash=digest, settled_at=now)
        return now - attempt["settled_at"]

    def warn_pane(self, job, attempt, now):
        # "visible": Herdr refuses "recent" while a Pi agent works (alternate screen), checked 9 Oct.
        text = herdr("agent", "read", attempt["name"], "--source", "visible", plain=True)
        if not isinstance(text, str):
            return  # failed reads neither alter the episode nor warn
        content = pane_content(text)
        digest = sha256(content.encode("utf-8")).hexdigest()
        previous = attempt.get("seen_hash")
        changed = previous is not None and digest != previous
        if changed:
            attempt.update(seen_at=now, stall=False)
        attempt.setdefault("seen_at", attempt.get("prompted", attempt["started"]))
        attempt.setdefault("stall", False)
        attempt.setdefault("loop", False)
        lines = [line for line in content.splitlines() if line.strip()][-30:]
        line, count = Counter(lines).most_common(1)[0] if lines else (None, 0)
        repeated = line if count >= 15 else None
        if repeated is None:
            attempt["loop"] = False
        elif changed and repeated == attempt.get("loop_line") and not attempt["loop"]:
            attempt["loop"] = True
            self.log(
                f'LOOP {job["id"]}: suspected loop, new output keeps repeating "{line[:60]}" '
                f"({count} of the last 30 lines); not stopped, the caller decides"
            )
        attempt.update(seen_hash=digest, loop_line=repeated)
        if now - attempt["seen_at"] >= STALL_S and not attempt["stall"]:
            attempt["stall"] = True
            self.log(
                f"STALLED {job['id']}: no new output for {round((now - attempt['seen_at']) / 60, 1):g} min; "
                f"likely {stall_cause(job, content)}; not stopped, the caller decides"
            )

    # ---- one scheduling pass --------------------------------------------------------------------------
    def tick(self, jobs, state, caps):
        now = time.time()
        busy = {}
        self.forget_removed(jobs, state)
        for job in jobs:
            s = state.setdefault(job["id"], {"state": "pending", "attempts": []})
            if job.get("stop") and s["state"] not in ENDED:
                self.stop_on_request(job, s)
                continue
            if s["state"] != "started":
                continue
            a = s["attempts"][-1]
            status = self.status_of(a)
            a["herdr"] = status
            if status == "unknown":
                busy[job.get("bucket", "default")] = busy.get(job.get("bucket", "default"), 0) + 1
                continue  # no kill, nudge or retry on a failed query, even after the hard limit
            question = None
            if status in SETTLED and job.get("harness") == "agy":
                screen = herdr("agent", "read", a["name"], "--source", "visible", plain=True)
                if isinstance(screen, str):
                    lines = [line.strip() for line in screen.splitlines() if line.strip()]
                    tail = "\n".join(lines[-10:])
                    found = PERMISSION.search(tail)
                    if found:
                        end = tail.find("\n", found.end())
                        question = " ".join(tail[found.start() : end if end >= 0 else None].lower().split())
                elif a.get("ask_kind") == "permission":
                    question = a.get("asked_question")  # a failed read cannot prove the question was answered
            if status == "blocked" or question:
                kind = "permission" if question else "blocked"
                # The counter also spots a new blocked question answered between two ticks.
                if (
                    not a.get("asking")
                    or a.get("state_seq") != a.get("asked_seq")
                    or kind != a.get("ask_kind")
                    or question != a.get("asked_question")
                ):
                    a.update(
                        asking=True,
                        asked=now,
                        asked_seq=a.get("state_seq"),
                        asks=a.get("asks", 0) + 1,
                        ask_kind=kind,
                        asked_question=question,
                    )
                    self.log(
                        f"WAITING {job['id']}: answer the worker in Herdr pane {a.get('pane')} "
                        f"(question {a['asks']} in this session)"
                    )
                busy[job.get("bucket", "default")] = busy.get(job.get("bucket", "default"), 0) + 1
                continue
            a.pop("asking", None)
            a.pop("ask_kind", None)
            a.pop("asked_question", None)
            if status == "working":
                a["worked"] = True
                self.warn_pane(job, a, now)
            settled = status in SETTLED and now - a.get("prompted", a["started"]) > SETTLE_S
            if status is None or settled:
                if status is None:
                    a["stopped_confirmed"] = True
                art, why = check_artifact(self.repo / job["out"], a["started"], job.get("min_words", 0))
                if art:
                    if a.get("briefs_sha") and brief_digest(job, self.repo) != a["briefs_sha"]:
                        a["brief_changed"] = True
                        self.log(
                            f"BRIEF-CHANGED {job['id']}: a brief changed while the worker ran; its report answers the "
                            f"brief it read, so check it against the job"
                        )
                    a.update(artifact=art, ended=now, stopped_confirmed=a.get("stopped_confirmed") or self.stop(a))
                    if not a["stopped_confirmed"]:
                        self.fail_or_retry(job, s, "artifact present but the worker could not be confirmed stopped")
                        continue
                    self.count_usage(job, a)
                    rc, verify_why = run_verify(job, self.repo)
                    a["verify_rc"] = rc
                    if rc is None:
                        s["state"] = "artifact-present"
                        self.log(f"ARTIFACT {job['id']} ({art['words']} words): no check, so not verified")
                    elif rc == 0:
                        s["state"] = "verified"
                        self.log(f"VERIFIED {job['id']} ({art['words']} words, check ok)")
                    else:
                        s["state"], a["why"] = "check-failed", f"artifact present but {verify_why}"
                        self.log(
                            f"CHECK-FAILED {job['id']} ({art['words']} words): {verify_why}; report kept at "
                            f"{job['out']}, no relaunch; fix the check or the report, then --check {job['id']}"
                        )
                    continue
                a["turn_end"] = turn_end(job, a, self.repo)
                why = f"{why}; {a['turn_end']}"
                if status is None:
                    self.fail_or_retry(job, s, f"worker is gone and {why}")
                    continue
                size, quiet = session_log(a, now)
                source = "Pi wrote its log"
                if quiet is None:
                    quiet, source = self.pane_quiet(a, now), "its pane last changed"
                if quiet is not None and quiet < QUIET_S:
                    if not a.get("held"):
                        a["held"] = True
                        self.log(f"HOLD {job['id']}: turn looks settled but {source} {quiet:.0f} s ago; {why}")
                elif a.get("wait_until", 0) > now:
                    pass  # waiting out a short quota reset (QUOTA-WAIT); the nudge comes after it
                elif self.stop_hand_over(job, s, a, why, now):
                    if s["state"] == "handed-over":
                        continue
                elif not self.nudge(job, s, a, now, size, why):
                    continue
            elif now - a["started"] > HARD_S + a.get("overtime", 0):
                if a.get("overtime"):
                    self.hand_over(job, s, "still working after the hard limit and the extra time")
                    continue
                a["overtime"] = OVERTIME_S
                self.log(f"OVERTIME {job['id']}: hard limit reached while working; {OVERTIME_S / 60:g} min more, once")
            busy[job.get("bucket", "default")] = busy.get(job.get("bucket", "default"), 0) + 1
        for job in jobs:
            s = state[job["id"]]
            if s["state"] != "pending":
                continue
            if s.get("trust_wait"):
                a = s["trust_wait"]
                trust = self.trust_screen(a)
                if trust is None:
                    continue  # a failed read is not an answer
                if trust:
                    if not a.get("trust_logged"):
                        a["trust_logged"] = True
                        self.log(
                            f"WAITING {job['id']}: agy asks to trust {self.repo}; open agy there once and answer Yes, "
                            f"then the job starts (Herdr pane {a['pane']})"
                        )
                    continue
                if not self.stop(a):
                    s.update(
                        state="failed",
                        why="trust pane could not be confirmed closed; no retry",
                        trust_stopped_confirmed=False,
                    )
                    self.log(f"FAILED {job['id']}: {s['why']}; close the pane and start a new run")
                    continue
                s.pop("trust_wait")
            deps = [state.get(d, {}).get("state") for d in job.get("after", [])]
            if any(d in ENDED and d != "verified" for d in deps):
                s["state"] = "blocked"
                self.log(f"BLOCKED {job['id']}: a dependency failed or was never verified")
                continue
            if any(d != "verified" for d in deps):
                continue
            bucket = job.get("bucket", "default")
            if busy.get(bucket, 0) >= caps.get(bucket, 2):
                continue
            why = missing_brief(job, self.repo)
            if why:
                s.update(state="failed", why=why)
                self.log(f"FAILED {job['id']}: {why}; fix the path in jobs.json and start a new run")
                continue
            n = len(s["attempts"]) + 1
            out = self.repo / job["out"]
            try:
                if (
                    n > 1
                    and not s["attempts"][-1].get("output_kept")
                    and out.exists()
                    and out.stat().st_mtime >= s["attempts"][-1]["started"]
                ):
                    kept = held(lambda: keep_output(out, f"{out.stem}.attempt{n - 1}", move=True))
                    s["attempts"][-1]["output_kept"] = str(kept)
                    self.log(f"KEPT {job['id']}: previous output saved as {kept.name}")
                elif n == 1 and out.exists() and not s.get("output_kept"):
                    kept = held(lambda: keep_output(out, f"{out.stem}.kept", move=False))
                    s["output_kept"] = str(kept)
                    self.log(f"KEPT {job['id']}: {out.name} existed before this run; a copy is at {kept.name}")
            except OSError as exc:
                s["state"] = "failed"
                self.log(f"KEPT-FAILED {job['id']}: could not keep the previous output, so no worker starts: {exc}")
                continue
            a = {"name": agent_name(job["id"], n, self.root), "started": time.time()}
            s["attempts"].append(a)
            if self.launch(job, a, state):
                s["state"] = "started"
                busy[bucket] = busy.get(bucket, 0) + 1
                self.log(f"LAUNCH {job['id']} attempt {n} on {job['model']} in Herdr pane {a['pane']}")
            elif (
                job.get("harness") == "agy"
                and "blocked" in (a.get("launch_code", "") + " " + a.get("launch_error", "")).lower()
                and (trust := self.trust_screen(a)) is not False
            ):
                s["trust_wait"] = s["attempts"].pop()  # setup needs an owner, not a paid attempt
                if trust:
                    a["trust_logged"] = True
                    self.log(
                        f"WAITING {job['id']}: agy asks to trust {self.repo}; open agy there once and answer Yes, "
                        f"then the job starts (Herdr pane {a['pane']})"
                    )
                else:
                    self.log(
                        f"WAITING {job['id']}: could not read blocked agy pane {a['pane']}; watching it before retry"
                    )
            elif a.get("first_run"):
                self.hand_over(
                    job,
                    s,
                    f'first-run screen ("{a["first_run"]}"); brief not sent: finish the setup once in Herdr tab '
                    f"{job['id']}, then rerun the job",
                )
            else:
                self.fail_or_retry(job, s, f"launch failed: {a.get('launch_error', 'prompt not sent')}")
        return state

    def count_usage(self, job, attempt):
        """Keep what the attempt's session log says it used; a log that cannot be read costs a log line, never a run."""
        try:
            usage = usage_of(job, attempt, self.repo, self.log)
        except Exception as exc:  # noqa: BLE001 - reading usage must not break the loop that reads it
            self.log(f"USAGE {job['id']}: not read ({type(exc).__name__}: {exc}); the run goes on")
            return
        if usage:
            attempt["usage"] = usage

    def stop_on_request(self, job, s):
        """`--stop <job>` set "stop" in jobs.json: close a live worker's pane; a pending job never starts."""
        how = "it never started"
        if s["state"] == "started":
            a = s["attempts"][-1]
            a.update(stopped_confirmed=self.stop(a), ended=time.time(), why="stopped on request")
            self.count_usage(job, a)
            how = f"Herdr pane {a.get('pane')} closed" if a["stopped_confirmed"] else "its pane could not be closed"
        elif s.get("trust_wait"):
            a = s.pop("trust_wait")
            a["stopped_confirmed"] = self.stop(a)
            s["trust_stopped_confirmed"] = a["stopped_confirmed"]
            how = f"Herdr pane {a.get('pane')} closed" if a["stopped_confirmed"] else "its pane could not be closed"
        s["state"] = "stopped"
        self.log(f"STOPPED {job['id']}: on request, {how}; its successors are blocked")

    def forget_removed(self, jobs, state):
        """A started job deleted from jobs.json is no longer watched: say so once, and leave its pane alone."""
        ids = {job["id"] for job in jobs}
        for jid, s in state.items():
            if jid.startswith("_") or jid in ids or not (s.get("state") == "started" or s.get("trust_wait")):
                continue
            s["state"] = "removed"
            pane = s["trust_wait"]["pane"] if s.get("trust_wait") else s["attempts"][-1].get("pane")
            self.log(
                f"REMOVED {jid}: deleted from jobs.json while its worker runs in Herdr pane {pane}; no longer "
                f"watched and the pane is left open (to stop a job, use --stop {jid})"
            )

    def nudge(self, job, s, a, now, size, why):
        """Prompt a settled worker again in its own session; False when the job was handed over instead."""
        stamp = output_stamp(self.repo / job["out"])
        if "nudge_size" in a:  # idle: since it was sent, the session log did not grow or the output did not change
            grew = size is not None and a["nudge_size"] is not None and size > a["nudge_size"]
            changed = stamp != a.get("nudge_stamp")
            a["idle_nudges"] = 0 if grew and changed else a.get("idle_nudges", 0) + 1
        if a.get("idle_nudges", 0) >= MAX_NUDGES:
            self.hand_over(job, s, f"{MAX_NUDGES} nudges in a row brought no new work; turn settled but {why}")
            return False
        note = ""
        if now - a["started"] > HARD_S + a.get("overtime", 0):
            if a.get("overtime"):
                self.hand_over(job, s, f"past the hard limit and the extra time; turn settled but {why}")
                return False
            a["overtime"] = OVERTIME_S
            note = f" You are past the time limit: finish within {OVERTIME_S / 60:g} minutes."
        a["nudges"] = a.get("nudges", 0) + 1
        lost = not a.get("worked") and (
            a.get("seq0") is None or a.get("completion_seq") is None or a["completion_seq"] == a["seq0"]
        )
        prompt = (
            launch_prompt(job) if lost else RESUME.format(briefs=", ".join(job["briefs"]) or "(none)", out=job["out"])
        )
        herdr("agent", "prompt", a["name"], prompt + note)
        a.update(prompted=now, nudge_size=size, nudge_stamp=stamp, held=False)
        self.reset_observation(a)
        if lost:
            self.log(f"PROMPT {job['id']}: no turn ran after the brief was sent; brief resent{note}")
        else:
            self.log(f"RESUME {job['id']}: turn settled but {why}; same session, nudge {a['nudges']}{note}")
        return True

    def stop_hand_over(self, job, s, a, why, now):
        """Hand over a settled worker whose quota is used up or whose sign-in ran out, or wait out a quota that resets
        soon; True when it did either."""
        sign = stop_sign(a, herdr("agent", "read", a["name"], "--source", "visible", plain=True))
        if not sign or sign[1] == a.get("waited_for"):  # after the wait the old message is still on the pane
            return False
        kind, text = sign
        a[kind] = text
        wait = reset_seconds(text) if kind == "quota" else None
        ends = now + wait + 30 if wait is not None else 0
        limit = a["started"] + HARD_S + a.get("overtime", 0)
        if wait is not None and wait <= QUOTA_WAIT_S and not a.get("quota_waited") and ends <= limit:
            a.update(waited_for=text, wait_until=ends, quota_waited=True)  # once per attempt, inside the time limit
            self.log(
                f'QUOTA-WAIT {job["id"]}: "{text}"; the limit resets in {wait / 60:.0f} min, so the same session '
                f"gets a nudge after it instead of a hand-over"
            )
            return True
        if kind == "login":
            what = "sign the harness in again (Claude Code: run claude, then /login), then rerun the job"
            self.hand_over(job, s, f'sign-in needed: "{text}"; not resent, {what}; {why}')
        else:
            self.hand_over(
                job, s, f'provider quota or usage limit: "{text}"; not resent, rerun the job after it resets; {why}'
            )
        return True

    def hand_over(self, job, s, why):
        """Stop watching a live worker without closing it: the lead reads its tab and decides."""
        a = s["attempts"][-1]
        s["state"] = "handed-over"
        a.update(why=why, ended=time.time())
        self.count_usage(job, a)
        self.log(f"HANDED-OVER {job['id']}: {why}; the session stays open in Herdr pane {a.get('pane')}, no relaunch")

    def fail_or_retry(self, job, s, why):
        a = s["attempts"][-1]
        if "stopped_confirmed" not in a:
            a["stopped_confirmed"] = self.stop(a)
        a["ended"] = time.time()
        self.count_usage(job, a)
        if not a["stopped_confirmed"]:
            why += "; worker could not be confirmed stopped; no retry"
        if not a["stopped_confirmed"] or len(s["attempts"]) >= MAX_TRIES:
            s["state"] = "failed"
            self.log(f"FAILED {job['id']}: {why}; {len(s['attempts'])} attempts")
        else:
            s["state"] = "pending"
            self.log(f"RETRY {job['id']}: {why}")
        s["attempts"][-1]["why"] = why

    def status(self, jobs, state):
        per_model, per_job = usage_tally(jobs, state)

        def used(jid):
            """The job's tokens and cost as two printed columns; "-" where no attempt recorded them."""
            row = per_job.get(jid)
            tokens = short_tokens(row["tokens"] if row else None)
            cost = short_cost(row["cost"] if row and row["known"] else None)
            return f"{tokens:>10}{cost:>10}"

        print(f"{'job':<16}{'state':<18}{'tries':>6}{'tokens':>10}{'cost':>10}  last attempt")
        for job in jobs:
            s = state.get(job["id"], {"state": "pending", "attempts": []})
            a = s["attempts"][-1] if s["attempts"] else {}
            detail = ", ".join(
                f"{k}={a[k]}"
                for k in ("pane", "model", "herdr", "stall", "loop", "brief_changed", "verify_rc", "why")
                if a.get(k) is not None
            )
            if s.get("why"):
                detail += (", " if detail else "") + f"why={s['why']}"
            if s.get("trust_wait"):
                detail += (", " if detail else "") + f"waiting for blocked agy pane {s['trust_wait'].get('pane')}"
            if a.get("asking"):
                detail += (", " if detail else "") + f"waiting for an answer in pane {a.get('pane')}"
            if a.get("wait_until", 0) > time.time():  # a running quota wait, as a clock time
                detail += f", waiting until {time.strftime('%H:%M', time.localtime(a['wait_until']))}"
            print(f"{job['id']:<16}{s['state']:<18}{len(s['attempts']):>6}{used(job['id'])}  {detail}")
        ids = {job["id"] for job in jobs}
        for jid, s in state.items():
            if not jid.startswith("_") and jid not in ids:
                print(f"{jid:<16}{s['state'] + ' (not in jobs.json)':<18}{len(s['attempts']):>6}{used(jid)}")
        self.print_totals(per_model)

    def failure_tally(self):
        """Count shared failure-log events, not event names mentioned in a message."""
        path = self.repo / ".pm" / "local" / "failures.log"
        counts = Counter()
        try:
            with path.open(encoding="utf-8", errors="replace") as f:
                for line in f:
                    parts = line.split(maxsplit=4)
                    if (
                        len(parts) >= 4
                        and re.fullmatch(r"\d{4}-\d\d-\d\d", parts[0])
                        and re.fullmatch(r"\d\d:\d\d:\d\d", parts[1])
                        and parts[3] in FAILURES
                    ):
                        counts[parts[3]] += 1
        except FileNotFoundError:
            pass
        except OSError as exc:
            print(f"failures: could not read {path}: {exc}; check access and try --status --tally again")
            return
        ordered = sorted(counts, key=lambda kind: (-counts[kind], kind))
        print("failures: " + (", ".join(f"{kind}={counts[kind]}" for kind in ordered) or "none"))

    def print_totals(self, per_model):
        """One line per model and the grand total; a cost any attempt did not report stays "-"."""
        print(f"{'model':<24}{'tokens':>10}{'cost':>10}")
        for model in sorted(per_model):
            row = per_model[model]
            print(
                f"{model:<24}{short_tokens(row['tokens']):>10}{short_cost(row['cost'] if row['known'] else None):>10}"
            )
        tokens = sum(row["tokens"] for row in per_model.values())
        known = per_model and all(row["known"] for row in per_model.values())
        cost = sum(row["cost"] for row in per_model.values()) if known else None
        print(f"{'total':<24}{short_tokens(tokens if per_model else None):>10}{short_cost(cost):>10}")

    def request_stop(self, jobs, state, job_id):
        """Mark a job "stop" in jobs.json; the running loop stops it on its next tick."""
        job = next((j for j in jobs if j["id"] == job_id), None)
        if not job:
            sys.exit(f"no job {job_id}")
        job["stop"] = True
        tmp = self.root / "jobs.json.tmp"
        try:
            held(lambda: tmp.write_text(json.dumps(jobs, indent=1) + "\n", encoding="utf-8"))
            held(lambda: os.replace(tmp, self.root / "jobs.json"))
        except PermissionError as exc:
            sys.exit(f"pm_run: could not mark {job_id} stopped, a file is held by another process: {exc}; try again")
        ended = state.get(job_id, {}).get("state")
        if ended in ENDED:
            print(f"{job_id}: marked stop in jobs.json; it has already ended ({ended}), so there is no pane to close")
        else:
            print(
                f"{job_id}: marked stop in jobs.json; if it is still running, the loop closes its pane within one tick"
            )

    def check(self, jobs, state, job_id):
        """Evidence 1, 2 and 4 for one job, without Herdr; a person or the lead uses it by hand."""
        job = next((j for j in jobs if j["id"] == job_id), None)
        if not job:
            sys.exit(f"no job {job_id}")
        attempts = state.get(job_id, {}).get("attempts", [])
        started = attempts[-1]["started"] if attempts else 0
        art, why = check_artifact(self.repo / job["out"], started, job.get("min_words", 0))
        rc, verify_why = run_verify(job, self.repo) if art else (None, "")
        verdict = "verified" if art and rc == 0 else ("artifact-present" if art and rc is None else "not verified")
        print(f"{job_id}: {verdict}" + (f" ({why})" if why else "") + (f", {verify_why}" if verify_why else ""))
        return verdict == "verified"


def main():
    # Worker errors and briefs carry non-ASCII text (Turkish); a redirected stdout on Windows is cp1252.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    run = Run(sys.argv[1])
    jobs = run.load("jobs.json", [])
    state = run.load("receipts.json", {})
    if "--status" in sys.argv:
        run.status(jobs, state)
        if "--tally" in sys.argv:
            run.failure_tally()
        return
    if "--tally" in sys.argv:
        sys.exit("pm_run: use --tally with --status")
    if "--check" in sys.argv:
        sys.exit(0 if run.check(jobs, state, sys.argv[sys.argv.index("--check") + 1]) else 1)
    if "--stop" in sys.argv:
        run.request_stop(jobs, state, sys.argv[sys.argv.index("--stop") + 1])
        return
    caps = run.load("caps.json", {})
    run.take_lease()
    run.log(f"pm_run start: {len(jobs)} jobs")
    saved = True
    while True:
        run.refresh_lease()
        jobs, caps, state, saved = run.cycle(jobs, caps, state, saved)
        # the run ends only once its final receipts are on disk
        if saved and all(state.get(j["id"], {}).get("state") in ENDED for j in jobs):
            run.log("pm_run done: " + ", ".join(f"{j['id']}={state[j['id']]['state']}" for j in jobs))
            run.print_totals(usage_tally(jobs, state)[0])
            unconfirmed = any(
                state[j["id"]].get("trust_stopped_confirmed") is False
                or any(a.get("stopped_confirmed") is False for a in state[j["id"]]["attempts"])
                for j in jobs
            )
            # a handed-over session stays open, and so does the pane of a job deleted while it ran
            handed = any(s["state"] in ("handed-over", "removed") for k, s in state.items() if not k.startswith("_"))
            if state.get("_herdr_workspace") and not unconfirmed and not handed:
                herdr("workspace", "close", state["_herdr_workspace"])
            (run.root / "pm_run.lease").unlink(missing_ok=True)
            return
        time.sleep(TICK)


if __name__ == "__main__":
    main()
