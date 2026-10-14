# Report: <task ID and title>

Use these headings exactly. Paste the decisive line of each check, not a full transcript. Do not guess your model's name; the lead reads identity and cost from the harness run record.

```text
STATUS      DONE | BLOCKED | PARTIAL
BRANCH      <branch and commit SHA, or uncommitted>
CHANGED     <paths and what changed, in two or three sentences>
RAN         <each VERIFY command, exit code and decisive output; name skipped checks>
REPRO       <the check that failed before your change and passes after it, or "none: <why>">
NO-REGRESS  <what else you re-ran green after the change>
NOT COVERED <behaviour no check exercised; say it plainly>
DEVIATIONS  <anything outside the brief, or none>
DOC IMPACT  <living docs/decisions affected; do not edit them unless assigned lead>
FOLLOW-UPS  <out-of-scope work, or none>
COST        <tokens/cost from harness if available; otherwise unavailable>
```

Evidence means a command you ran in this session and its output, not a recollection or a plan. If `PARTIAL` or `BLOCKED`, say the **next concrete step** and the last observed result. Repeating an unchanged command is not progress. A lead transfers that next step into the Backlog task's live block.
