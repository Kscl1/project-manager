"""Install the project-management package into a project, or upgrade it.

Usage: python .pm/tools/pm_init.py <target project> [--name NAME] [--map] [--check | --keep-existing | --upgrade]

The package is the .pm/ folder this script lives in, so any installed project can install another one.
- Package files (tools, tests, hooks, roles, templates) are copied; --upgrade replaces them (D-49).
- Every pm-* skill next to the package goes to .agents/skills/, with a pointer in .claude/skills/ for Claude Code (D-116);
  --upgrade replaces them too. The project's own skills are never touched.
- Project data (tasks, decisions, worklog, specs, charter) is never copied from here and never overwritten.
- Seed files and root files are written only when they are missing. So are .claude/settings.json (the hooks that
  run pm_board --resume when a session starts and after a compaction) and .mcp.json (Context7; LikeC4 with --map).
  A user's own copy is never edited: what it lacks goes to the "Merge by hand" list.
- The plan is printed before anything is written. A first install into a project that already has its own
  AGENTS.md, CLAUDE.md, Backlog.md or git hooks stops there (exit 3) and writes nothing; --keep-existing installs
  and keeps those files as they are. --check prints the plan and the conflicts only.
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
# LF everywhere in the package: the hook is a shell script and breaks with CRLF on Windows.
GITATTRIBUTES = [
    ".pm/** text eol=lf",
    "AGENTS.md text eol=lf",
    "CLAUDE.md text eol=lf",
    "backlog.config.yml text eol=lf",
]
DECISIONS = """# Decisions

The index of this project's decisions. Each decision is one file, `.pm/decisions/D-01.md`, with a stable ID that other
docs cite; its fields are in `.pm/templates/decision.md`. A replaced decision moves to `.pm/decisions/archive/` and names
its replacement and why it was dropped. Never delete one. After adding or moving a file, run
`python .pm/tools/pm_check.py --write-index`; the part below is generated.

<!-- decision-index:begin -->
<!-- decision-index:end -->
"""
SKIP = shutil.ignore_patterns("__pycache__", "*.pyc")
SKILLS = PKG.parent / ".agents" / "skills"  # shipped skills sit next to the package; theirs all start with pm- (D-116)
# Claude Code reads skills only from .claude/skills, so each skill gets a pointer there; the instructions stay in one copy.
POINTER = """---
{front}
---

