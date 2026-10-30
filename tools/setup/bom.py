"""Bill of materials checks for the setup TUI: load bom.toml, read the installed versions, compare (DESIGN.md).

Standard library only, so the tests and the plain-text output run without Textual. This file never installs
anything: it runs each command item's version check with a timeout and works out which steps are left (plan());
the TUI runs a step only after the user presses Enter on it.

usage: python tools/setup/bom.py [--layers core,map,swarm] [--project FOLDER] [--json]
       the check table and the To do list for this machine (and the project's files with --project);
       exit 0 when nothing is left, 1 when steps or notes are left
       python tools/setup/bom.py --updates [--layers ...] [--json]
       only the programs to raise with the user after a release (pm_init --upgrade prints it); exit 1 when one
       is needed
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

import tomllib

BOM = Path(__file__).with_name("bom.toml")
KINDS = ("command", "project-file", "manual")
LAYERS = ("core", "map", "swarm", "evren")
DEFAULT_LAYERS = ("core", "map")  # swarm and evren are opted into: they need accounts of the user's own
# What a layer still needs after every step is done, said on Done and in the plain output: nothing checks it.
AFTER = {
    "evren": (
        "Put your own EVREN API key where the Quick start of the evren-bridge README says (setup never asks for it "
        "or reads it), then in a terminal cd ~/evren-bridge, run python evren_bridge.py and leave it running, and "
        "point your agent at http://127.0.0.1:8787/v1 (the same README shows how)."
    ),
    "swarm": (
        "Before the first pm_run job: start herdr once in a terminal and leave it running, "
        "and sign in to a model in Pi (run pi, then /login; with a ChatGPT plan, choose OpenAI, then Sign in with ChatGPT). "
        "Pi may then pick a model a ChatGPT plan cannot use: type /model, choose openai/gpt-6.1-sol and press Ctrl+S "
        "to keep it for new sessions."
    ),
}
SYSTEMS = ("windows", "linux", "macos", "all")  # the keys of install.<os> and upgrade.<os>
TIMEOUT_S = 15
COLUMNS = ("Item", "Installed", "Minimum", "Tested", "Status", "Path")

# The first word that starts like a version, with whatever is glued to it ("3.15.0rc1", "2.54.0.windows.1").
VERSION_WORD = re.compile(r"(?<![\w.])v?(\d+\.\d+[^\s,;()]*)")
COMPARABLE = re.compile(r"\d+\.\d+(?:\.\d+)?")  # 3.11 or 3.11.9; anything else cannot be compared
GIT_WINDOWS = re.compile(r"\.windows\.\d+$")  # git version 2.54.0.windows.1, a known suffix

MISSING = "missing"
FAILED = "check failed"
UNREADABLE = "version unreadable"
CANNOT_COMPARE = "cannot compare"
NOT_CHECKED = "not checked"
BELOW = "below minimum"
OK = "ok"
UNTESTED = "not tested yet"
IN_PROJECT = "in project"
NOT_IN_PROJECT = "not in project"
MERGE = "merge by hand"  # the file is the user's own and lacks our part; the installer never edits it

# How much each status asks of the user: good (nothing), warn (works, worth a look), bad (act), skip (not checked).
LEVEL = {
    OK: "good",
    IN_PROJECT: "good",
    UNTESTED: "warn",
    CANNOT_COMPARE: "warn",
    UNREADABLE: "warn",
    MERGE: "warn",
    BELOW: "bad",
    FAILED: "bad",
    MISSING: "bad",
    NOT_IN_PROJECT: "bad",
    NOT_CHECKED: "skip",
}
PM_INIT = Path(__file__).resolve().parents[2] / "template" / ".pm" / "tools" / "pm_init.py"
RECORD = Path(".pm") / "local" / "setup.json"  # in the project: what setup did there, for a rerun and for /pm-setup


def load(path=BOM):
    """The [[item]] tables of bom.toml, in file order. Raises ValueError with a plain message on a bad entry."""
    with open(path, "rb") as f:
        items = tomllib.load(f).get("item", [])
    seen = set()
    for item in items:
        where = f"bom.toml item {item.get('id') or item.get('name') or '?'}"
        if not item.get("id") or not item.get("name"):
            raise ValueError(f"{where}: needs an id and a name")
        if item["id"] in seen:
            raise ValueError(f"{where}: duplicate id")
        seen.add(item["id"])
        if item.get("kind") not in KINDS:
            raise ValueError(f"{where}: kind must be one of {', '.join(KINDS)}")
        if item.get("layer") not in LAYERS:
            raise ValueError(f"{where}: layer must be one of {', '.join(LAYERS)}")
        for key in ("min", "tested"):
            if item.get(key) and not COMPARABLE.fullmatch(item[key]):
                raise ValueError(f"{where}: {key} must look like 3.11 or 3.11.9, or be left out")
        if item.get("min") and item.get("tested") and compare(item["min"], item["tested"]) > 0:
            raise ValueError(f"{where}: min is above tested")
        if item["kind"] == "command":
            check = item.get("check")
            if not isinstance(check, list) or not check or not all(isinstance(arg, str) for arg in check):
                raise ValueError(f"{where}: a command item needs check, a list of strings")
            if check[0] == "npx":
                raise ValueError(f"{where}: npx may download; the scan must stay read-only")
            if not item.get("min") or not item.get("tested"):
                raise ValueError(f"{where}: a command item needs min and tested")
        for key in ("install", "upgrade"):
            lines = item.get(key, {})
            if (
                not isinstance(lines, dict)
                or set(lines) - set(SYSTEMS)
                or not all(isinstance(line, str) and line.strip() for line in lines.values())
            ):
                raise ValueError(f'{where}: {key} takes {key}.<os> = "command" with <os> one of {", ".join(SYSTEMS)}')
        if "package" in item and (item["kind"] != "command" or not isinstance(item["package"], str)):
            raise ValueError(f"{where}: package is the name a command item's check lists, such as npm:pi-web-access")
        if "folder" in item and (item["kind"] != "command" or not isinstance(item["folder"], str)):
            raise ValueError(f"{where}: folder is where a command item's check runs, such as ~/evren-bridge")
        if item["kind"] == "project-file" and not item.get("path"):
            raise ValueError(f"{where}: a project-file item needs a path")
        if not all(isinstance(name, str) for name in item.get("similar", [])):
            raise ValueError(f"{where}: similar takes a list of names")
    return items


def parse_version(text):
    """The version in a command's output: 'v24.14.0' -> '24.14.0', 'git version 2.54.0.windows.1' -> '2.54.0'.

    Anything glued to the number stays ('3.15.0rc1'), so status() reports it as cannot compare. None if no version.
    """
    match = VERSION_WORD.search(text or "")
    return GIT_WINDOWS.sub("", match.group(1).rstrip(".")) if match else None


def compare(a, b):
    """-1, 0 or 1, number by number; missing parts count as 0, so 3.11 equals 3.11.0."""
    x = [int(p) for p in a.split(".")]
    y = [int(p) for p in b.split(".")]
    size = max(len(x), len(y))
    x += [0] * (size - len(x))
    y += [0] * (size - len(y))
    return (x > y) - (x < y)


def status(path, ran_ok, version, minimum, tested):
    if path is None:
        return MISSING
    if not ran_ok:
        return FAILED
    if version is None:
        return UNREADABLE
    if not COMPARABLE.fullmatch(version):
        return CANNOT_COMPARE
    if compare(version, minimum) < 0:
        return BELOW
    if compare(version, tested) > 0:
        return UNTESTED
    return OK


def probe(check, timeout=TIMEOUT_S, package=None, folder=None):
    """(path, ran_ok, version) for a check command such as ["git", "--version"].

    path is the resolved executable, None if not found; "python" is the interpreter running this tool.
    A non-zero exit or a timeout gives ran_ok False and no version, even if the output shows one.
    With package (bom.toml `package`), the check lists packages (`pi list`): see listed_version().
    With folder (bom.toml `folder`, ~ is the home folder), the check runs inside it and path is the folder;
    no folder means missing, so the check never runs somewhere else.
    """
    where = Path(folder).expanduser() if folder is not None else None
    if where is not None and not where.is_dir():
        return None, False, None
    path = sys.executable if check[0] == "python" else shutil.which(check[0])  # which() finds .cmd shims too
    if path is None:
        return None, False, None
    shown = str(where) if where is not None else path
    try:
        done = subprocess.run(
            [path, *check[1:]],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            cwd=where,
        )
    except (OSError, ValueError, subprocess.SubprocessError):
        return shown, False, None
    if done.returncode != 0:
        return shown, False, None
    if package is not None:
        return listed_version(done.stdout, package)
    return shown, True, parse_version(done.stdout + done.stderr)


def listed_version(output, package):
    """(path, ran_ok, version) for one package in `pi list` output, which names each one with the folder under it:

        npm:pi-web-access@0.35.0
          ~/.pi/agent/npm/node_modules/pi-web-access

    The name line is only what the settings ask for, so the version is read from the folder's package.json. Not listed
    means missing; listed without a readable package.json gives no version, so it is never counted as ready. Pi marks
    a package whose settings pick only some of its resources "(filtered)": what it loads is unknown here, so it gets no
    version either. With --no-approve Pi lists only the user's own packages, never a project's.
    """
    lines = [line.rstrip() for line in output.splitlines()]
    names = [line.strip().removesuffix(" (filtered)") for line in lines]
    named = (i for i, name in enumerate(names) if name == package or name.startswith(package + "@"))
    at = next(named, None)
    if at is None:
        return None, False, None
    under = lines[at + 1] if at + 1 < len(lines) else ""
    folder = under.strip() if under.startswith("    ") else ""  # Pi prints the folder only for an installed package
    if not folder or lines[at].endswith(" (filtered)"):  # never read a package.json from the current folder
        return folder or "-", True, None
    try:
        version = json.loads((Path(folder) / "package.json").read_text(encoding="utf-8"))["version"]
    except (OSError, ValueError, KeyError, TypeError):
        return folder or "-", True, None
    return folder, True, parse_version(str(version))


def project_status(item, project):
    """in project, not in project, or merge by hand: the file is there but lacks the item's `has` text."""
    path = Path(project) / item["path"]
    if not path.exists():
        return NOT_IN_PROJECT
    if item.get("has") and item["has"] not in path.read_text(encoding="utf-8", errors="replace"):
        return MERGE
    return IN_PROJECT


