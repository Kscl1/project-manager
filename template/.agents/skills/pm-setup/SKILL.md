---
name: pm-setup
description: Integrate .pm into the user's project through conversation, after the setup TUI has installed the tools. Walks the project's existing agent rules, hooks, CI, tests, task lists and the installer's merge-by-hand list one item at a time, records each answer in a Backlog setup Epic, then asks how the user wants the tools explained. Run only when the user calls it.
disable-model-invocation: true
---

# pm-setup

The user's own lead runs this once the setup TUI has installed the tools and `pm_init` has put `.pm/` in the project. Call it `/pm-setup` (Claude Code), `/skill:pm-setup` (Pi) or `$pm-setup` (Codex). Never run it on your own or as a worker.
Reply in the user's language. Assume they know their project, not AI or project-management words: explain each tool in one sentence the first time it is needed, not as a separate lesson.

## Step 0: check the installation

- Read `.pm/local/setup.json` if it exists: the setup TUI wrote it, with `source` (the project-manager checkout), `layers` (the chosen layers, such as `core` and `map`) and the date. Read `.pm/local/merge-by-hand.md` if it exists: what `pm_init` found in the project and did not touch. Do not guess a path or a layer that these files do not give; ask.
- If `.pm/` is missing, run `python "<source>/template/.pm/tools/pm_init.py" "<project>" --check` (add `--map` if map was chosen). It prints every write and every conflict and writes nothing: exit 0 means no conflicts, 3 means conflicts, anything else means stop and report it. Explain the plan in plain words and ask. Only on a clear yes run it again without `--check`, adding `--keep-existing` if it reported conflicts. On no, install nothing and stop.
- If `.pm/` is there, do not reinstall or upgrade it to run this skill. `setup.json` also lists `similar`: skills, MCP servers or plugins the user already has that do the job of one of ours.
- Read the project's own instructions, `.pm/README.md` and the installed templates before proposing changes. If a tool or interface is missing, report the blocker; do not invent flags, patch `.pm/` files or install more tools without permission.

## Standards to keep

Adapt the workflow to the project, not these rules. When one clashes with the project, explain it and offer a compatible option instead of dropping it silently.

- A Backlog task with acceptance criteria comes before the work.
- `python .pm/tools/pm_check.py` runs before a commit; hooks are never bypassed.
- One home per fact: link to it, never copy its status or content.
- Decisions live in `.pm/decisions/`, one file each, indexed by `.pm/decisions.md`.
- Workers report to the lead; only the lead edits tasks and living docs.
- The user decides; the model brings evidence, options and trade-offs.

## Track the conversation

- Check that Backlog uses this project's `.pm/backlog/`. If a kept `backlog.config.yml` or a `backlog/` folder points elsewhere, settle that with the user first; never write into the wrong tracker. Step 0 is the only work before a task exists.
- Reuse the setup Epic on a repeat run. Otherwise create it: `backlog task create "Set up project-manager" --type epic --ac "Every setup checklist answer and outcome is recorded in a child task" --ac "The final check result and the remaining work are reported"`. Use the ID it returns.
- Before working on a checklist item, create or reuse its child: `backlog task create "<item>" -p <epic-id> --ac "The user's answer and the approved outcome are recorded with evidence"`.
- Ask about one item at a time and wait for the answer. Use what the files already show, so the user need not recite their setup. Offer one recommendation with its trade-off; ask only what needs their judgment.
- Record every answer in its child task, "none", declined and deferred included. Show every change to a user file as a diff, explain its effect and wait for a clear yes; a yes to install is not a yes to later merges. Do not commit, push, change remote settings or migrate a tracker without being asked.
- Close a child only with checked evidence and a `Doc impact:` line; deferred work stays open.

## Walk the checklist

One child task per item; split a large item if needed. Do not ask the whole list at once.

