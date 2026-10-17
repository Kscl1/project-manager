"""Check that the repo's docs are consistent. No dependencies, no model.

Usage: python .pm/tools/pm_check.py                check every doc
       python .pm/tools/pm_check.py --staged       check only docs staged for commit (the pre-commit hook)
       python .pm/tools/pm_check.py --stale        list docs whose described code changed since review (never blocks)
       python .pm/tools/pm_check.py --write-index  rewrite the generated part of the decision index
Exit code 1 when a consistency problem is found, so hooks and CI can block on it.
Task files are checked too: a Done task needs every box checked and a `Doc impact:` line;
an open task keeps its live Next and Evidence lines short, so the resume summary stays short.
A file path written in backticks must exist: in a living doc any repo path, in a decision in force a path into
a repository next to this one (`../repo/file`). A deleted file passes when its deleting commit is named beside it.

A clean result means the docs are consistent, not that they are correct.
"""

import functools
import os
import re
import subprocess
import sys
from datetime import date
from pathlib import Path
from urllib.parse import unquote


def find_root(start):
    """The project root holds backlog.config.yml or .git; the tools live in <root>/.pm/tools."""
    for folder in [start, *start.parents]:
        if (folder / "backlog.config.yml").exists() or (folder / ".git").exists():
            return folder
    return start.parent


ROOT = find_root(Path(__file__).resolve().parent)
# Decisions live in .pm/decisions.md: either the whole log, or an index of .pm/decisions/D-n.md files (one per
# decision; replaced ones in .pm/decisions/archive/). Older projects keep the log in docs/decisions.md.
DECISIONS = next((p for p in (ROOT / ".pm" / "decisions.md", ROOT / "docs" / "decisions.md") if p.exists()), None)
DECISION_DIR = DECISIONS.with_suffix("") if DECISIONS else None
LINE_LIMIT = 300
LIVE_LINE_LIMIT = 300  # characters of a live Next or Evidence line in an open task
# Append-only logs and dated snapshots grow by design, so they skip the line limit.
NO_LINE_LIMIT = ("research/", "docs/research/", "docs/archive/", ".pm/decisions.md", "docs/decisions.md")
INDEX_BEGIN, INDEX_END = "<!-- decision-index:begin -->", "<!-- decision-index:end -->"
# The catalogue page lists every typed record between these markers; without the markers there is no catalogue.
CATALOGUE = ROOT / "docs" / "README.md"
CATALOGUE_BEGIN, CATALOGUE_END = "<!-- record-catalogue:begin -->", "<!-- record-catalogue:end -->"
ARCHIVED = "archived"  # an archived decision that names no replacement
# Decision files carry `id`, `title`, `status`, `date` and, when replaced, `replaced_by` in their frontmatter.
STATUSES = {"accepted": False, "superseded": True, "elsewhere": True}  # status -> lives in archive/
# Research standard v1 (docs/research/research-standard/README.md): only entries that declare `terms:` are checked.
STUDY_ENTRY = re.compile(r"^docs/research/[^/]+/README\.md$")
STUDY_FIELDS = ("title", "date", "task", "question", "validity", "decisions", "models", "terms")
STUDY_SECTIONS = (
    "Kısa cevap",
    "Soru ve yöntem",
    "Bulgular",
    "Öneri ve sonuç",
    "Alternatifler ve itirazlar",
    "Sınırlar",
    "Okuma haritası",
)
SKIP_DIRS = {".git", "node_modules", ".worktrees", "__pycache__"}
# Local runs, worktrees and Backlog's own task archive are not docs. A docs archive is checked like any doc.
SKIP_PREFIXES = ((".pm", "local"), (".claude", "worktrees"), (".pm", "backlog", "archive"), ("backlog", "archive"))

# A decision is a list item that starts with its bold ID, optionally struck through. Examples in prose do not count.
DECISION = re.compile(r"^\s*-\s+(?:~~)?\*\*(D-\d+)\*\*")
REPLACED_BY = re.compile(r"→\s*(D-\d+)")
DECISION_FILE = re.compile(r"^D-\d+$")
# A file path in backticks, alone or inside a command: `docs/x.md`, `python ../repo/tool.py`, `pm_check.py`.
# A bare file name (no folder) counts only with one of these extensions; a commit is 7 to 40 hex digits.
PATH_WORD = re.compile(r"[\w.-]+(/[\w.-]+)*")
BARE_NAME_TYPES = (".md", ".py", ".yml", ".yaml", ".toml", ".json", ".txt", ".sh", ".ps1", ".c4")
COMMIT = re.compile(r"\b[0-9a-f]{7,40}\b")
# Records that carry frontmatter by type. A list key may say `kayıtta yok` / `not recorded`.
WORKLOG_DIR = ROOT / ".pm" / "worklog"
RECORD_KEYS = {
    "worklog": ("type", "title", "date", "task", "models"),
    "living_doc": ("type", "title"),
    "study": ("type", *STUDY_FIELDS),
    "lessons_log": ("type", "title"),
}
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
INLINE_CODE = re.compile(r"`[^`]*`")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TASK_DIRS = (".pm/backlog/tasks/", "backlog/tasks/")
DRAFT_DIRS = (".pm/backlog/drafts/", "backlog/drafts/")
UNCHECKED = re.compile(r"^\s*-\s+\[ \]")


