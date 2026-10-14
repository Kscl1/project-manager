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

See `template/README.md`.

## Status

Early and changing. Expect breaking changes.

## Licence and support

MIT, see `LICENSE`. Support is experimental and best effort, with no promised response time.
