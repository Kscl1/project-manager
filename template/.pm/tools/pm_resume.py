"""Print an English resume summary for active Backlog tasks.

Usage: python .pm/tools/pm_resume.py
       python .pm/tools/pm_resume.py --did YYYY-MM-DD   the Did part of a multi-goal worklog (D-109)
       python .pm/tools/pm_resume.py --commits REQ-n    one task's commits and models (D-109)
"""

import os
import re
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path


def find_root(start):
    """The project root holds backlog.config.yml or .git; the tools live in <root>/.pm/tools."""
    for folder in [start, *start.parents]:
        if (folder / "backlog.config.yml").exists() or (folder / ".git").exists():
            return folder
    return start.parent


ROOT = find_root(Path(__file__).resolve().parent)
TASKS_DIR = ROOT / ".pm" / "backlog" / "tasks"
COMPLETED_DIR = ROOT / ".pm" / "backlog" / "completed"  # where `backlog task complete` moves Done tasks
CLOSED_SHOWN = 3  # D-105: a one-goal session writes no worklog, so the next one reads the last closing summaries
# The D-105 lines shown under the first line; the owner line carries the owner's name or the word Owner.
SUMMARY_LINE = re.compile(r"(?:[A-Z][\w'-]* said|Found|Next):")
DRAFTS_DIR = ROOT / ".pm" / "backlog" / "drafts"  # private work items (Backlog drafts); shown only when present
WORKTREES_DIR = ROOT / ".worktrees"
AUDITS_DIR = ROOT / ".pm" / "local" / "audits"
WORKLOG_DIR = ROOT / ".pm" / "worklog"
WEEKLY_AUDIT_DAYS = 7
WIP_LIMIT = 7  # open top-level work (Epics, packages, standalone tasks); sub-tasks are not counted
REVIEW_DAYS = 14  # a Ready task or draft not reviewed for longer than this shows up (REQ-61.1)
ACTIVE_STATUSES = {"Active", "In review", "Owner check"}
LIVE_FIELDS = ("Next", "Evidence", "Blocker", "Needs owner")
# A `Needs owner:` line holding one of these words asks for nothing; `yok` is Turkish for "none" and older
# task files use it.
NOTHING_NEEDED = {"none", "nothing", "yok", "-", "?", "n/a"}
SECTION_MARKER = re.compile(r"<!--\s*SECTION:([A-Za-z0-9_:]+)\s*-->", re.IGNORECASE)
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
FINDING_ROW = re.compile(r"^\|\s*(\d+)\s*\|")


def scalar(value):
    """Unwrap the simple quoted scalars used in Backlog task frontmatter."""
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        inner = value[1:-1]
        return inner.replace("''", "'") if value[0] == "'" else inner
    return value


def read_frontmatter(lines):
    """Read simple Backlog YAML-like frontmatter, or return None if it is malformed."""
    if not lines or lines[0].strip() != "---":
        return None

    fields, key, block, joiner = {}, None, None, " "
    for line in lines[1:]:
        if line.strip() == "---":
            return fields
        if block is not None and line.startswith((" ", "\t")):  # a folded (>) or literal (|) value
            block.append(line.strip())
            fields[key] = joiner.join(block)
            continue
        block = None
        if line.startswith((" ", "\t")) or line.lstrip().startswith("- "):
            continue
        name, separator, value = line.partition(":")
        if not separator:
            continue
        key = name.strip()
        if value.strip() in (">", ">-", ">+", "|", "|-", "|+"):
            block, joiner = [], " " if value.strip()[0] == ">" else "\n"
            fields[key] = ""
        else:
            fields[key] = scalar(value)
    return None


def implementation_notes(lines):
    """Return notes within the Implementation Notes section, if present."""
    for index, line in enumerate(lines):
        if not re.match(r"^\s*##\s+Implementation Notes\s*#*\s*$", line):
            continue

        notes = []
        for body_line in lines[index + 1 :]:
            if re.match(r"^\s*##\s", body_line):
                break
            marker = SECTION_MARKER.search(body_line)
            if marker:
                if marker.group(1).upper().endswith(":BEGIN"):
                    continue
                break
            notes.append(body_line)
        return notes
    return []