def rel(path):
    return path.relative_to(ROOT).as_posix()


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout


def load_decisions():
    """Map each decision ID to the ID that replaced it, or None if it is still active.

    Also return problems for IDs defined twice, which happens when two branches add the same next ID.
    """
    decisions, problems = {}, []
    if DECISIONS is None:
        return decisions, problems
    for path, archived in decision_files():
        ident, meta = path.stem, decision_meta(path)
        if ident in decisions:
            problems.append(f"{rel(path)}: {ident} is defined twice\n    → keep one file: in force or archived")
        problems += [f"{rel(path)}: {problem}" for problem in decision_problems(ident, meta, archived)]
        if not archived:
            decisions[ident] = None
        else:
            decisions[ident] = meta["replaced_by"] if meta["status"] == "superseded" else ARCHIVED
    for ident, replacement in list(decisions.items()):
        if replacement not in (None, ARCHIVED) and replacement not in decisions:
            problems.append(f"{ident}: replaced_by {replacement} does not exist\n    → name an existing decision")
    for number, line in enumerate(DECISIONS.read_text(encoding="utf-8").splitlines(), start=1):
        match = DECISION.search(line)
        if not match:
            continue
        if match.group(1) in decisions:
            problems.append(
                f"{rel(DECISIONS)}:{number}: {match.group(1)} is defined twice\n"
                f"    → give the newer decision the next free ID"
            )
        replaced = line.lstrip().startswith("- ~~")
        replacement = REPLACED_BY.search(line) if replaced else None
        decisions[match.group(1)] = replacement.group(1) if replacement else None
    return decisions, problems


def decision_files():
    """(path, archived) for every one-file decision, in ID order; empty while a project keeps a single log."""
    if not DECISION_DIR or not DECISION_DIR.is_dir():
        return []
    found = [(p, False) for p in DECISION_DIR.glob("D-*.md")]
    found += [(p, True) for p in (DECISION_DIR / "archive").glob("D-*.md")]
    found = [(p, a) for p, a in found if DECISION_FILE.match(p.stem)]
    return sorted(found, key=lambda pa: int(pa[0].stem[2:]))


