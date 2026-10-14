# <project name>

Project-specific product rules belong here; the portable work system lives in `.pm/README.md`. This repo tracks its PM layer in git.

## Start here

Workers: skip this list. Your brief is your whole world; see .pm/roles/worker.md.

1. `python .pm/tools/pm_board.py --resume` — compare active task notes with git, worktrees and reports; do not trust an old transcript.
2. `.pm/charter.md` — project intent, acceptance and where every answer lives (D-62).
3. `.pm/decisions.md` — relevant decision IDs, not a second copy of their text.
4. `.pm/README.md` and the relevant Epic requirements in `.pm/specs/<epic>/`.

The **lead** creates and closes scoped Backlog tasks with acceptance criteria and evidence. **Workers never create or edit Backlog tasks; they report to the lead.** The lead uses `backlog browser` to inspect or edit tasks. Product docs stay in `docs/`, not Backlog's doc/decision commands. Run `python .pm/tools/pm_check.py` before committing docs, and do not bypass hooks.

When the package itself misbehaves (a `.pm/` tool, rule, role card or template, not this project's code), do not patch `.pm/` here: write a report from `.pm/templates/feedback.md` into `.pm/local/feedback/` and tell the owner, who carries it to the package's home project.
