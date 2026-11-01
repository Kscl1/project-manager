"""Install the project-management package into a project, or upgrade it.

Usage: python .pm/tools/pm_init.py <target project> [--name NAME] [--map] [--swarm]
                                   [--check | --keep-existing | --upgrade]

The package is the .pm/ folder this script lives in, so any installed project can install another one.
- Package files (tools, tests, hooks, roles, templates) are copied; --upgrade replaces them. A replaced folder is
  built in a new temporary folder beside the old one, whose name cannot already exist, and only then swapped in, so
  a copy that fails (a lock, antivirus, a full disk) leaves the project with the tools it had; no folder of the
  project's is ever removed on the way, and the run stops with one line saying where the old copy is and the command
  that puts it back.
- Every pm-* skill next to the package goes to .agents/skills/, with a pointer in .claude/skills/ for Claude Code;
  --upgrade replaces them too. The map layer's skill (pm-likec4-dsl) comes only with --map, then stays until
  deleted.
  The project's own skills are never touched.
- The swarm layer (.pm/swarm: pm_run, which runs workers as visible Herdr agents, and its tests) comes only with
  --swarm, then is upgraded like the other package files until deleted.
- Project data (tasks, decisions, worklog, specs, charter) is never copied from here and never overwritten.
- Seed files and root files are written only when they are missing. So are .claude/settings.json (the hooks that
  run pm_board --resume when a session starts and after a compaction), .mcp.json (Context7; LikeC4 with --map) and
  .claude/launch.json, which Claude Desktop opens in a preview pane: the board, and the map with --map, so the
  board needs no terminal.
  A user's own copy is never edited: what it lacks goes to the "Merge by hand" list.
- A real install prints a few lines when it is done (what it added or changed, what it kept of the user's, what to
  merge by hand) and then what to do next; --check prints the whole plan and the conflicts instead. A first install
  into a project that already has its own AGENTS.md, CLAUDE.md, Backlog.md or git hooks stops there (exit 3) and
  writes nothing, after showing that plan; --keep-existing installs and keeps those files as they are. The
  project's own git hooks are never bypassed, on any run: core.hooksPath is set only when it is unset and there are
  none.
- --lang <code> sets the project language: one 'Language: <code>' line under a '## Language' heading in AGENTS.md
  (appended with a short rule, or only the value changed), in the user's own copy too, since the flag asks for it; and
  the language key in a .claude/settings.json the installer wrote, while a user's own copy gets a merge-by-hand line. Without the flag no language is written, and --upgrade never touches either file. The installed copy
  in .pm/tools may run on its own project with --lang only, so /pm-setup can set the language later.
- --upgrade compares the '## ' sections of the package's AGENTS.md template with the project's own file and names the
  ones it lacks in one line; it never rewrites that file, so the user's text stays as it is.
- After an upgrade from the project-manager checkout, the programs on this machine (Backlog.md, Pi and the rest)
  are compared with the release's tested versions (tools/setup/bom.py --updates); nothing is installed.
- A second run with the same arguments changes nothing.

For a clean package, install from the canonical source (template/.pm in project-manager): an installed
project's .pm/ also carries that project's own edits to its package files.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import NamedTuple

PKG = Path(__file__).resolve().parent.parent  # the .pm/ folder this script belongs to
PACKAGE = ["tools", "tests", "hooks", "roles", "templates"]  # refreshed by --upgrade
SEED = ["README.md", "board.md", "principles.md", "models.md"]  # the project may tune these, so written once
DATA_DIRS = ["backlog/tasks", "backlog/drafts", "backlog/archive/tasks", "worklog", "specs", "decisions/archive"]
GITIGNORE = [".pm/local/", ".pm-report.md", ".worktrees/", "__pycache__/"]
# ripgrep skips hidden folders, so a plain search misses decisions, tasks and worklogs. .pm/local/ is named again
# because ripgrep reads .gitignore only inside a git repository.
IGNORE = ["!.pm/", ".pm/local/"]
# LF everywhere the installer writes: a hook is a shell script and breaks with CRLF on Windows, and a CRLF copy of a
# package file looks edited next to the manifest's hash. Git is told so for each file pm_init writes, the root files
# included, or "git add" warns about every one of them in a project with core.autocrlf=true.
GITATTRIBUTES = [
    ".pm/** text eol=lf",
    ".agents/skills/pm-*/** text eol=lf",
    ".claude/** text eol=lf",
    ".gitignore text eol=lf",
    ".gitattributes text eol=lf",
    ".ignore text eol=lf",
    ".mcp.json text eol=lf",
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
# The folder a copy is built in, beside its destination: tempfile makes the name, so it cannot already exist.
STAGING = ".pm-init-"
# Claude Desktop opens each entry of .claude/launch.json in its own preview pane; templates/root/launch.json holds
# that file's version and its entries.
# LikeC4's release, the pin in tools/setup/bom.toml: the map preview starts this exact version, so a person who
# follows it sees what this package was tested with. Move it together with the MCP server in templates/root/mcp-map.json.
LIKEC4_VERSION = "1.60.0"
# Claude Code's language setting takes a language name, not a code; an unknown code is written as it is.
LANG_NAMES = {
    "ar": "arabic", "az": "azerbaijani", "de": "german", "en": "english", "es": "spanish", "fa": "persian",
    "fr": "french", "it": "italian", "ja": "japanese", "ko": "korean", "nl": "dutch", "pl": "polish",
    "pt": "portuguese", "ru": "russian", "tr": "turkish", "uk": "ukrainian", "zh": "chinese",
}  # fmt: skip
# Only the line right under a "## Language" heading counts: a fenced example or a "Language: Python" line is not it.
LANG_LINE = re.compile(r"^## Language[ \t]*\n(?:[ \t]*\n)*Language: *(\S*)[ \t]*$", re.MULTILINE)
FENCE = re.compile(r"^(`{3,}|~{3,}).*?^\1[ \t]*$", re.MULTILINE | re.DOTALL)
LANG_SECTION = """
## Language