def decision_meta(path):
    """The frontmatter fields of a decision file as plain strings, plus its first `# ` heading."""
    lines = path.read_text(encoding="utf-8").splitlines()
    fields = read_frontmatter(lines)
    meta = {
        key: ", ".join(v for _, v in fields.get(key, [])) for key in ("id", "title", "status", "date", "replaced_by")
    }
    title = meta["title"]
    if len(title) > 1 and title[0] == title[-1] == '"':
        meta["title"] = title[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    meta["heading"] = next((line for line in lines if line.startswith("# ")), "")
    return meta


def decision_problems(ident, meta, archived):
    """A decision file names itself, carries a known status and lives in the folder its status implies."""
    problems = []
    if meta["id"] != ident:
        problems.append(f"frontmatter id is {meta['id'] or 'missing'}, the file is {ident}\n    → set `id: {ident}`")
    if not meta["title"]:
        problems.append("frontmatter has no title\n    → add `title:`")
    if not meta["heading"].startswith(f"# {ident} "):
        problems.append(f"the heading must be `# {ident} <title>`\n    → fix the heading")
    if meta["status"] not in STATUSES:
        problems.append(f"status is {meta['status'] or 'missing'}\n    → use one of {', '.join(STATUSES)}")
    elif STATUSES[meta["status"]] != archived:
        where = "archive/" if STATUSES[meta["status"]] else "the decision folder, not archive/"
        problems.append(f"status {meta['status']} belongs in {where}\n    → move the file or fix the status")
    if meta["status"] == "superseded" and not DECISION_FILE.match(meta["replaced_by"]):
        problems.append("a superseded decision needs `replaced_by: D-n`\n    → name the decision that replaced it")
    return problems


def render_index():
    """The generated part of the decision index: one line per decision, in force first, then the archive."""
    rows = {False: [], True: []}
    for path, archived in decision_files():
        meta = decision_meta(path)
        link = path.relative_to(DECISIONS.parent).as_posix()
        first = f"| [{path.stem}]({link}) | {meta['title'].replace('|', '/')} |"
        if archived:
            rows[True].append(f"{first} {meta['status'] or '—'} | {meta['replaced_by'] or '—'} |")
        else:
            rows[False].append(f"{first} {meta['date'] or '—'} |")
    lines = [INDEX_BEGIN, "", "| ID | Decision | Date |", "|---|---|---|", *rows[False], ""]
    lines += ["Archive: decisions no longer in force here, kept for their history.", ""]
    lines += ["| ID | Decision | Status | Replaced by |", "|---|---|---|---|", *rows[True], "", INDEX_END]
    return "\n".join(lines)


def check_index():
    """With one file per decision, the index must list exactly those files."""
    if not decision_files():
        return []
    text = DECISIONS.read_text(encoding="utf-8")
    start, end = text.find(INDEX_BEGIN), text.find(INDEX_END)
    if start < 0 or end < 0 or text[start : end + len(INDEX_END)] != render_index():
        return [
            f"{rel(DECISIONS)}: the decision index is out of date\n    → run python .pm/tools/pm_check.py --write-index"
        ]
    return []


def check_worklogs():
    """Once one worklog carries frontmatter, every worklog must: type, title, date (the file's date), task, models."""
    logs = sorted(WORKLOG_DIR.glob("*.md")) if WORKLOG_DIR.is_dir() else []
    fronts = {path: read_frontmatter(path.read_text(encoding="utf-8").splitlines()) for path in logs}
    if not any(("type", "worklog") in [(k, v) for k, vals in f.items() for _, v in vals] for f in fronts.values()):
        return []
    problems = []
    for path, front in fronts.items():
        name = rel(path)
        missing = [key for key in RECORD_KEYS["worklog"] if not front.get(key)]
        if missing:
            problems.append(
                f"{name}: frontmatter lacks {', '.join(missing)}\n    → add them (use `kayıtta yok` if unknown)"
            )
            continue
        if front["type"][0][1] != "worklog":
            problems.append(f"{name}:{front['type'][0][0]}: type must be worklog")
        when = front["date"][0][1]
        if not path.name.startswith(when):
            problems.append(f"{name}:{front['date'][0][0]}: date {when} does not match the file name")
    return problems


def write_index():
    text = DECISIONS.read_text(encoding="utf-8")
    start, end = text.find(INDEX_BEGIN), text.find(INDEX_END)
    if start < 0 or end < 0:
        text = text.rstrip("\n") + "\n\n" + render_index() + "\n"
    else:
        text = text[:start] + render_index() + text[end + len(INDEX_END) :]
    DECISIONS.write_text(text, encoding="utf-8", newline="\n")
    print(f"Wrote the index in {rel(DECISIONS)}: {len(decision_files())} decisions")


def records():
    """{type: [(path, frontmatter)]} for every Markdown record that declares a known type (Backlog files excluded)."""
    found = {kind: [] for kind in RECORD_KEYS}
    for path in markdown_files():
        if rel(path).startswith(TASK_DIRS + DRAFT_DIRS):
            continue
        front = read_frontmatter(path.read_text(encoding="utf-8").splitlines())
        kind = front.get("type", [(0, "")])[0][1]
        if kind in found:
            found[kind].append((path, front))
    return found


def render_catalogue():
    """The generated record list in the catalogue page: one table per record type, read from the frontmatter."""

    def value(front, key):
        text = ", ".join(v for _, v in front.get(key, [])).strip('"').replace("|", "/")
        return text or "—"

    def link(path):
        return f"[`{os.path.relpath(path, CATALOGUE.parent).replace(os.sep, '/')}`]({os.path.relpath(path, CATALOGUE.parent).replace(os.sep, '/')})"

    found = records()
    files = decision_files()
    in_force = sum(1 for _, archived in files if not archived)
    lines = [
        CATALOGUE_BEGIN,
        "",
        "Generated by `python .pm/tools/pm_check.py --write-index` from each record's frontmatter.",
        "",
    ]
    if DECISIONS:
        index = os.path.relpath(DECISIONS, CATALOGUE.parent).replace(os.sep, "/")
        lines += [f"**Decisions:** {len(files)} ({in_force} in force), listed in [`{index}`]({index}).", ""]
    tables = [
        ("living_doc", "Living docs", ["Doc", "Title"], lambda p, f: [link(p), value(f, "title")]),
        (
            "study",
            "Studies",
            ["Study", "Title", "Date", "Validity"],
            lambda p, f: [link(p), *(value(f, k) for k in ("title", "date", "validity"))],
        ),
        ("lessons_log", "Lessons", ["Log", "Title"], lambda p, f: [link(p), value(f, "title")]),
        (
            "worklog",
            "Worklogs",
            ["Date", "Worklog", "Tasks"],
            lambda p, f: [value(f, "date"), link(p), value(f, "task")],
        ),
    ]
    for kind, heading, columns, row in tables:
        if not found[kind]:
            continue
        lines += [
            f"**{heading}** ({len(found[kind])})",
            "",
            "| " + " | ".join(columns) + " |",
            "|" + "---|" * len(columns),
        ]
        lines += ["| " + " | ".join(row(p, f)) + " |" for p, f in sorted(found[kind], key=lambda pf: rel(pf[0]))]
        lines.append("")
    return "\n".join(lines + [CATALOGUE_END])


def check_catalogue():
    """When the catalogue page carries the markers, its generated list must match the records."""
    if not CATALOGUE.exists():
        return []
    text = CATALOGUE.read_text(encoding="utf-8")
    start, end = text.find(CATALOGUE_BEGIN), text.find(CATALOGUE_END)
    if start < 0 or end < 0:
        return []
    if text[start : end + len(CATALOGUE_END)] != render_catalogue():
        return [
            f"{rel(CATALOGUE)}: the record catalogue is out of date\n    → run python .pm/tools/pm_check.py --write-index"
        ]
    return []


def write_catalogue():
    if not CATALOGUE.exists():
        return
    text = CATALOGUE.read_text(encoding="utf-8")
    start, end = text.find(CATALOGUE_BEGIN), text.find(CATALOGUE_END)
    if start < 0 or end < 0:
        return
    CATALOGUE.write_text(
        text[:start] + render_catalogue() + text[end + len(CATALOGUE_END) :], encoding="utf-8", newline="\n"
    )
    print(f"Wrote the record catalogue in {rel(CATALOGUE)}")


def read_frontmatter(lines):
    """Return {key: [(line number, value), ...]} for `key: [a, b]`, `key: value` and `key:` + `- item` forms."""
    fields, key = {}, None
    if not lines or lines[0].strip() != "---":
        return fields
    for number, line in enumerate(lines[1:], start=2):
        if line.strip() == "---":
            break
        if line.lstrip().startswith("- ") and key:
            fields[key].append((number, line.strip()[2:].strip()))
            continue
        name, _, value = line.partition(":")
        if not _ or line.startswith(" "):
            key = None
            continue
        key = name.strip()
        values = [v.strip() for v in value.strip().strip("[]").split(",") if v.strip()]
        fields[key] = [(number, v) for v in values]
    return fields


def exists_exact_case(base, target):
    """Like Path.exists, but case-sensitive even on Windows, where docs/X.md and Docs/x.md look the same."""
    path = base
    for part in Path(os.path.normpath(target)).parts:
        if part in (".", ""):
            continue
        if part == "..":
            path = path.parent
            continue
        try:
            if part not in os.listdir(path):
                return False
        except (NotADirectoryError, FileNotFoundError):
            return False
        path = path / part
    return True


def check_record_type(name, front):
    """A file that declares `type:` must use a known type and carry that type's keys (worklog dates: check_worklogs)."""
    if "type" not in front:
        return []
    kind = front["type"][0][1] if front["type"] else ""
    number = front["type"][0][0] if front["type"] else 1
    if kind not in RECORD_KEYS:
        return [f"{name}:{number}: unknown type {kind or '(empty)'}\n    → use one of {', '.join(RECORD_KEYS)}"]
    missing = [key for key in RECORD_KEYS[kind] if key not in front]
    if missing and kind != "worklog":
        return [f"{name}: a {kind} needs {', '.join(missing)} in its frontmatter\n    → add them"]
    return []


def vendored(name):
    """A file of a skill copied from another project (a LICENSE sits beside its SKILL.md): its text is upstream's."""
    parts = name.split("/")
    return parts[:2] == [".agents", "skills"] and len(parts) > 3 and (ROOT / "/".join(parts[:3]) / "LICENSE").is_file()


def check_file(path, decisions):
    name = rel(path)
    lines = path.read_text(encoding="utf-8").splitlines()
    problems = []

    for number, ref in read_frontmatter(lines).get("depends_on", []):
        if ref not in decisions:
            problems.append(
                f"{name}:{number}: depends on {ref}, which does not exist\n    → check the ID in the decision log"
            )
        elif decisions[ref] == ARCHIVED:
            problems.append(
                f"{name}:{number}: depends on {ref}, which is archived and no longer in force here\n"
                f"    → review the file without {ref}, then update depends_on"
            )
        elif decisions[ref]:
            problems.append(
                f"{name}:{number}: depends on {ref}, which was superseded by {decisions[ref]}\n"
                f"    → review the file against {decisions[ref]}, then update depends_on"
            )

    if not name.startswith(TASK_DIRS + DRAFT_DIRS):  # Backlog files keep Backlog's own `type`
        problems += check_record_type(name, read_frontmatter(lines))

    in_fence = False
    for number, line in enumerate(lines, start=1):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        if in_fence:
            continue
        for target in LINK.findall(INLINE_CODE.sub("", line)):
            if re.match(r"[a-z]+:", target) or target.startswith("#"):
                continue
            target_path = unquote(target.split("#")[0])
            if not exists_exact_case(path.parent, target_path):
                problems.append(
                    f"{name}:{number}: link to {target_path} does not exist (paths are case-sensitive)\n"
                    f"    → fix the path or remove the link"
                )
            elif (ROOT / ".pm" / "local") in Path(os.path.normpath(path.parent / target_path)).parents:
                problems.append(
                    f"{name}:{number}: link to {target_path} points into .pm/local/, which git ignores\n"
                    f"    → CI and other clones cannot see it: write the path as `code` or move the file into git"
                )

    if len(lines) > LINE_LIMIT and not name.startswith(NO_LINE_LIMIT) and not vendored(name):
        problems.append(
            f"{name}: {len(lines)} lines, limit is {LINE_LIMIT}\n    → split by topic and keep this file as an index"
        )
    if DECISION_DIR and path.parent == DECISION_DIR and DECISION_FILE.match(path.stem):
        problems += check_repo_paths(name, path, lines, siblings_only=True)
    elif [value for _, value in read_frontmatter(lines).get("type", [])] == ["living_doc"]:
        problems += check_repo_paths(name, path, lines)
    if name.startswith(TASK_DIRS + DRAFT_DIRS):
        problems += check_done_task(name, lines)
    if name.startswith(TASK_DIRS):
        problems += check_open_task_type(name, lines)
    if name.startswith(TASK_DIRS + DRAFT_DIRS):
        problems += check_live_lines(name, lines)
    if STUDY_ENTRY.match(name):
        problems += check_study(path, name, lines)
    return problems


def check_study(path, name, lines):
    """A study entry that declares `terms:` follows research standard v1: its fields, seven sections, a tidy root."""
    fields = read_frontmatter(lines)
    if "terms" not in fields:
        return []  # older studies predate the standard
    problems = [
        f"{name}: study entry lacks {key}\n    → add `{key}:` to the front matter"
        for key in STUDY_FIELDS
        if key not in fields
    ]
    if not fields["terms"]:
        problems.append(f"{name}: terms is empty\n    → list every name, rejected alternative and alias in the study")
    if [v for _, v in fields.get("type", [])] != ["study"]:
        problems.append(f"{name}: a study entry declares `type: study`\n    → add it as the first front matter key")
    found = sections(lines)
    problems += [f"{name}: lacks the section '{s}'\n    → add `## {s}`" for s in STUDY_SECTIONS if s not in found]
    folder = rel(path.parent)
    problems += [
        f"{folder}: {entry} sits in the study root\n    → move it into material/"
        for entry in sorted(os.listdir(path.parent))
        if entry not in ("README.md", "material")
    ]
    return problems


def sections(lines):
    """Map each `## heading` to the lines under it."""
    found, current = {}, None
    for line in lines:
        if line.startswith("## "):
            current = line[3:].strip()
            found[current] = []
        elif current:
            found[current].append(line)
    return found


def check_repo_paths(name, path, lines, siblings_only=False):
    """Every file path a doc writes in backticks exists, alone or inside a command (`python ../repo/x.py`).

    A living doc: paths in this repo, from the root or from the doc's folder; a bare file name (`pm_check.py`)
    must be the name of some file in the repo. A decision in force: only paths into a sibling repository
    (`../repo/file`). A sibling repository that is not next to this one, as in CI or another clone, is skipped.
    A missing file passes when the commit that deleted it is named on the same line. Placeholders (`...`),
    `.pm/local/` and fenced code are skipped; a line suffix (`file.py:12`) is not part of the path.
    """
    problems = []
    in_fence = False
    for number, line in enumerate(lines, start=1):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        if in_fence:
            continue
        for word in path_words(line):
            if word.startswith("../"):
                parts = Path(os.path.normpath(word)).parts
                if len(parts) < 2 or parts[1] == ".." or not (ROOT.parent / parts[1]).is_dir():
                    continue
                repo, target, found = ROOT.parent / parts[1], "/".join(parts[2:]), exists_exact_case(ROOT, word)
            elif siblings_only or word.startswith(".pm/local/"):
                continue
            elif "/" in word:
                repo, target = ROOT, word
                found = exists_exact_case(ROOT, word) or exists_exact_case(path.parent, word)
            else:
                repo, target, found = ROOT, word, word in repo_file_names()
            if not found and not deleted_on_line(repo, target, line):
                problems.append(
                    f"{name}:{number}: {word} does not exist (paths are case-sensitive)\n"
                    f"    → fix the path and reread the text against the file, "
                    f"or name the commit that deleted it on the same line"
                )
    return problems


def path_words(line):
    """The words inside backticks that look like a file path; quotes, commas and a line suffix are dropped."""
    for span in INLINE_CODE.findall(line):
        for word in span.strip("`").split():
            word = re.sub(r"(:\d+)+$", "", word.strip("\"'(),;"))
            if not PATH_WORD.fullmatch(word) or "..." in word:
                continue
            last = word.rsplit("/", 1)[-1]
            if word.startswith("../") or ("/" in word and re.search(r".\.\w+$", last)):
                yield word
            elif "/" not in word and last.endswith(BARE_NAME_TYPES) and last not in BARE_NAME_TYPES:
                yield word


@functools.cache
def repo_file_names():
    """The name of every file in the repo, for matching a bare file name; skipped folders are not the repo."""
    names = set()
    for folder, dirs, files in os.walk(ROOT):
        here = Path(folder).relative_to(ROOT).parts
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not any((*here, d)[: len(p)] == p for p in SKIP_PREFIXES)]
        names.update(files)
    return names