Read `.agents/skills/{name}/SKILL.md` and follow it exactly, with the arguments given.
That file is the only copy of the instructions; this one only points Claude Code to it.
"""


def say(action, path, note=""):
    print(f"  {action:<8}{path}{'  (' + note + ')' if note else ''}")


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


def shipped_skills():
    return sorted(p for p in SKILLS.glob("pm-*") if (p / "SKILL.md").is_file())


def package_parts(target):
    """Yield (source, installed copy, manifest key prefix) for every package folder; skills are keyed from the root."""
    for part in PACKAGE:
        yield PKG / part, target / ".pm" / part, part
    for skill in shipped_skills():
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


def copy_dir(src, dst, upgrade, backup, manifest, part):
    if dst.exists() and not upgrade:
        say("skip", dst, "exists; use --upgrade to refresh")
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
        out.write("# project-management package (D-55)\n" + "\n".join(missing) + "\n")
    say("update", path, ", ".join(missing))


def write_version(target):
    """Stamp which package revision is installed, so a feedback report can name it (REQ-42). Rewritten on every run."""
    rev = subprocess.run(["git", "log", "-1", "--format=%h %cs", "--", "."], cwd=PKG, capture_output=True, text=True)
    dirty = subprocess.run(["git", "status", "--porcelain", "--", "."], cwd=PKG, capture_output=True, text=True)
    commit = (
        rev.stdout.strip() if rev.returncode == 0 and rev.stdout.strip() else "unknown (source is not a git checkout)"
    )
    if dirty.returncode == 0 and dirty.stdout.strip():
        commit += " +local changes"
    path = target / ".pm" / "VERSION"
    if path.exists() and path.read_text(encoding="utf-8").startswith(f"package: {commit}\n"):
        say("keep", path, commit)  # same package: keep the first install date, so a second run changes nothing
        return
    path.write_text(f"package: {commit}\ninstalled: {time.strftime('%Y-%m-%d')}\n", encoding="utf-8", newline="\n")
    say("write", path, commit)


EXIT_CONFLICT = 3
ROOT_TEMPLATES = PKG / "templates" / "root"
MERGE_HOW = {
    "AGENTS.md": "add the 'Start here' and 'Lead only' sections of .pm/templates/root/AGENTS.md to yours",
    "CLAUDE.md": "add the line @AGENTS.md to yours",
    "backlog.config.yml": "your Backlog.md setup stays as it is; .pm keeps its tasks in .pm/backlog: pick one",
    "backlog": "your Backlog.md tasks stay where they are; .pm keeps its tasks in .pm/backlog: pick one",
    "git core.hooksPath": "call .pm/hooks/pre-commit and .pm/hooks/commit-msg from your hooks, or move yours",
    ".git/hooks": "call .pm/hooks/pre-commit and .pm/hooks/commit-msg from your hooks, or move yours",
}


def git_out(args, cwd):
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return result.stdout.strip() if result.returncode == 0 else ""


def find_conflicts(target):
    """What a first install would clash with, as (name, why). Empty once .pm/ is installed: those files are ours then."""
    if (target / ".pm" / "VERSION").exists():
        return []
    found = []
    if (target / "AGENTS.md").exists():
        found.append(("AGENTS.md", "the project has its own agent instructions"))
    claude = target / "CLAUDE.md"
    if claude.exists() and claude.read_text(encoding="utf-8", errors="replace").strip() != "@AGENTS.md":
        found.append(("CLAUDE.md", "it holds more than @AGENTS.md"))
    for name in ("backlog.config.yml", "backlog"):
        if (target / name).exists():
            found.append((name, "the project already uses Backlog.md"))
    if (target / ".git").is_dir():
        hooks_path = git_out(["config", "--get", "core.hooksPath"], target)
        if hooks_path and hooks_path != ".pm/hooks":
            found.append(("git core.hooksPath", f"points to {hooks_path}"))
        hooks = target / ".git" / "hooks"
        custom = sorted(p.name for p in hooks.glob("*") if p.is_file() and not p.name.endswith(".sample"))
        if custom:
            found.append((".git/hooks", "custom hooks: " + ", ".join(custom)))
    return found


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def json_text(data):
    return json.dumps(data, indent=2) + "\n"


def settings_action(target):
    """write, keep or merge for .claude/settings.json: ours means a SessionStart hook that runs pm_board --resume."""
    path = target / ".claude" / "settings.json"
    if not path.exists():
        return "write"
    groups = ((read_json(path) or {}).get("hooks") or {}).get("SessionStart") or []
    commands = (hook.get("command", "") for group in groups for hook in group.get("hooks", []))
    return "keep" if any("pm_board.py --resume" in command for command in commands) else "merge"


def wanted_servers(map_layer):
    servers = dict(read_json(ROOT_TEMPLATES / "mcp.json")["mcpServers"])
    if map_layer:
        servers.update(read_json(ROOT_TEMPLATES / "mcp-map.json")["mcpServers"])
    return servers


def mcp_action(target, map_layer):
    """(write | update | keep | merge, the servers to add). update only rewrites a file this installer wrote itself."""
    path, want = target / ".mcp.json", wanted_servers(map_layer)
    if not path.exists():
        return "write", want
    data = read_json(path)
    have = (data or {}).get("mcpServers") or {}
    missing = {name: server for name, server in want.items() if name not in have}
    if not missing:
        return "keep", {}
    if data is not None and set(data) == {"mcpServers"} and have == wanted_servers(False):
        return "update", want  # exactly what an install without --map wrote
    return "merge", missing


def missing_lines(target, name, wanted):
    path = target / name
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    return [line for line in wanted if line not in lines]


def plan(target, args, conflicts):
    """Every write, as (action, path, note), before anything is written."""
    entries = []
    for src, dst, _ in package_parts(target):
        if not dst.exists():
            entries.append(("copy", dst, ""))
        elif args.upgrade:
            entries.append(("upgrade", dst, "old copy to .pm/local/backup/"))
    for part in [*SEED, "decisions.md"]:
        if not (target / ".pm" / part).exists():
            entries.append(("write", target / ".pm" / part, ""))
    for name in ("AGENTS.md", "CLAUDE.md", "backlog.config.yml"):
        if not (target / name).exists():
            entries.append(("write", target / name, ""))
    for name, wanted in ((".gitignore", GITIGNORE), (".gitattributes", GITATTRIBUTES)):
        if missing_lines(target, name, wanted):
            entries.append(("update", target / name, "adds lines"))
    action = settings_action(target)
    if action != "keep":
        entries.append((action, target / ".claude" / "settings.json", "session start and compaction hooks"))
    action, servers = mcp_action(target, args.map)
    if action != "keep":
        entries.append((action, target / ".mcp.json", ", ".join(servers)))
    hooks_blocked = any(name in ("git core.hooksPath", ".git/hooks") for name, _ in conflicts)
    if (target / ".git").exists() and not hooks_blocked:
        if git_out(["config", "--get", "core.hooksPath"], target) != ".pm/hooks":
            entries.append(("set", "git core.hooksPath", ".pm/hooks"))
    return entries


def write_settings(target):
    action = settings_action(target)
    path = target / ".claude" / "settings.json"
    if action == "write":
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT_TEMPLATES / "claude-settings.json", path)
        say("write", path, "session start and compaction hooks")
    else:
        say("keep", path, "merge by hand" if action == "merge" else "")
    return action == "merge"


def write_mcp(target, map_layer):
    action, servers = mcp_action(target, map_layer)
    path = target / ".mcp.json"
    if action in ("write", "update"):
        path.write_text(json_text({"mcpServers": servers}), encoding="utf-8", newline="\n")
        say(action, path, ", ".join(servers))
        return {}
    say("keep", path, "merge by hand" if action == "merge" else "")
    return servers if action == "merge" else {}


MERGE_LIST = """# Merge by hand

