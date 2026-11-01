"""Status board in English for the Backlog.md task files. Standard library only.

Usage: python .pm/tools/pm_board.py [--tasks DIR] [--today YYYY-MM-DD]
                                      [--next | --tree | --resume [--brief] | --did [DAY] | --commits TASK]
"""

import argparse
import re
import sys
from datetime import date
from pathlib import Path


def find_root(start):
    """The project root holds backlog.config.yml or .git; the tools live in <root>/.pm/tools."""
    for folder in [start, *start.parents]:
        if (folder / "backlog.config.yml").exists() or (folder / ".git").exists():
            return folder
    return start.parent


ROOT = find_root(Path(__file__).resolve().parent)
WIP_LIMIT = 7  # open top-level work (Epics, packages, standalone tasks); sub-tasks are not counted
URGENT_LIMIT = 1
# The Backlog status names, in board order; a task with any other status goes to "Other".
SECTIONS = ["Active", "In review", "Owner check", "Ready", "Done"]
ACTIVE, READY, DONE = "Active", "Ready", "Done"
PRIORITIES = ("high", "medium", "low")  # `--next` picks a Ready task by this order; no priority comes last
NOT_SET = "not set"  # a live-block line the task does not carry yet; `?` reads as an error to a beginner


def default_tasks_dir():
    """The first existing tasks folder: new .pm layout, then the old layout."""
    for candidate in (ROOT / ".pm" / "backlog" / "tasks", ROOT / "backlog" / "tasks"):
        if candidate.is_dir():
            return candidate
    return ROOT / ".pm" / "backlog" / "tasks"


BLOCK_SCALARS = (">", ">-", ">+", "|", "|-", "|+")
LIST_FIELDS = ("labels", "dependencies")  # frontmatter fields holding a list, inline `[a, b]` or one `- a` per line


def scalar(value):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        inner = value[1:-1]
        return inner.replace("''", "'") if value[0] == "'" else inner
    return value


def read_frontmatter(lines):
    """Return {key: value} for the simple YAML-like frontmatter, or None if absent."""
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
        if key in LIST_FIELDS and line.lstrip().startswith("- "):
            fields[key].append(scalar(line.strip()[2:]))
            continue
        name, sep, value = line.partition(":")
        if not sep or line.startswith((" ", "\t")):
            key = None
            continue
        key = name.strip()
        if key in LIST_FIELDS:
            fields[key] = [scalar(v) for v in value.strip().strip("[]").split(",") if v.strip()]
        elif value.strip() in BLOCK_SCALARS:
            block, joiner = [], " " if value.strip()[0] == ">" else "\n"
            fields[key] = ""
        else:
            fields[key] = scalar(value)
    return None  # the closing --- never came, so this is not frontmatter


def number(value):
    """The first whole number in a frontmatter value, or None when it holds none."""
    found = re.search(r"-?\d+", value or "")
    return int(found.group()) if found else None


def section_lines(lines, heading):
    """The lines under a `## heading` in the task body, up to the next heading."""
    found, inside = [], False
    for line in lines:
        if line.startswith("## "):
            inside = line[3:].strip().casefold() == heading
            continue
        if inside:
            found.append(line)
    return found


LIVE_NEXT = re.compile(r"Next(?:\s*\([^)]*\))?:(.*)$")
OPEN_CRITERION = re.compile(r"^\s*[-*]\s+\[ \]\s*(.*)$")


def live_next(lines):
    """The live block's `Next:` line, or None when the task has none yet."""
    for line in section_lines(lines, "implementation notes"):
        found = LIVE_NEXT.match(line.strip())
        if found:
            return found.group(1).strip() or None
    return None


def open_criteria(lines):
    """The acceptance criteria still unchecked, as written (`#1` number included)."""
    criteria = []
    for line in section_lines(lines, "acceptance criteria"):
        found = OPEN_CRITERION.match(line)
        if found:
            criteria.append(found.group(1).strip())
    return criteria