def final_summary(lines):
    """Return the lines of the Final Summary section, if present."""
    for index, line in enumerate(lines):
        if not re.match(r"^\s*##\s+Final Summary\s*#*\s*$", line):
            continue
        summary = []
        for body_line in lines[index + 1 :]:
            if re.match(r"^\s*##\s", body_line):
                break
            marker = SECTION_MARKER.search(body_line)
            if marker:
                if marker.group(1).upper().endswith(":BEGIN"):
                    continue
                break
            if body_line.strip():
                summary.append(body_line.strip())
        return summary
    return []


def shorten(text, limit):
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def closed_lines(tasks):
    """The last few Done tasks with a closing summary, newest first by updated_date."""
    done = [task for task in tasks if task["status"] == "Done" and task["summary"]]
    done.sort(key=lambda task: (task["updated"], task_order(task)), reverse=True)
    lines = []
    for task in done[:CLOSED_SHOWN]:
        lines.append(f"- {task['id']} · {task['title']} ({task['updated'][:10] or '?'})")
        first, rest = task["summary"][0], task["summary"][1:]
        lines.append(f"  {shorten(first, 300)}")
        lines.extend(f"  {shorten(line, 200)}" for line in rest if SUMMARY_LINE.match(line))
    return lines


def parse_live_block(lines):
    """Extract known live-block fields; a live block may name more than one Worker."""
    values = {name: None for name in (*LIVE_FIELDS, "Worker")}
    values["Worker"] = []
    for line in lines:
        stripped = line.strip()
        for name in (*LIVE_FIELDS, "Worker"):
            # "Needs owner (both leads agree): ..." still counts as "Needs owner:"
            match = re.match(rf"{re.escape(name)}(?:\s*\([^)]*\))?:(.*)$", stripped)
            if not match:
                continue
            value = match.group(1).strip() or "?"
            if name == "Worker":
                values["Worker"].append(value)
            elif values[name] is None:
                values[name] = value
            break
    return values


def review_fields(lines):
    """Review by (the last one written), Reviewed (the newest date), Audit report path and outcome rows.

    Formats: `Review by: YYYY-MM-DD · owner · reason`, `Reviewed: YYYY-MM-DD`, `Audit report: <path>`, and an
    `Audit outcomes:` line followed by a table whose rows start with the finding number (REQ-61.1).
    """
    review_by, reviewed, report, outcomes, in_table = None, [], None, set(), False
    for line in lines:
        stripped = line.strip()
        if in_table:
            row = FINDING_ROW.match(stripped)
            if row:
                outcomes.add(int(row.group(1)))
                continue
            if stripped.startswith("|"):
                continue  # header and separator rows
            in_table = False
        if stripped.startswith("Audit outcomes:"):
            in_table = True
        elif stripped.startswith("Audit report:"):
            report = stripped.split(":", 1)[1].strip().strip("`") or None
        elif stripped.startswith("Review by:"):
            review_by = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("Reviewed:"):
            reviewed += DATE.findall(stripped)
    return {
        "review_by": review_by,
        "reviewed": max(reviewed, default=None),
        "audit_report": report,
        "outcomes": outcomes,
    }


def as_date(text):
    found = DATE.search(text or "")
    try:
        return date.fromisoformat(found.group(0)) if found else None
    except ValueError:
        return None


def task_order(task):
    numbers = tuple(int(value) for value in re.findall(r"\d+", task["id"]))
    return numbers, task["id"]


