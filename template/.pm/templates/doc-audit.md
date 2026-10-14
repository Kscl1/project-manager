# Brief: doc truth audit

The lead gives this brief to a cheap worker model. The worker reads, compares and reports; it never edits. The lead verifies every finding before anything is changed or shown to the owner, because a clean `pm_check` means consistent, not correct.

Two kinds, same brief:

- **delivery:** before a delivery closes. Audits only the living docs and decision cites the delivered change touched; the lead lists them in the brief.
- **weekly:** when `pm_board --resume` says the weekly check is due, or any time the owner or lead asks (for example after a heavy day). Audits the living docs plus the extra scope below. A second worker from another model family runs `decision-audit.md` at the same time.

Fill `<kind>` and `<date>`, then launch a worker as in `roles/lead.md` (visible, watched) with this brief and the line "Kind: <kind>. Date: <date>. Do the task in the attached brief." Ask it to write the report in small edits.

```text
GOAL        Find every place where a living doc says something that the repo's real state contradicts, with evidence for each.

SCOPE       Read-only on the whole repo. The ONLY file you may create or write is
            .pm/local/audits/<kind>-<date>/report.md
            Work in the repo root. No worktree, no branch.

CONTEXT     Living docs (both kinds):
              AGENTS.md, .pm/charter.md, .pm/README.md,
              every .md under docs/ whose frontmatter has depends_on:,
              docs/research/README.md if it exists.
            Extra scope (weekly only):
              Decisions (.pm/decisions/ or the single log): a decision in force that names a path, tool or ID that later decisions changed, without being archived or marked.
              Backlog hygiene: open every open task's file (not just the list), then check: open tasks untouched for 14+ days; open tasks whose acceptance criteria are already met; live blocks whose Next/Evidence contradict git; tasks pointing to archived or missing tasks.
              .pm/models.md: rows that contradict the model decisions.
              .pm/lessons.md: lessons marked as a proposal (öneri) for 7+ days without an owner decision.
            Sources of truth, strongest first:
              1. Code and files on disk (ls, rg, reading .pm/tools/*.py, backlog.config.yml)
              2. git history (git log --oneline, git show <sha> --stat)
              3. Backlog tasks: `backlog task list --plain`, `backlog task <id> --plain`, .pm/backlog/tasks/ and .pm/backlog/archive/tasks/
              4. Decisions: .pm/decisions/ (one file each; .pm/decisions/archive/ holds replaced ones, which name their replacement),
                 or in an older single log .pm/decisions.md, where "- ~~" marks a struck decision and "→" its replacement.
            A doc is wrong when it (a) states a status, file, path, command, count, owner or workflow that the sources contradict,
            (b) cites a superseded decision as current, (c) describes a layout or flow the files no longer have,
            or (d) contradicts another living doc. Dated snapshots are history, not errors: research notes, worklogs,
            and text carrying an update or correction marker. A list the owner marked as future or candidate is not an error.
            Quote doc text in its original language; write the report in English.

ACCEPTANCE  1. report.md starts with the report header block below, then a "## Findings" heading and a findings table:
               | # | Doc:line | Doc says (short quote) | Reality | Evidence (command + decisive output, or file:line) | Kind | Confidence |
               Kind: stale-status, wrong-path, wrong-command, superseded-decision, layout-drift, contradiction, hygiene, other.
               Confidence: high (direct evidence) or medium (inference; say why).
               Example row (made up, shows the format only):
               | 3 | docs/example.md:12 | "`tools/foo.py` builds the board" | no such file; .pm/tools/pm_board.py does | `ls tools/foo.py` → "No such file or directory" | wrong-path | high |
            2. A "Checked and consistent" list: one line per audited doc naming what you verified, so coverage is visible.
            3. No finding without evidence. Suspicions you cannot prove go under "Unverified suspicions" with the reason.
            4. No style, wording, typo or grammar findings.
            5. Create report.md early and fill it in small edits (long single replies can time out); append the
               exact last line <!-- done --> only when the report is complete, whether STATUS is DONE, PARTIAL or BLOCKED.

VERIFY      Every row's Doc:line exists and its evidence was actually run or read.
            `git status --short` shows no change made by you outside .pm/local/.

FORBIDDEN   Editing, creating, moving or deleting any file other than report.md. Any backlog edit/create/archive command.
            git add/commit/checkout/stash/reset. Network calls. Running pm_init.py. Starting servers.

TIMEBOX     80 turns (weekly: 120). Do not rerun a command without a changed input.
            On expiry write what you have with STATUS PARTIAL and name the docs you did not finish.

REPORT      Header block at the top of report.md:
            STATUS      DONE | PARTIAL | BLOCKED
            BRANCH      read-only
            CHANGED     report.md only
            RAN         main commands, one line each
            DEVIATIONS  none, or what you did outside this brief
            DOC IMPACT  n/a (the findings are the doc impact)
            FOLLOW-UPS  none, or out-of-scope issues you noticed
            COST        unavailable
```
