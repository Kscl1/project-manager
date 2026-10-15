"""Install the project-management package into a project, or upgrade it.

Usage: python .pm/tools/pm_init.py <target project> [--name NAME] [--upgrade]

The package is the .pm/ folder this script lives in, so any installed project can install another one.
- Package files (tools, tests, hooks, roles, templates) are copied; --upgrade replaces them (D-49).
- Every pm-* skill next to the package goes to .agents/skills/, with a pointer in .claude/skills/ for Claude Code (D-116);
  --upgrade replaces them too. The project's own skills are never touched.
- Project data (tasks, decisions, worklog, specs, charter) is never copied from here and never overwritten.
- Seed files and root files are written only when they are missing.
Every action is printed.

For a clean package, install from the canonical source (template/.pm in project-manager): an installed
project's .pm/ also carries that project's own edits to its package files.
"""

import argparse
import hashlib
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
    (target / ".pm" / MANIFEST).write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    say("write", target / ".pm" / MANIFEST, f"{len(lines)} package files")


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
    text = f"package: {commit}\ninstalled: {time.strftime('%Y-%m-%d')}\n"
    (target / ".pm" / "VERSION").write_text(text, encoding="utf-8", newline="\n")
    say("write", target / ".pm" / "VERSION", commit)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Install or upgrade the .pm/ package in a project.")
    parser.add_argument("target", help="the project to install into")
    parser.add_argument("--name", help="Backlog project name (default: the target folder name)")
    parser.add_argument("--upgrade", action="store_true", help="replace package files; project data is never touched")
    parser.add_argument("--dry-run", action="store_true", help="with --upgrade: list what would change, write nothing")
    args = parser.parse_args()

    target = Path(args.target).resolve()
    if not target.is_dir():
        sys.exit(f"{target} is not a directory")
    if (target / ".pm").resolve() == PKG:
        sys.exit("this is the package's own project; install into another folder")
    name = args.name or target.name
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
        return
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
    write_version(target)

    if (target / ".git").exists():
        run(["git", "config", "core.hooksPath", ".pm/hooks"], cwd=target)
        # Git on Linux and macOS skips a hook without the exec bit, and a Windows checkout cannot keep the bit on
        # disk, so set it on the files and stage them with it; the first commit then records them as executable.
        hooks = sorted(p for p in (target / ".pm" / "hooks").iterdir() if p.is_file())
        for hook in hooks:
            hook.chmod(hook.stat().st_mode | 0o111)
        run(["git", "add", "--chmod=+x", "--", *(h.relative_to(target).as_posix() for h in hooks)], cwd=target)
    else:
        say("note", "not a git repository yet: run git init, then git config core.hooksPath .pm/hooks")

    print("\nNext:")
    print("  1. Fill .pm/models.md with the models you have.")
    print("  2. Write .pm/charter.md from .pm/templates/charter.md (the entry door, D-62).")
    print("  3. python .pm/tools/pm_check.py    # should print: No problems found")
    print("  4. backlog browser                 # the task screen (D-98)")


if __name__ == "__main__":
    main()