def load_tasks(directory=None):
    tasks = []
    try:
        paths = sorted((directory or TASKS_DIR).glob("*.md"), key=lambda path: path.name.casefold())
    except OSError:
        return tasks

    for path in paths:
        try:
            lines = path.read_text(encoding="utf-8-sig").splitlines()
        except (OSError, UnicodeError, ValueError):
            continue
        fields = read_frontmatter(lines)
        if fields is None:
            continue
        task_id = fields.get("id", "").strip()
        title = fields.get("title", "").strip()
        status = fields.get("status", "").strip()
        if not task_id or not title or not status:
            continue
        notes = implementation_notes(lines)
        task = {
            "id": task_id,
            "title": title,
            "status": status,
            "created": fields.get("created_date", ""),
            "updated": fields.get("updated_date", ""),
            "summary": final_summary(lines),
            "parent": fields.get("parent_task_id", "").strip(),
            "live": parse_live_block(notes),
            **review_fields(notes),
        }
        tasks.append(task)
    return sorted(tasks, key=task_order)


def worker_path(worker):
    """Return the worktree part of a Worker line, if it has the expected format."""
    if worker is None or worker == "?":
        return None
    parts = [part.strip() for part in worker.split("·")]
    if len(parts) < 2 or not parts[1]:
        return None
    return Path(parts[1]).expanduser()


def absolute_path(path):
    if not path.is_absolute():
        path = ROOT / path
    try:
        return path.resolve()
    except (OSError, RuntimeError):
        return Path(os.path.abspath(path))


def path_key(path):
    return os.path.normcase(os.path.normpath(str(absolute_path(path))))


def display_path(path):
    path = absolute_path(path)
    try:
        return path.relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def worktree_directories():
    try:
        return sorted(
            (path for path in WORKTREES_DIR.iterdir() if path.is_dir()), key=lambda path: path.name.casefold()
        )
    except OSError:
        return []


def collect_warnings(tasks):
    warnings = []
    referenced = set()
    for task in tasks:
        for worker in task["live"]["Worker"]:
            path = worker_path(worker)
            if path is None:
                continue
            resolved = absolute_path(path)
            referenced.add(path_key(resolved))
            if task["status"] in ACTIVE_STATUSES and not resolved.exists():
                warnings.append(f"- ⚠️ Missing worktree: {task['id']} · {display_path(resolved)}")

    directories = worktree_directories()
    for directory in directories:
        if path_key(directory) not in referenced:
            warnings.append(f"- ⚠️ Orphan worktree: {display_path(directory)}")

    for directory in directories:
        report = directory / ".pm-report.md"
        if report.is_file():
            warnings.append(f"- ⚠️ Pending report: {display_path(report)}")

    return warnings


def weekly_audit_warning(today):
    """Warn when no weekly doc audit (.pm/local/audits/weekly-YYYY-MM-DD) was verified in the last seven days.

    Only a folder with a non-empty lead-verification.md counts: an empty or unverified folder does not.
    """
    dates = []
    try:
        for folder in AUDITS_DIR.glob("weekly-*"):
            verification = folder / "lead-verification.md"
            if not verification.is_file() or not verification.read_text(encoding="utf-8", errors="replace").strip():
                continue
            try:
                dates.append(date.fromisoformat(folder.name[len("weekly-") :]))
            except ValueError:
                continue
    except OSError:
        pass
    last = max(dates, default=None)
    if last is not None and (today - last).days < WEEKLY_AUDIT_DAYS:
        return None
    since = f"last: {last.isoformat()}" if last else "never ran"
    return f"- ⚠️ Weekly doc audit due ({since}): .pm/templates/doc-audit.md, kind weekly"


def worklog_gap_warning():
    """Warn about commits after the newest worklog that no task records either (D-105).

    A one-goal session writes no worklog, so a commit is recorded when every task its Refs line names is open
    or a draft (its file holds the work) or Done with a Final Summary; a commit with `Refs: none`, no Refs line,
    an unknown task or a Done task without a summary is not.
    """
    try:
        newest = max(WORKLOG_DIR.glob("*.md"), key=lambda path: path.name, default=None)
    except OSError:
        return None
    if newest is None:
        return None
    relative = newest.relative_to(ROOT).as_posix()
    last = (git_stdout(["log", "-1", "--format=%H", "--", relative], "") or "").strip()
    if not last:
        return None  # the worklog is not committed yet
    recorded = {
        task["id"]
        for task in load_tasks() + load_tasks(COMPLETED_DIR) + load_tasks(DRAFTS_DIR)
        if task["status"] != "Done" or task["summary"]
    }
    loose = [c for c in commits(f"{last}..HEAD") if not c["refs"] or not c["refs"] <= recorded]
    if not loose:
        return None
    return (
        f"- ⚠️ {len(loose)} commit(s) after the newest worklog ({newest.name}) are in no record "
        f"(open task, draft or closing summary): git log --oneline {last[:7]}..HEAD"
    )


