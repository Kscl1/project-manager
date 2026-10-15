# project-manager

A small, file-based way to run software projects with a mix of AI models: one strong model leads, cheap fast models do scoped work, a model from another family reviews, and plain scripts keep the docs honest.

It is not a framework or a harness. It is a folder of conventions (`.pm/`), one dependency-free check (`.pm/tools/pm_check.py`) and a git hook, installed by `.pm/tools/pm_init.py`.

## What you get

- **`.pm/`** — role cards (lead, worker, test-writer, reviewer), a one-table model map, brief and report formats, five working principles, and a decision log with stable IDs.
- **`.pm/tools/pm_check.py`** — fails when a doc depends on a superseded decision, links to a missing file, or grows past a size limit. `--stale` lists docs whose described code changed since they were last reviewed, without blocking anything.
- **A pre-commit hook** that runs the consistency check, and **a CI workflow** that runs the package tests.

## Ideas it borrows

- [pstack](https://github.com/cursor/plugins/tree/main/pstack) (MIT): briefs, verification first, depth over breadth.
- OpenAI's [harness engineering](https://openai.com/index/harness-engineering/) write-up: a short map instead of a long manual, rules as checks instead of prose.
- [Doorstop](https://github.com/doorstop-dev/doorstop) and [kontext](https://github.com/patkusch/kontext): docs as claims that can be checked against git.

## Install

You need Python 3.11 or newer, Git, and the [Backlog.md](https://github.com/MrLesk/Backlog.md) CLI 1.52 or newer (`npm i -g backlog.md`, which needs Node.js). On Windows, use `python`; the `python3` alias there is a stub.

1. Clone this repo **next to** your project, not inside it:

   ```bash
   git clone https://github.com/Kscl1/project-manager.git
   ```

2. Your project must be a git repository. For a new project, create the folder and run `git init` in it first.

3. From your project folder, install the package and check it:

   ```bash
   python ../project-manager/template/.pm/tools/pm_init.py . --name my-project
   python .pm/tools/pm_check.py
   ```

   `--name` is your project's name; without it the folder name is used. The installer copies `template/.pm/` to `.pm/`, writes `AGENTS.md`, `CLAUDE.md` and `backlog.config.yml` if they are missing, and sets git's hooks path to `.pm/hooks`. `pm_check` should print `No problems found`.

4. Open your first task. Use `backlog browser`, or the command line:

   ```bash
   backlog task create "Add a hello script" --type task --ac "python hello.py prints hello" --ac "README says how to run it"
   ```

   Tasks are Markdown files in `.pm/backlog/tasks/`. Each `--ac` adds one acceptance criterion; `pm_check` needs every open task to have a `--type` (`epic`, `package`, `task` or `bug`).

5. Commit. The pre-commit hook runs `pm_check` on staged docs.

Then read `.pm/README.md` in your project. Upgrades and installs into an existing project are covered in this repo's `template/README.md`.

## Status

Early and changing. Expect breaking changes.

## Licence and support

MIT, see `LICENSE`. Support is experimental and best effort, with no promised response time.
