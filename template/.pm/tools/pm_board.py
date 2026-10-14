"""Turkish status board for the Backlog.md task files. Standard library only.

Usage: python .pm/tools/pm_board.py [--tasks DIR] [--today YYYY-MM-DD] [--tree | --resume | --did [DAY] | --commits TASK]
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
ACIL_LIMIT = 1
STATUS = {
    "Active": "Devam ediyor",
    "In review": "İncelemede",
    "Owner check": "Sahip kontrolü",
    "Ready": "Sırada",
    "Done": "Bitti",
}
SECTIONS = ["Devam ediyor", "İncelemede", "Sahip kontrolü", "Sırada", "Bitti"]


def default_tasks_dir():
    """The first existing tasks folder: new .pm layout, then the old layout."""
    for candidate in (ROOT / ".pm" / "backlog" / "tasks", ROOT / "backlog" / "tasks"):
        if candidate.is_dir():
            return candidate
    return ROOT / ".pm" / "backlog" / "tasks"


BLOCK_SCALARS = (">", ">-", ">+", "|", "|-", "|+")


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
        if key == "labels" and line.lstrip().startswith("- "):
            fields["labels"].append(scalar(line.strip()[2:]))
            continue
        name, sep, value = line.partition(":")
        if not sep or line.startswith((" ", "\t")):
            key = None
            continue
        key = name.strip()
        if key == "labels":
            fields["labels"] = [scalar(v) for v in value.strip().strip("[]").split(",") if v.strip()]
        elif value.strip() in BLOCK_SCALARS:
            block, joiner = [], " " if value.strip()[0] == ">" else "\n"
            fields[key] = ""
        else:
            fields[key] = scalar(value)
    return None  # the closing --- never came, so this is not frontmatter


def read_task(path):
    fields = read_frontmatter(path.read_text(encoding="utf-8-sig").splitlines())
    if fields is None:
        return None
    labels = fields.get("labels", [])
    return {
        "id": fields.get("id", ""),
        "title": fields.get("title", ""),
        "status": fields.get("status", ""),
        "type": fields.get("type", ""),
        "parent": fields.get("parent_task_id", ""),
        "acil": "urgent" in labels or "acil" in labels,
    }


def order(task):
    number = re.search(r"\d+", task["id"])
    return (int(number.group()) if number else float("inf"), task["id"])


def line(task):
    return f"- {task['id']} · {task['title']}" + (" (acil)" if task["acil"] else "")


def section(name, tasks):
    items = "\n".join(line(t) for t in sorted(tasks, key=order)) or "- (yok)"
    return f"## {name}\n{items}"


def tree_block(tasks, today):
    """The Epic tree with direct-child progress as Turkish Markdown."""
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
        name = STATUS.get(task["status"], task["status"])
        text = f"{'  ' * depth}{line(task)} · {name}"
        if task["type"] == "epic" or kids:
            done = sum(1 for kid in kids if kid["status"] == "Done")
            text += f" [{done}/{len(kids)}]"
        out = [text]
        for kid in kids:
            out.extend(render(kid, depth + 1, seen))
        return out

    roots = [t for t in tasks if not t["parent"] and (t["type"] == "epic" or has_children(t))]
    lines = [f"# Epic ağacı ({today})"]
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
            orphan_lines.append(
                f"{line(orphan)} · {STATUS.get(orphan['status'], orphan['status'])} (ebeveyn yok: {orphan['parent']})"
            )
            seen.add(orphan["id"])
            for kid in sorted(children.get(orphan["id"], []), key=order):
                orphan_lines.extend(render(kid, 1, seen))
        blocks.append("## Sahipsiz\n" + "\n".join(orphan_lines))

    # Cycles: tasks with an existing parent that no root reaches (finding 2).
    cycle_ids = _cycle_ids(tasks, by_id, seen)
    if cycle_ids:
        cycle_tasks = sorted((by_id[cid] for cid in cycle_ids), key=order)
        items = "\n".join(f"{line(t)} · {STATUS.get(t['status'], t['status'])} (döngü)" for t in cycle_tasks)
        blocks.append(f"## Döngü\n{items}")

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


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Print a Turkish status board from Backlog tasks.")
    parser.add_argument("--tasks", default=None)
    parser.add_argument("--today", default=date.today().isoformat())
    parser.add_argument("--tree", action="store_true", help="print only the Epic tree")
    parser.add_argument("--resume", action="store_true", help="print the session resume summary (D-51)")
    parser.add_argument(
        "--did",
        nargs="?",
        const=date.today().isoformat(),
        metavar="DAY",
        help="print the Did part of a multi-goal worklog for DAY, default today (D-109)",
    )
    parser.add_argument("--commits", metavar="TASK", help="print one task's commits and models (D-109)")
    args = parser.parse_args()

    if args.resume or args.did or args.commits:
        import pm_resume  # a sibling script: the tools folder is on sys.path when run directly

        if args.did:
            return pm_resume.did_main(args.did)
        if args.commits:
            return pm_resume.commits_main(args.commits)
        return pm_resume.main()

    tasks_dir = args.tasks if args.tasks else default_tasks_dir()
    tasks = [t for t in (read_task(p) for p in sorted(Path(tasks_dir).glob("*.md"))) if t]
    if args.tree:
        print(tree_block(tasks, args.today))
        return 0

    by = {name: [] for name in SECTIONS}
    other = []
    for task in tasks:
        name = STATUS.get(task["status"])
        (other if name is None else by[name]).append(task)

    in_scope = by["Devam ediyor"] + by["İncelemede"] + by["Sahip kontrolü"]
    wip = sum(1 for t in in_scope if not t["acil"] and not t["parent"])  # sub-tasks are not limited
    acil = sum(1 for t in in_scope if t["acil"])
    devam = len(by["Devam ediyor"])
    inceleme = len(by["İncelemede"])
    owner = len(by["Sahip kontrolü"])
    sirada, biten = len(by["Sırada"]), len(by["Bitti"])

    blocks = [
        f"# Durum panosu ({args.today})",
        f"WIP: {wip}/{WIP_LIMIT} · Acil: {acil}/{ACIL_LIMIT} · Devam ediyor: {devam} · İncelemede: {inceleme} · Sahip kontrolü: {owner} · Sırada: {sirada} · Biten: {biten}",
    ]
    if wip > WIP_LIMIT:
        blocks.append(f"⚠️ WIP sınırı aşıldı: {wip}/{WIP_LIMIT}")
    if acil > ACIL_LIMIT:
        blocks.append(f"⚠️ Acil şerit dolu: {acil}/{ACIL_LIMIT}")
    if sirada < 2:
        blocks.append(f"Hazır: {sirada} (< 2) → planlama zamanı")
    blocks += [section(name, by[name]) for name in SECTIONS]
    if other:
        blocks.append(section("Diğer", other))

    print("\n\n".join(blocks))
    return 0


if __name__ == "__main__":
    sys.exit(main())
