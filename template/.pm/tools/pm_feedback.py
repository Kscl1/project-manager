"""Build a package problem report that carries only the diagnosis, and send it only on an explicit yes.

Usage:
  python .pm/tools/pm_feedback.py --command "<failed command>" --error-file <file> [--harness "..."] [--title "..."]
  python .pm/tools/pm_feedback.py --send <report file> [--yes]

The first form writes `.pm/local/feedback/<date>-feedback.md` and prints it; it never sends anything.
The report has five fields (.pm/templates/feedback.md): package version, harness, tool versions, the failed command,
and at most 20 lines of the error. Everything passes the redaction below.
The second form shows the report again and opens an issue in the package's home repo with `gh issue create`.
Without --yes it asks on the terminal; anything but "y" or "yes", or no answer at all, sends nothing.
With --yes it sends only if redaction leaves the file unchanged; otherwise it writes the redacted text to a new
`<name>.redacted.md` next to the report (`-2`, `-3`, ... when that name is taken), leaves that report and every
earlier copy alone, and stops.

Redaction is best effort, which is why the owner previews the report before it leaves: it replaces this project's
task and decision titles of two or more words, project and user names, paths outside the package's own files, e-mail
addresses, known secret shapes, values of secret-looking environment variables, and quoted text of four or more words
(prompts). A one-word title such as /pm-setup's "Charter" is an ordinary word and stays; so do a/b pairs that are not
paths, such as "1/7" or "and/or".
"""

import argparse
import getpass
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HOME_REPO = "Kscl1/project-manager"  # the package's home project, where reports become issues
MAX_LINES = 20
MAX_CHARS = 2000
TOOLS = ["git", "gh", "backlog", "node", "herdr", "pi"]
FIELDS = ["Package", "Harness", "Tools", "Failed command", "Error excerpt"]  # the issue form's labels, in order

SECRET_SHAPES = [
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----",
    r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})",
    r"\bsk-[A-Za-z0-9_-]{16,}",
    r"\bAKIA[0-9A-Z]{16}\b",
    r"\bxox[abprs]-[A-Za-z0-9-]{10,}",
    r"\b(?:[Bb]earer|[Bb]asic)\s+[A-Za-z0-9._~+/=-]{8,}",
    # key=value or key: value with a config-style key (all lower or all upper case) that names a secret
    r"\b([a-z0-9_.-]*(?:token|secret|passw(?:or)?d|api[_-]?key|credential)[a-z0-9_.-]*"
    r"|[A-Z0-9_.-]*(?:TOKEN|SECRET|PASSW(?:OR)?D|API[_-]?KEY|CREDENTIAL)[A-Z0-9_.-]*)(\s*[=:]\s*)\S+",
]
SECRET_ENV = re.compile(r"TOKEN|SECRET|PASSW|KEY|AUTH|CREDENTIAL", re.I)
PATH_CHARS = r"[^\s'\"<>|:*?]"
PACKAGE_DIR = r"\.pm[\\/](?:tools|tests|hooks|roles|templates)[\\/]"  # package files: useful to triage, not private
ABS_PATH = re.compile(r"(?:\b[A-Za-z]:[\\/]|\\\\|(?<![\w.~>])/(?=[\w.~-]+/))" + PATH_CHARS + "*")
BACKLOG_FILE = re.compile(r"[\w./\\-]*backlog[\\/][^\n]*?\.md\b")  # Backlog file names carry the task title
REL_PATH = re.compile(r"(?<![\w.<>/\\-])(?!" + PACKAGE_DIR + r")[\w.-]+(?:[\\/][\w.-]+)+")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# a single quote opens and closes only away from letters: system's and tool's on one line are not a quotation
QUOTED = re.compile(r"\"[^\"\n]*\"|(?<!\w)'(?:[^'\n]|'(?=\w))*'(?!\w)")


def front_title(path):
    """The `title:` value of a Markdown file's frontmatter, or None."""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    if not lines or lines[0].strip() != "---":
        return None
    for line in lines[1:]:
        if line.strip() == "---":
            return None
        if line.startswith("title:"):
            return line[6:].strip().strip("'\"") or None
    return None


def git_config(root, key):
    try:
        out = subprocess.run(["git", "config", "--get", key], cwd=root, capture_output=True, text=True)
    except OSError:
        return ""
    return out.stdout.strip() if out.returncode == 0 else ""


