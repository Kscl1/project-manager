"""Install the project-management package into a project, or upgrade it.

Usage: python .pm/tools/pm_init.py <target project> [--name NAME] [--map] [--swarm]
                                   [--check | --keep-existing | --upgrade]

The package is the .pm/ folder this script lives in, so any installed project can install another one.
- Package files (tools, tests, hooks, roles, templates) are copied; --upgrade replaces them.
- Every pm-* skill next to the package goes to .agents/skills/, with a pointer in .claude/skills/ for Claude Code;
  --upgrade replaces them too. The map layer's skill (pm-likec4-dsl) comes only with --map, then stays until
  deleted.
  The project's own skills are never touched.
- The swarm layer (.pm/swarm: pm_run, which runs workers as visible Herdr agents, and its tests) comes only with
  --swarm, then is upgraded like the other package files until deleted.
- Project data (tasks, decisions, worklog, specs, charter) is never copied from here and never overwritten.
- Seed files and root files are written only when they are missing. So are .claude/settings.json (the hooks that
  run pm_board --resume when a session starts and after a compaction) and .mcp.json (Context7; LikeC4 with --map).
  A user's own copy is never edited: what it lacks goes to the "Merge by hand" list.
- The plan is printed before anything is written. A first install into a project that already has its own
  AGENTS.md, CLAUDE.md, Backlog.md or git hooks stops there (exit 3) and writes nothing; --keep-existing installs
  and keeps those files as they are. --check prints the plan and the conflicts only. The project's own git hooks
  are never bypassed, on any run: core.hooksPath is set only when it is unset and there are none.
- A second run with the same arguments changes nothing.

For a clean package, install from the canonical source (template/.pm in project-manager): an installed
project's .pm/ also carries that project's own edits to its package files.
"""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

PKG = Path(__file__).resolve().parent.parent  # the .pm/ folder this script belongs to
PACKAGE = ["tools", "tests", "hooks", "roles", "templates"]  # refreshed by --upgrade
SEED = ["README.md", "board.md", "principles.md", "models.md"]  # the project may tune these, so written once
DATA_DIRS = ["backlog/tasks", "backlog/drafts", "backlog/archive/tasks", "worklog", "specs", "decisions/archive"]
GITIGNORE = [".pm/local/", ".pm-report.md", ".worktrees/", "__pycache__/"]
# ripgrep skips hidden folders, so a plain search misses decisions, tasks and worklogs; .gitignore still keeps
# .pm/local/ out of it.
IGNORE = ["!.pm/"]
# LF everywhere in the package: the hook is a shell script and breaks with CRLF on Windows.
GITATTRIBUTES = [
    ".pm/** text eol=lf",
    ".agents/skills/pm-*/** text eol=lf",
    "AGENTS.md text eol=lf",
    "CLAUDE.md text eol=lf",
    "backlog.config.yml text eol=lf",
]
DECISIONS = """# Decisions

The index of this project's decisions. Each decision is one file, `.pm/decisions/D-01.md`, with a stable ID that other
docs cite; its fields are in `.pm/templates/decision.md`. A replaced decision moves to `.pm/decisions/archive/` and names
its replacement and why it was dropped. Never delete one. After adding or moving a file, run
`python .pm/tools/pm_check.py --write-index`; the part below is generated.

- Living docs list the decisions they rely on in frontmatter: `depends_on: [D-01]`.
- When a decision changes, search for its ID and review every file that cites it.

<!-- decision-index:begin -->
<!-- decision-index:end -->
"""
SKIP = shutil.ignore_patterns("__pycache__", "*.pyc")
# Shipped skills sit next to the package; their names all start with pm-, a namespace apart from the user's own skills.
SKILLS = PKG.parent / ".agents" / "skills"
MAP_SKILLS = {"pm-likec4-dsl"}  # the map layer's skills: copied with --map, then upgraded like the others
SWARM = "swarm"  # the swarm layer's folder in .pm/: copied with --swarm, then upgraded like the others
UPGRADE_GUIDE = "https://github.com/Kscl1/project-manager/blob/main/docs/upgrading.md"
# Claude Code reads skills only from .claude/skills, so each skill gets a pointer there; the instructions stay in one copy.
POINTER = """---
{front}
---

Read `.agents/skills/{name}/SKILL.md` and follow it exactly, with the arguments given.
That file is the only copy of the instructions; this one only points Claude Code to it.
"""


