# Task live block

Put this **entire block** in the task's `Implementation Notes` using `backlog task edit <id> --notes "..."`. Pass actual newline characters in the argument (the literal characters `\n` stay literal); use your shell's multiline-string syntax. Rewrite the entire notes value after each meaningful step and commit; do not append a second block. Keep the five prefixes and their order exact so `pm_board --resume` can read them. Use one line per field; do not put extra prose inside the block. `Next` is only the next action and `Evidence` only the latest proof, each at most 300 characters (`pm_check` blocks longer ones in an open task); history goes to a dated note below the block, so the block never repeats it.

```text
Next: <next concrete action>
Evidence: <latest short commit SHA, test result, or "none yet">
Blocker: <blocker or "none">
Needs owner: <what only the owner can provide, or "nothing">
Worker: <model> · <worktree path> · <report path>
```

Omit **only** `Worker:` when no worker has the task. Several `Worker:` lines are allowed: **one line per running worker**. A `Worker:` line means the worker was started, not merely planned, and it identifies an assigned worktree and expected report, **not** proof of a live process. Compare the block with git status, the worktree and the report on session pickup. `Needs owner: nothing` is compatible with `Active`; move a task to `Owner check` only for the narrow gate described in `board.md`. The task's closing summary (and, for a session that spans several goals, the worklog) records a delivery, not this live state.

Two more lines for held work. A Ready task or draft kept waiting on purpose carries, from the start, `Review by: <YYYY-MM-DD> · <owner> · <condition>`; the condition names a task, a decision or a date, never "when the phase starts". Add `Reviewed: <YYYY-MM-DD>` only after a real review (keep, merge or cancel decided); a plain note does not count, and `pm_board --resume` measures age from this date. An audit task also carries `Audit report: <path>` and, after a line `Audit outcomes:`, a table `| # | Verified | Outcome | Evidence |` with one row per finding. `pm_check` checks the shape (outcome, evidence format, existing target), not that a fix is real; without the local raw report it cannot check that every finding has a row.
