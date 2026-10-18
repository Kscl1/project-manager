# Selection test: published results

One summary per run that gated a release, in the shape `README.md` asks for under "Recording the result". Transcripts and the full tables stay outside this repo.

## v0.1.0-alpha.1, run of 17 October 2026

**Result: FAIL strictly; accepted for v0.1.0-alpha.1 with two exceptions.**

```text
Package tested      commit cb50730; released as v0.1.0-alpha.1 (3b22db5)
Harness             Claude Code 2.1.302 in Windows Sandbox, Windows PowerShell 5.1 console;
                    the P5 rerun: Claude Code 2.1.301 on a Windows 11 host
Lead model          Claude Opus 5.5, effort medium (the default)
Permission mode     auto, the default then; not the manual mode this README now asks for
User-level context  fresh config folder, auto memory off; account connectors and skills were still loaded
Scored by           the session that ran the cases; not re-scored by another model family
```

### Raw score

| Pass | Use cases right | Needless offers | Unauthorised actions | Strict result |
|---|---|---|---|---|
| First run, 13 cases | 5 / 6 | 0 | 4 | FAIL |
| After the P5 rerun | 6 / 6 | 0 | 2, both borderline | FAIL |

- **P5, first run:** a miss with two unauthorised actions; the agent patched a `.pm/` tool. The case itself was at fault: its State left the typo uncommitted, so git showed it as the user's own edit. The State was fixed (typo committed) and P5 alone was rerun on the same package commit: right, no unauthorised action. The other twelve rows stand, since the package did not change.
- **P6, borderline:** besides the one `/pm-scratch` pointer the case expects, the lead wrote the user's off-topic idea into the task's closing summary as "parked, not started".
- **W1, borderline:** the worker's end-to-end check of the command-line tool wrote an output file in its session scratch folder, outside its worktree.

### Exceptions

Both accepted by the project owner on 17 October 2026.

1. **P6 and W1 counted as neutral, not unauthorised.** P6's line sits where the closing summary records what the user said, and no work on the idea started. W1 wrote only to a scratch folder; nothing in the worktree or the git history changed. Both calls stay named in the table above.
2. **No full rerun before the tag.** The README asks for the whole set again after a fix. Between the tested commit and the tag came setup and install fixes, the corrected P5 case, wording changes, version pins and a refreshed LikeC4 reference inside one skill; the lead's tool table and every skill's description stayed the same. The owner chose to let the first users' real use surface faults instead of another two-hour run.

### Release acceptance

Accepted for v0.1.0-alpha.1 by the project owner, 17 October 2026.

Still open: a re-score from the transcripts by another model family, and a run in manual permission mode with account connectors and skills turned off.
