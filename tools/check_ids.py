"""Fail when a product file cites a decision or task ID from the maintainer's own records.

Users of the package cannot open those records, so a product file gives the reason in a sentence instead.
Two cases are allowed:
- test data: inside a test file (test_*.py) only comments and docstrings are checked; a string the test
  feeds to the code may look like an ID, since a user's project numbers its decisions and tasks too
  (an assert message is a string as well, so it counts as data: keep IDs out of it by hand);
- the template's own examples, D-01 and REQ-1, wherever they appear.
A binary file is skipped; a text file that is not UTF-8 is reported, since it cannot be read.

Usage: python tools/check_ids.py   (checks the files git tracks; exit 1 on a finding)
"""

import ast
import io
import re
import subprocess
import sys
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ID = re.compile(r"\b(?:D|REQ)-\d+(?:\.\d+)*\b")
EXAMPLES = {"D-01", "REQ-1"}
DOCSTRING_OWNERS = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)


def ids_in(text, first_line=1):
    """(line, ID) for every ID in text that is not a template example."""
    for match in ID.finditer(text):
        if match.group() not in EXAMPLES:
            yield first_line + text.count("\n", 0, match.start()), match.group()


def prose_of_test(text):
    """(first line, text) of every comment and docstring in a test file's source."""
    for token in tokenize.generate_tokens(io.StringIO(text).readline):
        if token.type == tokenize.COMMENT:
            yield token.start[0], token.string
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, DOCSTRING_OWNERS) and node.body:
            first = node.body[0]
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                yield first.lineno, first.value.value


def findings(name, text):
    """(line, ID) for every ID in one file the check does not allow."""
    if Path(name).name.startswith("test_") and name.endswith(".py"):
        return sorted(hit for line, prose in prose_of_test(text) for hit in ids_in(prose, line))
    return list(ids_in(text))


def main():
    names = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.split("\0")
    found = 0
    for name in filter(None, names):
        try:
            data = (ROOT / name).read_bytes()
        except FileNotFoundError:
            continue  # deleted in the working tree; CI checks the committed files
        if b"\0" in data:
            continue  # a binary file holds no prose
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            print(f"{name}: not UTF-8, so it cannot be checked; save it as UTF-8")
            found += 1
            continue
        for line, found_id in findings(name, text):
            print(f"{name}:{line}: {found_id} points to a record users cannot see; give the reason in a sentence")
            found += 1
    if found:
        print(f"{found} private ID(s) found. Allowed: test data in test_*.py strings and the examples D-01, REQ-1.")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