def resume_tool():
    """The sibling pm_resume script, so both tools read a `Review by:` line the same way.

    The two ship together; a lone copy of this file still prints the board, just without the hold dates.
    """
    tools = Path(__file__).resolve().parent
    if str(tools) not in sys.path:
        sys.path.insert(0, str(tools))
    try:
        import pm_resume
    except ImportError:
        return None
    return pm_resume


def read_task(path):
    # A task saved in a Windows code page must not crash the board: the odd byte reads as a replacement mark.
    lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    fields = read_frontmatter(lines)
    if fields is None:
        return None
    labels = fields.get("labels", [])
    resume = resume_tool()
    review_by = resume.review_fields(resume.implementation_notes(lines))["review_by"] if resume else None
    return {
        "id": fields.get("id", ""),
        "title": fields.get("title", ""),
        "status": fields.get("status", ""),
        "type": fields.get("type", ""),
        "parent": fields.get("parent_task_id", ""),
        "urgent": "urgent" in labels or "acil" in labels,
        "priority": fields.get("priority", "").strip().lower(),
        "ordinal": number(fields.get("ordinal", "")),
        "dependencies": [name for name in fields.get("dependencies", []) if name],
        "updated": fields.get("updated_date", "").strip(),
        "next": live_next(lines),
        "criteria": open_criteria(lines),
        "review_by": resume.as_date(review_by) if resume else None,
    }


def read_tasks(directory):
    """Every task file in a folder; a file with no frontmatter or that cannot be read is skipped."""
    try:
        paths = sorted(Path(directory).glob("*.md"))
    except OSError:
        return []
    tasks = []
    for path in paths:
        try:
            task = read_task(path)
        except (OSError, UnicodeError):
            continue
        if task:
            tasks.append(task)
    return tasks


def order(task):
    number = re.search(r"\d+", task["id"])
    return (int(number.group()) if number else float("inf"), task["id"])


def line(task):
    return f"- {task['id']} · {task['title']}" + (" (urgent)" if task["urgent"] else "")


def section(name, tasks):
    items = "\n".join(line(t) for t in sorted(tasks, key=order)) or "- (none)"
    return f"## {name}\n{items}"


def tree_block(tasks, today):
    """The Epic tree with direct-child progress as Markdown."""
    by_id = {task["id"]: task for task in tasks}
    children = {}
    for task in tasks:
        if task["parent"]:
            children.setdefault(task["parent"], []).append(task)

    def has_children(task):
        return bool(children.get(task["id"]))

    def render(task, depth, seen):
        """Return the indented lines for task and its descendants, marking seen ids."""
        if task["id"] in seen:
            return []
        seen.add(task["id"])
        kids = sorted(children.get(task["id"], []), key=order)
        text = f"{'  ' * depth}{line(task)} · {task['status']}"
        if task["type"] == "epic" or kids:
            done = sum(1 for kid in kids if kid["status"] == "Done")
            text += f" [{done}/{len(kids)}]"
        out = [text]
        for kid in kids:
            out.extend(render(kid, depth + 1, seen))
        return out

    roots = [t for t in tasks if not t["parent"] and (t["type"] == "epic" or has_children(t))]
    lines = [f"# Epic tree ({today})"]
    seen = set()
    for root in sorted(roots, key=order):
        lines.extend(render(root, 0, seen))

    blocks = ["\n".join(lines)]

    # Orphans: tasks whose parent is missing. Show each once with its subtree
    # (findings 1 and 3): a missing-parent epic no longer doubles as a root, and
    # an orphan's own children are printed beneath it instead of vanishing.
    orphans = [t for t in tasks if t["parent"] and t["parent"] not in by_id]
    if orphans:
        orphan_lines = []
        for orphan in sorted(orphans, key=order):
            orphan_lines.append(f"{line(orphan)} · {orphan['status']} (no parent: {orphan['parent']})")
            seen.add(orphan["id"])
            for kid in sorted(children.get(orphan["id"], []), key=order):
                orphan_lines.extend(render(kid, 1, seen))
        blocks.append("## Orphans\n" + "\n".join(orphan_lines))

    # Cycles: tasks with an existing parent that no root reaches (finding 2).
    cycle_ids = _cycle_ids(tasks, by_id, seen)
    if cycle_ids:
        cycle_tasks = sorted((by_id[cid] for cid in cycle_ids), key=order)
        items = "\n".join(f"{line(t)} · {t['status']} (cycle)" for t in cycle_tasks)
        blocks.append(f"## Cycle\n{items}")

    return "\n\n".join(blocks)


