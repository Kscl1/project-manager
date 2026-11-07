# Decisions

The index of this project's decisions. Each decision is one file, `.pm/decisions/D-01.md`, with a stable ID that other
docs cite; its fields are in `.pm/templates/decision.md`. A replaced decision moves to `.pm/decisions/archive/` and names
its replacement and why it was dropped. Never delete one. After adding or moving a file, run
`python .pm/tools/pm_check.py --write-index`; the part below is generated.

- Living docs cite decisions by ID in their text; `pm_check` warns when one cites a replaced decision as if it were
  in force. A line that is history names the replacement or carries a dated *(Update: ...)* note. A doc may also list
  the decisions it rests on in frontmatter (`depends_on: [D-01]`); `pm_check` checks that list too.
- When a decision changes, search for its ID and review every file that cites it.

<!-- decision-index:begin -->
<!-- decision-index:end -->
