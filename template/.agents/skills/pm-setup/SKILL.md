---
name: pm-setup
description: Integrate .pm into the user's project through conversation, after an install chat, the setup TUI or the user has installed the package. Opens with three fixed sentences and asks how the user wants the project-management side explained, walks the project's existing agent rules, hooks, CI, tests, task lists and the installer's merge-by-hand list, records the answers in a Backlog setup Epic, and ends with one small real task from the project. Run only when the user calls it.
disable-model-invocation: true
---

# pm-setup

The user's own lead runs this once the tools are installed and `pm_init` has put `.pm/` in the project, by an install chat (`docs/install-with-agent.md`), the setup TUI or by hand. Call it `/pm-setup` (Claude Code), `/skill:pm-setup` (Pi) or `$pm-setup` (Codex). Never run it on your own or as a worker.
Reply in the user's language. Assume they know their project, not AI or project-management words; explain as Step 1 sets, inside the work, never as a separate lesson.

## Step 0: check the installation

- This must be the project folder. If the current folder has no `.pm/` but a folder the user names, or a subfolder, has `.pm/local/setup.json`, that is the project: tell the user to open that folder itself in a new session and run `/pm-setup` there, because the agent reads a project's settings, hooks and skills only from the folder it starts in; then stop. Install here (below) only when the user confirms this folder is the project.
- Read `.pm/local/handover.md` first if it exists: the install chat wrote what it installed, what the user skipped, open problems and next steps. Carry its open problems into the setup Epic. When you find or solve an install problem, write it back under that file's `## Open problems` with the date, so the user never carries an error message between chats.
- Read `.pm/local/setup.json` if it exists: setup wrote it (the TUI's Done screen, or `bom.py --record` in an install chat), with `source` (the project-manager checkout), `layers` (the chosen layers, such as `core` and `map`) and the date. Read `.pm/local/merge-by-hand.md` if it exists: what `pm_init` found in the project and did not touch. Do not guess a path or a layer that these files do not give; ask.
- If `.pm/` is missing, run `python "<source>/template/.pm/tools/pm_init.py" "<project>" --check` (add `--map` if map was chosen). It prints every write and every conflict and writes nothing: exit 0 means no conflicts, 3 means conflicts, anything else means stop and report it. Explain the plan in plain words and ask. Only on a clear yes run it again without `--check`, adding `--keep-existing` if it reported conflicts. On no, install nothing and stop.
- Once `.pm/` is in place, read the `Language:` line under the `## Language` heading of the root `AGENTS.md`. If there is none, ask once, before the opening: "Which language should I talk to you in and write your project's records in?" Then run `python .pm/tools/pm_init.py . --lang <code> --check` (a code such as `tr` or `en`), show what it sets, the `AGENTS.md` line and Claude Code's `language` setting (for a settings file of the user's own, a merge-by-hand line for item 6), and on a yes run it without `--check`. From then on talk and write record prose in that language; keys such as `Next:` and status names stay English. No answer: carry on in the user's language and leave the line unset.
- If `.pm/` is there, do not reinstall or upgrade it to run this skill. `setup.json` also lists `similar`: skills, MCP servers or plugins the user already has that do the job of one of ours.
- Read the project's own instructions, `.pm/README.md` and the installed templates before proposing changes. If a tool or interface is missing, report the blocker; do not invent flags, patch `.pm/` files or install more tools without permission.

## Step 1: open and ask how to explain

1. Show the opening and the teaching question from `texts.md` (next to this file) in the project language, as written. Ask nothing else in the same message.
2. Write the answer to `.pm/local/teaching.md` (git-ignored; check that `.pm/local/` is in `.gitignore`). No answer means `hint`:

   ```
   mode: hint
   known: []
   hinted: {}
   ```

   On a repeat run keep the file and its lists: say the current mode in one line and ask again only if the user wants to change it.
3. From here on, explain as the root `AGENTS.md` section "Lead only: teaching" says: one hint after the action, `known` and `hinted` kept current, the first hints' words from `texts.md`.

## Standards to keep

Adapt the workflow to the project, not these rules. When one clashes with the project, explain it and offer a compatible option instead of dropping it silently.

- A Backlog task with acceptance criteria comes before the work.
- `python .pm/tools/pm_check.py` runs before a commit; hooks are never bypassed.
- One home per fact: link to it, never copy its status or content.
- Decisions live in `.pm/decisions/`, one file each, indexed by `.pm/decisions.md`.
- Workers report to the lead; only the lead edits tasks and living docs.
- The user decides; the model brings evidence, options and trade-offs.

## Track the conversation