def deleted_on_line(repo, target, line):
    """True when a commit named on the line deleted the target (a rename counts as a delete) in that repo."""
    for commit in COMMIT.findall(line):
        show = ["git", "-C", str(repo), "-c", "core.quotePath=false", "show", "--no-renames", "--diff-filter=D"]
        result = subprocess.run([*show, "--name-only", "--format=", commit], capture_output=True, encoding="utf-8")
        gone = result.stdout.splitlines() if result.returncode == 0 else []
        if any(p == target or p.endswith("/" + target) for p in gone):
            return True
    return False


def check_done_task(name, lines):
    """A Done task has every box checked and, if it carries a Definition of Done, a `Doc impact:` line."""
    status = next((value for _, value in read_frontmatter(lines).get("status", [])), "")
    if status.strip("'\"") != "Done":
        return []
    body = sections(lines)
    problems = [
        f"{name}: Done, but {section} has unchecked items\n"
        f"    → check them with evidence, or move the task back out of Done"
        for section in ("Acceptance Criteria", "Definition of Done")
        if any(UNCHECKED.match(line) for line in body.get(section, []))
    ]
    summary = body.get("Final Summary", [])
    if "Definition of Done" in body and not any(line.strip().startswith("Doc impact:") for line in summary):
        problems.append(
            f"{name}: Done, but the final summary has no 'Doc impact:' line\n"
            f"    → name the living docs this task changed, or write 'Doc impact: none'"
        )
    problems += check_audit_outcomes(name, lines)
    return problems


