---
title: Introduction
description: A file-based workspace for you and your coding agents, inside Git.
template: splash
hero:
  title: project-manager
  tagline: Tasks, decisions and working rules next to your code, so every agent session starts where the last one stopped.
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

It is not a new coding agent, a hosted project tracker or a framework for your application. It combines existing open tools with Markdown records and Python checks. You can read the records in an editor, review their changes in Git and take them with you when you switch agents.

## Who is it for?

For people building software with coding agents who want to stop explaining the project from scratch every session. Start with one project, one agent and the core layer. Architecture diagrams and visible worker agents are optional; you do not need a swarm to manage a task.

You should be comfortable opening a terminal and working in a Git repository. Your coding agent or the setup screen guides installation, and `/pm-setup` helps your agent fit the package to your project. It is still an alpha, not a fully automatic project manager.

## What changes in your project?

The installer adds a `.pm/` folder for the work system and root instructions that point your agent to it. Your application stays in its own folders. Tasks are ordinary Markdown files managed by Backlog.md; decisions explain why a choice was made; checks catch broken references and inconsistent records.

A new session starts from the repository and the active task, not from an old chat transcript. You still set the goal, approve important choices and decide when to merge. A passing check means the records are consistent, not that the implementation is correct.

## Start small

1. Read [how it works](how-it-works.md) to see the workflow and where each tool runs.
2. Paste the prompt from [install with your agent](install-with-agent.md) into your coding agent, or follow [getting started](getting-started.md), to install the core layer in your project.
3. Open your project in your coding agent and run `/pm-setup`.

The package does not require one model provider. Setup installs Claude Code today; the optional swarm uses Pi workers. Your model accounts and any API charges are separate from this MIT-licensed package.

## Status and support

**Alpha:** expect breaking changes. Windows has been tested end to end; Linux has not yet. Support is best effort, with no promised response time. See the [repository](https://github.com/Kscl1/project-manager), [releases](https://github.com/Kscl1/project-manager/releases) and [contributing guide](https://github.com/Kscl1/project-manager/blob/main/CONTRIBUTING.md).
