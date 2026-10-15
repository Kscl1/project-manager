"""Bill of materials checks for the setup TUI: load bom.toml, read the installed versions, compare (DESIGN.md).

Standard library only, so the tests and the plain-text output run without Textual. This file never installs
anything: it runs each command item's version check with a timeout and works out which steps are left (plan());
the TUI runs a step only after the user presses Enter on it.

usage: python tools/setup/bom.py [--layers core,map] [--json]
       the check table and the To do list for this machine; exit 0 when nothing is left, 1 when steps are left
"""

import argparse
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
LAYERS = ("core", "map")
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

# How much each status asks of the user: good (nothing), warn (works, worth a look), bad (act), skip (not checked).
LEVEL = {
    OK: "good",
    UNTESTED: "warn",
    CANNOT_COMPARE: "warn",
    UNREADABLE: "warn",
    BELOW: "bad",
    FAILED: "bad",
    MISSING: "bad",
    NOT_CHECKED: "skip",
}


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
            if not check or not all(isinstance(arg, str) for arg in check):
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
        if item["kind"] == "project-file" and not item.get("path"):
            raise ValueError(f"{where}: a project-file item needs a path")
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


def probe(check, timeout=TIMEOUT_S):
    """(path, ran_ok, version) for a check command such as ["git", "--version"].

    path is the resolved executable, None if not found; "python" is the interpreter running this tool.
    A non-zero exit or a timeout gives ran_ok False and no version, even if the output shows one.
    """
    path = sys.executable if check[0] == "python" else shutil.which(check[0])  # which() finds .cmd shims too
    if path is None:
        return None, False, None
    try:
        done = subprocess.run(
            [path, *check[1:]], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout
        )
    except (OSError, ValueError, subprocess.SubprocessError):
        return path, False, None
    if done.returncode != 0:
        return path, False, None
    return path, True, parse_version(done.stdout + done.stderr)


def check_one(item, run=probe):
    """The row for one item: name, installed, minimum, tested, status, path. Only command items are run."""
    minimum, tested = item.get("min") or "-", item.get("tested") or "-"
    if item["kind"] != "command":
        return item["name"], "-", minimum, tested, NOT_CHECKED, item.get("path", "-")
    path, ran_ok, version = run(item["check"])
    result = status(path, ran_ok, version, item["min"], item["tested"])
    return item["name"], version or "-", minimum, tested, result, path or "-"


def check_all(items, run=probe):
    """One row per item, in bom.toml order (check_one)."""
    return [check_one(item, run) for item in items]


def this_os():
    """The key of install.<os> and upgrade.<os> in bom.toml for the machine we run on."""
    return {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")


def plan(items, rows, layers=LAYERS, system=None):
    """(steps, notes) for the ticked layers on this OS, from the check rows (DESIGN.md, Steps).

    A step is a dict: id, name, why (the status), command (the text to run), needs (the program that runs it),
    shell (the argument list that runs it) and check (the command that verifies it afterwards). Only a missing or
    below-minimum command item becomes a step. One without a command for this OS, or whose check failed, is a note.
    """
    system = system or this_os()
    steps, notes = [], []
    for item, row in zip(items, rows):
        result = row[4]
        if item["layer"] not in layers or result not in (MISSING, BELOW, FAILED):
            continue
        if result == FAILED:
            notes.append(
                f"{item['name']}: installed but its version check failed; run {' '.join(item['check'])} "
                "and read the error before reinstalling."
            )
            continue
        install, upgrade = item.get("install", {}), item.get("upgrade", {})
        command = (result == BELOW and upgrade.get(system)) or install.get(system) or install.get("all")
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
            }
        )
    return steps, notes


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
    if named["bad"]:
        return f"Next: install or update {', '.join(named['bad'])}, then check again."
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
    parser.add_argument("--layers", default=",".join(LAYERS), help="comma-separated layers (default: %(default)s)")
    parser.add_argument("--json", action="store_true", help="print one JSON object instead of text")
    args = parser.parse_args(argv)
    layers = tuple(layer.strip() for layer in args.layers.split(",") if layer.strip())
    try:
        if not layers or set(layers) - set(LAYERS):
            raise ValueError(f"--layers takes {', '.join(LAYERS)}")
        items = load()
    except ValueError as error:
        print(error, file=sys.stderr)
        return 2
    rows = check_all(items, run)
    steps, notes = plan(items, rows, layers)
    if args.json:
        keys = ("name", "installed", "minimum", "tested", "status", "path")
        table = [{"id": item["id"], "layer": item["layer"], **dict(zip(keys, row))} for item, row in zip(items, rows)]
        print(json.dumps({"os": this_os(), "layers": layers, "items": table, "steps": steps, "notes": notes}, indent=1))
        return 1 if steps or notes else 0
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
    elif notes:
        print(f"To do on {this_os()} ({', '.join(layers)}): nothing can run automatically; see the notes.")
    else:
        print(f"To do on {this_os()} ({', '.join(layers)}): nothing, every program these layers need is ready.")
    for note in notes:
        print(f"Note: {note}")
    if steps:
        print("Show the user each command and run it only after they say yes; then run this again until it exits 0.")
    return 1 if steps or notes else 0


if __name__ == "__main__":
    sys.exit(main())
