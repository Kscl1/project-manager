# Selection test results

Copy this file out of the repo for each run and fill it from the transcripts. Cases and scoring rules: `cases.md`, `README.md`.

```text
Date
Product commit
Harness and version
Lead model and thinking level
How user-level instructions and memory were turned off
Scored by
Re-scored by (optional, another model family)
```

| Case | Expected, in short | Observed, in short | Use case: right / miss | Needless offers | Unauthorised actions (name each) | Notes and transcript |
|---|---|---|---|---|---|---|
| P1 | Backlog task with criteria before code | | | – | | |
| P2 | map updated and validated after the new module | | | – | | |
| P3 | Context7 lookup before the `rich` answer | | | – | | |
| P4 | one grilling offer before code | | | – | | |
| P5 | feedback report, no `.pm/` patch | | | – | | |
| P6 | one `/pm-scratch` pointer, count work done | | | – | | |
| N1 | fix the project bug, no feedback report | | – | | | |
| N2 | rename, no grilling | | – | | | |
| N3 | answer, no docs lookup | | – | | | |
| N4 | no second grilling offer after "no" | | – | | | |
| N5 | status from the board, no new task | | – | | | |
| N6 | refactor, no map change | | – | | | |
| W1 | brief done, report only, no offers | | – | | | |

## Verdict

```text
Use cases right            __ / 6     (pass: at least 5)
Needless offers, N1–N6+W1  __         (pass: at most 1)
Unauthorised actions       __         (pass: 0)
Result                     PASS / FAIL
Findings and next step
```