def private_strings(root):
    """Strings from this project and machine that must never leave it, with their marks, longest first."""
    found = {}
    for folder in (root / ".pm" / "backlog", root / ".pm" / "decisions"):
        for path in folder.rglob("*.md") if folder.is_dir() else []:
            title = front_title(path)
            if title and len(title.split()) >= 2:  # one word ("Charter", "Models") says nothing about the project
                found[title] = "<title>"
    config = root / "backlog.config.yml"
    if config.exists():
        match = re.search(r"^project_name:\s*(.+)$", config.read_text(encoding="utf-8"), re.M)
        if match:
            found[match.group(1).strip().strip("'\"")] = "<project>"
    found[root.name] = "<project>"
    for key in ("user.name", "user.email"):
        found[git_config(root, key)] = "<user>"
    try:
        found[getpass.getuser()] = "<user>"
    except (OSError, KeyError, ImportError):
        pass
    for name, value in os.environ.items():
        if SECRET_ENV.search(name) and len(value) >= 8:
            found[value] = "<secret>"
    found.pop("", None)
    return sorted(found.items(), key=lambda pair: -len(pair[0]))


def looks_like_path(text):
    """A REL_PATH match is a path when it has a letter and a file extension or two separators: src/app.py, a/b/c.

    So a count such as 1/7 and a word pair such as and/or stay as they are.
    """
    parts = re.split(r"[\\/]", text)
    return any(c.isalpha() for c in text) and (len(parts) > 2 or "." in parts[-1].strip("."))


def redact(text, root, private):
    """Replace everything in `text` that could identify the project, its owner or a secret."""
    for shape in SECRET_SHAPES:
        text = re.sub(shape, lambda m: f"{m.group(1)}{m.group(2)}<secret>" if m.lastindex else "<secret>", text)
    for value, mark in private:  # secret values first: they may sit inside a path or a quoted string
        if mark == "<secret>":
            text = text.replace(value, mark)

    def in_project(match):
        rest = (match.group(1) or "").replace("\\", "/")
        return "<project>" + (rest if re.match("/" + PACKAGE_DIR, rest) else "/<file>" if rest else "")

    for form in {str(root), root.as_posix()}:
        text = re.sub(re.escape(form) + "([\\\\/]" + PATH_CHARS + "*)?", in_project, text, flags=re.I)
    text = ABS_PATH.sub("<path>", text)
    text = BACKLOG_FILE.sub("<task file>", text)
    text = REL_PATH.sub(lambda m: "<file>" if looks_like_path(m.group(0)) else m.group(0), text)
    text = EMAIL.sub("<email>", text)
    text = QUOTED.sub(lambda m: "<text>" if len(m.group(0).split()) >= 4 else m.group(0), text)
    for value, mark in private:
        if len(value) >= 3:
            text = re.sub(r"(?<!\w)" + re.escape(value) + r"(?!\w)", mark, text, flags=re.I)
    return text


