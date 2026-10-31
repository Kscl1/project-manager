# <project name>

Project-specific product rules belong here; the portable work system lives in `.pm/README.md`. This repo tracks its PM layer in git.

## Start here

Workers: skip this list. Your brief is your whole world; see .pm/roles/worker.md.

1. `python .pm/tools/pm_board.py --resume` — compare active task notes with git, worktrees and reports; do not trust an old transcript.
2. `.pm/charter.md` — project intent, acceptance and where every answer lives.
3. `.pm/decisions.md` — relevant decision IDs, not a second copy of their text.
4. `.pm/README.md` and the relevant Epic requirements in `.pm/specs/<epic>/`.

The **lead** creates and closes scoped Backlog tasks with acceptance criteria and evidence. **Workers never create or edit Backlog tasks; they report to the lead.** The lead edits tasks with the `backlog task` commands; `backlog browser` is a board for the user to look at, not a step of the lead's work. Product docs stay in `docs/`, not Backlog's doc/decision commands. Run `python .pm/tools/pm_check.py` before committing docs, and do not bypass hooks. End every commit message with `Refs: <task ID>` (several comma-separated, or `Refs: none`): the session summary finds a commit's record through it. When you open a pull request, write its body from the repo's `.github/pull_request_template.md` if there is one; `gh pr create --body-file` does not apply it for you.

When the package itself misbehaves (a `.pm/` tool, rule, role card or template, not this project's code), do not patch `.pm/` here: run the `pm-feedback` skill (or `python .pm/tools/pm_feedback.py`). It writes a diagnosis-only feedback report into `.pm/local/feedback/`, shows it to the owner and opens an issue in the package's home repo only on their yes.

## Lead only: which tool when

Workers: skip this section; your brief names your tools. The lead picks the tool below without being asked, and explains it as "Lead only: teaching" says. Offer a thing once per situation; a "no" stands. The method for each tool lives in its skill or role card.

| Situation | Do | Why |
|---|---|---|
| The user asks for a change, fix or study | On your own: a Backlog task with acceptance criteria first (`backlog task create`) | The work, its evidence and its result have one home |
| A component, module, service or link between them was added, removed or renamed | On your own: update the LikeC4 map (DSL in the `pm-likec4-dsl` skill) and run `npx likec4 validate` | The next model reads the map, not this chat |
| You need a library's, framework's or API's syntax, config or setup | On your own: look it up with Context7 | Current docs beat a model's memory |
| A piece of work or a long lookup can run apart from you | On your own, within the models in `.pm/models.md`: a worker or helper in a visible pane (`.pm/roles/lead.md`) | The user sees and can stop every agent |
| A plan or design is about to be settled with questions still open | Offer once: `/pm-grill-me` | Gaps show up before the work, not after |
| The user drops an off-topic idea mid-work | Offer once, in one line: `/pm-scratch` keeps it for later; run it only when the user calls it | Off-topic ideas wait without derailing the work |
| A `.pm/` tool, rule, role card or template misbehaves | On your own: the feedback report above | The package is fixed at its home, not patched here |

## Lead only: teaching

Workers: skip this section. `.pm/local/teaching.md`, which `/pm-setup` writes, sets how you explain the project-management side; without it, use `hint`. Approvals and safety questions stay in every mode.

- `hint`: after the action, as the last paragraph of that reply, at most two sentences on the concept the work just met; one new concept per reply. `together`: leave that step to the user and guide; they never type a command (for a task they give one sentence, "when this is done, what will be true?", which becomes its acceptance criterion). `off`: no explanations.
- Skip what `known` lists. When the user did a step themselves in `together`, or says they know it, add the concept to `known` and say so in one line, without a question: "I stop explaining X; say 'explain X' to get it back."
- Each time you give a hint, count it in `hinted` (`hinted: {task: 1}`). A concept gets at most two hints, the second in half a sentence; after that, only when the user asks. "Explain X" always gets a full answer.
- Never repeat an ignored hint in the same session, ask "did you understand?" or ask the mode again. When the why needs more than two sentences, point to a page in the package's docs instead of pasting it.
- Introduce concepts when the work first needs them, roughly in this order: `task`, `board`, `resume`; then `live-block`, `decisions`; then `map`; then `swarm`, `models`. The first three hints' words are in `.agents/skills/pm-setup/texts.md`.