def check_open_task_type(name, lines):
    """An open task carries a type (epic, package, task or bug)."""
    fields = read_frontmatter(lines)
    status = next((value for _, value in fields.get("status", [])), "").strip("'\"")
    kind = next((value for _, value in fields.get("type", [])), "").strip("'\"")
    if status == "Done" or kind:
        return []
    return [f"{name}: open task without a type\n    → backlog task edit <id> --type <epic|package|task|bug>"]


def check_live_lines(name, lines):
    """An open task's live Next and Evidence lines stay short; their history goes below the block."""
    status = next((value for _, value in read_frontmatter(lines).get("status", [])), "").strip("'\"")
    if status == "Done":
        return []
    problems, seen = [], set()
    for line in sections(lines).get("Implementation Notes", []):
        field = line.split(":", 1)[0]
        if field in ("Next", "Evidence") and field not in seen:
            seen.add(field)
            if len(line) > LIVE_LINE_LIMIT:
                problems.append(
                    f"{name}: live '{field}:' line is {len(line)} characters, limit is {LIVE_LINE_LIMIT}\n"
                    f"    → keep the current state in one short line; move the history to a dated note below the block"
                )
    return problems


def unfenced_lines(lines):
    """Ignore fenced examples, including tilde fences and longer backtick fences."""
    fence = None
    for line in lines:
        match = re.match(r"^\s{0,3}(`{3,}|~{3,})(.*)$", line)
        if match:
            marker, tail = match.groups()
            if fence is None:
                yield "```"  # a fence is a non-table boundary, even though its contents are ignored
                fence = marker
            elif marker[0] == fence[0] and len(marker) >= len(fence) and not tail.strip():
                fence = None
            continue
        if fence is None:
            yield line