def _cycle_ids(tasks, by_id, seen):
    """Return the ids of tasks that sit on a parent-cycle no root reaches.

    Such tasks each have a parent that exists but are not reached from any
    root, so following parents must eventually revisit a node; the revisited
    stretch is the cycle and every member is returned.
    """
    unreached = {t["id"]: t for t in tasks if t["id"] not in seen and t["parent"] and t["parent"] in by_id}
    cycle = set()
    done = set()
    for task in sorted(unreached.values(), key=order):
        if task["id"] in done or task["id"] in cycle:
            continue
        path = []
        node = task
        while node["id"] in unreached and node["id"] not in done and node["id"] not in cycle:
            if node["id"] in path:
                cycle.update(path[path.index(node["id"]) :])
                break
            path.append(node["id"])
            node = by_id[node["parent"]]
        done.update(path)
    return cycle


def priority_rank(task):
    """high, medium, low, then a task whose priority is empty or unknown."""
    return PRIORITIES.index(task["priority"]) if task["priority"] in PRIORITIES else len(PRIORITIES)


def start_key(task):
    """The Ready pick: priority first, then the lowest ordinal, then the lowest task number."""
    return (priority_rank(task), task["ordinal"] if task["ordinal"] is not None else float("inf"), order(task))


def newest_first(tasks):
    """Tasks by updated_date, newest first; one without a stamp keeps its id order and comes last."""
    tasks = sorted(tasks, key=order)
    tasks.sort(key=lambda task: task["updated"][:16].replace("T", " "), reverse=True)
    return tasks


def updated_note(task):
    stamp = task["updated"][:16].replace("T", " ")
    return f" · updated {stamp}" if stamp else ""


def criteria_lines(task, when_empty):
    """The acceptance criteria still unchecked as a checklist, or one plain line when there are none."""
    if not task["criteria"]:
        return [when_empty]
    return ["Acceptance criteria:", *(f"- [ ] {item}" for item in task["criteria"])]


def continue_lines(active):
    """The newest Active task to continue, then the other Active tasks newest first."""
    lines = [f"{len(active)} tasks are Active; continue the newest one."] if len(active) > 1 else []
    chosen = active[0]
    lines.append(f"Continue: {chosen['title']} ({chosen['id']})")
    lines.append(f"Next: {chosen['next'] or NOT_SET}")
    lines.extend(criteria_lines(chosen, "Acceptance criteria: none unchecked"))
    if len(active) > 1:
        lines.append("Also Active (newest first; leave them for now):")
        lines.extend(f"- {task['title']} ({task['id']}){updated_note(task)}" for task in active[1:])
    return lines


def start_lines(task):
    """The next Ready task, why it comes first, and what finishing it means."""
    priority = task["priority"] or "none"
    ordinal = task["ordinal"] if task["ordinal"] is not None else "none"
    return [
        f"Start: {task['title']} ({task['id']}) · priority {priority} · ordinal {ordinal}",
        *criteria_lines(task, "Acceptance criteria: none written yet"),
    ]


def held_on_purpose(task, today):
    """A `Review by:` date that has not passed yet: the lead parked this task on purpose."""
    review_by = task["review_by"]
    return review_by is not None and review_by >= today


def next_lines(tasks, closed_done=(), today=None):
    """The one task to work on now in plain words, or one line saying there is nothing to start."""
    today = today or date.today()
    tasks = [task for task in tasks if task["id"] and task["title"]]
    active = newest_first([task for task in tasks if task["status"] == ACTIVE])
    if active:
        return continue_lines(active)
    done = {task["id"] for task in tasks if task["status"] == DONE} | set(closed_done)
    ready = [task for task in tasks if task["status"] == READY]
    startable = [task for task in ready if all(name in done for name in task["dependencies"])]
    held = [task for task in startable if held_on_purpose(task, today)]
    startable = [task for task in startable if task not in held]
    if startable:
        return start_lines(min(startable, key=start_key))
    if held:
        lines = [
            f"Nothing to start; {len(held)} task(s) wait on purpose (Review by). "
            "Ask the user what to build or fix next."
        ]
    else:
        lines = ["Nothing is Ready to start. The lead can open a task from the user's next request."]
    for task in sorted(ready, key=order):
        waiting = ", ".join(name for name in task["dependencies"] if name not in done)
        if waiting:
            lines.append(f"- Ready but waiting for another task: {task['id']} (needs {waiting})")
    return lines


