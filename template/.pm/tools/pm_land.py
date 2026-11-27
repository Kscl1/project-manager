"""Check a commit against a branch, then land it only after that check is green.

Usage: python .pm/tools/pm_land.py check <commit> --into <branch> --task <ID> --cmd "<command>" [--repo DIR]
       python .pm/tools/pm_land.py land  <commit> --into <branch> --task <ID> [--repo DIR] [--records DIR]

`check` merges in a throw-away worktree, runs the command there and writes a Receipt line to the task's notes.
`land` merges only when that receipt is green and the branch has not moved; it exits 2 when it refuses.
`--repo` holds the commit and the branch (default: this folder); `--records` holds the Backlog task (default: --repo).
"""

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

TASK_DIRS = (".pm/backlog/tasks", ".pm/backlog/completed", ".pm/backlog/archive/tasks")
RECEIPT = re.compile(r"Receipt:\s*(\S+) onto (\S+) \| (.*) \| exit (-?\d+) \| (.*)")
LANDED = re.compile(r"Landed:\s*(\S+) into (\S+) \|")


def git(repo, *arguments):
    return subprocess.run(
        ["git", "-C", str(repo), *arguments], capture_output=True, text=True, encoding="utf-8", errors="replace"
    )


def resolve(repo, revision):
    """The full hash of a commit or branch, or None."""
    result = git(repo, "rev-parse", "--verify", "--quiet", f"{revision}^{{commit}}")
    return result.stdout.strip() if result.returncode == 0 else None


def append_note(records, task_id, note):
    """Append a note with the Backlog CLI; the one CLI call, so a test can replace it."""
    command = [shutil.which("backlog") or "backlog", "task", "edit", task_id, "--append-notes", note]
    try:
        return subprocess.run(command, cwd=str(records), capture_output=True).returncode
    except OSError:
        return 127


def utc_now():
    """The UTC stamp a Receipt or Landed line carries."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def find_task(records, task_id):
    """The task file in the project Backlog, found by frontmatter id like pm_resume.py."""
    for relative in TASK_DIRS:
        for path in sorted((Path(records) / relative).glob("*.md")):
            try:
                text = path.read_text(encoding="utf-8-sig")
            except (OSError, UnicodeError):
                continue
            if re.search(rf"(?m)^id:\s*['\"]?{re.escape(task_id)}['\"]?\s*$", text):
                return path
    return None


def target(repo, records, commit_arg, branch, task_id):
    """(commit, tip, task path) once resolved, or None after one line saying what was not found."""
    commit, tip = resolve(repo, commit_arg), resolve(repo, branch)
    if commit is None or tip is None:
        print(f"Could not resolve {commit_arg!r} or {branch!r} in {repo}.")
        return None
    task_path = find_task(records, task_id)
    if task_path is None:
        print(f"Task {task_id} was not found under {records}.")
        return None
    return commit, tip, task_path


def write_landed(records, task_id, task_path, commit, branch):
    """Write the one Landed line unless the task already has it."""
    for line in task_path.read_text(encoding="utf-8-sig").splitlines():
        match = LANDED.search(line)
        if match and match.group(1) == commit and match.group(2) == branch:
            return 0
    line = f"Landed: {commit} into {branch} | {utc_now()}"
    if append_note(records, task_id, line) != 0:
        print(f"Could not write the Landed line to {task_path.name}.")
        return 1
    print(line)
    return 0


def remove_worktree(repo, path):
    """Remove a throw-away worktree, even one left by a conflicted merge."""
    git(repo, "worktree", "remove", "--force", str(path))
    shutil.rmtree(path, ignore_errors=True)
    git(repo, "worktree", "prune")


def check(repo, records, commit_arg, branch, task_id, command):
    ready = target(repo, records, commit_arg, branch, task_id)
    if ready is None:
        return 2
    commit, tip, task_path = ready
    folder = Path(tempfile.mkdtemp(prefix="pm-land-"))
    path = folder / "worktree"
    try:
        if git(repo, "worktree", "add", "--detach", str(path), tip).returncode != 0:
            print(f"Could not make a throw-away worktree at {tip[:12]}.")
            return 2
        if git(path, "merge", "--no-ff", "--no-commit", commit).returncode != 0:
            code = 1
            print(f"Merge conflict: {commit[:12]} does not merge into {branch}; the command was not run.")
        else:
            code = subprocess.run(command, shell=True, cwd=str(path)).returncode
    finally:
        remove_worktree(repo, path)
        shutil.rmtree(folder, ignore_errors=True)
    line = f"Receipt: {commit} onto {tip} | {command} | exit {code} | {utc_now()}"
    if append_note(records, task_id, line) != 0:
        print(f"Could not write the receipt to {task_path.name}.")
        return 2
    print(line)
    return code


def branch_worktree(repo, branch):
    """The folder where the branch is checked out, or None."""
    for block in git(repo, "worktree", "list", "--porcelain").stdout.split("\n\n"):
        lines = block.splitlines()
        if f"branch refs/heads/{branch}" in lines:
            return lines[0][len("worktree ") :]
    return None


def land(repo, records, commit_arg, branch, task_id):
    branch = branch[len("refs/heads/") :] if branch.startswith("refs/heads/") else branch
    ready = target(repo, records, commit_arg, branch, task_id)
    if ready is None:
        return 2
    commit, tip, task_path = ready
    if git(repo, "merge-base", "--is-ancestor", commit, tip).returncode == 0:
        return write_landed(records, task_id, task_path, commit, branch)
    found = []
    for line in task_path.read_text(encoding="utf-8-sig").splitlines():
        match = RECEIPT.search(line)
        if match and match.group(1) == commit:
            found.append((match.group(2), int(match.group(4))))
    if not found:
        print(f"No receipt for {commit} in {task_id}: run check first.")
        return 2
    checked_tip, code = found[-1]
    if code != 0:
        print(f"The last check for {commit} exited {code}: run check again.")
        return 2
    if checked_tip != tip:
        print(f"The target moved since the check ({checked_tip[:12]} to {tip[:12]}): run check again.")
        return 2
    where = branch_worktree(repo, branch)
    folder = None if where else Path(tempfile.mkdtemp(prefix="pm-land-"))
    path = Path(where) if where else folder / "worktree"
    try:
        if where is None:
            git(repo, "worktree", "add", str(path), branch)
        if git(path, "merge", "--no-edit", commit).returncode != 0:
            git(path, "merge", "--abort")
            print(f"Merging {commit[:12]} into {branch} failed; nothing was landed.")
            return 1
    finally:
        if folder is not None:
            remove_worktree(repo, path)
            shutil.rmtree(folder, ignore_errors=True)
    return write_landed(records, task_id, task_path, commit, branch)


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Check a commit, then land it only after a green check.")
    actions = parser.add_subparsers(dest="action", required=True)
    for name in ("check", "land"):
        action = actions.add_parser(name)
        action.add_argument("commit")
        action.add_argument("--into", required=True)
        action.add_argument("--task", required=True)
        action.add_argument("--repo", type=Path)
        action.add_argument("--records", type=Path)
        if name == "check":
            action.add_argument("--cmd", required=True)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    repo = (args.repo or Path.cwd()).resolve()
    records = args.records.resolve() if args.records else repo
    arguments = (repo, records, args.commit, args.into, args.task)
    return check(*arguments, args.cmd) if args.action == "check" else land(*arguments)


if __name__ == "__main__":
    sys.exit(main())