def say(action, path, note=""):
    print(f"  {action + ' ':<8}{path}{'  (' + note + ')' if note else ''}")  # a long label keeps one space


def files_in(folder):
    return {p.relative_to(folder) for p in folder.rglob("*") if p.is_file() and "__pycache__" not in p.parts}


MANIFEST = "package-files.sha256"  # sha256sum format: what each package file looked like when installed


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_manifest(target):
    path = target / ".pm" / MANIFEST
    if not path.exists():
        return {}
    pairs = (line.split("  ", 1) for line in path.read_text(encoding="utf-8").splitlines() if "  " in line)
    return {name: digest for digest, name in pairs}


def shipped_skills(target, map_layer=False):
    """The pm-* skills next to the package; a map skill only with --map or once the project has it."""
    return sorted(
        p
        for p in SKILLS.glob("pm-*")
        if (p / "SKILL.md").is_file()
        and (p.name not in MAP_SKILLS or map_layer or (target / ".agents" / "skills" / p.name).exists())
    )


def package_parts(target, map_layer=False, swarm=False):
    """Yield (source, installed copy, manifest key prefix) for every package folder; skills are keyed from the root."""
    for part in PACKAGE:
        yield PKG / part, target / ".pm" / part, part
    if (PKG / SWARM).is_dir() and (swarm or (target / ".pm" / SWARM).exists()):
        yield PKG / SWARM, target / ".pm" / SWARM, SWARM
    for skill in shipped_skills(target, map_layer):
        yield skill, target / ".agents" / "skills" / skill.name, f".agents/skills/{skill.name}"


def write_manifest(target):
    lines = []
    for _, folder, part in package_parts(target):
        if not folder.exists():
            continue
        for rel in sorted(files_in(folder), key=str):
            lines.append(f"{sha256(folder / rel)}  {(Path(part) / rel).as_posix()}")
    path, text = target / ".pm" / MANIFEST, "\n".join(lines) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == text:
        say("keep", path)
        return
    path.write_text(text, encoding="utf-8", newline="\n")
    say("write", path, f"{len(lines)} package files")


def classify(src, dst, part, manifest):
    """Yield (kind, rel) for every package file: which side changed since install, if the manifest knows."""
    old, new = files_in(dst), files_in(src)
    for rel in sorted(old | new, key=str):
        key = (Path(part) / rel).as_posix()
        if rel not in new:
            edited = key in manifest and sha256(dst / rel) != manifest[key]
            yield ("remove-edited" if edited else "remove"), rel
        elif rel not in old:
            yield "new", rel
        elif (dst / rel).read_bytes() == (src / rel).read_bytes():
            continue
        elif key not in manifest:
            yield "differs", rel
        elif sha256(dst / rel) == manifest[key]:
            yield "update", rel
        elif sha256(src / rel) == manifest[key]:
            yield "local-edit", rel
        else:
            yield "both-changed", rel


NOTES = {
    "remove": "not in the package any more; kept in the backup",
    "remove-edited": "EDITED HERE and no longer in the package: only the backup will keep your edit",
    "new": "new in the package",
    "differs": "differs; no manifest, so it is unknown which side changed",
    "update": "package changed, project did not: replaced",
    "local-edit": "EDITED IN THIS PROJECT, package unchanged: the upgrade overwrites it (old copy in the backup)",
    "both-changed": "EDITED HERE AND IN THE PACKAGE: merge by hand from the backup after upgrading",
}


def report_changes(src, dst, part, manifest):
    """Name every package file the upgrade will replace or remove, so local work is never lost silently."""
    found = 0
    for kind, rel in classify(src, dst, part, manifest):
        say(kind, dst / rel, NOTES[kind])
        found += 1
    return found