def closed_done_ids(tasks_dir):
    """Ids of Done tasks Backlog moved out of the tasks folder, so a finished dependency still counts."""
    folder = Path(tasks_dir)
    found = set()
    for closed in (folder.parent / "completed", folder.parent / "archive" / "tasks"):
        found.update(task["id"] for task in read_tasks(closed) if task["status"] == DONE)
    return found


def main():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except (OSError, ValueError):
            pass
    parser = argparse.ArgumentParser(description="Print an English status board from Backlog tasks.")
    parser.add_argument("--tasks", default=None)
    parser.add_argument("--today", default=date.today().isoformat())
    parser.add_argument("--next", action="store_true", help="print the one task to work on now")
    parser.add_argument("--tree", action="store_true", help="print only the Epic tree")
    parser.add_argument("--resume", action="store_true", help="print the session resume summary")
    parser.add_argument("--brief", action="store_true", help="a short resume briefing for the owner")
    parser.add_argument(
        "--did",
        nargs="?",
        const=date.today().isoformat(),
        metavar="DAY",
        help="print the Did part of a multi-goal worklog for DAY, default today",
    )
    parser.add_argument("--commits", metavar="TASK", help="print one task's commits and models")
    args = parser.parse_args()

    if args.resume or args.brief or args.did or args.commits:
        import pm_resume  # a sibling script: the tools folder is on sys.path when run directly

        if args.did:
            return pm_resume.did_main(args.did)
        if args.commits:
            return pm_resume.commits_main(args.commits)
        return pm_resume.main(brief=args.brief)

    tasks_dir = args.tasks if args.tasks else default_tasks_dir()
    tasks = read_tasks(tasks_dir)
    if args.next:
        resume = resume_tool()
        today = (resume.as_date(args.today) if resume else None) or date.today()
        print("\n".join(next_lines(tasks, closed_done_ids(tasks_dir), today)))
        return 0
    if args.tree:
        print(tree_block(tasks, args.today))
        return 0

    by = {name: [] for name in SECTIONS}
    other = []
    for task in tasks:
        name = task["status"] if task["status"] in SECTIONS else None
        (other if name is None else by[name]).append(task)

    in_scope = by["Active"] + by["In review"] + by["Owner check"]
    wip = sum(1 for t in in_scope if not t["urgent"] and not t["parent"])  # sub-tasks are not limited
    urgent = sum(1 for t in in_scope if t["urgent"])
    active = len(by["Active"])
    in_review = len(by["In review"])
    owner_check = len(by["Owner check"])
    ready, done = len(by["Ready"]), len(by["Done"])

    blocks = [
        f"# Status board ({args.today})",
        (
            f"WIP: {wip}/{WIP_LIMIT} · Urgent: {urgent}/{URGENT_LIMIT} · Active: {active}"
            f" · In review: {in_review} · Owner check: {owner_check} · Ready: {ready} · Done: {done}"
        ),
    ]
    if wip > WIP_LIMIT:
        blocks.append(f"⚠️ WIP limit exceeded: {wip}/{WIP_LIMIT}")
    if urgent > URGENT_LIMIT:
        blocks.append(f"⚠️ Urgent lane full: {urgent}/{URGENT_LIMIT}")
    if ready < 2:
        blocks.append(f"Ready: {ready} (< 2) → time to plan")
    blocks += [section(name, by[name]) for name in SECTIONS]
    if other:
        blocks.append(section("Other", other))

    print("\n\n".join(blocks))
    return 0


if __name__ == "__main__":
    sys.exit(main())
