# Project package

`template/.pm/` is the portable work system; the installer puts it in each project's `.pm/` without taking over the product's `docs/`, `tools/` or `tests/`. Root `AGENTS.md`, `CLAUDE.md` and `backlog.config.yml` are adapters; the task data, worklog, decisions and specs live inside `.pm/` (D-47–D-49).

## Install

The step-by-step first install is in the root `README.md`. The general form:

```text
python <source>/.pm/tools/pm_init.py <target> [--name NAME] [--upgrade [--dry-run]]
python <target>/.pm/tools/pm_check.py
```

`<source>` is the folder that holds the package's `.pm/`: this repo's `template/` folder (so the script is `template/.pm/tools/pm_init.py`), or any project that already has `.pm/`. `<target>` is your project folder; it should be a git repository (run `git init` first), otherwise the installer cannot set the hooks path. Keep the source clone outside `<target>`. Bracketed flags are optional; `--dry-run` works only with `--upgrade`. The installer fills missing root adapters and sets `core.hooksPath` to `.pm/hooks`. It adds ignore rules for `.pm/local/`, `.pm-report.md` and `.worktrees/`. Review any existing root `AGENTS.md` for compatibility: the installer does not overwrite it.

For an existing project, repeat the command with `--upgrade` to refresh **package files** only. Project data (`.pm/backlog/`, `decisions.md`, `decisions/`, `worklog/`, `specs/`, `charter.md`, `lessons.md`) must remain untouched. The upgrade compares package files with the hash manifest written at install and backs up the old ones; there is no automatic merge, so inspect local customizations to package files before upgrading.

## Daily entry points

```bash
python .pm/tools/pm_board.py --resume          # git and active-task handoff
python .pm/tools/pm_board.py --tree            # Epic → package → leaf
backlog browser                                # create and edit tasks
python .pm/tools/pm_check.py --stale          # doc freshness hints
```

Edit task fields in Backlog's browser; documents are plain Markdown, read in any editor (D-98). `--resume` and `--tree` are board interfaces (D-45, D-51); verify the installed version supports them.

See `.pm/README.md` for the package/data ownership table and roles. `pm_check` in the git pre-commit hook checks doc consistency; a clean result does not prove the docs are true.