def same_files(src, dst, part):
    return not any(classify(src, dst, part, {}))


def copy_dir(src, dst, upgrade, backup, manifest, part):
    if dst.exists() and not upgrade:
        say("skip", dst, "exists; use --upgrade to refresh")
        return
    if dst.exists() and same_files(src, dst, part):
        say("keep", dst, "same as the package")  # no backup either: nothing would be lost
        return
    if dst.exists():
        report_changes(src, dst, part, manifest)
        # Keep the old copy until the new one is in place: local edits stay recoverable.
        backup = backup / Path(part).parent
        backup.mkdir(parents=True, exist_ok=True)
        shutil.move(str(dst), str(backup / dst.name))
        say("backup", backup / dst.name)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst, ignore=SKIP)
    say("upgrade" if upgrade else "copy", dst)


def write_pointer(skill, target, upgrade):
    """Write the Claude Code pointer for one skill: its frontmatter, then where the instructions are."""
    lines = (skill / "SKILL.md").read_text(encoding="utf-8").splitlines()
    front = "\n".join(lines[1 : lines.index("---", 1)])
    text = POINTER.format(front=front, name=skill.name)
    dst = target / ".claude" / "skills" / skill.name / "SKILL.md"
    if dst.exists() and (not upgrade or dst.read_text(encoding="utf-8") == text):
        say("keep", dst)
        return
    action = "upgrade" if dst.exists() else "write"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(text, encoding="utf-8", newline="\n")
    say(action, dst)


def write_once(dst, text=None, src=None):
    if dst.exists():
        say("keep", dst)
        return
    if src is not None and not src.exists():
        say("missing", src, "the package has no such file")
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src is not None:
        shutil.copy2(src, dst)
    else:
        dst.write_text(text, encoding="utf-8", newline="\n")
    say("write", dst)


def run(command, cwd):
    say("run", " ".join(command))
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode:
        say("failed", (result.stderr or result.stdout).strip().splitlines()[-1:])
    return result.returncode == 0


def add_lines(target, name, wanted):
    path = target / name
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    missing = [line for line in wanted if line not in lines]
    if not missing:
        say("keep", path)
        return
    with path.open("a", encoding="utf-8", newline="\n") as out:
        if lines and lines[-1].strip():
            out.write("\n")
        out.write("# project-management package\n" + "\n".join(missing) + "\n")
    say("update", path, ", ".join(missing))


def package_commit():
    """The package revision this installer comes from, as '<hash> <date>', with the release tag when the source
    sits on one, and marked when it has local changes. The skills ship with the package, so their commits count."""
    paths = ["--", ".", str(SKILLS)]
    rev = subprocess.run(["git", "log", "-1", "--format=%h %cs", *paths], cwd=PKG, capture_output=True, text=True)
    dirty = subprocess.run(["git", "status", "--porcelain", *paths], cwd=PKG, capture_output=True, text=True)
    tag = subprocess.run(["git", "describe", "--tags", "--exact-match"], cwd=PKG, capture_output=True, text=True)
    commit = (
        rev.stdout.strip() if rev.returncode == 0 and rev.stdout.strip() else "unknown (source is not a git checkout)"
    )
    if tag.returncode == 0 and tag.stdout.strip():
        commit += f" ({tag.stdout.strip()})"
    if dirty.returncode == 0 and dirty.stdout.strip():
        commit += " +local changes"
    return commit


def version_is_current(target):
    path = target / ".pm" / "VERSION"
    return path.exists() and path.read_text(encoding="utf-8").startswith(f"package: {package_commit()}\n")


def write_version(target):
    """Stamp which package revision is installed, so a feedback report can name it."""
    commit = package_commit()
    path = target / ".pm" / "VERSION"
    if path.exists() and path.read_text(encoding="utf-8").startswith(f"package: {commit}\n"):
        say("keep", path, commit)  # same package: keep the first install date, so a second run changes nothing
        return
    path.write_text(f"package: {commit}\ninstalled: {time.strftime('%Y-%m-%d')}\n", encoding="utf-8", newline="\n")
    say("write", path, commit)