- Check that Backlog uses this project's `.pm/backlog/`. If a kept `backlog.config.yml` or a `backlog/` folder points elsewhere, settle that with the user first; never write into the wrong tracker. Steps 0 and 1 are the only work before a task exists.
- Reuse the setup Epic on a repeat run. Otherwise create it: `backlog task create "Set up project-manager" --type epic --ac "Every setup checklist answer and outcome is recorded in a child task" --ac "The final check result and the remaining work are reported"`. Use the ID it returns. The Epic and its children are setup bookkeeping: create them without a hint; the task hint and the task moment belong to the first real task.
- Before working on a checklist item, create or reuse its child: `backlog task create "<item>" -p <epic-id> --ac "The user's answer and the approved outcome are recorded with evidence"`.
- First read what items 1-6 need, without changing anything. When none of them has anything to merge (no agent rules of the project's own, no hooks, CI or task lists to connect, an empty merge-by-hand list), record all six in one child, `Existing setup`, show the user what you found as a short list and ask once; one child per item only for the items that need work.
- Ask about one item at a time and wait for the answer. Use what the files already show, so the user need not recite their setup. Offer one recommendation with its trade-off; ask only what needs their judgment.
- Record every answer in its child task, "none", declined and deferred included. Show every change to a user file as a diff, explain its effect and wait for a clear yes; a yes to install is not a yes to later merges. Do not commit, push, change remote settings or migrate a tracker without being asked.
- Close a child only with checked evidence and a `Doc impact:` line; deferred work stays open.

## Walk the checklist

One child task per item (or one `Existing setup` child for items 1-6, above); split a large item if needed. Do not ask the whole list at once.

1. **Agent instructions.** Read `AGENTS.md`, `CLAUDE.md`, `.cursorrules` and `.github/copilot-instructions.md` when present. Ask which rules still apply. Show a small merge that keeps the project's rules and makes the 'Start here' and both 'Lead only' sections of `.pm/templates/root/AGENTS.md` reachable. Never erase another agent's instructions or replace a real `CLAUDE.md` with `@AGENTS.md`.
2. **Git hooks.** Read `core.hooksPath`, `.git/hooks` and any husky, pre-commit or lefthook setup. Ask which checks must keep running. Show how they and `.pm/hooks` can both run, through the project's hook manager when there is one; change the hook path only on a yes and check that both sets run. An unsolved clash stays open, never bypassed.
3. **CI.** Read the workflow files and ask which checks gate delivery. Show where `pm_check` could run without replacing the project's checks. Do not create a CI system because none exists.
4. **Tests.** Find the project's test commands. With permission run a small one and record the exact command and result. The package's tests do not prove the user's product works.
5. **Task lists.** Look for TODO files and issue-tracker links; ask where current work lives. Offer a small move or links, never a silent bulk import, and keep one authoritative home.
6. **Merge by hand.** Walk every line of `.pm/local/merge-by-hand.md`, one at a time. For `.claude/settings.json` the hooks to add are in `.pm/templates/root/claude-settings.json`; for `.mcp.json` the line gives the server's JSON. Add only that entry, keep every other key, check that the JSON still parses, and show the diff before writing.
7. **Charter.** If `.pm/charter.md` is missing, build it from `.pm/templates/charter.md`, in small questions: why the project exists, for whom, what is out of scope, what result counts as success. Fill its links from real project paths. Leave review gates the template names as pending; never mark them passed.
8. **Models.** Go through `.pm/models.md` with the user: which roles they need and which accounts or tools they already have. Do not ask them to buy anything or store a credential. A role nobody can fill stays recorded as open.
9. **Your existing tools.** Start with each `similar` line in `setup.json`, then ask whether the user has other MCP servers, plugins, skills or apps they want to use. Do one tool at a time, with a child task per tool (create or reuse).
   - Record the tool's job and trigger, its current client and scope, and its official setup source.
   - Record its permissions, data and cost boundary, and one overlap choice: ours, theirs or both. Remove nothing of theirs; duplicates can have different permissions or invoke services twice, so name the preferred route.
   - Inspect only approved configuration, never credentials. Show a minimal diff and wait for approval before installing, configuring or making an external call.
   - Verify from the actual agent and project with one approved low-risk query, or mark it configured, not tested, with the blocker. Lead access is not proof of worker access. Name the fallback when the tool is missing or fails.
   - After approval add one row to the project's own `AGENTS.md` tool table (or its existing equivalent) in that table's three cells: Situation, Do (tool, boundary, fallback), Why (expected result). Keep evidence and status in the task; link official install instructions instead of copying a catalogue. The method, with Context7 and LikeC4 examples: https://github.com/Kscl1/project-manager/blob/main/docs/own-tools.md
10. **Map.** Only if `map` is in the chosen layers: check that `.mcp.json` names `likec4` (item 6 adds it when listed), then offer to draw a first small model of the project's main parts with the user (the `pm-likec4-dsl` skill holds the syntax), and check it with `npx likec4@1.60.0 validate`. Map not chosen: skip this item and say so.

If an item is blocked, move to the next independent one and record the dependency. If a later change affects an earlier answer, check it again.

## The first real task

After the checklist, or earlier if the user wants to start work and the rest can wait, ask for one small, real job from their project that fits in this session: a bug, a small feature, a missing test, a doc fix. Never a demo or an example file.

- Do it in try-together mode unless the user chose off, whatever mode they picked; `teaching.md` keeps their choice.
- In try-together mode, show the task moment from `texts.md` before creating the task: the user gives one sentence, it becomes the task's acceptance criterion, and the user never types a command. Then add `task` to `known` and say the one line from `texts.md`.
- Give the board hint when the user's second own task exists or they ask what is left.
- Do the work with the usual approvals, and close the task only when its criterion holds, with evidence.

## Finish

1. Run `python .pm/tools/pm_check.py`. Show its result; fix only approved in-scope problems and run it again. A clean check means consistent, not that the setup works.
2. From the Epic's children, show what was changed and checked, what was declined and what is still open, with task IDs.
3. If `handover.md` exists, mark what this session settled; open problems stay under their heading.
4. If the install chat made a branch (`handover.md` names it, usually `pm-setup`), offer to merge it into the branch it was made from: show `git switch <old branch>` and `git merge pm-setup`, run them only on a yes, never push. To undo instead, the same file's `## Undo` says how.
5. Close the Epic only when its children are done, with evidence and a `Doc impact:` line. No commit unless the user asks.
6. End with the resume hint from `texts.md` (unless the mode is off), then the next session's prompt, ready to paste: how to open this folder, and "continue" in the project language.
