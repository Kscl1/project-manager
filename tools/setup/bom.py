"""Bill of materials checks for the setup TUI: load bom.toml, read the installed versions, compare (DESIGN.md).

Standard library only, so the tests and the plain-text table run without Textual. Read-only: it runs each
command item's version check with a timeout and never installs or downloads anything.

usage: python tools/setup/bom.py    print the check table as plain text
"""

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


def check_all(items, run=probe):
    """One row per item: name, installed, minimum, tested, status, path. Only command items are run."""
    rows = []
    for item in items:
        minimum, tested = item.get("min") or "-", item.get("tested") or "-"
        if item["kind"] != "command":
            rows.append((item["name"], "-", minimum, tested, NOT_CHECKED, item.get("path", "-")))
            continue
        path, ran_ok, version = run(item["check"])
        result = status(path, ran_ok, version, item["min"], item["tested"])
        rows.append((item["name"], version or "-", minimum, tested, result, path or "-"))
    return rows


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
        text = f"Next: install or update {', '.join(named['bad'])}, then check again."
    elif named["warn"]:
        text = f"All programs are there and should work. Worth a look: {', '.join(named['warn'])}."
    elif named["good"]:
        text = "All programs are ready."
    else:
        text = "Nothing to check on this machine yet."
    if named["skip"]:
        text += f' Items marked "{NOT_CHECKED}" are checked in a later step.'
    return text


def main():
    try:
        rows = check_all(load())
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1
    widths = [max(len(str(r[i])) for r in [COLUMNS, *rows]) for i in range(len(COLUMNS))]
    for row in [COLUMNS, *rows]:
        print("  ".join(str(cell).ljust(w) for cell, w in zip(row, widths)).rstrip())
    print(summary(rows))
    print(next_step(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
