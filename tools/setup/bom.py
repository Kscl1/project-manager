"""Bill of materials checks for the setup TUI: load bom.toml, read the installed versions, compare (DESIGN.md).

Standard library only, so the tests and the plain-text table run without Textual.

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
VERSION = re.compile(r"\d+(?:\.\d+)+")
TIMEOUT_S = 15
COLUMNS = ("Item", "Installed", "Minimum", "Tested", "Status")

MISSING = "missing"
UNREADABLE = "version unreadable"
BELOW = "below minimum"
OK = "ok"
UNTESTED = "not tested yet"


def load(path=BOM):
    """The [[item]] tables of bom.toml, in file order."""
    with open(path, "rb") as f:
        return tomllib.load(f)["item"]


def parse_version(text):
    """The first dotted number in a command's output ('git version 2.54.0.windows.1' -> '2.54.0'), else None."""
    match = VERSION.search(text or "")
    return match.group(0) if match else None


def compare(a, b):
    """-1, 0 or 1, number by number; missing parts count as 0, so 3.11 equals 3.11.0."""
    x = [int(p) for p in a.split(".")]
    y = [int(p) for p in b.split(".")]
    size = max(len(x), len(y))
    x += [0] * (size - len(x))
    y += [0] * (size - len(y))
    return (x > y) - (x < y)


def status(found, version, minimum, tested):
    if not found:
        return MISSING
    if version is None:
        return UNREADABLE
    if compare(version, minimum) < 0:
        return BELOW
    if compare(version, tested) > 0:
        return UNTESTED
    return OK


def installed_version(check):
    """(found, version) for a check command such as ["git", "--version"]; version is None if the output has none."""
    exe = shutil.which(check[0])  # also finds npm's .cmd shims on Windows
    if exe is None:
        return False, None
    try:
        done = subprocess.run(
            [exe, *check[1:]], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=TIMEOUT_S
        )
    except (OSError, subprocess.TimeoutExpired):
        return True, None
    return True, parse_version(done.stdout + done.stderr)


def check_all(items, probe=installed_version):
    """One row per item: name, installed, minimum, tested, status."""
    rows = []
    for item in items:
        found, version = probe(item["check"])
        result = status(found, version, item["min"], item["tested"])
        rows.append((item["name"], version or "-", item["min"], item["tested"], result))
    return rows


def summary(rows):
    """'5 checked: 3 ok, 2 missing'."""
    counts = Counter(row[-1] for row in rows)
    return f"{len(rows)} checked: " + ", ".join(f"{n} {name}" for name, n in counts.items())


def main():
    rows = check_all(load())
    widths = [max(len(str(r[i])) for r in [COLUMNS, *rows]) for i in range(len(COLUMNS))]
    for row in [COLUMNS, *rows]:
        print("  ".join(str(cell).ljust(w) for cell, w in zip(row, widths)).rstrip())
    print(summary(rows))


if __name__ == "__main__":
    sys.exit(main())
