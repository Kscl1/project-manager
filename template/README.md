# Project package

`template/.pm/` is the work system that the installer copies into a project's `.pm/`, without taking over the product's `docs/`, `tools/` or `tests/`. Root `AGENTS.md`, `CLAUDE.md` and `backlog.config.yml` are adapters: they point your agent at those files.

You do not need to read this folder by hand; your agent does. Everything here is plain Markdown and Python, so you can open any file when you want to check what the agent was told.

## Install

The step-by-step first install is in the root `README.md`. The general form:

```text
python <source>/.pm/tools/pm_init.py <target> [--name NAME] [--map] [--swarm] [--check | --keep-existing]
python <source>/.pm/tools/pm_init.py <target> --upgrade [--dry-run]
python <target>/.pm/tools/pm_check.py
```

`<source>` is the folder that holds the package's `.pm/`: this repo's `template/` folder (so the script is `template/.pm/tools/pm_init.py`), or any project that already has `.pm/`. `<target>` is your project folder; keep the source clone outside `<target>`.

- **First install.** It fills missing root adapters, points `core.hooksPath` at `.pm/hooks` and stages the hooks as executable, copies the `pm-*` skills to `.agents/skills/` (with a pointer in `.claude/skills/` for each, since Claude Code reads only that folder), adds the ignore rules, and writes `.claude/settings.json` and `.mcp.json` only when they are missing. `--map` adds LikeC4; `--swarm` adds `.pm/swarm/` with its runner and tests. It prints its plan before writing; `--check` stops after the plan (exit 0, or 3 on conflicts).
- **Upgrade.** Repeat the command with `--upgrade` to refresh **package files** only. It compares them with the hash manifest written at install, backs up what it replaces under `.pm/local/backup/<timestamp>/`, and leaves project data (`.pm/backlog/`, `decisions.md`, `decisions/`, `worklog/`, `specs/`, `charter.md`, `lessons.md`) untouched. Read `--dry-run` before the real run; there is no automatic merge.
- **What it never touches.** It never rewrites a file of yours: it only appends lines to `.gitignore`, `.gitattributes` and `.ignore`. Your own `AGENTS.md`, `CLAUDE.md`, Backlog.md, git hooks, `.claude/settings.json` and `.mcp.json` are kept, and it never sets or changes `core.hooksPath` while the project has hooks of its own.
- **On a conflict.** Exit 3 means the project has its own agent rules, hooks or settings. Nothing is written; run again with `--keep-existing` to install and keep yours, then read `.pm/local/merge-by-hand.md`, which the `pm-setup` skill walks through with you. A second run changes nothing.

## Daily entry points

```bash
python .pm/tools/pm_board.py --resume          # git and active-task handoff
python .pm/tools/pm_board.py --resume --brief  # the same as a one-minute briefing for you
python .pm/tools/pm_board.py --tree            # Epic → package → leaf
backlog browser                                # create and edit tasks
python .pm/tools/pm_check.py --stale          # doc freshness hints
python -m unittest discover -s .pm/tests      # the package's own tests
```

Edit task fields in Backlog's browser; documents are plain Markdown, read in any editor. `--resume` and `--tree` are board interfaces; verify the installed version supports them. `--resume` also lists Ready tasks by name and, when the GitHub CLI is installed, the open pull requests of this repo (if it has a GitHub remote) and of each `owner/repo` line in an optional `.pm/pr-repos.txt`.

See `.pm/README.md` for the package/data ownership table and roles. `pm_check` in the git pre-commit hook checks doc consistency; a clean result does not prove the docs are true.