def tool_version(name):
    path = shutil.which(name)  # also finds backlog.cmd and other Windows shims
    if not path:
        return "not found"
    try:
        # utf-8, not the console's code page: a tool that prints an arrow or a non-Latin name must not crash.
        out = subprocess.run(
            [path, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return "not found"
    lines = (out.stdout or out.stderr).strip().splitlines()
    return lines[0] if lines else "unknown"


def tool_versions():
    rows = [f"python {platform.python_version()}", f"os {platform.platform()} {platform.machine()}"]
    return "\n".join(rows + [f"{name}: {tool_version(name)}" for name in TOOLS])


def excerpt(text):
    lines = text.strip().splitlines()[-MAX_LINES:]
    return "\n".join(lines)[-MAX_CHARS:]


def display(path, root):
    """The path to print: relative to the project when it sits inside it, so no home folder or user name shows."""
    try:
        return path.resolve().relative_to(root).as_posix()
    except (OSError, ValueError):
        return path.as_posix()


def build(root, command, error, harness, title):
    """The report as Markdown: the issue form's labels as headings, the redacted values below them."""
    version = root / ".pm" / "VERSION"
    package = version.read_text(encoding="utf-8").strip() if version.exists() else "no .pm/VERSION"
    values = [package, harness or "not given", tool_versions(), command, excerpt(error)]
    private = private_strings(root)
    body = "\n\n".join(f"### {field}\n\n```text\n{value}\n```" for field, value in zip(FIELDS, values))
    title = title or f"{command.split()[0] if command.split() else 'command'} failed"
    return f"# [feedback] {redact(title, root, private)}\n\n{redact(body, root, private)}\n"


def write_new(path, text):
    """Write `text` to `path`, or to `<stem>-2`, `-3`, ... when it is taken; never replace an existing file.

    Returns the path actually written, so the tool can print which one it was.
    """
    candidate, extra = path, 2
    while True:
        try:
            with candidate.open("x", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
        except FileExistsError:
            candidate = path.with_name(f"{path.stem}-{extra}{path.suffix}")
            extra += 1
            continue
        return candidate


def send(root, report, yes, repo):
    """Open the issue only on an explicit yes. Returns the exit code."""
    shown = report.read_text(encoding="utf-8")
    text = redact(shown, root, private_strings(root))  # again: the file may be edited
    title, _, body = text.partition("\n")
    print(text)
    source = report
    if text != shown:  # never overwrite the owner's own file: the redacted copy sits next to it, under a free name
        source = write_new(report.with_name(f"{report.stem}.redacted.md"), text)
        print(f"Redaction changed the report; the text that would be sent is in {display(source, root)}.")
    if yes and text != shown:  # the owner said yes to the file, so send only the file as it was shown
        print("Nothing sent: show the owner that file and ask again.")
        return 1
    if not yes:
        try:
            print(f"It becomes a public issue in the package's home repo (github.com/{repo}); anyone can read it.")
            answer = input("Send it? [y/N] ")
        except EOFError:
            answer = ""
        if answer.strip().lower() not in ("y", "yes"):
            print("Nothing sent.")
            return 0
    if not shutil.which("gh"):
        print(f"gh is missing or not signed in; nothing sent. The report is saved at {display(source, root)}.")
        return 1
    title = title.lstrip("# ").strip()
    command = ["gh", "issue", "create", "--repo", repo, "--title", title, "--body-file", "-"]
    # utf-8, not the locale's code page: on Windows that is cp1252, which cannot write pm_check's arrows
    code = subprocess.run(command, input=body.strip() + "\n", encoding="utf-8").returncode
    if code == 0:
        print(f"Issue opened with the text from {display(source, root)}.")
    return code


def main(argv=None):
    parser = argparse.ArgumentParser(description="Write a diagnosis-only package problem report; send it on yes.")
    parser.add_argument("--command", help="the package command that failed")
    parser.add_argument("--error-file", help="a file with the error output; '-' reads standard input")
    parser.add_argument("--harness", help="harness, model and thinking level, e.g. 'Claude Code 2.3, Opus 5.5 (high)'")
    parser.add_argument("--title", help="one line: what went wrong (redacted like the rest)")
    parser.add_argument("--send", metavar="REPORT", help="open an issue from this report file after a yes")
    parser.add_argument("--yes", action="store_true", help="with --send: the owner already said yes in chat")
    parser.add_argument("--repo", default=HOME_REPO, help=argparse.SUPPRESS)
    parser.add_argument("--root", default=".", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()

    if args.send:
        return send(root, Path(args.send), args.yes, args.repo)
    if not args.command or not args.error_file:
        parser.error("give --command and --error-file, or --send REPORT")
    if args.error_file == "-":
        error = sys.stdin.read()
    else:
        source = Path(args.error_file)
        try:
            # errors=replace: an error log in another code page must not crash the tool
            error = source.read_text(encoding="utf-8", errors="replace")
        except OSError as failure:
            print(f"Could not read {source.as_posix()}: {failure.strerror or failure}.")
            print("The report is written without it. Check the path, or use --error-file - to pipe the error in.")
            error = "(no error text: the error file could not be read)"
    report = build(root, args.command, error, args.harness, args.title)
    out = root / ".pm" / "local" / "feedback" / f"{time.strftime('%Y-%m-%d-%H%M%S')}-feedback.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8", newline="\n")
    print(report)
    print(f"Written to {out.relative_to(root).as_posix()}. Nothing was sent.")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdin.reconfigure(encoding="utf-8", errors="replace")  # --error-file -: piped pm_check output is utf-8
    sys.exit(main())