Language: {code}

Talk to the user in this language and write the prose of every record in it: tasks, decisions, the charter, worklogs,
the project's own docs, and commit subjects and bodies. Machine keys (`Next:`, `Needs owner:`, `Doc impact:`,
`<Name> said:`, `Refs:`), status names, Backlog's section headings, file names, commit types, worker briefs and reports
stay English. A change to this line affects only what is written next; older records are not translated.
"""
# Shipped skills sit next to the package; their names all start with pm-, a namespace apart from the user's own skills.
SKILLS = PKG.parent / ".agents" / "skills"
MAP_SKILLS = {"pm-likec4-dsl"}  # the map layer's skills: copied with --map, then upgraded like the others
SWARM = "swarm"  # the swarm layer's folder in .pm/: copied with --swarm, then upgraded like the others
UPGRADE_GUIDE = "https://github.com/Kscl1/project-manager/blob/main/docs/upgrading.md"
BOM_TIMEOUT_S = 180  # the program check after an upgrade; each program's own check has a shorter limit


def checkout_bom():
    """The release's program check, only when this package is the project-manager checkout's template/.pm.

    Every installed .pm carries a VERSION stamp and the checkout's has none, so an installed project used as the
    source, even one in a folder named template, never runs a script from the folder above it.
    """
    setup = PKG.parent.parent / "tools" / "setup"
    if PKG.parent.name != "template" or (PKG / "VERSION").exists() or not (setup / "bom.toml").is_file():
        return None
    return setup / "bom.py"


BOM_TOOL = Path(os.environ["PM_BOM_TOOL"]) if os.environ.get("PM_BOM_TOOL") else checkout_bom()  # tests: a fake
# Claude Code reads skills only from .claude/skills, so each skill gets a pointer there; the instructions stay in one copy.
POINTER = """---
{front}
---

