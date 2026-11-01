---
title: Glossary
description: The words this documentation uses, each in one or two plain sentences.
---

New to AI coding assistants? These are the words the other pages use, in the order you meet them.

**Coding agent.** A chat window that can read and change the files in a folder, such as Claude Code, Codex or Pi. You say what you want in plain words, and it runs commands and edits files for you.

**Session.** One conversation with your coding agent, from the moment you open it to the moment you close it. The agent forgets most of a session afterwards, which is why project-manager keeps the work in files.

**Project folder.** The folder on your computer that holds your code. project-manager adds its records to this folder, in a hidden folder called `.pm/`.

**Task.** One piece of work with a clear finish, written as a Markdown file on the board. "Add a login button" is a task; "make the app better" is not.

**Acceptance criterion.** One checkable sentence that says when a task is finished, for example "the button logs the user in". The agent checks the work against these before calling it done.

**Board.** The list of tasks and their states, from Ready (nobody started) through Active (in progress) to Done. Backlog.md reads it and also opens it as a screen.

**Epic.** A parent task that holds smaller tasks. Use one when a goal is too big for one task; the children are the work that actually gets done.

**Charter.** A short document that says what the project is for, who it serves and what it will not do. It keeps later tasks pointed at the same goal, and the agent reads it before suggesting work.

**Decision.** A short record of a choice and the reason behind it, kept next to the code. It answers "why is it like this?" months later, when nobody remembers.

**Live block.** The few lines in an active task where the agent keeps the next action, the latest evidence and any blocker. It is the note the next session reads first, and it is checked against the real files before it is trusted.

**Worklog.** The dated notes from a piece of work: what was tried, what passed and what is still open. It lives in `.pm/worklog/` and is how a later session learns what an earlier one did.

**Resume.** Starting a session by reading where the work stopped instead of asking you to explain it again. `python .pm/tools/pm_board.py --resume` prints the same picture by hand.

**Commit.** One saved step in Git, with a message that says what changed. Work that is not committed can be lost; work that is committed can be compared and undone.

**Branch.** A separate line of commits, so a change can be tried without touching the main one. The installer works on a branch called `pm-setup`, so you can throw its changes away in one command.

**Merge.** Bringing the commits of one branch into another, so finished work joins the main line. You decide when to merge; the agent prepares it.

**Diff.** The lines that changed between two commits or between two branches, shown as removals and additions. It is how you and a reviewer see exactly what a change did without rereading every file.

**Git.** The program that records the history of a folder: what changed, when, and by which commit. project-manager keeps its records in Git, so every change to them is reviewable.

**Worktree.** A second working folder for the same Git repository, on its own branch, so work can go on without touching the folder you have open. Swarm workers each get one, which keeps their edits apart.

**Hook.** A small command Git runs by itself at a fixed moment, such as just before a commit. The package's hooks check the records; they cannot prove the work is correct.

**Lead.** The agent you talk to: it frames the task, writes the plan and checks that the evidence is real. In a project without the swarm, the lead does the work itself.

**Worker.** A helper agent that receives one brief, does only that job, and reports back. Workers exist only with the optional Swarm layer.

**Brief.** A short written instruction for one job: what to change, what counts as done and what not to touch. A worker reads the brief instead of your whole conversation.

**Swarm.** The optional layer that runs helper agents (workers) in terminal panes you can watch, each with its own worktree and brief. You can step into any pane and take over.

**MCP server.** A small helper program your agent can ask for data, over the Model Context Protocol. Context7 serves library documentation this way; an MCP server only answers questions, it does not change your files.

**Skill.** A saved instruction that teaches your agent one job, which you call by name, for example `/pm-setup`. project-manager ships skills whose names start with `pm-`.

**Layer.** One part of the package: Core (always installed), Map (diagrams, on by default), Swarm (visible helper agents) and EVREN (your own models). You add a layer only when the work needs it.
