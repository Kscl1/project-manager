---
title: Install with your agent
description: The steps a coding agent follows to install project-manager into your project, asking you before every change.
---

You do not have to install project-manager by hand. Open your coding agent (Claude Code, Codex, Pi or another) in the folder that holds your project, and paste this:

```text
Install project-manager into my project. Read all of https://raw.githubusercontent.com/Kscl1/project-manager/main/docs/install-with-agent.md (download it with curl if your web tool only gives a summary), follow it step by step, ask me before every change, and stop where it says to stop.
```

The agent asks a few questions, checks your machine, installs on a new branch of your project and leaves a hand-over note. Then you open your project in a new session and type `/pm-setup`, where the agent fits the package to your project with you. It does not build a demo project and does not touch your code. If you prefer a guided screen in your terminal, use the [setup TUI](getting-started.md) instead.

## For the agent

You install project-manager into the user's project. Follow these steps in order.

- Talk to the user in their language, plainly; assume they know their project, not AI or project-management words. Ask one question at a time.
- Before each command that changes something (an install, a git command that writes, the installer), say in one sentence what it does, show it, and run it only after a clear yes. Read-only checks need no yes. Never add `sudo` to npm.
- Do not edit the project's code and do not create example files. Do not run `/pm-setup` here.
- Keep a list as you go: what you installed, what the user skipped, and every error with its command. It goes into the hand-over file in step 6.
- Stop after step 7.
- Write commit messages in the project language after the type, for example `chore: <install project-manager, in that language>`; the type stays English.

### 1. Ask

Ask these, one at a time, with one sentence on each choice:

1. **The project folder**, as a full path. If the user is not sure, list the folders where you are and ask.
2. **The language** for talking and for the project's records, as a code such as `tr` or `en`. Field names and status names stay English, because the tools read them.
3. **Map** (default yes): diagrams of the project's architecture that the agent can read and keep current. It needs Node.js.
4. **Swarm** (default no): helper agents that run in terminal panes the user can watch. It needs Pi and Herdr; say it can be added later.

The layers are `core`, plus `map` and `swarm` when chosen. Use them below as `<layers>`, for example `core,map`.

### 2. Check Python and Git, and get project-manager

It needs Python 3.11 or newer and Git. If `python --version` or `git --version` fails, give the user the commands under "Before you start" in [Getting started](getting-started.md), run them on a yes, and ask them to open a new terminal if the program is still not found. Go on only when both work.

Clone project-manager **next to** the project, in the folder that holds it, never inside it:

```bash
git clone --branch v0.1.0-alpha.5 https://github.com/Kscl1/project-manager.git
```

Git may print `warning: refs/tags/... is not a commit!` before it lands on the release: that is expected for a release tag, and the clone is fine.

If a `project-manager` folder is already there, check it: `git -C project-manager describe --tags --exact-match` must print the release above and `git -C project-manager status --porcelain` must print nothing. If the release differs and the folder is clean, offer `git -C project-manager fetch --tags` and `git -C project-manager switch --detach <release>`; if it has changes of its own, do not touch it: stop and ask. Below, `<pm>` is that folder and `<project>` the project folder; quote both in every command, because a path may contain spaces.

### 3. Make the project safe to change

In the project folder:

1. If `.pm/` is already there, project-manager is installed: stop, and point the user to [Upgrade and roll back](upgrading.md), or to `/pm-setup` in a new session in that folder.
2. `git rev-parse --show-toplevel`. If it fails, the project has no Git history yet: on a yes run `git init`, then show `git status --short` and check that `.gitignore` keeps out secrets and large folders (`.env`, `node_modules`). On a second yes run `git add -A` and `git commit` with a message such as "chore: first commit before project-manager" in the project language. If it prints a different folder, the chosen folder sits inside another repository: stop and ask which folder is the project.
3. `git status --porcelain`. If it lists changes, show them and offer two ways: commit them, or put them aside with `git stash push -u -m "before project-manager"`. With neither, stop here.
4. Note the current branch (`git branch --show-current`) and whether `git config core.hooksPath` prints anything. Then, on a yes, `git switch -c pm-setup`.

Tell the user how to undo everything that happens in the project from here, once the install is committed on the branch (step 5): `git switch <old branch>`, then `git branch -D pm-setup`; delete the `.pm` folder if it is still there (it did not exist before, so nothing of theirs is in it); if `core.hooksPath` was empty before, `git config --unset core.hooksPath`; a stash comes back with `git stash pop`. Programs installed on the machine (step 4) stay; [Upgrade and roll back](upgrading.md) covers them.

### 4. Check the machine

```bash
python "<pm>/tools/setup/bom.py" --layers <layers> --project "<project>"
```

It installs nothing. It prints what is installed and a To do list, one command per step; exit 1 only means steps are left, 2 means a wrong argument. Leave the step for the `.pm` project files to step 5. For every other step, say what the program is for in one sentence, show the command and run it on a yes; a skipped step goes on your list. Lines that start with `Note:` are things only the user can do; tell them. Run the check again after each step, until only the project files are left.

### 5. Install the package

```bash
python "<pm>/template/.pm/tools/pm_init.py" "<project>" --check --lang <code>
```

Add `--map` and `--swarm` when chosen. It writes nothing. Exit 0 means no conflicts; exit 3 means the project already has its own agent rules, hooks or settings, which are kept and listed for `/pm-setup` to merge with the user; any other exit, stop and write the error down. Explain the plan in a few plain lines, then on a yes run the same command without `--check` (add `--keep-existing` after exit 3).

Then record the setup for `/pm-setup`:

```bash
python "<pm>/tools/setup/bom.py" --layers <layers> --project "<project>" --record
```

Commit the installed files on the `pm-setup` branch, on a yes: `git add -A` and `git commit` with a message such as "chore: install project-manager" in the project language. This commit is what makes the undo above work. The package's commit hook runs; if it fails, do not bypass it: write the error down. If the user says no, write under Undo in the hand-over file that the files `pm_init --check` listed must be removed by hand.

### 6. Write the hand-over file

Write `<project>/.pm/local/handover.md` (git-ignored, next to `setup.json`). The next session reads it before anything else and writes install problems back into it, so the user never has to carry an error message between the chats. Keep the headings in English, for the tools and every model; write the content in the user's language.

```markdown
# Hand-over from the install chat

Date: <YYYY-MM-DD> · Release: <tag> · Source: <pm> · Layers: <layers> · Language: <code>
Branch: pm-setup, made from <old branch> · Stash: <none, or its message> · core.hooksPath before: <empty, or its value>

## Installed

## Skipped

## Open problems

## Next steps

1. Open <project> in a new session and run /pm-setup.

## Undo

git switch <old branch>, git branch -D pm-setup, then delete .pm if it is still there.
```

Fill each section from your list; write `none` where there is nothing. Add every open problem as a next step too.

### 7. Hand over and stop

Tell the user in a few lines what is installed and what is open. Then give them the next step, ready to follow:

> Open your project folder itself in a new session, not this one: the agent reads a project's settings, hooks and skills only from the folder it starts in.
> - Claude Code in a terminal: `cd "<project>"`, then `claude`. Claude Desktop: Code, then choose the folder.
> - Pi: `cd "<project>"`, then `pi`.
>
> Claude Code first asks whether you trust the folder: it is your project, so choose "Yes, I trust this folder". It may also ask whether to turn on the project's servers for current documentation and diagrams (Context7, LikeC4): allow them.
>
> Then type `/pm-setup` (in Pi `/skill:pm-setup`, in Codex `$pm-setup`).

Stop here. Do not continue the setup in this chat.
