# .pm

You do not need to read this folder by hand; your agent does.

The project's work system, installed inside its own repository. Start at the root `AGENTS.md`, then open only the file your task needs.

| Need | Open |
|---|---|
| Work or task details | `backlog browser` (`.pm/backlog/tasks/` is the data) |
| Lanes, WIP, hierarchy | `board.md` |
| Resume an interrupted session | `python .pm/tools/pm_board.py --resume`, then the active task |
| What to do now | `python .pm/tools/pm_board.py --next` |
| Project intent and Epic scope | `charter.md` if it exists, then `specs/<epic>/requirements.md` if it exists |
| Roles and delegation | `roles/lead.md`, `roles/worker.md`, `templates/brief.md`, `templates/report.md`, `templates/doc-audit.md` |
| Model assignment and design principles | `models.md`, `principles.md` |
| Why a choice was made | `decisions/`, one file per decision; `decisions.md` is the index (cite IDs; do not copy decisions) |

## Ownership and upgrades

| Kind | Files in an installed project | On upgrade |
|---|---|---|
| Package | `.pm/roles/`, `templates/`, `tools/`, `tests/`, `hooks/`, `swarm/` (with `--swarm`) | Replaced by the package version. Keep project-specific changes out of these directories. |
| Version stamp | `.pm/VERSION`, `.pm/package-files.sha256` | Rewritten on every install and upgrade: the package commit, and each package file's hash as installed. `--upgrade --dry-run` uses the hashes to say which side changed a file. |
| Seed | `.pm/README.md`, `board.md`, `principles.md`, `models.md` | Written once if missing; then owned by the project and kept on upgrade. |
| Project data | `.pm/charter.md`, `decisions.md`, `decisions/`, `lessons.md` (started with the first lesson; the installer does not create it), `specs/`, `backlog/`, `worklog/` | Never overwritten. |

| Root adapters | `AGENTS.md`, `CLAUDE.md`, `backlog.config.yml` | Written only when absent. Review an existing file manually. |
| Claude Desktop previews | `.claude/launch.json`: the board, and the map with `--map` | Written only when absent. A missing entry is listed for `/pm-setup`. |
| Machine-local | `.pm/local/`, worker `.pm-report.md` files, `.worktrees/` | Not distributed or committed. |

A worklog starts with frontmatter: `type: worklog`, `title`, `date` (the date in its file name), `task` and `models` as lists, or `kayıtta yok` / `not recorded`. Once one worklog has it, `pm_check` requires it of all.

The package lives in git, including tasks, decisions, specs and delivery records. Ignore only `.pm/local/`, `.pm-report.md`, `.worktrees/` and `__pycache__/`, the rules the installer adds. Product code, tests and living product docs stay in the product's own directories. Do not use `backlog decision` or `backlog doc`: decisions live in `.pm/decisions/`, one file each with `.pm/decisions.md` as the index, product documentation in `docs/`. Backlog may recreate empty internal directories; they are not extra sources of truth.

## Install and use

From a source project with the package installed, run:

```text
python <source>/.pm/tools/pm_init.py <target> [--name NAME] [--upgrade]
python <target>/.pm/tools/pm_check.py
```

Omit `--name` to use the target folder name. To refresh package files later, run the same install command with `--upgrade`; inspect local changes to package files first. The upgrade compares package files with the hash manifest written at install (`package-files.sha256`) and backs up the old ones; there is no automatic merge. The installer sets `core.hooksPath` to `.pm/hooks` only when no hooks path is set and the project has no hooks of its own, adds root adapters only if absent, and the local ignore rules. Run from the target repo afterwards:

```bash
python .pm/tools/pm_board.py --next      # the one task to work on now
python .pm/tools/pm_board.py --resume
python .pm/tools/pm_board.py --tree
python .pm/tools/pm_board.py --did      # the Did part of a worklog for a session that spans several goals
backlog browser
python .pm/tools/pm_check.py --stale
python -m unittest discover -s .pm/tests   # the package's own tests, standard library only
python -m unittest discover -s .pm/swarm   # with --swarm: pm_run against a fake Herdr, about 80 s
```

`--next`, `--tree` and `--resume` must exist in your installed package version before you rely on them. Edit tasks in Backlog's browser; documents are plain Markdown, read in any editor.

## When the package misbehaves

Do not patch package files in a project. Run the `pm-feedback` skill (or `python .pm/tools/pm_feedback.py`): it writes a diagnosis-only report from `.pm/templates/feedback.md` into `.pm/local/feedback/`, shows it to the owner and, only on their yes, opens an issue in the package's home project, which triages and fixes it in `template/.pm/`.

## Everyone

- One home per fact: link to a task, decision or code instead of keeping another status list.
- Stay inside your brief's scope. Report out-of-scope findings rather than changing them.
- Close with a command result, commit or measurement, not an agent's assertion.
- If the brief or check is unclear, stop and report `BLOCKED`. Never bypass hooks.