def section_lines(lines, title):
    """Read one level-two section through the next same-or-higher-level heading."""
    found = False
    for line in unfenced_lines(lines):
        heading = re.match(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$", line)
        if heading and len(heading.group(1)) <= 2:
            if found:
                break
            found = len(heading.group(1)) == 2 and heading.group(2) == title
        elif found:
            yield line.strip()


def audit_targets():
    """Resolve IDs from live task/draft frontmatter, never from filenames or archive/prose."""
    targets = {}
    for directory in TASK_DIRS + DRAFT_DIRS:
        for path in sorted((ROOT / directory).rglob("*.md")):
            if "archive" in path.relative_to(ROOT / directory).parts:
                continue
            lines = path.read_text(encoding="utf-8").splitlines()
            task_id = next((value for _, value in read_frontmatter(lines).get("id", [])), "")
            if task_id:
                targets[task_id.strip("'\"")] = list(section_lines(lines, "Implementation Notes"))
    return targets


def check_audit_outcomes(name, lines):
    """Validate Done audit structure, not the truth of a fix, rejection or verification."""
    notes = list(section_lines(lines, "Implementation Notes"))
    reports = [line.split(":", 1)[1].strip().strip("`") for line in notes if line.startswith("Audit report:")]
    if not reports:
        return []
    problems = []
    if len(reports) != 1 or not reports[0]:
        problems.append(f"{name}: audit needs exactly one non-empty 'Audit report:' line")

    table, started = [], False
    marker = next((index for index, line in enumerate(notes) if line == "Audit outcomes:"), None)
    if marker is not None:
        for line in notes[marker + 1 :]:
            if not started and not line:
                continue
            if not line.startswith("|"):
                break
            started = True
            table.append(line)
    header = ["#", "Verified", "Outcome", "Evidence"]
    cells = [line[1:-1].split("|") if line.endswith("|") else [] for line in table]
    cells = [[cell.strip() for cell in row] for row in cells]
    if not cells:
        problems.append(f"{name}: Done audit has no 'Audit outcomes:' table")
    elif cells[0] != header:
        problems.append(f"{name}: audit outcomes header must be '# | Verified | Outcome | Evidence'")
    elif len(cells) < 2 or len(cells[1]) != 4 or not all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells[1]):
        problems.append(f"{name}: audit outcomes table needs a four-cell separator")
    elif len(cells) == 2:
        problems.append(f"{name}: audit outcomes table is empty")

    targets, ids = None, set()
    for row in cells[2:] if cells and cells[0] == header else []:
        if len(row) != len(header):
            problems.append(f"{name}: audit outcome row has wrong cell count (expected 4)")
            continue
        finding, verified, outcome, evidence = row
        prefix = f"{name}: audit finding {finding}"
        if not re.fullmatch(r"[0-9]+", finding) or int(finding) < 1:
            problems.append(f"{prefix}: finding number must be a positive integer")
        elif int(finding) in ids:
            problems.append(f"{prefix}: duplicate finding number")
        else:
            ids.add(int(finding))
        if verified not in ("yes", "no"):
            problems.append(f"{prefix}: Verified must be yes or no")
        if outcome not in ("fixed", "rejected", "linked", "asked"):
            problems.append(f"{prefix}: invalid Outcome '{outcome}'")
        elif outcome == "fixed":
            if not re.fullmatch(r"[0-9a-fA-F]{7,40}|\S+:[1-9][0-9]*", evidence):
                problems.append(f"{prefix}: fixed needs a 7-40 hex commit hash or path:line")
        elif outcome == "rejected":
            if len(evidence.split()) < 3:
                problems.append(f"{prefix}: rejected needs a reason of at least three words")
        else:
            if targets is None:
                targets = audit_targets()
            if evidence not in targets:
                problems.append(f"{prefix}: {outcome} needs an existing task or draft ID (not archived)")
                continue
            if outcome == "asked":
                target = targets[evidence]
                needs = [
                    match.group(1).strip()
                    for line in target
                    for match in [re.match(r"Needs owner(?:\s*\([^)]*\))?:(.*)$", line)]
                    if match
                ]
                if not any(value.lower() not in ("", "none", "nothing", "yok", "-", "?", "n/a") for value in needs):
                    problems.append(f"{prefix}: asked target {evidence} needs a non-empty 'Needs owner:' line")
                reviews = [line.split(":", 1)[1].strip() for line in target if line.startswith("Review by:")]
                review = reviews[-1].split("·") if reviews else []
                valid_date = False
                if review and DATE.fullmatch(review[0].strip()):
                    try:
                        date.fromisoformat(review[0].strip())
                        valid_date = True
                    except ValueError:
                        pass
                if len(review) != 3 or not valid_date or not all(part.strip() for part in review[1:]):
                    problems.append(
                        f"{prefix}: asked target {evidence} needs 'Review by: YYYY-MM-DD · owner · condition'"
                    )

    if reports[0]:
        report = ROOT / reports[0]
        if report.is_file():
            findings = {
                int(match.group(1))
                for line in section_lines(report.read_text(encoding="utf-8").splitlines(), "Findings")
                for match in [re.match(r"^\|\s*([0-9]+)\s*\|", line)]
                if match
            }
            for finding in sorted(findings - ids):
                problems.append(f"{name}: report finding {finding} has no audit outcome row")
        else:
            print(f"Info: {name}: audit report missing: {reports[0]}; coverage skipped (row checks still run)")
    return problems