What pm_init found in this project and did not touch. /pm-setup walks these with you, one at a time.
A later run only adds lines: conflicts are not looked for again once .pm/ is installed.

"""


def keep_merge_list(target, lines):
    """Keep the list for /pm-setup in .pm/local/ (git-ignored); add new lines, never drop old ones."""
    path = target / ".pm" / "local" / "merge-by-hand.md"
    old = path.read_text(encoding="utf-8") if path.exists() else MERGE_LIST
    new = [line for line in lines if line not in old.splitlines()]
    if not new:
        say("keep", path)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(old + "\n".join(new) + "\n", encoding="utf-8", newline="\n")
    say("write", path, f"{len(new)} item(s) for /pm-setup")


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Install or upgrade the .pm/ package in a project.")
    parser.add_argument("target", help="the project to install into")
    parser.add_argument("--name", help="Backlog project name (default: the target folder name)")
    parser.add_argument("--upgrade", action="store_true", help="replace package files; project data is never touched")
    parser.add_argument("--dry-run", action="store_true", help="with --upgrade: list what would change, write nothing")
    parser.add_argument("--map", action="store_true", help="also add the LikeC4 MCP server to .mcp.json")
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
    conflicts = find_conflicts(target)
    if not args.dry_run:
        entries = plan(target, args, conflicts)
        print(f"Plan for {target} ({len(entries)} change(s)):")
        for entry in entries:
            say(*entry)
        if not entries:
            print("  nothing to change")
        if conflicts:
            print("\nAlready in the project (kept as it is; see 'Merge by hand' below):")
            for item, why in conflicts:
                say("conflict", item, why)
        if args.check:
            return EXIT_CONFLICT if conflicts else 0
        if conflicts and not args.keep_existing:
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
            report_changes(src, dst, part, manifest) for src, dst, part in package_parts(target) if dst.exists()
        )
        print(
            f"\nDry run: {total} package file(s) would change; nothing was written."
            + ("" if manifest else " No manifest yet: run one real upgrade to record one.")
        )
        return 0
    backup = target / ".pm" / "local" / "backup" / time.strftime("%Y%m%d-%H%M%S")
    for src, dst, part in package_parts(target):
        copy_dir(src, dst, args.upgrade, backup, manifest, part)
    for skill in shipped_skills():
        write_pointer(skill, target, args.upgrade)
    write_manifest(target)
    for part in SEED:
        write_once(target / ".pm" / part, src=PKG / part)
    write_once(target / ".pm" / "decisions.md", text=DECISIONS)
    for part in DATA_DIRS:
        (target / ".pm" / part).mkdir(parents=True, exist_ok=True)

    root = PKG / "templates" / "root"
    agents = root / "AGENTS.md"
    if agents.exists():
        write_once(target / "AGENTS.md", text=agents.read_text(encoding="utf-8").replace("<project name>", name))
    write_once(target / "CLAUDE.md", src=root / "CLAUDE.md")
    config = (root / "backlog.config.yml").read_text(encoding="utf-8").replace("<project>", name)
    write_once(target / "backlog.config.yml", text=config)
    add_lines(target, ".gitignore", GITIGNORE)
    add_lines(target, ".gitattributes", GITATTRIBUTES)
    merge = [(item, MERGE_HOW[item]) for item, _ in conflicts]
    if write_settings(target):
        merge.append((".claude/settings.json", "add the SessionStart hooks of .pm/templates/root/claude-settings.json"))
    for server, config in write_mcp(target, args.map).items():
        merge.append((".mcp.json", f"add the {server} server: {json.dumps(config)}"))
    write_version(target)

    hooks_blocked = any(item in ("git core.hooksPath", ".git/hooks") for item, _ in conflicts)
    if not (target / ".git").exists():
        say("note", "not a git repository yet: run git init, then git config core.hooksPath .pm/hooks")
    elif not hooks_blocked:
        if git_out(["config", "--get", "core.hooksPath"], target) == ".pm/hooks":
            say("keep", "git core.hooksPath", ".pm/hooks")
        else:
            run(["git", "config", "core.hooksPath", ".pm/hooks"], cwd=target)
        # Git on Linux and macOS skips a hook without the exec bit, and a Windows checkout cannot keep the bit on
        # disk, so set it on the files and stage them with it; the first commit then records them as executable.
        hooks = sorted(p for p in (target / ".pm" / "hooks").iterdir() if p.is_file())
        for hook in hooks:
            hook.chmod(hook.stat().st_mode | 0o111)
        names = [h.relative_to(target).as_posix() for h in hooks]
        staged = git_out(["ls-files", "--stage", "--", *names], target).splitlines()
        if len(staged) < len(names) or any(not line.startswith("100755") for line in staged):
            run(["git", "add", "--chmod=+x", "--", *names], cwd=target)

    if merge:
        print("\nMerge by hand (the installer never edits your own copy):")
        for item, how in merge:
            print(f"  - {item}: {how}")
        keep_merge_list(target, [f"- {item}: {how}" for item, how in merge])
    print("\nNext:")
    print("  1. Open the project in your coding agent and run /pm-setup: it fills the charter and models with you.")
    print("  2. python .pm/tools/pm_check.py    # should print: No problems found")
    print("  3. backlog browser                 # the task screen")
    return 0


if __name__ == "__main__":
    sys.exit(main())
