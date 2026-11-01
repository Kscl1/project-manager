# Project charter: <project name>

The entry door of the project file: why the project exists, what it will not do, how it is accepted, and where every other answer lives. The lead writes it; the owner confirms intent and acceptance. Review the charter under the risk rule in the lead card, step 7. Copy into `.pm/charter.md` only when missing, then keep it as project data.

**Status:** Draft · version 0.1 (<date>) · owner approval pending

## Where is the answer?

Every question gets an answer here, a link to its single home, or a named open item with an owner and a decision point. Cite decision IDs; never restate their reasons.

| Question | Part | Home | Maintained by | Update when | Check |
|---|---|---|---|---|---|
| Why, what is out, how is it accepted? | Charter | this file | lead writes, owner approves | scope or acceptance changes | reading test when a milestone closes |
| How is the system built? | Blueprint | `<product docs path>` | lead | a part, interface or data shape changes | compared with the code when a milestone closes |
| What exactly must an Epic do? | Requirements | `.pm/specs/<epic>/requirements.md` | lead with owner | behaviour changes | each acceptance scenario has a test |
| Why this choice? | Decisions | `.pm/decisions/` (index `.pm/decisions.md`) | owner decides, lead writes | a new choice is made | new file, archive the old one, `rg "D-xx"`, reread, `pm_check --write-index` |
| How is code and text written? | Standards | `AGENTS.md`, `<linters / CI>` | lead | a new rule or lesson | pre-commit hook, tests |
| What is next, who does it? | Plan and tasks | `.pm/backlog/` | lead | every meaningful step | `pm_board --resume` |
| Does it really work? | Evidence | `<tests>`, the task's Final Summary; `.pm/worklog/` only for a session that spans several goals | worker and lead | every delivery | test output |
| What did we learn? | Lessons | `.pm/lessons.md` | lead | every mistake | — |

**Open items:** <item · owner · decision point, or "none">

Skip a row only with one line saying why (for example "no product code yet").

## Why and for whom

<One paragraph: the problem, users and desired outcome.>

## Boundaries

- In: <what this project owns>
- Out: <what it explicitly will not do>
- Existing constraints: <interfaces, privacy or deployment limits>

## Acceptance scenarios

Each carries a readiness level: Draft → Intent approved → Ready to implement → Verified (with the evidence path).

1. Given <state>, when <action>, then <observable result>. *[Draft]*
2. Given <interruption/failure>, when <recovery>, then <observable result>. *[Draft]*

## Review gate

Mark a gate passed only when it was actually done. Otherwise leave it pending with an owner and a review point. A lead self-check is not an independent review.

- Owner: <intent and acceptance confirmed, with date or link; or pending · owner · review point>
- Review: <`Review: lead self-check` and evidence for low-risk work; or independent reviewer, family, result and evidence when step 7 requires it; or pending · owner · review point>
- Reading test: <date, model and result link; or pending · owner · review point>
- Open product choice: <owner decision needed, or none>

## Self-check before approval

1. What will this project not do?
2. Which observation proves the first acceptance scenario?
3. If a decision changes, which single record do I update?
