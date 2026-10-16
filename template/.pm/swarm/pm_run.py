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
quiet for PM_RUN_QUIET_S, and never repeats Pi's own retry; when the log is not found (another harness, a
lookup gap) it nudges at once. A nudge goes to the same session: RESUME, or the
full brief again when no turn ran (no completion_seq advance and no observed working state).
A nudge counts as idle when the session log did not grow or the output file did not change since the previous one
(a worker that answers every nudge without touching its output is idle too); after PM_RUN_MAX_NUDGES idle nudges
in a row the job is **handed-over**: pm_run stops watching, leaves the session open in its Herdr tab and tells the lead.
A settled worker whose Pi error message or last pane lines name a used-up quota or usage limit is handed over at once,
without a nudge: a resent brief would hit the same limit until it resets. A bare 429 (an upstream outage answers
with it too) is nudged as before.
At the hard limit a live worker gets PM_RUN_OVERTIME_S more, once (a settled one also gets a nudge), then is handed
over. A fresh session (a retry) starts only when the worker is gone or did not start, up to PM_RUN_MAX_TRIES attempts;
before it, this attempt's fresh output is kept as <stem>.attempt<n><suffix>, with -2, -3 on name clashes.
A dependency that failed, was blocked, handed-over, check-failed or is only artifact-present blocks its successors.
A worker that asks a question (Herdr state `blocked`) is never killed for it; it waits until someone answers.

usage: python .pm/swarm/pm_run.py <run-dir>                 loop until every job has ended (see ENDED)
       python .pm/swarm/pm_run.py <run-dir> --status        print the receipt table and exit
       python .pm/swarm/pm_run.py <run-dir> --check <job>   check one job's current artifact and verify command, no Herdr

<run-dir>/jobs.json: [{"id", "model", "out", "briefs": [...], "after": [...], "verify": "cmd", "min_words": 1000,
                       (verify runs through the system shell, cmd.exe on Windows: keep it a plain command, put logic in a script)
                       "bucket": "router", "thinking": "high",
                       "harness": "pi" | "claude", "setup": "shell line run in the pane first", "args": [...],
                       "probe": "http://127.0.0.1:8080/v1/models",  (optional HTTP health probe; never include a secret)
                       "writes": ["site/"]}]   (paths the worker may write besides `out`, e.g. code it builds)
                       (harness "claude" starts Claude Code with --model and args; thinking applies to Pi only;
                        both start without in-process sub-agent tools: a helper is its own pm_run job, so it is visible too)
