# The board

Backlog.md owns task data in `.pm/backlog/tasks/`; its browser (`backlog browser`) is the task screen. Use `python .pm/tools/pm_board.py --tree` for the terminal Epic tree. No second editable board.

## Shape and lanes

An **Epic** (`type: epic`) contains **packages** (`type: package`), which contain **leaf tasks** (`type: task`; bugs may use `bug`). Use Backlog's `parent` relation, not a directory tree:

```bash
backlog task create "Leaf outcome" -p <package-id> --type task --ac "Checkable result"
```

Give small-model workers a scoped leaf brief, not an entire Epic. Use `dependencies` for ordering across tasks. A `milestone` is a finite goal that several separate pieces of work reach together; if one Epic or task reaches it, open none. Open one only when its finish sentence and proof can be written; the lead proposes, the owner's yes opens it, and both live only in the milestone's description. Only the top-level tasks or packages the finish needs join (not an Epic that also holds later goals), the proof task included; an idea the finish does not need flows outside. It closes when its tasks are Done and the proof holds, with a reading test of the charter, and is never reopened: later work in the same area flows without one or under a new goal. An abandoned goal gets 'abandoned because ...' in its description, loses its open tasks and is archived, never marked Done. How many may be open at once and whether they carry a due date is the project's choice. An area that never ends (the template, the machine layer) is a label on top-level tasks; each project writes its own area labels. It is not a capacity or WIP limit.

```text
Ready → Active → Owner check → Done
```

- **Ready:** acceptance criteria make the task actionable.
- **Active:** someone is doing the work, including the review by a different model family; its `Implementation Notes` has a current live block.
- **Owner check:** only a code change immediately before merge, or an action only the owner can do. Evidence-backed research or discussion goes straight to `Done`.
- **Done:** final summary names evidence. Keep `Done` **last** in Backlog's configured status list; Backlog treats the last status as complete.

Count open top-level work (an Epic, a package, or a task with no parent) in `Active` or `Owner check`: at most **7**, plus **1** with label `urgent`; sub-tasks are not counted. When fewer than two tasks are Ready, `pm_board` prints a planning reminder. Review work is still work.

## Use native task fields

| Meaning | Backlog location |
|---|---|
| Outcome and done condition | Description and checkable acceptance criteria |
| Epic/package/leaf | `parent_task_id` (created with `-p`) |
| Kind of work | `type`: every open task has one; `pm_check` flags a missing type |
| Order and real blockers | `ordinal`, `dependencies` (only when B cannot start before A is done) |
| Importance | `priority` (high, medium, low): set only by the owner, on drafts and Ready tasks; empty means not triaged yet; `backlog task list --sort priority` |
| Which lead holds it now | `assignee` on every `Active` or `Owner check` task: the one lead holding it, changed on handoff; who touched it comes from git (`Refs:` and `Assisted-by:` lines) |
| Plan the owner approves | `Implementation Plan`, for multi-step or code-changing work |
| Owner's words, options offered, dated findings | `Comments` (author `@<owner>` or the lead) |
| Links to decisions, research, reports, evidence | `References` (not `Documentation`); commit hashes are not listed by hand, `git log --grep "<task ID>"` finds them |
| Finite goal several tasks reach together | `milestone` |
| Area that never ends | area label (the project's own list in `backlog.config.yml`) |
| Expedite | `urgent` label |
| Next action, evidence and blocker | `Implementation Notes` live block; see `templates/live-block.md` |
| Final proof | Final task summary: evidence, `Doc impact:`, and three short lines (what the owner said, what was found, what comes next) |
| Changed files | git: commits carry `Refs: <task ID>` |

Not used: `modified_files`, `documentation`. Backlog does not preserve unknown frontmatter. Do not invent task fields or duplicate status in project docs. The lead rewrites the full live block using `backlog task edit <id> --notes "..."` after meaningful progress and commits; it is not an end-of-session ritual.
