# <project name>

Project-specific product rules belong here; the portable work system lives in `.pm/README.md`. This repo tracks its PM layer in git.

## Start here

Workers: skip this list. Your brief is your whole world; see .pm/roles/worker.md.

1. `python .pm/tools/pm_board.py --resume` — compare active task notes with git, worktrees and reports; do not trust an old transcript.
2. `.pm/charter.md` — project intent, acceptance and where every answer lives (D-62).
3. `.pm/decisions.md` — relevant decision IDs, not a second copy of their text.
4. `.pm/README.md` and the relevant Epic requirements in `.pm/specs/<epic>/`.

The **lead** creates and closes scoped Backlog tasks with acceptance criteria and evidence. **Workers never create or edit Backlog tasks; they report to the lead.** The lead uses `backlog browser` to inspect or edit tasks. Product docs stay in `docs/`, not Backlog's doc/decision commands. Run `python .pm/tools/pm_check.py` before committing docs, and do not bypass hooks. When you open a pull request, write its body from the repo's `.github/pull_request_template.md` if there is one; `gh pr create --body-file` does not apply it for you.

When the package itself misbehaves (a `.pm/` tool, rule, role card or template, not this project's code), do not patch `.pm/` here: run the `pm-feedback` skill (or `python .pm/tools/pm_feedback.py`). It writes a diagnosis-only feedback report into `.pm/local/feedback/`, shows it to the owner and opens an issue in the package's home repo only on their yes.

## Lead only: which tool when

Workers: skip this section; your brief names your tools. The lead picks the tool below without being asked, and says why in one short sentence unless the user has said they know it. Offer a thing once per situation; a "no" stands. The method for each tool lives in its skill or role card.

| Situation | Do | Why |
|---|---|---|
| The user asks for a change, fix or study | On your own: a Backlog task with acceptance criteria first (`backlog task create`) | The work, its evidence and its result have one home |
| A component, module, service or link between them was added, removed or renamed | On your own: update the LikeC4 map and run `npx likec4 validate` | The next model reads the map, not this chat |
| You need a library's, framework's or API's syntax, config or setup | On your own: look it up with Context7 | Current docs beat a model's memory |
| A piece of work or a long lookup can run apart from you | On your own, within the models in `.pm/models.md`: a worker or helper in a visible pane (`.pm/roles/lead.md`) | The user sees and can stop every agent |
| A plan or design is about to be settled with questions still open | Offer once: `/pm-grill-me` | Gaps show up before the work, not after |
| The user drops an off-topic idea mid-work | Offer once, in one line: `/pm-scratch` keeps it for later; run it only when the user calls it | Off-topic ideas wait without derailing the work |
| A `.pm/` tool, rule, role card or template misbehaves | On your own: the feedback report above | The package is fixed at its home, not patched here |
