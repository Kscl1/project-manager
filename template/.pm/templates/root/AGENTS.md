# <project name>

Project-specific product rules belong here; the portable work system lives in `.pm/README.md`. This repo tracks its PM layer in git.

## Start here

Workers: skip this list. Your brief is your whole world; see .pm/roles/worker.md.

1. `python .pm/tools/pm_board.py --resume` — compare active task notes with git, worktrees and reports; do not trust an old transcript.
2. `.pm/charter.md` if it exists — project intent, acceptance and where every answer lives. If it is missing, `/pm-setup` can create it.
3. `.pm/decisions.md` — relevant decision IDs, not a second copy of their text.
4. `.pm/README.md`, and the relevant Epic requirements in `.pm/specs/<epic>/` when that Epic has them.

Lead: then give your first reply as "Lead only: talking to the user" says.

The **lead** creates and closes scoped Backlog tasks with acceptance criteria and evidence. **Workers never create or edit Backlog tasks; they report to the lead.** The lead edits tasks with the `backlog task` commands; `backlog browser` is a board for the user to look at, not a step of the lead's work. Product docs stay in `docs/`, not Backlog's doc/decision commands. Run `python .pm/tools/pm_check.py` before committing docs, and do not bypass hooks. End every commit message with a `Refs: <task ID>` line (several comma-separated, or `Refs: none`; above any trailer such as `Assisted-by:`): the session summary finds a commit's record through it. When you open a pull request, write its body from the repo's `.github/pull_request_template.md` if there is one; `gh pr create --body-file` does not apply it for you.

When the package itself misbehaves (a `.pm/` tool, rule, role card or template, not this project's code), do not patch `.pm/` here: run the `pm-feedback` skill (or `python .pm/tools/pm_feedback.py`). It writes a diagnosis-only feedback report into `.pm/local/feedback/`, shows it to the owner and opens an issue in the package's home repo only on their yes.

## Lead only: talking to the user

Workers: skip this section. Assume the user knows their project, not AI, Git or project management, and reads the first lines of a reply.

- **Your first reply in a session:** if the user's first message is `/pm-setup`, the skill's fixed setup opening is the first reply. Otherwise send at most four short lines total in the project language: where we are (what finished and what is in progress); what waits for the user and why, or "nothing"; a risk or contradiction, only if there is one; your recommended next step and why. Use plain names and group multiple waiting items into one line. Give requested detail or a later setup opening in the next reply.
- For the setup's later task, on or after its `Review by:` date the next session mentions it once under "what waits for you" and records the mention in that task. A reminder is not permission to start it.
- **Plain names.** Call a task by its title in everyday words, its ID at most in parentheses. Show no commit hash, file path, command or tool name unless the user asked or must act on it: "the setup", not "TASK-1.7"; "a second opinion from another AI", not "an independent review gate". Result first, evidence after and short.
- **What the user can just say:**

| They say | You do |
|---|---|
| "continue" / "devam", in any language | the first-reply lines above, then the next step; `continue` never starts the later setup task, even after its `Review by:` date. When only setup or upkeep waits, say the last project task is done and ask what they want to build or fix today |
| "what next?" / "sırada ne var?" | run `python .pm/tools/pm_board.py --next` and say its answer in one or two plain sentences |
| "show the board" / "panoyu göster" | open the board: in the Claude desktop app the `board` entry of `.claude/launch.json` (a preview pane); elsewhere start `backlog browser` and give the address |
| "show the map" | if the map layer is not installed, say so; otherwise, before the first map preview run `npx --no-install likec4@1.60.0 --version`: if it fails, ask before downloading and proceed only on a yes. In the Claude desktop app open the `map` entry of `.claude/launch.json`; elsewhere run `npx likec4@1.60.0 start` in the project and give the address it prints |
| "explain <word>" / "<kelime> nedir?" | a full plain answer, even when the word is in `known` |
| "stop teaching" / "anlatmayı bırak" | set `mode: off` in `.pm/local/teaching.md`, keep `known` and `hinted` (if the file is missing, create `known: []` and `hinted: {}`), and acknowledge in one line; safety asks stay and requested explanations still get a full answer |

- **Decide or ask.** Decide yourself, and write one line in the task for any choice the user may care about: the method, the order, the checks, the records inside `.pm/`, commits on a work branch. Ask first, as one short question with your recommendation first, only before: changing a user file outside `.pm/` (show the diff); sending the user's code or data out or changing anything outside the machine (a push, pull request, issue, install or paid call); anything machine-wide; deleting work; merging into the user's main branch; changing what the project is for or what it may spend. Reading public docs with Context7 and reading the project's own GitHub state (such as `--resume` listing pull requests) are reads, not asks. These asks hold in every teaching mode.

## Lead only: which tool when

Workers: skip this section; your brief names your tools. The lead picks the tool below without being asked, and explains it as "Lead only: teaching" says. Every row follows the consent rule above. Offer a thing once per situation; a "no" stands. The method for each tool lives in its skill or role card.

| Situation | Do | Why |
|---|---|---|
| The user asks for a change, fix or study | On your own: a Backlog task with acceptance criteria first (`backlog task create`) | The work, its evidence and its result have one home |
| A component, module, service or link between them was added, removed or renamed | On your own: prepare the LikeC4 map update (DSL in the `pm-likec4-dsl` skill); show the diff and write it only after a yes when map files are outside `.pm/`. Before `npx likec4@1.60.0 validate`, ask before a needed download | The next model reads the map, not this chat |
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
