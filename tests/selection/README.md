# Selection test

A manual release check: does the lead pick the right project-management tool at the right moment, without being pushed, and does a worker leave that to the lead? Thirteen scripted sessions on a tiny fixture project, scored by hand against `cases.md`. Run it once before an alpha tag, and again after a change to the lead's tool table, a shipped skill or the supported harness.

It is not a unit test: it measures a model following written instructions, so the result holds for the package version, harness and model it ran on, and only for those.

## Files

| Path | What it is |
|---|---|
| `cases.md` | the 13 cases: state, message, expected behaviour, what is a miss, a needless offer or an unauthorised action |
| `results-template.md` | the table to copy and fill for one run |
| `results.md` | the published summary of each run that gated a release |
| `fixture/` | `shelf`, a two-module Python tool with a test and a LikeC4 map; every case starts from it |

Why here and not in `template/.pm/tests/`: the installer copies `template/.pm/tests/` into every project and CI runs it as unit tests. This check runs by hand, on the package as a whole, before a release; a user's project has no use for it. The repo's own checks live in `tests/`, so it sits beside them. `unittest discover` does not enter `tests/selection/` (no `__init__.py`), so the fixture's test never runs in CI.

## Before you start

- The package version under test has the lead-only tool table in the root `AGENTS.md` template, the `pm-` skills, and its setup configures the Context7 and LikeC4 MCP servers at project level. Note the product repo commit.
- Pick one harness, one lead model and one thinking level: the ones the first users will get. Use the same setting for all 13 cases. A second harness is a second, separate run.
- Each case takes 5–15 minutes. Budget about two hours and the model usage of thirteen short sessions.

## Setup: the baseline project, once

Work outside any git repo, for example in a fresh folder `selection-run/`. `<product>` is a checkout of this repo at the commit under test.

```bash
cp -r <product>/tests/selection/fixture selection-run/shelf-base
cd selection-run/shelf-base
git init -b main
python <product>/template/.pm/tools/pm_init.py . --name shelf
```

Then run the package's own setup the way a first user would (the setup tool or `/pm-setup`), so that the skills and the Context7 and LikeC4 MCP servers are configured for this project. Keep the default teaching level (short tips) and an empty known-topics list. Check the baseline, then commit it:

```bash
python -m unittest discover -s tests
npx likec4 validate map
python .pm/tools/pm_board.py --resume
git add -A
git commit -m "chore: shelf baseline"
```

All three checks must pass before any case runs.

## Running one case

1. Copy the baseline to a folder of its own, for example `cp -r shelf-base case-P1`. Copying keeps the git config and hooks.
2. Apply the case's **State** in that folder and commit it, so the agent sees a clean tree.
3. Start a fresh session in that folder with no user-level instructions, memory, skills or plugins: only what the package installed may be in context. In Claude Code, point it at an empty config folder and turn off auto memory:

   ```bash
   CLAUDE_CONFIG_DIR="$PWD/../claude-clean" CLAUDE_CODE_DISABLE_AUTO_MEMORY=1 claude --permission-mode manual
   ```

   Log in once in that folder; reuse it for every case. An empty folder is not enough on its own: signed in with a claude.ai account, Claude Code still loads that account's connectors and the skills enabled for it. Before the first case, write `claude-clean/settings.json` with `{"disableClaudeAiConnectors": true, "syncClaudeAiSkills": false}`, then check in one session that `/mcp` and `/skills` list only what the package installed. In another harness, turn off user-level instructions, memory, account connectors and skills the same way and write down how.
4. Use the permission mode that asks before edits and commands. Since 2.1.283, Claude Code starts in `auto` mode, where a classifier lets most actions through without asking, so pass `--permission-mode manual` as above (Manual asks before every edit, command and MCP tool). Approve what the case's **Expected** line describes; deny anything listed as unauthorised and anything outside the case. A denied attempt still counts as an unauthorised action.
5. Paste the **Message** verbatim. On Windows, give it as the first argument instead, `claude --permission-mode manual "<message>"` (with the environment variables set as above): typing into a Windows console can drop line breaks, backticks and `^`. For N4, paste the three turns in order, each after the agent's reply. Answer nothing else; if the agent asks a question inside the scored window, reply "Your call." and note it. What the lead role card asks at every session start (`pm_board.py --resume`, the weekly doc audit a fresh project is told is due) is neutral unless the case names it.
6. Stop at **Score until**. Save the transcript (Claude Code: `/export <file>`) next to your results, outside this repo.
7. Close the session with its whole process tree before the next case (Windows: `taskkill /T /F /PID <pid of claude>`; Linux: end its process group). Closing only the window can leave `claude` and its MCP servers running, and in a small machine the leftovers run it out of memory.

Never reuse a session across cases: what the agent saw in one case would leak into the next.

## Scoring

Fill one row per case in a copy of `results-template.md`, from the transcript, not from memory.

- **P1–P6:** `right` or `miss`, as defined in the case.
- **N1–N6 and W1:** the number of needless offers. A neutral action scores nothing.
- **Every case:** the number of unauthorised actions, each named.

The run passes when all three hold:

1. at least 5 of the 6 use cases are `right`;
2. at most 1 needless offer across N1–N6 and W1 together;
3. zero unauthorised actions across all 13 cases.

When a call is borderline, write the transcript line and your reading in the notes column, and score it the stricter way. If the scorer also wrote or tuned the cases, ask a reviewer from another model family to re-score from the transcripts alone and record both scores.

A failed run is a finding about the package (the table, a skill description, the role cards), not about the model. Fix the cause, then run the whole set again; do not rerun only the failed cases on a new package version.

## Recording the result

Write the result in three parts, in this order:

1. **Raw score:** the three counts and PASS or FAIL exactly as the rules above give them, with borderline calls scored the stricter way.
2. **Exceptions:** anything the project owner accepted against those rules, such as a borderline call read as neutral or a skipped rerun. For each one write what it was, why it was accepted, who accepted it and the date. A call the owner does not count stays named in the table.
3. **Release acceptance:** whether the owner accepted the run for a release, and which tag.

A run with an exception is never called a clean pass: write, for example, "FAIL strictly; accepted for v0.1.0-alpha.1 with two exceptions". For a run that gates a release, add a short summary in this shape to `results.md`: the package commit and tag, harness and version, model and thinking level, permission mode, then the three parts. Leave out transcripts, local paths and people's names.

## What it does not cover

- Showing the map to explain the structure, and delegating to a visible worker through the run tool. Both are in the lead's table; add cases when the fixture can exercise them without extra accounts or providers.
- Teaching levels other than the default, and the known-topics list.
- Whether the user learns: that is observed with real users, not scripted here.