EXIT_CONFLICT = 3
ROOT_TEMPLATES = PKG / "templates" / "root"
HOOKS_HOW = "call .pm/hooks/pre-commit and .pm/hooks/commit-msg from your hooks, or move yours"
MERGE_HOW = {
    "AGENTS.md": "add the 'Start here' and 'Lead only' sections of .pm/templates/root/AGENTS.md to yours",
    "CLAUDE.md": "add the line @AGENTS.md to yours",
    "backlog.config.yml": "your Backlog.md setup stays as it is; .pm keeps its tasks in .pm/backlog: pick one",
    "backlog": "your Backlog.md tasks stay where they are; .pm keeps its tasks in .pm/backlog: pick one",
    "git core.hooksPath": HOOKS_HOW,
    ".git/hooks": HOOKS_HOW,
}
SETTINGS_HOW = "add the SessionStart hooks of .pm/templates/root/claude-settings.json (they run pm_board.py --resume)"


def git_out(args, cwd):
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return result.stdout.strip() if result.returncode == 0 else ""


def is_repo(target):
    return (target / ".git").exists()  # a folder, or a file in a worktree or submodule


def hook_conflicts(target):
    """The project's own git hooks, on every run: the installer never changes a hooks path the user set, and never
    bypasses hooks of theirs. Git names the hooks folder, so a worktree's or submodule's is found too."""
    if not is_repo(target):
        return []
    hooks_path = git_out(["config", "--get", "core.hooksPath"], target)
    if hooks_path:
        return [] if hooks_path == ".pm/hooks" else [("git core.hooksPath", f"points to {hooks_path}")]
    hooks = target / (git_out(["rev-parse", "--git-path", "hooks"], target) or ".git/hooks")
    custom = sorted(p.name for p in hooks.glob("*") if p.is_file() and not p.name.endswith(".sample"))
    return [(".git/hooks", "custom hooks: " + ", ".join(custom))] if custom else []


def find_conflicts(target):
    """What a first install stops on, as (name, why). Files only count before .pm/ is installed: then they are ours."""
    found = []
    if not (target / ".pm" / "VERSION").exists():
        if (target / "AGENTS.md").exists():
            found.append(("AGENTS.md", "the project has its own agent instructions"))
        claude = target / "CLAUDE.md"
        if claude.exists() and claude.read_text(encoding="utf-8", errors="replace").strip() != "@AGENTS.md":
            found.append(("CLAUDE.md", "it holds more than @AGENTS.md"))
        for name in ("backlog.config.yml", "backlog"):
            if (target / name).exists():
                found.append((name, "the project already uses Backlog.md"))
    return found + hook_conflicts(target)


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def settings_action(target):
    """write, keep or merge for .claude/settings.json: ours means a SessionStart hook that runs pm_board --resume."""
    path = target / ".claude" / "settings.json"
    if not path.exists():
        return "write"
    try:
        groups = read_json(path)["hooks"]["SessionStart"]
        commands = [str(hook["command"]) for group in groups for hook in group["hooks"]]
    except (TypeError, KeyError):  # unreadable, or a shape that is not ours: the user merges it
        return "merge"
    return "keep" if any("pm_board.py --resume" in command for command in commands) else "merge"


def wanted_servers(map_layer):
    servers = dict(read_json(ROOT_TEMPLATES / "mcp.json")["mcpServers"])
    if map_layer:
        servers.update(read_json(ROOT_TEMPLATES / "mcp-map.json")["mcpServers"])
    return servers


def mcp_action(target, map_layer):
    """(write | keep | merge, the servers to add). An existing .mcp.json is never rewritten, even one we wrote."""
    path, want = target / ".mcp.json", wanted_servers(map_layer)
    if not path.exists():
        return "write", want
    data = read_json(path)
    have = data.get("mcpServers") if isinstance(data, dict) else None
    if not isinstance(have, dict):
        return "merge", want
    missing = {name: server for name, server in want.items() if name not in have}
    return ("merge", missing) if missing else ("keep", {})


