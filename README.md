# project-manager

You talk to your AI coding assistant in plain words; it keeps your project's tasks, decisions and notes as files in your project, so the next session continues where you stopped.

You do not learn a new tool: it uses files and programs you already have. Your application keeps its own folders, and every record is a file you can open in an editor or review in Git.

## What you need

- **A coding agent:** a chat window that can read and change your project, such as [Claude Code](https://code.claude.com). Do you not have one yet? Install it first, then come back.
- **A project folder:** the folder that holds your code. It should be a Git repository; if it is not, run `git init` once inside it.
- **About 15 minutes.** The agent path below needs no terminal skills; the other two ways ask you to type commands.

You need five programs. The installer checks them and names what is missing; the badges show the minimum version, and the installer pins a tested one and tells you when yours differs.

[![Status: alpha](https://img.shields.io/badge/status-alpha-orange)](#status)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![Git 2.54.0+](https://img.shields.io/badge/Git-2.54.0%2B-F05032?logo=git&logoColor=white)
![Node.js 24.14.0+](https://img.shields.io/badge/Node.js-24.14.0%2B-5FA04E?logo=nodedotjs&logoColor=white)
[![Backlog.md 1.55.3+](https://img.shields.io/badge/Backlog.md-1.55.3%2B-000000?logo=markdown&logoColor=white)](https://github.com/MrLesk/Backlog.md)
[![Claude Code 2.1.296+](https://img.shields.io/badge/Claude_Code-2.1.296%2B-D97757?logo=claude&logoColor=white)](https://code.claude.com)

[Getting started](docs/getting-started.md) · [Package guide](template/.pm/README.md) · [Principles](template/.pm/principles.md)

## Install

Open your coding agent in the folder that holds your project and paste this:

```text
Install project-manager into my project. Read all of https://raw.githubusercontent.com/Kscl1/project-manager/main/docs/install-with-agent.md, follow it step by step, ask me before every change, and stop where it says to stop.
```

The agent asks which project and which optional parts you want, checks your machine, keeps its changes on a separate branch so you can undo them, and writes a short note for the next chat. Nothing changes without your yes. Then you open the project in a new session and type `/pm-setup`.

The steps your agent follows: [Install with your agent](docs/install-with-agent.md) ([Türkçe](docs/tr/install-with-agent.md)).

## After setup, just say

Once `/pm-setup` has made your first real task, you do not need commands to run the work:

- `continue`: your agent says where you stopped and what is next.
- `what next?`: it names the next task and why.
- `show the board`: the task board opens.
- `explain <word>`: a plain explanation, and nothing changes.

The words in these sentences (task, Epic, commit, MCP server and others) are in the [glossary](docs/glossary.md).

## Other ways

### The setup screen

A text menu in your terminal. It checks each program, lets you tick optional parts and runs one step at a time.

You need **Python 3.11+** and **Git** in a Git repository. Clone project-manager **next to** your project, not inside it, and start the screen:

```bash
git clone --branch v0.1.0-alpha.6 https://github.com/Kscl1/project-manager.git
cd project-manager
python -m venv tools/setup/.venv
```

Windows PowerShell:

```powershell
tools/setup/.venv/Scripts/python -m pip install -r tools/setup/requirements.txt
tools/setup/.venv/Scripts/python tools/setup/app.py "C:/projects/my-project"
```

Linux (Omarchy / Arch-based):

```bash
tools/setup/.venv/bin/python -m pip install -r tools/setup/requirements.txt
tools/setup/.venv/bin/python tools/setup/app.py ~/projects/my-project
```

- **Safe by default:** `Check` is read-only, each install step waits for `y`, and existing project files are never overwritten.
- **Next step:** open your project in your coding agent and run `/pm-setup`.
- **Full guide, and what each screen shows:** [Getting started](docs/getting-started.md).

### By hand

If you like commands, or the other two ways do not work: install each program and the package yourself, working down the Core layer table in [Getting started](docs/getting-started.md#core-layer).

## How the parts fit together

See [How it works](docs/how-it-works.md) for the workflow, roles, architecture diagram and what runs where.

- [Introduction](docs/index.md): what it is and who it is for.
- [Getting started](docs/getting-started.md): the guided setup and manual path.
- [Türkçe giriş](docs/tr/index.md) · [Türkçe başlangıç](docs/tr/getting-started.md).
- [Working principles](template/.pm/principles.md): the rules behind the workflow.

## Layers

Only the Core layer is needed to start. The other three are optional and can be added later.

| Layer           | Default              | Contents                                                                                                            |
| --------------- | -------------------- | ------------------------------------------------------------------------------------------------------------------- |
| **Core**  | Always on            | Python, Git, Node.js, Claude Code, Backlog.md, conventions and checks, session hooks, Context7 MCP, `pm-` skills. |
| **Map**   | On (`--map`)       | LikeC4 CLI (`npx likec4@1.60.0 start`), LikeC4 MCP server, `pm-likec4-dsl` skill.                               |
| **Swarm** | Opt-in (`--swarm`) | Pi, Herdr, and the swarm runner for visible worker panes and evidence checks.                                       |
| **EVREN** | Opt-in, only if you have an EVREN account | evren-bridge, a local bridge to your own EVREN models for Pi. EVREN is a model service some people already pay for ([details](docs/optional-layers.md#evren-layer-optional)). |

## Status

- **Stage:** Alpha; expect breaking changes. New alpha releases will come quickly.
- **Platforms:** Windows is tested end to end. The Linux steps are documented but not tested yet.
- **Licence and support:** [MIT](LICENSE). Experimental, best-effort support with no promised response time. Issues and pull requests: [CONTRIBUTING.md](CONTRIBUTING.md).

## Credits

### Built on

- **[Backlog.md](https://github.com/MrLesk/Backlog.md)** — task board and backbone of the project.
- **[Claude Code](https://code.claude.com)** — coding agent installed by setup today.
- **[Pi](https://github.com/earendil-works/pi)** — coding agent harness for workers and leads.
- **[Herdr](https://herdr.dev)** — runs worker agents in visible terminal panes.
- **[LikeC4](https://likec4.dev)** — architecture model, CLI, and MCP server.
- **[Context7](https://github.com/upstash/context7)** — MCP server for current library documentation.
- **[gitleaks](https://github.com/gitleaks/gitleaks)** and **[ruff](https://github.com/astral-sh/ruff)** — secret scanning and Python checks on this repo.

### Adapted

- **Matt Pocock's [skills](https://github.com/mattpocock/skills)** (MIT).
- **[pstack](https://github.com/cursor/plugins/tree/main/pstack)** (MIT) — our [working principles](template/.pm/principles.md).

### Thanks

- Inspired by OpenAI's [harness engineering](https://openai.com/index/harness-engineering/) write-up.
- Inspired by [kontext](https://github.com/patkusch/kontext).
- Inspired by [ADR and MADR](https://adr.github.io/madr/).
- Inspired by [Everything Claude Code](https://github.com/affaan-m/everything-claude-code).
