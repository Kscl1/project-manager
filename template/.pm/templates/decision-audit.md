# Brief: decision audit

The weekly partner of `doc-audit.md`: a second cheap worker, from a different model family than the doc auditor, checks whether the recorded decisions and the project's practice still agree. The worker reads and reports; it never edits. The lead verifies every finding; a finding that changes something the owner decided, or that the two leads disagree on, goes to the owner.

Fill `<date>`, copy the lead's notes that live outside git (if any) into `.pm/local/audits/weekly-<date>/memory/`, then launch a worker as in `roles/lead.md` (visible, watched) with this brief.

```text
GOAL        Find every place where a file or the practice contradicts an active decision (a file in .pm/decisions/, or an entry of an older single log), with evidence.

SCOPE       Read-only on the whole repo. The ONLY file you may create or write is
            .pm/local/audits/weekly-<date>/decisions.md
            Do not read files outside the repo.

CONTEXT     Decisions: every decision in force: a file in .pm/decisions/ (its index is .pm/decisions.md), or in an older
            single log an entry not struck through ("- ~~", replacement after "→"). Files in .pm/decisions/archive/ are
            replaced; their replacement field names the decision that took over. Text in an update marker is part of the
            decision. Skip entries that only point to another repository.
            Files that restate rules: AGENTS.md, CLAUDE.md, README.md, .pm/*.md, .pm/roles/*.md, .pm/templates/*.md,
            template/README.md, docs/*.md, personal files if the repo has them, and the lead's notes copied into
            .pm/local/audits/weekly-<date>/memory/ (nothing else ever checks them).
            Practice: the code, hooks and CI, and the last two weeks of git log and worklogs.
            Dated research records are history, not errors.

            A finding is one of:
              1. a file states a rule that contradicts an active decision;
              2. a file restates a decision in its own words without its ID and has drifted, or states a rule that
                 has no decision;
              3. practice does the opposite of an active decision;
              4. two active decisions contradict each other, or a decision cites a superseded one as current;
              5. an open task or draft in .pm/backlog that an active decision already answered or made stale.
            Not a finding: wording, style, or a decision that says it is not implemented yet.

ACCEPTANCE  1. decisions.md starts with "# Decision audit <date>", then a "## Findings" heading and a findings table:
               | # | Decision | Where (path:line) | It says | The decision says (.pm/decisions/D-n.md:line) | Kind 1-5 | Suggested choice: fix the file / change the decision / strike it | Confidence |
            2. A "Checked and consistent" list: one line per decision checked with no finding.
            3. "Unverified suspicions" with the reason they could not be proven.
            Every path:line must exist; the lead's check opens each one.

FORBIDDEN   Editing any file other than decisions.md. Backlog edits. git add/commit/checkout. Network calls.

OUTPUT      Create the file early, fill it in small edits (long single replies can time out), and end with the exact
            last line <!-- done -->.
```