def missing_lines(target, name, wanted):
    path = target / name
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    return [line for line in wanted if line not in lines]


def merge_items(target, args, conflicts):
    """Everything the user merges by hand, as '- item: how' lines for .pm/local/merge-by-hand.md."""
    items = [(item, MERGE_HOW[item]) for item, _ in conflicts]
    if settings_action(target) == "merge":
        items.append((".claude/settings.json", SETTINGS_HOW))
    action, servers = mcp_action(target, args.map)
    if action == "merge":
        items += [(".mcp.json", f"add the {name} server: {json.dumps(config)}") for name, config in servers.items()]
    return [f"- {item}: {how}" for item, how in items]


MERGE_LIST = """# Merge by hand

What pm_init found in this project and did not touch. /pm-setup walks these with you, one at a time.
A later run only adds lines; delete a line once it is merged.

"""


def new_merge_lines(target, lines):
    path = target / ".pm" / "local" / "merge-by-hand.md"
    old = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    return [line for line in lines if line not in old]


def keep_merge_list(target, lines):
    """Keep the list for /pm-setup in .pm/local/ (git-ignored); add new lines, never drop old ones."""
    path = target / ".pm" / "local" / "merge-by-hand.md"
    new = new_merge_lines(target, lines)
    if not new:
        return
    old = path.read_text(encoding="utf-8") if path.exists() else MERGE_LIST
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(old + "\n".join(new) + "\n", encoding="utf-8", newline="\n")
    say("write", path, f"{len(new)} item(s) for /pm-setup")


def hook_names():
    return [f".pm/hooks/{p.name}" for p in sorted((PKG / "hooks").iterdir()) if p.is_file()]


def hooks_to_stage(target):
    """The hooks git does not yet record as executable; empty when there is nothing to stage."""
    names = hook_names()
    staged = git_out(["ls-files", "--stage", "--", *names], target).splitlines()
    return names if len(staged) < len(names) or any(not line.startswith("100755") for line in staged) else []


def set_hooks_path(target):
    """Only when no hooks path is set and the project has no hooks of its own (hook_conflicts)."""
    return is_repo(target) and not hook_conflicts(target) and not git_out(["config", "--get", "core.hooksPath"], target)


def plan(target, args, conflicts):
    """Every change the install makes, as (action, path relative to the project, note), before anything is written.
    main() makes exactly these changes; the tests check that no file is written outside this list."""
    entries, copies = [], 0
    for src, dst, part in package_parts(target, args.map, args.swarm):
        if not dst.exists():
            entries.append(("copy", dst, ""))
        elif args.upgrade and not same_files(src, dst, part):
            entries.append(("upgrade", dst, "old copy to .pm/local/backup/"))
        else:
            continue
        copies += 1
    for skill in shipped_skills(target, args.map):
        pointer = target / ".claude" / "skills" / skill.name / "SKILL.md"
        if not pointer.exists() or args.upgrade:
            entries.append(("write", pointer, "points Claude Code to the skill"))
    if copies or not (target / ".pm" / "VERSION").exists() or not (target / ".pm" / MANIFEST).exists():
        entries.append(("write", target / ".pm" / MANIFEST, "what each package file looked like"))
    for part in [*SEED, "decisions.md"]:
        if not (target / ".pm" / part).exists():
            entries.append(("write", target / ".pm" / part, ""))
    for part in DATA_DIRS:
        if not (target / ".pm" / part).exists():
            entries.append(("create", target / ".pm" / part, "empty folder"))
    for name in ("AGENTS.md", "CLAUDE.md", "backlog.config.yml"):
        if not (target / name).exists():
            entries.append(("write", target / name, ""))
    for name, wanted in ((".gitignore", GITIGNORE), (".gitattributes", GITATTRIBUTES), (".ignore", IGNORE)):
        if missing_lines(target, name, wanted):
            entries.append(("append", target / name, "adds lines at the end"))
    if settings_action(target) == "write":
        entries.append(("write", target / ".claude" / "settings.json", "session start and compaction hooks"))
    action, servers = mcp_action(target, args.map)
    if action == "write":
        entries.append(("write", target / ".mcp.json", ", ".join(servers)))
    if not version_is_current(target):
        entries.append(("write", target / ".pm" / "VERSION", "the package revision"))
    if new_merge_lines(target, merge_items(target, args, conflicts)):
        entries.append(("append", target / ".pm" / "local" / "merge-by-hand.md", "what /pm-setup merges with you"))
    if set_hooks_path(target):
        entries.append(("set", "git core.hooksPath", ".pm/hooks"))
    if is_repo(target) and not hook_conflicts(target) and hooks_to_stage(target):
        entries.append(("stage", "git index", "the .pm hooks as executable"))
    return [(action, shown(target, path), note) for action, path, note in entries]


