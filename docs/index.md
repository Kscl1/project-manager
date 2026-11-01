---
title: Introduction
description: A file-based workspace for you and your coding agents, inside Git.
template: splash
hero:
  title: project-manager
  tagline: Tasks, decisions and notes next to your code, kept by your AI assistant, so the next chat starts where you stopped.
  image:
    file: ../src/assets/logo.svg
    alt: project-manager logo
  actions:
    - text: Install with your agent
      link: /project-manager/install-with-agent/
      icon: right-arrow
    - text: Get started
      link: /project-manager/getting-started/
      variant: secondary
    - text: How it works
      link: /project-manager/how-it-works/
      variant: secondary
    - text: GitHub
      link: https://github.com/Kscl1/project-manager
      icon: external
      variant: minimal
---

Used ChatGPT or Gemini on your phone? You already know how to ask for help in plain words. On your computer the same words do more: the assistant can read and change the files in the folder you open, and project-manager gives it a place to keep the work notes for the next chat.

project-manager keeps **tasks, decisions and working rules next to your code**. You and your coding agents use the same files to plan work, check it and pick up where the last session stopped.

It is not a new coding agent, a hosted project tracker, or a set of rules for how your application should be written. It combines existing open tools with Markdown records and Python checks. You can read the records in an editor, review their changes in Git and take them with you when you switch agents.

**Only used AI on your phone?** [Start here](first-time.md). Words such as task, Epic, board or MCP server: the [glossary](glossary.md) explains each in one sentence.

![Four panels: you ask for a small change; the assistant shows its plan, you approve, it changes the file and runs the check; the notes are saved in .pm/ in your project; next time a new chat reads the notes, checks the files and names the next step.](../public/next-chat.svg)

**The new chat reads saved files, not the old assistant's mind.** In words: you ask for a small change; after your yes the assistant updates the project and writes a work note in `.pm/`; you close the chat; in a new chat you open the same folder and say "continue"; the assistant reads the notes, checks the files and names the next action.

Think of `.pm/` as the project's notebook. The assistant writes the job list, the reasons for choices and where you stopped there, in plain files you can open. It is not the AI's memory and it does not keep every word of a chat: the assistant reads the notes and checks the files each time.

## Who is it for?

For people building software with coding agents who want to stop explaining the project from scratch every session. Start with one project, one agent and the core layer; the [optional layers](optional-layers.md) wait until the work needs them.

The agent path needs no terminal skills: you paste one prompt and answer a few questions. The setup screen and the by-hand path expect you to be comfortable opening a terminal and working in a Git repository. It is still an alpha, not a fully automatic project manager.

## What changes in your project?

The installer adds a `.pm/` folder for the work system and root instructions that point your agent to it. Your application stays in its own folders. Tasks are ordinary Markdown files managed by Backlog.md; decisions explain why a choice was made; checks catch broken references and inconsistent records.

A new session starts from the repository and the active task, not from an old chat transcript. You still set the goal, approve important choices and decide when to merge. A passing check means the records are consistent, not that the implementation is correct.

This setup asks before changing your files; your assistant's own permission settings matter too. The AI can make mistakes; check what it did.

## Start small

1. Paste the prompt from [install with your agent](install-with-agent.md) into your coding agent. This is the shortest path, and it needs no terminal skills.
2. Open your project in your coding agent and type `/pm-setup` in the chat box. It fits the package to your project and ends with one small real task.
3. When you want the whole picture, read [how it works](how-it-works.md). The setup screen and the by-hand path are in [getting started](getting-started.md).

No single model provider is required. Setup installs Claude Code today, and the optional swarm uses Pi workers. Your model accounts and any API charges are separate from this MIT-licensed package.

## Status and support

**Alpha:** expect breaking changes. Windows has been tested end to end; Linux has not yet. Support is best effort, with no promised response time. See the [repository](https://github.com/Kscl1/project-manager), [releases](https://github.com/Kscl1/project-manager/releases) and [contributing guide](https://github.com/Kscl1/project-manager/blob/main/CONTRIBUTING.md).