Read `.agents/skills/{name}/SKILL.md` and follow it exactly, with the arguments given.
That file is the only copy of the instructions; this one only points Claude Code to it.
"""


QUIET = False  # a real install prints a few lines at the end; --check and --dry-run print every change


def quiet(on=True):
    """Keep the per-file lines to ourselves; a failure or a note still shows."""
    global QUIET
    QUIET = on


def say(action, path, note=""):
    """One line per change, unless the run is quiet and ends with a summary instead."""
    if QUIET and action not in ("failed", "note"):
        return
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


def installed_parts(target):
    """The (folder, part) pairs the manifest records where they are installed, skipping a part that is not there."""
    return [(folder, part) for _, folder, part in package_parts(target) if folder.exists()]


def manifest_lines(folders):
    """Each manifest line for these (folder, part) pairs: a file's hash and its path in the project."""
    return [
        f"{sha256(folder / rel)}  {(Path(part) / rel).as_posix()}"
        for folder, part in folders
        for rel in sorted(files_in(folder), key=str)
    ]


def manifest_text(folders):
    """The manifest write_manifest writes for these (folder, part) pairs, so a plan can tell whether it will change."""
    return "\n".join(manifest_lines(folders)) + "\n"


def write_manifest(target):
    path, lines = target / ".pm" / MANIFEST, manifest_lines(installed_parts(target))
    text = "\n".join(lines) + "\n"
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


def staging(dst):
    """A new, empty folder beside the old one, holding the copy while it is made. tempfile picks a name that cannot
    already exist, so a folder the project happens to have beside its package is never reused, cleared or replaced."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=STAGING, dir=dst.parent))


def free_entry(entry):
    """Where the old folder goes: the run's own backup name, or a numbered one when something already sits there.
    Only a path that does not exist is ever moved to, so nothing of the project's is replaced."""
    candidate, n = entry, 1
    while candidate.exists():
        n += 1
        candidate = entry.with_name(f"{entry.name}-{n}")
    return candidate


def clear(path):
    """Remove a half-made copy, so the next run can build it again."""
    if not path.exists():
        return
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def clear_quietly(path):
    """A leftover copy only costs disk space; a run that stopped has a bigger problem to report."""
    try:
        clear(path)
    except OSError:
        pass


def restore_command(entry, dst):
    """The exact command that puts a backed-up folder back, the same on Windows and elsewhere."""
    inner = f"import shutil; shutil.move(r'{entry}', r'{dst}')"
    return f'python -c "{inner}"'


class InstallStopped(Exception):
    """One plain line when a package folder could not be replaced: what is left, and the way back."""

    def __init__(self, dst, error, entry, moved):
        super().__init__(str(error.strerror or error))
        self.dst, self.error, self.entry, self.moved = dst, error, entry, moved

    def __str__(self):
        reason = self.error.strerror or self.error
        if self.moved:  # the old folder sits in the backup: name it, and the command that puts it back
            return (
                f"Upgrade stopped: the new {self.dst.name} could not be put in place ({reason}). Your old copy is in "
                f"{self.entry}; put it back with: {restore_command(self.entry, self.dst)}"
            )
        if self.dst.exists():
            return (
                f"Upgrade stopped: {self.dst} could not be copied ({reason}). The folder is as it was, and the backup "
                f"folder is {self.entry.parent}."
            )
        return f"Upgrade stopped: {self.dst} could not be copied ({reason}). Nothing of the project's was removed."


def copy_dir(src, dst, upgrade, backup, manifest, part):
    """Copy or replace one package folder: build the copy in a fresh folder of its own, back the old one up, then
    rename the copy into place. Only this run's staging folder is ever removed."""
    if dst.exists() and not upgrade:
        say("skip", dst, "exists; use --upgrade to refresh")
        return
    if dst.exists() and same_files(src, dst, part):
        say("keep", dst, "same as the package")  # no backup either: nothing would be lost
        return
    entry, moved, holder = backup / Path(part).parent / dst.name, False, None
    if dst.exists():
        report_changes(src, dst, part, manifest)
    try:
        holder = staging(dst)
        new = holder / dst.name
        shutil.copytree(src, new, ignore=SKIP)  # the project keeps its folder whole while this runs
        if dst.exists():
            entry = free_entry(entry)
            entry.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(dst), str(entry))  # the old copy, kept until the new one is in place
            moved = True
            say("backup", entry)
        shutil.move(str(new), str(dst))  # one rename on the same disk, so the folder is never away for long
    except OSError as error:
        if holder is not None:
            clear_quietly(holder)  # only the folder this run made
        raise InstallStopped(dst, error, entry, moved) from error
    clear_quietly(holder)  # the staging folder, empty now that the copy is in place
    say("upgrade" if upgrade else "copy", dst)