def stale_flags(path):
    """Docs that declare `describes` are stale when the described paths changed after `reviewed`."""
    fields = read_frontmatter(path.read_text(encoding="utf-8").splitlines())
    globs = [value for _, value in fields.get("describes", [])]
    if not globs:
        return []
    reviewed = next((value for _, value in fields.get("reviewed", [])), None)
    if not reviewed:
        return [
            f"{rel(path)}: describes code but has no reviewed: commit or date\n"
            f"    → read the doc against the code, then set reviewed:"
        ]
    since = [f"--since={reviewed}T23:59:59"] if DATE.match(reviewed) else [f"{reviewed}..HEAD"]
    try:
        commits = git("log", "--format=%h", *since, "--", *globs).split()
    except subprocess.CalledProcessError:
        return [
            f"{rel(path)}: reviewed: {reviewed} is not a commit git knows\n"
            f"    → set reviewed: to a commit hash or a YYYY-MM-DD date"
        ]
    if not commits:
        return []
    return [
        f"{rel(path)}: {', '.join(globs)} changed in {len(commits)} commit(s) since {reviewed}\n"
        f"    → reread the doc against the code; update the text if needed, then set reviewed: {commits[0]}"
    ]


def markdown_files():
    for path in sorted(ROOT.rglob("*.md")):
        parts = path.relative_to(ROOT).parts
        if not SKIP_DIRS.intersection(parts) and not any(parts[: len(p)] == p for p in SKIP_PREFIXES):
            yield path