def worklog_next_warning(tasks):
    """Name the tasks in the newest worklog's Next section that are Done by now (REQ-89).

    The worklog is a dated record and stays as written; this line keeps an opener from following a finished step.
    """
    try:
        newest = max(WORKLOG_DIR.glob("*.md"), key=lambda path: path.name, default=None)
        lines = newest.read_text(encoding="utf-8").splitlines() if newest else []
    except (OSError, UnicodeError):
        return None
    section, inside = [], False
    for line in lines:
        if line.startswith("## "):
            inside = line[3:].strip().lower().startswith("next")
        elif inside:
            section.append(line)
    status = {task["id"]: task["status"] for task in tasks}
    named = re.findall(r"\b[A-Z][A-Z0-9]*-\d+(?:\.\d+)*\b", "\n".join(section))
    done = [task_id for task_id in dict.fromkeys(named) if status.get(task_id) == "Done"]
    if not done:
        return None
    return f"- ⚠️ Tasks in the Next section of the newest worklog ({newest.name}) are done now: {', '.join(done)}"


def folders(listing, skip):
    """The folders up to two levels deep that hold a tracked file, leaving out dot-folders, docs/ and `skip`."""
    found = set()
    for path in listing.split("\0"):
        parts = path.split("/")[:-1][:2]
        for depth in range(1, len(parts) + 1):
            folder = "/".join(parts[:depth])
            if parts[0] == "docs" or any(p.startswith(".") for p in parts[:depth]) or folder in skip:
                break
            found.add(folder)
    return found


def map_warning():
    """Name the folders added or removed since the last commit that changed the LikeC4 map (D-118).

    The map is every tracked .c4 or .likec4 file; a project without one gets no warning, since the map is optional.
    """
    now = git_stdout(["ls-tree", "-r", "-z", "--name-only", "HEAD"], None)
    maps = [path for path in (now or "").split("\0") if path.endswith((".c4", ".likec4"))]
    if not maps:
        return None
    last = (git_stdout(["log", "-1", "--format=%H", "--", *maps], "") or "").strip()
    then = git_stdout(["ls-tree", "-r", "-z", "--name-only", last], None) if last else None
    if then is None:
        return None
    skip = {path.rsplit("/", 1)[0] for path in maps if "/" in path}
    changed = sorted(folders(now, skip) ^ folders(then, skip))
    if not changed:
        return None
    shown = ", ".join(changed[:3]) + (f" and {len(changed) - 3} more" if len(changed) > 3 else "")
    return f"- ⚠️ Map may be out of date: folders added or removed since the map last changed ({last[:7]}): {shown}"


