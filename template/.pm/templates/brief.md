# Brief: <leaf task ID and title>

Fill each field before giving a leaf to a worker who has not seen this chat. Paste concrete upstream findings, not a transcript. The brief and its acceptance checks are the contract.

```text
GOAL        <One observable outcome, in one sentence.>
SCOPE       <Exact writable paths, branch and worktree; say which files cannot be touched.>
CONTEXT     <Files, decisions, inputs and upstream results the worker needs.>
ACCEPTANCE  <Numbered, checkable expected outputs with literal examples, edge cases and format.>
ENV         <Runtime, dependency and tool versions that matter.>
VERIFY      <Exact commands, cwd, expected pass signal and known traps; do not repeat without a changed input.>
FORBIDDEN   <Other paths, unrelated fixes, destructive operations, unapproved commits or network calls.>
TIMEBOX     <Time or turn ceiling; on expiry stop and return PARTIAL with the last command and result.>
REPORT      <Use templates/report.md, including STATUS, changed paths, exact check results and deviations.>
TOOLS       The "Lead only" tool table in root AGENTS.md does not apply to you; use only what this brief allows.
```

Before dispatch, answer three questions: **What exact shape is the output? What should the worker do if a check repeats or stalls? Where should the result be written?** Ambiguity here made pilot workers differ on T2; one repeated commands for 63 turns. A missing acceptance example is a scoping problem, not a worker's invitation to guess. Model identity is taken from the run record, not a name the worker puts in the report.

For a tiny change, shorten the prose, not the goal/scope/check/report contract.