def shown(target, path):
    return path.relative_to(target).as_posix() if isinstance(path, Path) else path


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Install or upgrade the .pm/ package in a project.")
    parser.add_argument("target", help="the project to install into")
    parser.add_argument("--name", help="Backlog project name (default: the target folder name)")
    parser.add_argument("--upgrade", action="store_true", help="replace package files; project data is never touched")
    parser.add_argument("--dry-run", action="store_true", help="with --upgrade: list what would change, write nothing")
    parser.add_argument("--map", action="store_true", help="also add the LikeC4 MCP server and skill")
    parser.add_argument("--swarm", action="store_true", help="also add pm_run, which runs workers in Herdr")
    parser.add_argument("--check", action="store_true", help="print the plan and the conflicts, write nothing")
    parser.add_argument(
        "--keep-existing", action="store_true", help="install even if the project has its own AGENTS.md, hooks..."
    )
    args = parser.parse_args(argv)

    target = Path(args.target).resolve()
    if not target.is_dir():
        sys.exit(f"{target} is not a directory")
    if (target / ".pm").resolve() == PKG:
        sys.exit("this is the package's own project; install into another folder")
    name = args.name or target.name
    # An installed project used as the source carries only the layers it chose. A layer asked for, or one the target
    # already has, must be in the source: otherwise the upgrade would drop it from the manifest and stop updating it.
    skills = {p.name for p in SKILLS.glob("pm-*")}
    missing = sorted(
        n for n in MAP_SKILLS if n not in skills and (args.map or (target / ".agents" / "skills" / n).exists())
    )
    if (args.swarm or (target / ".pm" / SWARM).is_dir()) and not (PKG / SWARM).is_dir():
        missing.append(f"{SWARM}/")
    if missing:
        sys.exit(
            f"this package has no {', '.join(missing)}, which this project needs; use the project-manager checkout"
        )
    conflicts = find_conflicts(target)
    first = not (target / ".pm" / "VERSION").exists()
    stops = first and bool(conflicts)  # once installed, the project's own hooks are kept and listed, not a stop
    if not args.dry_run:
        entries = plan(target, args, conflicts)
        print(f"Plan for {target} ({len(entries)} change(s)):")
        for entry in entries:
            say(*entry)
        if conflicts:
            print("\nAlready in the project, kept as it is (/pm-setup merges it with you):")
            for item, why in conflicts:
                say("keep", item, why)
        if args.check:
            return EXIT_CONFLICT if stops else 0
        if stops and not args.keep_existing:
            print(
                "\nStopped: nothing was written. Run again with --keep-existing to install and keep those files"
                " as they are, then merge them by hand."
            )
            return EXIT_CONFLICT
        print()
    print(f"{'Upgrading' if args.upgrade else 'Installing'} the package from {PKG} into {target}")

    manifest = read_manifest(target)
    if args.dry_run:
        if not args.upgrade:
            sys.exit("--dry-run only makes sense with --upgrade")
        total = sum(
            report_changes(src, dst, part, manifest)
            for src, dst, part in package_parts(target, args.map, args.swarm)
            if dst.exists()
        )
        for _, dst, _ in package_parts(target, args.map, args.swarm):
            if not dst.exists():
                say("new", dst, NOTES["new"])
                total += 1
        print(
            f"\nDry run: {total} package file(s) would change; nothing was written."
            + ("" if manifest else " No manifest yet: run one real upgrade to record one.")
        )
        return 0
    merge = merge_items(target, args, conflicts)  # before the writes below, which make some files ours
    backup = target / ".pm" / "local" / "backup" / time.strftime("%Y%m%d-%H%M%S")
    for src, dst, part in package_parts(target, args.map, args.swarm):
        copy_dir(src, dst, args.upgrade, backup, manifest, part)
    for skill in shipped_skills(target, args.map):
        write_pointer(skill, target, args.upgrade)
    write_manifest(target)
    for part in SEED:
        write_once(target / ".pm" / part, src=PKG / part)
    write_once(target / ".pm" / "decisions.md", text=DECISIONS)
    for part in DATA_DIRS:
        (target / ".pm" / part).mkdir(parents=True, exist_ok=True)

    agents = ROOT_TEMPLATES / "AGENTS.md"
    if agents.exists():
        write_once(target / "AGENTS.md", text=agents.read_text(encoding="utf-8").replace("<project name>", name))
    write_once(target / "CLAUDE.md", src=ROOT_TEMPLATES / "CLAUDE.md")
    config = (ROOT_TEMPLATES / "backlog.config.yml").read_text(encoding="utf-8").replace("<project>", name)
    write_once(target / "backlog.config.yml", text=config)
    add_lines(target, ".gitignore", GITIGNORE)
    add_lines(target, ".gitattributes", GITATTRIBUTES)
    add_lines(target, ".ignore", IGNORE)
    if settings_action(target) == "write":
        write_once(target / ".claude" / "settings.json", src=ROOT_TEMPLATES / "claude-settings.json")
    action, servers = mcp_action(target, args.map)
    if action == "write":
        text = json.dumps({"mcpServers": servers}, indent=2) + "\n"
        write_once(target / ".mcp.json", text=text)
    write_version(target)
    keep_merge_list(target, merge)

    if not is_repo(target):
        say("note", "not a git repository yet: run git init, then run this installer again")
    elif hook_conflicts(target):
        say("keep", "git hooks", "yours stay; the .pm hooks are not active until you merge them (/pm-setup)")
    else:
        if set_hooks_path(target):
            run(["git", "config", "core.hooksPath", ".pm/hooks"], cwd=target)
        # Git on Linux and macOS skips a hook without the exec bit, and a Windows checkout cannot keep the bit on
        # disk, so set it on the files and stage them with it; the first commit then records them as executable.
        for hook in hook_names():
            path = target / hook
            path.chmod(path.stat().st_mode | 0o111)
        names = hooks_to_stage(target)
        if names:
            run(["git", "add", "--chmod=+x", "--", *names], cwd=target)

    if merge:
        print("\nMerge by hand (the installer never rewrites a file of yours):")
        for line in merge:
            print(f"  {line}")
    print("\nNext:")
    if first:
        print("  1. Open the project in your coding agent and run /pm-setup: it fills the charter and models with you.")
        print("  2. python .pm/tools/pm_check.py    # should print: No problems found")
        print("  3. backlog browser                 # the task screen")
        return 0
    # Already installed (an upgrade, a rollback or a new layer): the upgrade guide's checks, run from the project.
    checks = ["python .pm/tools/pm_check.py", "python -m unittest discover -s .pm/tests"]
    if (target / ".pm" / SWARM).is_dir():
        checks.append(f"python -m unittest discover -s .pm/{SWARM}")
    checks.append("python .pm/tools/pm_board.py --resume")
    print(f"  In {target}, review the diff and any merge list, then run:")
    for number, check in enumerate(checks, 1):
        print(f"  {number}. {check}")
    print(f"  Guide: {UPGRADE_GUIDE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