def git_stdout(arguments, failure_warning):
    try:
        result = subprocess.run(
            ["git", *arguments],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError:
        return failure_warning
    if result.returncode != 0:
        return failure_warning
    return result.stdout


def owner_lines(tasks):
    """Every open task that waits on the owner. Generated, so the owner list cannot go stale (D-64)."""
    lines = []
    for task in tasks:
        needs = task["live"]["Needs owner"]
        if task["status"] == "Done" or not needs or needs.split()[0].strip(".,;:").lower() in NOTHING_NEEDED:
            continue
        lines.append(f"- {task['id']} [{task['status']}]: {needs}")
    return lines


def held_lines(tasks, drafts, today):
    """Top-level WIP and Ready counts, then stale Ready tasks and drafts and passed Review by dates (REQ-61.1)."""
    wip = [task for task in tasks if task["status"] in ACTIVE_STATUSES and not task["parent"]]  # top-level only
    ready = [task for task in tasks if task["status"] == "Ready"]
    lines = [f"- Open top-level work (WIP): {len(wip)}/{WIP_LIMIT} · Ready: {len(ready)} · Drafts: {len(drafts)}"]
    for task in [task for task in tasks if task["status"] != "Done"] + drafts:
        review_by = as_date(task["review_by"])
        if review_by is not None and review_by < today:
            lines.append(f"- ⏰ {task['id']} · review date passed: {task['review_by']}")
    for task in ready + drafts:
        if as_date(task["review_by"]) is not None:
            continue  # a dated hold is shown only when its date passes (above)
        since = as_date(task["reviewed"]) or as_date(task["created"])
        if since is not None and (today - since).days > REVIEW_DAYS:
            seen = "last review" if task["reviewed"] else "opened"
            lines.append(f"- 💤 {task['id']} · waiting {(today - since).days} days ({seen} {since}): {task['title']}")
    return lines


def report_findings(path):
    """Finding numbers of a raw audit report: table rows `| n |` in the `## Findings` section.

    Same bounds as pm_check: the section ends at the next `#` or `##` heading (`###` stays inside), and
    fenced code is skipped, so an example table is never counted.
    """
    try:
        lines = absolute_path(Path(path)).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    numbers, inside, fence = set(), False, None
    for line in lines:
        marker = re.match(r"^\s{0,3}(`{3,}|~{3,})", line)
        if marker:
            if fence is None:
                fence = marker.group(1)
            elif marker.group(1)[0] == fence[0] and len(marker.group(1)) >= len(fence):
                fence = None
            continue
        if fence is not None:
            continue
        heading = re.match(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$", line)
        if heading and len(heading.group(1)) <= 2:
            inside = len(heading.group(1)) == 2 and heading.group(2).strip().lower() == "findings"
            continue
        row = FINDING_ROW.match(line.strip())
        if inside and row:
            numbers.add(int(row.group(1)))
    return numbers


def audit_warnings(tasks):
    """An open audit task whose findings do not all have an outcome row yet."""
    warnings = []
    for task in tasks:
        if not task["audit_report"] or task["status"] == "Done":
            continue
        findings = report_findings(task["audit_report"])
        missing = sorted(findings - task["outcomes"]) if findings else []
        if not task["outcomes"]:
            warnings.append(f"- ⚠️ Audit without outcomes: {task['id']} has no outcome written for its findings yet")
        elif missing:
            numbers = ", ".join(str(number) for number in missing)
            warnings.append(f"- ⚠️ Audit without outcomes: {task['id']} has no outcome for finding {numbers}")
    return warnings


def local_day(stamp):
    """Backlog writes updated_date in UTC ('2026-10-13 00:05'); the day a person means is the local one."""
    try:
        return datetime.strptime(stamp[:16], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc).astimezone().date()
    except ValueError:
        return as_date(stamp)


def commits(revisions="HEAD"):
    """Commits with short hash, local author day, subject, Refs task IDs and Assisted-by models (D-109)."""
    log = git_stdout(["log", "--date=short", "--format=%h%x1f%ad%x1f%s%x1f%B%x1e", revisions], "")
    found = []
    for record in log.split("\x1e"):
        parts = record.strip("\n").split("\x1f")
        if len(parts) != 4:
            continue
        sha, day, subject, body = parts
        refs = re.search(r"^Refs:\s*(.+)$", body, re.MULTILINE)
        found.append(
            {
                "sha": sha,
                "day": day,
                "subject": subject,
                "refs": {item.strip() for item in refs.group(1).split(",")} if refs else set(),
                "models": re.findall(r"^Assisted-by:\s*(.+?)\s*$", body, re.MULTILINE),
            }
        )
    return found


def did_main(day):
    """Print the Did part of a multi-goal worklog: tasks closed on `day` with their commits that day (D-109)."""
    sys.stdout.reconfigure(encoding="utf-8")
    tasks = load_tasks() + load_tasks(COMPLETED_DIR)
    closed = [task for task in tasks if task["status"] == "Done" and str(local_day(task["updated"])) == day]
    history = commits()
    lines = ["## Did", "", f"Generated by `pm_board.py --did {day}` (D-109); write Asked and Next by hand.", ""]
    for task in sorted(closed, key=task_order):
        summary = shorten(task["summary"][0], 300) if task["summary"] else "(no Final Summary)"
        shas = [c["sha"] for c in history if task["id"] in c["refs"] and c["day"] == day]
        lines.append(f"- {task['id']} · {task['title']}: {summary}" + (f" ({', '.join(shas)})" if shas else ""))
    if not closed:
        lines.append(f"- (no task closed on {day})")
    print("\n".join(lines))
    return 0


def commits_main(task_id):
    """Print one task's commits, newest first, and the models that touched them (D-109)."""
    sys.stdout.reconfigure(encoding="utf-8")
    mine = [c for c in commits() if task_id in c["refs"]]
    lines = [f"## {task_id}: {len(mine)} commits", ""]
    lines += [f"- {c['sha']} {c['day']} {c['subject']} · {', '.join(c['models']) or 'no Assisted-by'}" for c in mine]
    models = list(dict.fromkeys(model for c in mine for model in c["models"]))
    lines += ["", "Models: " + (", ".join(models) if models else "(none)")]
    print("\n".join(lines))
    return 0


def render_section(name, body):
    return f"## {name}\n{body}"


def main():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except (OSError, ValueError):
            pass

    all_tasks = load_tasks()
    tasks = [task for task in all_tasks if task["status"] in ACTIVE_STATUSES]
    status_output = git_stdout(["status", "-sb"], "⚠️ Could not run `git status -sb`.")
    log_output = git_stdout(["log", "-5", "--oneline"], "⚠️ Could not run `git log -5 --oneline`.")

    task_lines = []
    for task in tasks:
        task_lines.append(f"- {task['id']} · {task['title']} [{task['status']}]")
        for name in LIVE_FIELDS:
            value = task["live"][name]
            task_lines.append(f"  {name}: {value if value is not None else '?'}")
        for worker in task["live"]["Worker"]:
            task_lines.append(f"  Worker: {worker}")

    warning_lines = collect_warnings(all_tasks) + audit_warnings(all_tasks)
    weekly = weekly_audit_warning(date.today())
    if weekly:
        warning_lines.append(weekly)
    gap = worklog_gap_warning()
    if gap:
        warning_lines.append(gap)
    finished = worklog_next_warning(all_tasks + load_tasks(COMPLETED_DIR))
    if finished:
        warning_lines.append(finished)
    stale_map = map_warning()
    if stale_map:
        warning_lines.append(stale_map)
    drafts = load_tasks(DRAFTS_DIR)
    waiting = owner_lines(all_tasks) + owner_lines(drafts)
    sections = [
        ("Git status", status_output),
        ("Last 5 commits", log_output),
        ("Open tasks", "\n".join(task_lines) if task_lines else "- (none)"),
        ("Waiting on the owner", "\n".join(waiting) if waiting else "- (none)"),
        ("Waiting and ageing work", "\n".join(held_lines(all_tasks, drafts, date.today()))),
        ("Warnings", "\n".join(warning_lines) if warning_lines else "- (none)"),
    ]
    if drafts:
        sections.insert(3, ("Drafts", "\n".join(f"- {d['id']} · {d['title']}" for d in drafts)))
    closed = closed_lines(all_tasks + load_tasks(COMPLETED_DIR))
    if closed:
        sections.insert(2, ("Recently closed tasks", "\n".join(closed)))

    output = "# Resume summary\n\n"
    for index, (name, body) in enumerate(sections):
        output += render_section(name, body)
        if not output.endswith("\n"):
            output += "\n"
        if index < len(sections) - 1:
            output += "\n"
    print(output, end="")
    return 0


if __name__ == "__main__":
    if "--did" in sys.argv:
        sys.exit(did_main(sys.argv[sys.argv.index("--did") + 1]))
    if "--commits" in sys.argv:
        sys.exit(commits_main(sys.argv[sys.argv.index("--commits") + 1]))
    sys.exit(main())