def check_one(item, run=probe, project=None):
    """The row for one item: name, installed, minimum, tested, status, path. Only command items are run;
    project files are looked at only when a project folder is given."""
    minimum, tested = item.get("min") or "-", item.get("tested") or "-"
    if item["kind"] == "project-file" and project is not None:
        return item["name"], "-", minimum, tested, project_status(item, project), str(Path(project) / item["path"])
    if item["kind"] != "command":
        return item["name"], "-", minimum, tested, NOT_CHECKED, item.get("path", "-")
    extra = {key: item[key] for key in ("package", "folder") if item.get(key)}  # fake probes in tests take neither
    path, ran_ok, version = run(item["check"], **extra)
    result = status(path, ran_ok, version, item["min"], item["tested"])
    return item["name"], version or "-", minimum, tested, result, path or "-"


def check_all(items, run=probe, project=None):
    """One row per item, in bom.toml order (check_one)."""
    return [check_one(item, run, project) for item in items]


def chosen(items, rows, layers):
    """The rows of the ticked layers: an optional layer nobody chose must not make the table look broken."""
    return [row for item, row in zip(items, rows) if item["layer"] in layers]


def this_os():
    """The key of install.<os> and upgrade.<os> in bom.toml for the machine we run on."""
    return {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")


def plan(items, rows, layers=DEFAULT_LAYERS, system=None, project=None):
    """(steps, notes) for the ticked layers on this OS, from the check rows (DESIGN.md, Steps).

    A step is a dict: id, name, why (the status), command (the text to run), needs (the program that runs it),
    shell (the argument list that runs it) and check (the command that verifies it afterwards). Only a missing or
    below-minimum command item becomes a step. One without a command for this OS, or one that is installed but
    could not be verified (check failed, version unreadable or cannot compare), is a note: never ready.
    Project files not in the project become one last step, the installer (init_step). So does a file of the user's
    that lacks our part, until the installer has handed it to /pm-setup in its merge list (handed_over): from then
    on it is /pm-setup's work, not a step and not a note.
    """
    system = system or this_os()
    steps, notes, absent = [], [], []
    merge_lines = merge_list(project) if project is not None else []
    for item, row in zip(items, rows):
        result = row[4]
        if item["layer"] not in layers or result in (OK, UNTESTED, NOT_CHECKED, IN_PROJECT):
            continue
        if result == NOT_IN_PROJECT or (result == MERGE and not handed_over(item, merge_lines)):
            absent.append(item["id"])
            continue
        if result == MERGE:
            continue
        if result in (FAILED, UNREADABLE, CANNOT_COMPARE):
            notes.append(
                f"{item['name']}: installed, but it could not be verified ({result}); run "
                f"{' '.join(item['check'])}{' in ' + item['folder'] if item.get('folder') else ''} "
                "and read its output before reinstalling."
            )
            continue
        install, upgrade = item.get("install", {}), item.get("upgrade", {})
        if result == BELOW and upgrade.get(system):
            command = upgrade[system]
        else:
            command = install.get(system) or install.get("all")
        if not command:
            notes.append(
                f"{item['name']} ({result}): no install command for {system}; {item.get('note', 'install it by hand.')}"
            )
            continue
        steps.append(
            {
                "id": item["id"],
                "name": item["name"],
                "why": result,
                "command": command,
                "needs": needs(command, system),
                "shell": shell_args(command, system),
                "check": item["check"],
                "note": item.get("note", ""),
            }
        )
    if absent and project is not None:
        steps.append(init_step(project, layers, absent))
    return steps, notes


def init_step(project, layers, ids):
    """The step that runs pm_init into the project. --keep-existing because the user reads its plan first (preview):
    the project's own AGENTS.md, hooks or settings are kept and listed for /pm-setup, never overwritten."""
    flags = ["--keep-existing", *[f"--{layer}" for layer in ("map", "swarm") if layer in layers]]
    args = [sys.executable, str(PM_INIT), str(project), *flags]
    return {
        "id": "pm-init",
        "ids": ids,  # the project items it sets up, checked again afterwards
        "name": ".pm and project files",
        "why": f"{len(ids)} not in project",
        "command": " ".join(f'"{a}"' if " " in a else a for a in ["python", str(PM_INIT), str(project), *flags]),
        "needs": sys.executable,
        "shell": args,
        "preview": [*args[:3], "--check", *flags[1:]],  # read-only: prints every write and what is kept
        "check": None,
    }


def updates(items, rows, layers=DEFAULT_LAYERS, system=None):
    """The programs of the ticked layers to raise with the user after a release: needed, optional or newer.

    Needed: missing or below the minimum. Optional: older than this release's tested version, only when the install
    line pins that version (Backlog.md, Pi, its extensions); Python, Git or Node.js follow their vendor and are left
    out. Newer: above the tested version of a pinned item; the pinned line goes back to the tested one.
    """
    system = system or this_os()
    found = []
    for item, row in zip(items, rows):
        if item["kind"] != "command" or item["layer"] not in layers:
            continue
        installed, minimum, tested, result = row[1], row[2], row[3], row[4]
        install, upgrade = item.get("install", {}), item.get("upgrade", {})
        command = install.get(system) or install.get("all") or ""
        pinned = re.search(rf"(?<![\d.]){re.escape(tested)}(?![\d.]*\d)", command) is not None  # not 1.2 in 1.25
        if result in (MISSING, BELOW):
            need = "needed"
            command = upgrade.get(system, command) if result == BELOW else command
        elif result == OK and pinned and compare(installed, tested) < 0:
            need = "optional"
        elif result == UNTESTED and pinned:
            need = "newer"
        else:
            continue
        found.append(
            {
                "id": item["id"],
                "name": item["name"],
                "installed": installed,
                "minimum": minimum,
                "tested": tested,
                "need": need,
                "command": command,
                "note": item.get("note", ""),
            }
        )
    return found


def update_lines(found):
    """Plain lines for an agent to explain to the user, one program each, then what to do with them."""
    if not found:
        return ["Every program this project uses matches what this release was tested with."]
    why = {
        "needed": "needed, below the minimum this release supports",
        "optional": "optional, works but is older than this release was tested with",
        "newer": "newer than this release was tested with; keep it, this is information only",
    }
    lines = []
    for number, update in enumerate(found, 1):
        version = "not installed" if update["installed"] == "-" else update["installed"]
        lines.append(f"{number}. {update['name']} {version} (tested {update['tested']}): {why[update['need']]}")
        if update["need"] == "newer":
            lines.append(f"   only if something breaks, the tested version: {update['command']}")
        elif update["command"]:
            lines.append(f"   {update['command']}")
        else:
            lines.append(f"   {update.get('note') or 'no install command for this system; install it by hand'}")
    lines.append(
        "For the agent: tell the user what each line means for them in one sentence; a program such as Backlog.md "
        "or Pi is installed once for the whole machine, so an update also reaches their other projects. Run a "
        "command only after they say yes, one program at a time, then check again. A newer program is only reported."
    )
    return lines


def merge_list(project):
    """The '- item: how' lines pm_init left in the project for /pm-setup."""
    try:
        text = (Path(project) / ".pm" / "local" / "merge-by-hand.md").read_text(encoding="utf-8")
    except OSError:
        return []
    return [line for line in text.splitlines() if line.startswith("- ")]


def handed_over(item, merge_lines):
    """True when the installer's merge list already names this item's file (and its `has` text, if any)."""
    word = item.get("has", "").strip('"')
    return any(line.startswith(f"- {item['path']}:") and word in line for line in merge_lines)


def merge_names(merge_lines):
    """'AGENTS.md, .mcp.json' from the merge list, for one plain line."""
    return ", ".join(dict.fromkeys(line[2:].split(":", 1)[0] for line in merge_lines))


def project_outcome(code, rows, merge_lines=()):
    """Like outcome(), for the installer step, from its exit code, the re-checked project rows and its merge list."""
    if code not in (0, None):
        return "failed", f"the installer failed (exit code {code}). Read its output; y tries again, s skips it."
    absent = [row[0] for row in rows if row[4] == NOT_IN_PROJECT]
    if absent:
        return "unverified", f"still not in the project: {', '.join(absent)}."
    if merge_lines:
        return "merge", (
            f"done. Yours, kept as they are, for /pm-setup to merge with you: {merge_names(merge_lines)} "
            "(listed in .pm/local/merge-by-hand.md)."
        )
    return "done", "done, the project files are in place."


def user_scan(home=None):
    """Names of the skills, MCP servers and plugins the user already has, for the similar-items note (DESIGN.md).

    Only names are read: never a server's command, headers or keys. Missing or unreadable files give empty lists.
    """
    home = Path(home or Path.home())
    skills = sorted(
        {p.parent.name for folder in (".claude/skills", ".agents/skills") for p in (home / folder).glob("*/SKILL.md")}
    )

    def keys(path, *where):
        try:
            data = json.loads((home / path).read_text(encoding="utf-8"))
            for key in where:
                data = data.get(key) or {}
            return sorted(data) if isinstance(data, dict) else []
        except (OSError, ValueError, AttributeError):
            return []

    return {
        "skills": skills,
        "mcp": keys(".claude.json", "mcpServers"),
        "plugins": [name.split("@")[0] for name in keys(".claude/plugins/installed_plugins.json", "plugins")],
    }


def similar(items, scan, layers=DEFAULT_LAYERS):
    """One sentence per package item the user already has something like (bom.toml `similar`)."""
    lines = []
    for item in items:
        if item["layer"] not in layers or not item.get("similar"):
            continue
        found = [
            f"{kind} {name}"
            for kind, names in (("skill", scan["skills"]), ("MCP server", scan["mcp"]), ("plugin", scan["plugins"]))
            for name in names
            if any(name == alias or name.startswith(alias + "-") for alias in item["similar"])
        ]
        if found:
            lines.append(
                f"{item['name']}: you already have {', '.join(found)}. Both stay; /pm-setup asks which to use."
            )
    return lines


def read_record(project):
    try:
        return json.loads((Path(project) / RECORD).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def write_record(project, layers, similar_lines, today):
    """Keep what setup did in the project (git-ignored), once .pm/ is there: the rerun and /pm-setup read it."""
    if not (Path(project) / ".pm").is_dir():
        return False
    record = {
        "source": str(PM_INIT.parents[3]),
        "layers": list(layers),
        "bom": bom_hash(),
        "date": today,
        "similar": similar_lines,
    }
    path = Path(project) / RECORD
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")
    return True


def bom_hash(path=BOM):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:12]


def needs(command, system=None):
    """The program a bom.toml command line starts: 'winget', 'npm', 'pacman' (after sudo), or the shell itself for a
    PowerShell cmdlet line such as 'irm ... | iex'. The TUI checks it is there before running the step."""
    words = command.split()
    word = words[1] if words[0] == "sudo" and len(words) > 1 else words[0]
    if "-" in word or word in ("irm", "iex"):  # a PowerShell cmdlet or alias: PowerShell runs it
        return shell_args(command, system)[0]
    return word


def shell_args(command, system=None):
    """The argument list that runs one bom.toml command line through the platform shell (DESIGN.md)."""
    if (system or this_os()) == "windows":
        return ["powershell", "-NoProfile", "-Command", command]
    return ["bash", "-c", command]


def refresh_path():
    """On Windows, reload PATH from the registry so a program an installer just added is found without a new window.

    Keeps this process's own entries (the virtual environment) in front. Does nothing elsewhere or on any error.
    """
    if sys.platform != "win32":
        return
    try:
        import winreg

        parts = []
        for root, key in (
            (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
            (winreg.HKEY_CURRENT_USER, "Environment"),
        ):
            with winreg.OpenKey(root, key) as handle:
                parts.append(os.path.expandvars(winreg.QueryValueEx(handle, "Path")[0]))
    except OSError:
        return
    seen, merged = set(), []
    for entry in os.environ.get("PATH", "").split(os.pathsep) + os.pathsep.join(parts).split(os.pathsep):
        if entry and entry.lower() not in seen:
            seen.add(entry.lower())
            merged.append(entry)
    os.environ["PATH"] = os.pathsep.join(merged)


def outcome(code, row):
    """What a step's result means for the user, from its exit code and the item's re-check (DESIGN.md table).

    code is None when the user only asked to check again (after running the command elsewhere). Returns
    (state, message); state is done, not-found, too-old, unverified or failed. Only done means verified.
    """
    name, version, minimum, result = row[0], row[1], row[2], row[4]
    if code not in (0, None):
        return "failed", f"the command failed (exit code {code}). y tries again, c copies it, s skips it."
    lead = "the command finished, but" if code == 0 else "checked again:"
    if result in (OK, UNTESTED):
        return "done", f"done, {name} {version} is installed."
    if result == MISSING:
        return "not-found", (
            f"{lead} {name} is not found yet. Open a new terminal and run setup again; "
            "if it is still missing there, the command did not install it."
        )
    if result == BELOW:
        return "too-old", f"{lead} {name} is still {version}, below {minimum}."
    return "unverified", f"{lead} {name}'s version could not be verified ({result})."


def summary(rows):
    """'5 items: 3 ok, 2 missing'."""
    counts = Counter(row[4] for row in rows)
    return f"{len(rows)} items: " + ", ".join(f"{n} {name}" for name, n in counts.items())


def worst(rows):
    """The level that asks most of the user: bad, then warn, then good; skip when nothing was checked."""
    levels = {LEVEL[row[4]] for row in rows}
    return next((level for level in ("bad", "warn", "good") if level in levels), "skip")


def next_step(rows):
    """One plain sentence on what to do now, from the worst status in the table."""
    named = {level: [f"{row[0]} ({row[4]})" for row in rows if LEVEL[row[4]] == level] for level in set(LEVEL.values())}
    programs = [name for name in named["bad"] if not name.endswith(f"({NOT_IN_PROJECT})")]
    if programs:
        return f"Next: install or update {', '.join(programs)}, then check again."
    if named["bad"]:
        return f"Next: set up the project files ({len(named['bad'])} not in your project yet)."
    if named["warn"]:
        return f"All programs are installed. Worth a look: {', '.join(named['warn'])}."
    if named["good"]:
        return "All programs are ready."
    return "Nothing to check on this machine yet."


def later_note(rows):
    """The sentence about the items this check leaves for later, or an empty string."""
    count = sum(1 for row in rows if row[4] == NOT_CHECKED)
    if not count:
        return ""
    if count == 1:
        return f'The item marked "{NOT_CHECKED}" belongs to your project and is set up later.'
    return f'The {count} items marked "{NOT_CHECKED}" belong to your project and are set up later.'


def main(argv=None, run=probe):
    """Plain text for a person or an agent; --json for a program.

    Exit 0: every program the layers need is ready; 1: steps or notes are left; 2: a bad bom.toml or argument.
    """
    parser = argparse.ArgumentParser(description="Check this machine against bom.toml and list what is left to do.")
    parser.add_argument(
        "--layers",
        default=",".join(DEFAULT_LAYERS),
        help=f"comma-separated, of {', '.join(LAYERS)} (default: %(default)s)",
    )
    parser.add_argument("--json", action="store_true", help="print one JSON object instead of text")
    parser.add_argument("--project", help="the project folder: also check its project files")
    parser.add_argument(
        "--updates", action="store_true", help="only the programs to raise with the user after a release (updates())"
    )
    args = parser.parse_args(argv)
    layers = tuple(layer.strip() for layer in args.layers.split(",") if layer.strip())
    try:
        if not layers or set(layers) - set(LAYERS):
            raise ValueError(f"--layers takes {', '.join(LAYERS)}")
        if args.project and not Path(args.project).is_dir():
            raise ValueError(f"--project: {args.project} is not a folder")
        items = load()
    except (ValueError, OSError) as error:  # a bad entry, or bom.toml missing or unreadable
        print(error, file=sys.stderr)
        return 2
    project = Path(args.project).resolve() if args.project else None
    if args.updates:  # only the ticked layers' programs are run, so the list after an upgrade comes quickly
        items = [item for item in items if item["layer"] in layers and item["kind"] == "command"]
        found = updates(items, check_all(items, run), layers)
        if args.json:
            print(json.dumps({"os": this_os(), "layers": layers, "updates": found}, indent=1))
        else:
            print("\n".join(update_lines(found)))
            if found:
                print(f"Check again: python {Path(__file__).resolve()} --updates --layers {','.join(layers)}")
        return 1 if any(update["need"] == "needed" for update in found) else 0
    rows = check_all(items, run, project)
    steps, notes = plan(items, rows, layers, project=project)
    after = [AFTER[layer] for layer in layers if layer in AFTER]
    alike = similar(items, user_scan(), layers)  # information only: never a reason to stop
    if args.json:
        keys = ("name", "installed", "minimum", "tested", "status", "path")
        table = [{"id": item["id"], "layer": item["layer"], **dict(zip(keys, row))} for item, row in zip(items, rows)]
        found = {"os": this_os(), "layers": layers, "items": table, "steps": steps, "notes": notes, "similar": alike}
        found["merge"] = merge_list(project) if project is not None else []  # for /pm-setup, never a reason to stop
        found["after"] = after
        print(json.dumps(found, indent=1))
        return 1 if steps or notes else 0
    rows = chosen(items, rows, layers)
    widths = [max(len(str(r[i])) for r in [COLUMNS, *rows]) for i in range(len(COLUMNS))]
    for row in [COLUMNS, *rows]:
        print("  ".join(str(cell).ljust(w) for cell, w in zip(row, widths)).rstrip())
    print(summary(rows))
    print(next_step(rows))
    if later_note(rows):
        print(later_note(rows))
    print()
    if steps:
        print(f"To do on {this_os()} ({', '.join(layers)}), one command at a time, then run this again:")
        for number, step in enumerate(steps, 1):
            print(f"{number}. {step['name']} ({step['why']}): {step['command']}")
            if step.get("note"):
                print(f"   {step['note']}")
    elif notes:
        print(f"To do on {this_os()} ({', '.join(layers)}): nothing can run automatically; see the notes.")
    else:
        print(f"To do on {this_os()} ({', '.join(layers)}): nothing, every program these layers need is ready.")
    for note in notes:
        print(f"Note: {note}")
    for line in alike:
        print(f"Already on this machine: {line}")
    if project is not None and merge_list(project):
        print(f"For /pm-setup to merge with the user: {merge_names(merge_list(project))}.")
    for line in after:
        print(f"Then: {line}")
    if steps:
        print("Show the user each command and run it only after they say yes; then run this again until it exits 0.")
    return 1 if steps or notes else 0


if __name__ == "__main__":
    sys.exit(main())