def staged_markdown_files():
    """Docs in the commit. A changed decision log pulls in every doc, since any of them may depend on it."""
    staged = {
        ROOT / name
        for name in git("diff", "--cached", "--name-only", "--diff-filter=ACMR").splitlines()
        if name.endswith(".md")
    }
    if DECISIONS in staged or (DECISION_DIR and any(DECISION_DIR in path.parents for path in staged)):
        return list(markdown_files())
    return [path for path in markdown_files() if path in staged]


def main():
    sys.stdout.reconfigure(encoding="utf-8")

    if "--stale" in sys.argv:
        docs = list(markdown_files())
        covered = [
            path for path in docs if read_frontmatter(path.read_text(encoding="utf-8").splitlines()).get("describes")
        ]
        flags = [flag for path in covered for flag in stale_flags(path)]
        for flag in flags:
            print(flag)
        print(f"\n{len(flags)} docs may be stale" if flags else "No stale docs")
        print(
            f"Coverage: {len(covered)} of {len(docs)} docs declare `describes:`; the others are not checked for staleness."
        )
        return 0

    if "--write-index" in sys.argv:
        if decision_files():
            write_index()
        write_catalogue()
        return 0

    decisions, problems = load_decisions()
    problems += check_index()
    problems += check_worklogs()
    problems += check_catalogue()
    files = staged_markdown_files() if "--staged" in sys.argv else markdown_files()
    for path in files:
        problems += check_file(path, decisions)

    for problem in problems:
        print(problem)
    bad_files = len({p.split(":")[0] for p in problems})
    print(f"\n{len(problems)} problems in {bad_files} files" if problems else "No problems found")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
