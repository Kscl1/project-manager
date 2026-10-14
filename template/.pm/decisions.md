# Decisions

The index of this project's decisions. Each decision is one file, `.pm/decisions/D-01.md`, with a stable ID that other
docs cite; its fields are in `.pm/templates/decision.md`. A replaced decision moves to `.pm/decisions/archive/` and names
its replacement and why it was dropped. Never delete one. After adding or moving a file, run
`python .pm/tools/pm_check.py --write-index`; the part below is generated.

- Living docs list the decisions they rely on in frontmatter: `depends_on: [D-01]`.
- When a decision changes, search for its ID and review every file that cites it.

<!-- decision-index:begin -->
<!-- decision-index:end -->
