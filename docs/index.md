---
title: Introduction
description: A file-based workspace for you and your coding agents, inside Git.
template: splash
hero:
  title: project-manager
  tagline: Tasks, decisions and working rules next to your code, so your next chat starts where the last one stopped.
  image:
    file: ../src/assets/logo.svg
    alt: project-manager logo
  actions:
    - text: Get started
      link: /project-manager/getting-started/
      icon: right-arrow
    - text: How it works
      link: /project-manager/how-it-works/
      variant: secondary
    - text: GitHub
      link: https://github.com/Kscl1/project-manager
      icon: external
      variant: minimal
---

project-manager keeps **tasks, decisions and working rules next to your code**. You and your coding agents use the same files to plan work, check it and pick up where the last session stopped.

Words such as task, Epic, board or MCP server: the [glossary](glossary.md) explains each in one sentence.

It is not a new coding agent, a hosted project tracker or a framework for your application. It combines existing open tools with Markdown records and Python checks. You can read the records in an editor, review their changes in Git and take them with you when you switch agents.

## Who is it for?

For people building software with coding agents who want to stop explaining the project from scratch every session. Start with one project, one agent and the core layer; the [optional layers](optional-layers.md) wait until the work needs them.

The agent path needs no terminal skills: you paste one prompt and answer a few questions. The setup screen and the by-hand path expect you to be comfortable opening a terminal and working in a Git repository. It is still an alpha, not a fully automatic project manager.

## What changes in your project?

The installer adds a `.pm/` folder for the work system and root instructions that point your agent to it. Your application stays in its own folders. Tasks are ordinary Markdown files managed by Backlog.md; decisions explain why a choice was made; checks catch broken references and inconsistent records.

A new session starts from the repository and the active task, not from an old chat transcript. You still set the goal, approve important choices and decide when to merge. A passing check means the records are consistent, not that the implementation is correct.

## Start small

1. Paste the prompt from [install with your agent](install-with-agent.md) into your coding agent. This is the shortest path, and it needs no terminal skills.
2. Open your project in your coding agent and type `/pm-setup` in the chat box. It fits the package to your project and ends with one small real task.
3. When you want the whole picture, read [how it works](how-it-works.md). The setup screen and the by-hand path are in [getting started](getting-started.md).

No single model provider is required. Setup installs Claude Code today, and the optional swarm uses Pi workers. Your model accounts and any API charges are separate from this MIT-licensed package.

## Status and support

**Alpha:** expect breaking changes. Windows has been tested end to end; Linux has not yet. Support is best effort, with no promised response time. See the [repository](https://github.com/Kscl1/project-manager), [releases](https://github.com/Kscl1/project-manager/releases) and [contributing guide](https://github.com/Kscl1/project-manager/blob/main/CONTRIBUTING.md).