<run-dir>/caps.json: {"<bucket>": max parallel}.
Herdr binary: PM_RUN_HERDR, else `herdr` on PATH (where Herdr's installer puts it). The Herdr server must be running
(start `herdr` once).
Timeouts: PM_RUN_HERDR_TIMEOUT (30 seconds per CLI call), PM_RUN_VERIFY_S (600 seconds per check).
Other env vars: PM_RUN_HARD_S (4500), PM_RUN_OVERTIME_S (900), PM_RUN_QUIET_S (90), PM_RUN_MAX_NUDGES (3),
PM_RUN_TICK (15), PM_RUN_SETTLE_S (20), PM_RUN_SETUP_S (2), PM_RUN_MAX_TRIES (5),
PM_RUN_REPO (the repo root; default the current folder).
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
from collections import Counter
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

MARKER = "<!-- done -->"
# pm_run stops when every job is here
ENDED = ("verified", "artifact-present", "check-failed", "handed-over", "failed", "blocked")


def _env(name, default):
    return float(os.environ.get(f"PM_RUN_{name}", default))


HARD_S, TICK, SETTLE_S = _env("HARD_S", 75 * 60), _env("TICK", 15), _env("SETTLE_S", 20)
STALL_S = _env("STALL_S", 300)
SETUP_S = _env("SETUP_S", 2)  # let the pane's setup line finish before the agent starts
HERDR_TIMEOUT, VERIFY_S = _env("HERDR_TIMEOUT", 30), _env("VERIFY_S", 600)
MAX_TRIES = int(_env("MAX_TRIES", 5))
QUIET_S, MAX_NUDGES, OVERTIME_S = _env("QUIET_S", 90), int(_env("MAX_NUDGES", 3)), _env("OVERTIME_S", 15 * 60)
HERDR = os.environ.get("PM_RUN_HERDR") or shutil.which("herdr") or "herdr"
HERDR_CMD = json.loads(HERDR) if HERDR.startswith("[") else [HERDR]  # tests pass a JSON command list
SETTLED = ("done", "idle")
# A used-up allowance, not per-minute throttling ("rate limit" passes after a nudge). On a pane line it counts only
# beside an error sign: an API error, a 429, or a limit banner with its reset time.
QUOTA = re.compile(
    r"usage limit|quota|limit reached|(?:hit|reached) your (?:usage )?limit|out of (?:extra )?usage", re.I
)
ERROR_LINE = re.compile(r"\berror\b|\b429\b|\bresets?\b", re.I)
PROMPT = (
    "Read the brief file(s) {briefs} and do the task. Your output file is {out}. Create it early and fill it "
    "section by section. Only when it is complete, append the exact last line <!-- done -->. Write only that file{also}. "
    "Do not ask questions: if something blocks you, write the blocker into the output file and finish."
)
# Every helper runs in its own Herdr pane through pm_run, where the owner can watch it, so an agent started here
# gets no in-process sub-agent tools. Applies to this run only; the owner's own Pi and Claude Code setup is unchanged.
CLAUDE_SETTINGS = {"enableAllProjectMcpServers": True}  # the project's MCP servers (Context7...) start unasked
NO_HELPERS = {"pi": ["--exclude-tools", "Agent,SubagentWorkflow"], "claude": ["--disallowedTools", "Agent,Workflow"]}
RESUME = (
    "Your previous turn ended before the output was finished. Re-read the brief file(s) {briefs} and {out}, "
    "keep what is there, finish it, "
    "then append the exact last line <!-- done -->."
)


def herdr(*args, plain=False):
    """Run one Herdr CLI command; return JSON (or {"error": ...}), or raw stdout for a successful pane read."""
    try:
        result = subprocess.run(
            [*HERDR_CMD, *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=HERDR_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return {"error": {"code": "timeout", "message": f"Herdr call timed out after {HERDR_TIMEOUT:g} s"}}
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


def quota_sign(attempt, screen):
    """The provider's message that the quota or usage limit is used up, at a settled turn, or None.

    Pi's error from this turn is in its session log (turn_end); Claude Code prints the API error in its pane, so an
    error line among the last ten pane lines counts too. Worker prose that only mentions a quota does not, and neither
    does a bare 429: it also comes from an upstream outage, which a nudge can outlast.
    """
    error = attempt.get("errorMessage") or ""
    lines = (
        [line for line in pane_content(screen).splitlines() if line.strip()][-10:] if isinstance(screen, str) else []
    )
    for line in [error] + [line for line in lines if ERROR_LINE.search(line)]:
        if QUOTA.search(line):
            return " ".join(line.split())[:160]
    return None


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


def session_log(attempt, now):
    """(size, seconds since last write) of the attempt's Pi session log, or (None, None) when unknown."""
    try:
        st = Path(attempt["session_log"]).stat()
        return st.st_size, now - st.st_mtime
    except (KeyError, OSError):
        return None, None


def agent_name(job_id, n):
    return re.sub(r"[^a-z0-9-]", "-", f"run-{job_id}-{n}".lower())[:32]


def launch_prompt(job):
    also = f" and the paths {', '.join(job['writes'])}" if job.get("writes") else ""
    return PROMPT.format(briefs=", ".join(job["briefs"]) or "(none)", out=job["out"], also=also)


def turn_end(job, attempt, repo):
    """Read bounded head/tail samples of this repo's recent Pi sessions, then cache the matching path.

    --name is a session_info entry near the start. Only files created for this attempt count; names repeat
    across runs. Large/missing/unreadable logs are diagnostic gaps, never proof that a worker stopped.
    """
    if job.get("harness", "pi") != "pi":
        return "session log not found (only Pi logs supported)"
    attempt.update(stopReason=None, errorMessage=None)  # an earlier turn's error is no evidence for this one
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
                messages = [e.get("message") for e in entries if e.get("type") == "message"]
                last = next((m for m in reversed(messages) if isinstance(m, dict) and m.get("role") == "assistant"), {})
                attempt["stopReason"] = last.get("stopReason")
                attempt["errorMessage"] = last.get("errorMessage")
                if last.get("stopReason") == "error":
                    return f"provider error: {last.get('errorMessage') or 'no error message in session log'}"
                return f"Pi stopReason: {last.get('stopReason') or 'not found in session log sample'}"
            except (OSError, ValueError, TypeError):
                continue
    except OSError:
        pass
    return "session log not found for this attempt (bounded Pi log lookup)"


class Run:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.repo = Path(os.environ.get("PM_RUN_REPO", Path.cwd())).resolve()
        self.state_path = self.root / "receipts.json"
        self.log_path = self.root / "pm_run.log"

    def log(self, text):
        line = f"{time.strftime('%H:%M:%S')} {text}"
        print(line, flush=True)
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def load(self, name, default):
        """A missing file gives the default; a file that is not valid JSON stops the run with the parse error."""
        path = self.root / name
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return default
        try:
            return json.loads(text)
        except ValueError as exc:
            sys.exit(f"pm_run: {path} is not valid JSON: {exc}")

    def save(self, state):
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=1), encoding="utf-8")
        os.replace(tmp, self.state_path)

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
        """Open a tab, start the worker there (Pi, or Claude Code with "harness": "claude"), send the brief.
        True when the prompt was submitted."""
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
            return False
        self.status_of(attempt)  # baseline before sending: ready/idle alone does not prove Pi can receive the brief
        attempt["seq0"] = attempt.get("completion_seq")
        sent = herdr("agent", "prompt", attempt["name"], launch_prompt(job))
        attempt["prompted"] = time.time()
        self.reset_observation(attempt)
        return "error" not in sent

    def status_of(self, attempt):
        got = herdr("agent", "get", attempt["name"])
        if "error" in got:
            if got["error"].get("code") == "agent_not_found":
                return None
            attempt["herdr_error"] = got["error"].get("message", "unknown Herdr error")
            return "unknown"
        attempt.pop("herdr_error", None)
        agent = got["result"]["agent"]
        attempt["completion_seq"] = agent.get("completion_seq")
        return agent["agent_status"]

    def stop(self, attempt):
        """Close the worker's pane; True once Herdr no longer knows the agent."""
        if attempt.get("pane"):
            herdr("pane", "close", str(attempt["pane"]))
        for _ in range(5):
            if self.status_of(attempt) is None:
                return True
            time.sleep(1)
        return False

    def reset_observation(self, attempt):
        attempt.update(seen_hash=None, seen_at=attempt["prompted"], stall=False, loop=False, loop_line=None)

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
        for job in jobs:
            s = state.setdefault(job["id"], {"state": "pending", "attempts": []})
            if s["state"] != "started":
                continue
            a = s["attempts"][-1]
            status = self.status_of(a)
            a["herdr"] = status
            if status == "unknown":
                busy[job.get("bucket", "default")] = busy.get(job.get("bucket", "default"), 0) + 1
                continue  # no kill, nudge or retry on a failed query, even after the hard limit
            if status == "blocked":
                if not a.get("asked"):
                    a["asked"] = now
                    self.log(f"WAITING {job['id']}: the worker asks for input in Herdr tab {job['id']}")
                busy[job.get("bucket", "default")] = busy.get(job.get("bucket", "default"), 0) + 1
                continue
            if status == "working":
                a["worked"] = True
                self.warn_pane(job, a, now)
            settled = status in SETTLED and now - a.get("prompted", a["started"]) > SETTLE_S
            if status is None or settled:
                if status is None:
                    a["stopped_confirmed"] = True
                art, why = check_artifact(self.repo / job["out"], a["started"], job.get("min_words", 0))
                if art:
                    a.update(artifact=art, ended=now, stopped_confirmed=a.get("stopped_confirmed") or self.stop(a))
                    if not a["stopped_confirmed"]:
                        self.fail_or_retry(job, s, "artifact present but the worker could not be confirmed stopped")
                        continue
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
                if quiet is not None and quiet < QUIET_S:
                    if not a.get("held"):
                        a["held"] = True
                        self.log(f"HOLD {job['id']}: turn looks settled but Pi wrote its log {quiet:.0f} s ago; {why}")
                elif self.quota_hand_over(job, s, a, why):
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
            n = len(s["attempts"]) + 1
            if n > 1:
                out = self.repo / job["out"]
                try:
                    if out.exists() and out.stat().st_mtime >= s["attempts"][-1]["started"]:
                        stem = f"{out.stem}.attempt{n - 1}"
                        kept, extra = out.with_name(stem + out.suffix), 2
                        while kept.exists():
                            kept = out.with_name(f"{stem}-{extra}{out.suffix}")
                            extra += 1
                        out.rename(kept)
                        self.log(f"KEPT {job['id']}: previous output saved as {kept.name}")
                except OSError as exc:
                    s["state"] = "failed"
                    self.log(f"FAILED {job['id']}: could not keep previous output; no retry: {exc}")
                    continue
            a = {"name": agent_name(job["id"], n), "started": time.time()}
            s["attempts"].append(a)
            if self.launch(job, a, state):
                s["state"] = "started"
                busy[bucket] = busy.get(bucket, 0) + 1
                self.log(f"LAUNCH {job['id']} attempt {n} on {job['model']} in Herdr pane {a['pane']}")
            else:
                self.fail_or_retry(job, s, f"launch failed: {a.get('launch_error', 'prompt not sent')}")
        return state

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

    def quota_hand_over(self, job, s, a, why):
        """Hand over a settled worker whose provider says the quota or usage limit is used up; True when it did."""
        sign = quota_sign(a, herdr("agent", "read", a["name"], "--source", "visible", plain=True))
        if sign:
            a["quota"] = sign
            self.hand_over(
                job, s, f'provider quota or usage limit: "{sign}"; not resent, rerun the job after it resets; {why}'
            )
        return bool(sign)

    def hand_over(self, job, s, why):
        """Stop watching a live worker without closing it: the lead reads its tab and decides."""
        a = s["attempts"][-1]
        s["state"] = "handed-over"
        a.update(why=why, ended=time.time())
        self.log(f"HANDED-OVER {job['id']}: {why}; the session stays open in Herdr pane {a.get('pane')}, no relaunch")

    def fail_or_retry(self, job, s, why):
        a = s["attempts"][-1]
        if "stopped_confirmed" not in a:
            a["stopped_confirmed"] = self.stop(a)
        a["ended"] = time.time()
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
        print(f"{'job':<16}{'state':<18}{'tries':>6}  last attempt")
        for job in jobs:
            s = state.get(job["id"], {"state": "pending", "attempts": []})
            a = s["attempts"][-1] if s["attempts"] else {}
            detail = ", ".join(
                f"{k}={a[k]}"
                for k in ("pane", "model", "herdr", "stall", "loop", "verify_rc", "why")
                if a.get(k) is not None
            )
            print(f"{job['id']:<16}{s['state']:<18}{len(s['attempts']):>6}  {detail}")

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
        return
    if "--check" in sys.argv:
        sys.exit(0 if run.check(jobs, state, sys.argv[sys.argv.index("--check") + 1]) else 1)
    run.take_lease()
    run.log(f"pm_run start: {len(jobs)} jobs")
    while True:
        run.refresh_lease()
        jobs, caps = run.load("jobs.json", jobs), run.load("caps.json", {})
        state = run.tick(jobs, run.load("receipts.json", state), caps)
        run.save(state)
        if all(state[j["id"]]["state"] in ENDED for j in jobs):
            run.log("pm_run done: " + ", ".join(f"{j['id']}={state[j['id']]['state']}" for j in jobs))
            unconfirmed = any(a.get("stopped_confirmed") is False for j in jobs for a in state[j["id"]]["attempts"])
            handed = any(state[j["id"]]["state"] == "handed-over" for j in jobs)  # its session stays open
            if state.get("_herdr_workspace") and not unconfirmed and not handed:
                herdr("workspace", "close", state["_herdr_workspace"])
            (run.root / "pm_run.lease").unlink(missing_ok=True)
            return
        time.sleep(TICK)


if __name__ == "__main__":
    main()