1. **Agent instructions.** Read `AGENTS.md`, `CLAUDE.md`, `.cursorrules` and `.github/copilot-instructions.md` when present. Ask which rules still apply. Show a small merge that keeps the project's rules and makes the 'Start here' and 'Lead only' sections of `.pm/templates/root/AGENTS.md` reachable. Never erase another agent's instructions or replace a real `CLAUDE.md` with `@AGENTS.md`.
2. **Git hooks.** Read `core.hooksPath`, `.git/hooks` and any husky, pre-commit or lefthook setup. Ask which checks must keep running. Show how they and `.pm/hooks` can both run, through the project's hook manager when there is one; change the hook path only on a yes and check that both sets run. An unsolved clash stays open, never bypassed.
3. **CI.** Read the workflow files and ask which checks gate delivery. Show where `pm_check` could run without replacing the project's checks. Do not create a CI system because none exists.
4. **Tests.** Find the project's test commands. With permission run a small one and record the exact command and result. The package's tests do not prove the user's product works.
5. **Task lists.** Look for TODO files and issue-tracker links; ask where current work lives. Offer a small move or links, never a silent bulk import, and keep one authoritative home.
6. **Merge by hand.** Walk every line of `.pm/local/merge-by-hand.md`, one at a time. For `.claude/settings.json` the hooks to add are in `.pm/templates/root/claude-settings.json`; for `.mcp.json` the line gives the server's JSON. Add only that entry, keep every other key, check that the JSON still parses, and show the diff before writing.
7. **Charter.** If `.pm/charter.md` is missing, build it from `.pm/templates/charter.md`, in small questions: why the project exists, for whom, what is out of scope, what result counts as success. Fill its links from real project paths. Leave review gates the template names as pending; never mark them passed.
8. **Models.** Go through `.pm/models.md` with the user: which roles they need and which accounts or tools they already have. Do not ask them to buy anything or store a credential. A role nobody can fill stays recorded as open.
9. **Your existing tools.** Start with each `similar` line in `setup.json`, then ask whether the user has other MCP servers, plugins, skills or apps they want to use. Do one tool at a time, creating/reusing a child task per tool. Record its job/trigger, current client and scope, official setup source, permissions/data/cost boundary, overlap choice (ours, theirs or both), smoke check and fallback. Remove nothing of theirs; duplicates can have different permissions or invoke services twice, so name the preferred route. Inspect only approved configuration, never credentials; show a minimal diff and wait for approval before installing, configuring or making an external call. Verify from the actual agent/project with one approved low-risk query, or mark configured/not tested with the blocker. Lead access is not proof of worker access. After approval add a short situation → tool → expected result → boundary/fallback row to the project's own `AGENTS.md` tool table or existing equivalent. Keep evidence/status in the task; link official install instructions instead of copying a catalogue. The source checkout's `docs/own-tools.md`, when available, explains the method with Context7/LikeC4 examples; it is not required for this step.
10. **Map.** Only if `map` is in the chosen layers: check that `.mcp.json` names `likec4` (item 6 adds it when listed), then offer to draw a first small model of the project's main parts with the user (the `pm-likec4-dsl` skill holds the syntax), and check it with `npx likec4@1.60.0 validate`. Map not chosen: skip this item and say so.

If an item is blocked, move to the next independent one and record the dependency. If a later change affects an earlier answer, check it again.

## Finish and choose how to learn

1. Run `python .pm/tools/pm_check.py`. Show its result; fix only approved in-scope problems and run it again. A clean check means consistent, not that the setup works.
2. From the Epic's children, show what was changed and checked, what was declined and what is still open, with task IDs.
3. In a last child task, ask: "While we work on your project, how should I explain the project-management tools?"
   - **Short hint** (`hint`, the default): one sentence when a tool helps, then carry on.
   - **Try together** (`together`): guide one small step in the real task and let the user do it.
   - **Off** (`off`): no explanations; approvals and safety questions stay.
4. Write the answer to `.pm/local/teaching.md` (git-ignored; check that `.pm/local/` is in `.gitignore`):

   ```
   mode: hint
   known: []
   ```

   Add to `known` only concepts the user says they know (for example `backlog`, `likec4`, `worker`); keep the ones already there. No answer: leave the file as it is.
5. Tell the user they can change it in chat any time: "short hints", "let's try together", "stop teaching" or "I already know X"; update the same file when they do.
6. Close the Epic only when its children are done, with evidence and a `Doc impact:` line. No commit unless the user asks.
