# Project package

`template/.pm/` is the portable work system; the installer puts it in each project's `.pm/` without taking over the product's `docs/`, `tools/` or `tests/`. Root `AGENTS.md`, `CLAUDE.md` and `backlog.config.yml` are adapters; the task data, worklog, decisions and specs live inside `.pm/`.

## Install

The step-by-step first install is in the root `README.md`. The general form:

```text
python <source>/.pm/tools/pm_init.py <target> [--name NAME] [--map] [--swarm] [--check | --keep-existing]
python <source>/.pm/tools/pm_init.py <target> --upgrade [--dry-run]
python <target>/.pm/tools/pm_check.py
```

`<source>` is the folder that holds the package's `.pm/`: this repo's `template/` folder (so the script is `template/.pm/tools/pm_init.py`), or any project that already has `.pm/`. `<target>` is your project folder; it should be a git repository (run `git init` first), otherwise the installer cannot set the hooks path. Keep the source clone outside `<target>`. Bracketed flags are optional; `--dry-run` works only with `--upgrade`. The installer fills missing root adapters and sets `core.hooksPath` to `.pm/hooks` and stages the hooks as executable. It copies the package's skills (`template/.agents/skills/pm-*`) into `.agents/skills/` and writes a pointer to each in `.claude/skills/`, since Claude Code reads only that folder; the project's own skills are left alone. It adds ignore rules for `.pm/local/`, `.pm-report.md` and `.worktrees/`. It writes `.claude/settings.json` (a SessionStart hook that runs `pm_board.py --resume` at start and after a compaction) and `.mcp.json` (Context7; LikeC4 with `--map`) only when they are missing. It prints its plan before writing; `--check` stops there (exit 0, or 3 on conflicts). A first install into a project with its own `AGENTS.md`, `CLAUDE.md`, Backlog.md or git hooks stops with exit 3 and writes nothing; `--keep-existing` installs and keeps them. The installer never rewrites an existing file of the user's (it only appends lines to `.gitignore` and `.gitattributes`), so `--map` on a project that already has `.mcp.json` lists LikeC4 instead of adding it. `--swarm` also copies `.pm/swarm/`: `pm_run.py`, which runs worker jobs as visible Herdr agents and checks their output, and its tests; it needs Herdr, and later upgrades keep it current. It never sets or changes `core.hooksPath` while the project has hooks of its own, on any run. What it could not add goes to `.pm/local/merge-by-hand.md`, which the `pm-setup` skill walks with the user. A second run changes nothing.

For an existing project, repeat the command with `--upgrade` to refresh **package files** only. Project data (`.pm/backlog/`, `decisions.md`, `decisions/`, `worklog/`, `specs/`, `charter.md`, `lessons.md`) must remain untouched. The upgrade compares package files with the hash manifest written at install and backs up the old ones; there is no automatic merge, so inspect local customizations to package files before upgrading.

## Daily entry points

```bash
python .pm/tools/pm_board.py --resume          # git and active-task handoff
python .pm/tools/pm_board.py --tree            # Epic → package → leaf
backlog browser                                # create and edit tasks
python .pm/tools/pm_check.py --stale          # doc freshness hints
python -m unittest discover -s .pm/tests      # the package's own tests
```

Edit task fields in Backlog's browser; documents are plain Markdown, read in any editor. `--resume` and `--tree` are board interfaces; verify the installed version supports them.

See `.pm/README.md` for the package/data ownership table and roles. `pm_check` in the git pre-commit hook checks doc consistency; a clean result does not prove the docs are true.