def pointer_text(skill):
    """The Claude Code pointer for one skill: its frontmatter, then where the instructions are."""
    lines = (skill / "SKILL.md").read_text(encoding="utf-8").splitlines()
    front = "\n".join(lines[1 : lines.index("---", 1)])
    return POINTER.format(front=front, name=skill.name)


def write_pointer(skill, target, upgrade):
    """Write the pointer, or keep one that already says this: an upgrade changes nothing when nothing moved."""
    text = pointer_text(skill)
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


def tool_layers(target):
    """The layers the project has, for the program check: core, then map and swarm when installed."""
    has_map = any((target / ".agents" / "skills" / name).is_dir() for name in MAP_SKILLS)
    return ["core", *(["map"] if has_map else []), *(["swarm"] if (target / ".pm" / SWARM).is_dir() else [])]


def tool_updates(target):
    """Print which programs differ from what this release was tested with, for the agent to raise with the user."""
    if BOM_TOOL is None or not BOM_TOOL.is_file():
        return
    print("\nPrograms on this machine against this release (nothing was installed):", flush=True)
    command = [sys.executable, str(BOM_TOOL), "--updates", "--layers", ",".join(tool_layers(target))]
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}  # a path with ı or ş must not crash a cp1252 console
    try:
        result = subprocess.run(
            command, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=BOM_TIMEOUT_S
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        result = subprocess.CompletedProcess(command, -1, "", str(error))
    print(result.stdout, end="")
    if result.returncode not in (0, 1) or "Traceback" in result.stderr:  # 1 only means a program is needed
        print(f"  The program check could not run ({(result.stderr.strip().splitlines() or ['no output'])[-1]}).")
        print("  The upgrade itself is done; run the check again later.")


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
EXIT_FAILED = 1
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
SECTION = re.compile(r"^## (.+?)[ \t]*$", re.MULTILINE)


def section_names(text):
    """The '## ' section names of a document, in order and outside fenced examples."""
    fences = [match.span() for match in FENCE.finditer(text)]
    return [match.group(1) for match in SECTION.finditer(text) if not any(a <= match.start() < b for a, b in fences)]


def missing_sections(target):
    """The package AGENTS.md sections the project's own file lacks; that file is never rewritten."""
    template, own = ROOT_TEMPLATES / "AGENTS.md", target / "AGENTS.md"
    if not template.is_file() or not own.is_file():
        return []
    have = set(section_names(own.read_text(encoding="utf-8", errors="replace")))
    return [name for name in section_names(template.read_text(encoding="utf-8")) if name not in have]


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


def root_launch(name):
    """One root launch template, parsed, with the LikeC4 pin filled in."""
    text = (ROOT_TEMPLATES / name).read_text(encoding="utf-8").replace("<version>", LIKEC4_VERSION)
    return json.loads(text)


def wanted_launch(map_layer):
    """Claude Desktop's preview file as the root templates hold it: the board, and the map with --map."""
    launch = root_launch("launch.json")
    if map_layer:
        launch["configurations"] += root_launch("launch-map.json")["configurations"]
    return launch


def launch_action(target, map_layer):
    """(write | keep | merge, the file to write or the configurations to add). An existing file is never rewritten."""
    path, want = target / ".claude" / "launch.json", wanted_launch(map_layer)
    if not path.exists():
        return "write", want
    data = read_json(path)
    have = data.get("configurations") if isinstance(data, dict) else None
    names = (
        {item["name"] for item in have if isinstance(item, dict) and "name" in item}
        if isinstance(have, list)
        else set()
    )
    missing = [config for config in want["configurations"] if config["name"] not in names]
    return ("merge", missing) if missing else ("keep", [])


def missing_lines(target, name, wanted):
    path = target / name
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    return [line for line in wanted if line not in lines]


def lang_code(value):
    code = value.strip().lower()
    if not re.fullmatch(r"[a-z]{2,3}(-[a-z0-9]{2,8})?", code):
        raise argparse.ArgumentTypeError(f"{value!r} is not a language code such as tr, en or pt-br")
    return code


def lang_name(code):
    return LANG_NAMES.get(code.split("-")[0], code)


def language_line(text):
    """The Language line under its heading, outside fenced examples, or None."""
    fences = [match.span() for match in FENCE.finditer(text)]
    return next((m for m in LANG_LINE.finditer(text) if not any(a <= m.start() < b for a, b in fences)), None)


def language_plan(target, code):
    """(path, note) for each file --lang changes, plus a merge line for a settings file pm_init does not rewrite."""
    changes, merge = [], []
    agents = target / "AGENTS.md"
    found = language_line(agents.read_text(encoding="utf-8")) if agents.exists() else None
    if not found or found.group(1) != code:
        changes.append((agents, f"Language: {code}"))
    settings, name = target / ".claude" / "settings.json", lang_name(code)
    data = read_json(settings) if settings.exists() else {}
    if isinstance(data, dict) and data.get("language") == name:
        pass
    elif isinstance(data, dict) and settings_action(target) != "merge":  # ours: written now or holding our hooks
        changes.append((settings, f'language: "{name}"'))
    else:  # the user's own file, or one pm_init cannot read: never rewritten
        merge.append(f'- .claude/settings.json: add "language": "{name}"')
    return changes, merge


def set_language(target, code):
    """Write the Language line and the Claude Code key; every other line and key stays as it is."""
    agents = target / "AGENTS.md"
    text = agents.read_text(encoding="utf-8") if agents.exists() else ""
    found = language_line(text)
    if found and found.group(1) == code:
        say("keep", agents, f"Language: {code}")
    else:
        if found:
            text = text[: found.start(1)] + code + text[found.end(1) :]
        else:
            text = (text.rstrip("\n") + "\n" if text else "") + LANG_SECTION.format(code=code)
        agents.write_text(text, encoding="utf-8", newline="\n")
        say("set", agents, f"Language: {code}")
    settings = target / ".claude" / "settings.json"
    data = read_json(settings) if settings.exists() else {}
    if not isinstance(data, dict) or settings_action(target) == "merge":
        say("skip", settings, "yours or unreadable; the language key is on the merge list")
    elif data.get("language") == lang_name(code):
        say("keep", settings, f'language: "{lang_name(code)}"')
    else:
        data["language"] = lang_name(code)
        settings.parent.mkdir(parents=True, exist_ok=True)
        settings.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        say("set", settings, f'language: "{lang_name(code)}"')


def merge_items(target, args, conflicts):
    """Everything the user merges by hand, as '- item: how' lines for .pm/local/merge-by-hand.md."""
    items = [(item, MERGE_HOW[item]) for item, _ in conflicts]
    if settings_action(target) == "merge":
        items.append((".claude/settings.json", SETTINGS_HOW))
    action, servers = mcp_action(target, args.map)
    if action == "merge":
        items += [(".mcp.json", f"add the {name} server: {json.dumps(config)}") for name, config in servers.items()]
    action, missing = launch_action(target, args.map)
    if action == "merge":
        items += [
            (".claude/launch.json", f"add the {config['name']} preview: {json.dumps(config)}") for config in missing
        ]
    lang_merge = language_plan(target, args.lang)[1] if args.lang else []
    return [f"- {item}: {how}" for item, how in items] + lang_merge


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


class Change(NamedTuple):
    """One line of the plan, with the real files it writes: the summary counts files, not plan lines."""

    action: str
    path: str  # relative to the project
    note: str
    files: int  # 0 for an empty folder and for a git setting, which are no file at all
    added: bool  # the files are new, not files the project already had


def file_count(action, path, files):
    """(how many real files this line writes, whether they are new): a copied or replaced folder hands in its own
    count, an empty folder and a git setting write none, and every other line writes the one file it names, unless
    the project already had it."""
    if files is None:
        files = 1 if isinstance(path, Path) and action != "create" else 0
    return files, not isinstance(path, Path) or not path.exists()


def plan(target, args, conflicts):
    """Every change the install makes, as Change(action, path, note, files, added), before anything is written. The
    file count is the one the summary prints, so a copied folder counts every file in it. main() makes exactly these
    changes; the tests check that no file is written outside this list."""
    entries, counts, after = [], {}, []
    for src, dst, part in package_parts(target, args.map, args.swarm):
        same = dst.exists() and (not args.upgrade or same_files(src, dst, part))
        after.append((dst if same else src, part))  # the copy the manifest reads once this run is done
        if same:
            continue
        if dst.exists():
            entries.append(("upgrade", dst, "old copy to .pm/local/backup/"))
            counts[dst] = sum(1 for _ in classify(src, dst, part, {}))  # the files a commit will show
        else:
            entries.append(("copy", dst, ""))
            counts[dst] = len(files_in(src))
    for skill in shipped_skills(target, args.map):
        pointer = target / ".claude" / "skills" / skill.name / "SKILL.md"
        if not pointer.exists() or (args.upgrade and pointer.read_text(encoding="utf-8") != pointer_text(skill)):
            entries.append(("write", pointer, "points Claude Code to the skill"))
    recorded = target / ".pm" / MANIFEST
    if not recorded.exists() or recorded.read_text(encoding="utf-8") != manifest_text(after):
        entries.append(("write", recorded, "what each package file looked like"))
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
    action, launch = launch_action(target, args.map)
    if action == "write":
        entries.append(
            ("write", target / ".claude" / "launch.json", ", ".join(c["name"] for c in launch["configurations"]))
        )
    if args.lang:
        entries += [("set", path, note) for path, note in language_plan(target, args.lang)[0]]
    if not version_is_current(target):
        entries.append(("write", target / ".pm" / "VERSION", "the package revision"))
    if new_merge_lines(target, merge_items(target, args, conflicts)):
        entries.append(("append", target / ".pm" / "local" / "merge-by-hand.md", "what /pm-setup merges with you"))
    if set_hooks_path(target):
        entries.append(("set", "git core.hooksPath", ".pm/hooks"))
    if is_repo(target) and not hook_conflicts(target) and hooks_to_stage(target):
        entries.append(("stage", "git index", "the .pm hooks as executable"))
    changes = []
    for action, path, note in entries:
        files, added = file_count(action, path, counts.get(path))
        changes.append(Change(action, shown(target, path), note, files, added))
    return changes


def shown(target, path):
    return path.relative_to(target).as_posix() if isinstance(path, Path) else path


# The user's own files the installer would write if they were missing, so a run that found them names them as kept.
YOURS = ["AGENTS.md", "CLAUDE.md", "backlog.config.yml", ".claude/settings.json", ".mcp.json", ".claude/launch.json"]


def counted(count, word):
    return f"{count} {word}{'' if count == 1 else 's'}"


def phrase(count, word):
    """'3 files', or nothing at all when the run has none of them."""
    return counted(count, word) if count else ""


def listed(parts):
    """A short list as a person says it: 'a', 'a and b', 'a, b and c'."""
    parts = [part for part in parts if part]
    return parts[0] if len(parts) == 1 else f"{', '.join(parts[:-1])} and {parts[-1]}"


def result_lines(target, entries, conflicts, merge):
    """The few lines a real install prints instead of the whole plan: what it added or changed, what it kept of the
    user's, and where the rest waits. --check still prints the plan itself. The counts are files, not plan lines: a
    copied folder counts every file in it, so the number is one a person can check on disk."""
    added = sum(change.files for change in entries if change.added)
    changed = sum(change.files for change in entries if not change.added)
    folders = sum(1 for change in entries if change.action == "create")
    settings = sum(1 for change in entries if not change.files and change.action in {"set", "stage"})
    lines = []
    if added or folders:
        lines.append(f"Added {listed([phrase(added, 'file'), phrase(folders, 'empty folder')])}.")
    if changed:
        lines.append(f"Changed {counted(changed, 'file')}.")
    if settings:
        lines.append(f"Set {counted(settings, 'git setting')}.")
    if not lines:
        lines.append("Nothing to change: the package and your files are as they are.")
    kept = [name for name in dict.fromkeys([item for item, _ in conflicts] + YOURS) if (target / name).exists()]
    if kept:
        lines.append(f"Kept {counted(len(kept), 'file')} of yours: {', '.join(kept)}.")
    if merge:
        lines.append(f"Merge by hand: {counted(len(merge), 'item')}, listed in .pm/local/merge-by-hand.md.")
    return lines


def language_only(target, args):
    """Set the project language from the project's own .pm/tools: the two places, nothing else."""
    changes, merge = language_plan(target, args.lang)
    print(f"Plan for {target} ({len(changes)} change(s)):")
    for path, note in changes:
        say("set", shown(target, path), note)
    for line in merge:
        print(f"  {line}")
    if args.check:
        return 0
    keep_merge_list(target, merge)
    if changes:
        set_language(target, args.lang)
    return 0


def main(argv=None):
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Install or upgrade the .pm/ package in a project.")
    parser.add_argument("target", help="the project to install into")
    parser.add_argument("--name", help="Backlog project name (default: the target folder name)")
    parser.add_argument("--upgrade", action="store_true", help="replace package files; project data is never touched")
    parser.add_argument("--dry-run", action="store_true", help="with --upgrade: list what would change, write nothing")
    parser.add_argument("--map", action="store_true", help="also add the LikeC4 MCP server and skill")
    parser.add_argument("--swarm", action="store_true", help="also add pm_run, which runs workers in Herdr")
    parser.add_argument("--lang", type=lang_code, help="the project language, e.g. tr: AGENTS.md line, Claude setting")
    parser.add_argument("--check", action="store_true", help="print the plan and the conflicts, write nothing")
    parser.add_argument(
        "--keep-existing", action="store_true", help="install even if the project has its own AGENTS.md, hooks..."
    )
    args = parser.parse_args(argv)

    target = Path(args.target).resolve()
    if not target.is_dir():
        sys.exit(f"{target} is not a directory")
    if (target / ".pm").resolve() == PKG:
        if not args.lang or any((args.name, args.upgrade, args.dry_run, args.map, args.swarm, args.keep_existing)):
            sys.exit("this is the package's own project; install into another folder (only --lang may run here)")
        return language_only(target, args)
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
        # The whole plan is for a run that writes nothing: --check, or a first install that stops on the project's own
        # files. A real install prints a few lines at the end instead, so the next step is not buried.
        if args.check or (stops and not args.keep_existing):
            print(f"Plan for {target} ({len(entries)} change(s)):")
            for change in entries:
                say(change.action, change.path, change.note)
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
    print(f"Project: {target}")  # the folder this run changes, first, so a long log says where it went
    print(f"{'Upgrading' if args.upgrade else 'Installing'} the package from {PKG}")

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
    summary = result_lines(target, entries, conflicts, merge)  # the same: what the run found, not what it left
    lacking = missing_sections(target) if args.upgrade else []
    if lacking:  # the file is the user's: name what it lacks, never rewrite a line of it
        summary.append(
            f"Your AGENTS.md lacks these package sections: {', '.join(lacking)}. "
            "Ask your agent to add them from .pm/templates/root/AGENTS.md."
        )
    backup = target / ".pm" / "local" / "backup" / time.strftime("%Y%m%d-%H%M%S")
    quiet(True)  # one line per file is what --check is for; the run ends with a few lines instead
    try:
        for src, dst, part in package_parts(target, args.map, args.swarm):
            copy_dir(src, dst, args.upgrade, backup, manifest, part)
    except InstallStopped as stopped:
        print(stopped)  # one plain line: what is left and the way back; the run stops here
        return EXIT_FAILED
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
    action, launch = launch_action(target, args.map)
    if action == "write":
        write_once(target / ".claude" / "launch.json", text=json.dumps(launch, indent=2) + "\n")
    if args.lang:
        set_language(target, args.lang)
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
            try:
                path.chmod(path.stat().st_mode | 0o111)
            except OSError:
                pass  # a filesystem without POSIX modes (an exFAT stick, a network share): git records the bit anyway
        names = hooks_to_stage(target)
        if names:
            run(["git", "add", "--chmod=+x", "--", *names], cwd=target)

    quiet(False)
    print()
    for line in summary:  # a few lines for the person reading the run, not the file-by-file list
        print(line)
    if not first:
        tool_updates(target)
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
