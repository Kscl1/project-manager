# project-manager

[![Status: alpha](https://img.shields.io/badge/status-alpha-orange)](#status)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![Git 2.54.0+](https://img.shields.io/badge/Git-2.54.0%2B-F05032?logo=git&logoColor=white)
![Node.js 24.14.0+](https://img.shields.io/badge/Node.js-24.14.0%2B-5FA04E?logo=nodedotjs&logoColor=white)
[![Backlog.md 1.52.0+](https://img.shields.io/badge/Backlog.md-1.52.0%2B-000000?logo=markdown&logoColor=white)](https://github.com/MrLesk/Backlog.md)
[![Claude Code 2.1.296+](https://img.shields.io/badge/Claude_Code-2.1.296%2B-D97757?logo=claude&logoColor=white)](https://code.claude.com)

[Getting started](docs/getting-started.md) · [Package guide](template/.pm/README.md) · [Principles](template/.pm/principles.md)

A shared, file-based workspace where you and coding agents from different model families run a software project inside Git.

It is neither a harness nor a framework. It combines existing open tools with plain Markdown records and standard-library Python checks.

## How the parts fit together

See [How it works](docs/how-it-works.md) for the workflow, roles, architecture diagram and what runs where.

- [Introduction](docs/index.md): what it is and who it is for.
- [Getting started](docs/getting-started.md): the guided setup and manual path.
- [Türkçe giriş](docs/tr/index.md) · [Türkçe başlangıç](docs/tr/getting-started.md).
- [Working principles](template/.pm/principles.md): the rules behind the workflow.

## Layers

| Layer           | Default              | Contents                                                                                                            |
| --------------- | -------------------- | ------------------------------------------------------------------------------------------------------------------- |
| **Core**  | Always on            | Python, Git, Node.js, Claude Code, Backlog.md, conventions and checks, session hooks, Context7 MCP, `pm-` skills. |
| **Map**   | On (`--map`)       | LikeC4 CLI (`npx likec4@1.60.0 start`), LikeC4 MCP server, `pm-likec4-dsl` skill.                               |
| **Swarm** | Opt-in (`--swarm`) | Pi, Herdr, and the swarm runner for visible worker panes and evidence checks.                                       |

## Install

Requires **Python 3.11+** and **Git** in a Git repository (`git init`). Clone `project-manager` **next to** your project and run the setup TUI:

```bash
git clone --branch v0.1.0-alpha.3 https://github.com/Kscl1/project-manager.git
cd project-manager
python -m venv tools/setup/.venv

# Windows PowerShell
tools/setup/.venv/Scripts/python -m pip install -r tools/setup/requirements.txt
tools/setup/.venv/Scripts/python tools/setup/app.py "C:/projects/my-project"

# Linux (Omarchy / Arch-based)
tools/setup/.venv/bin/python -m pip install -r tools/setup/requirements.txt
tools/setup/.venv/bin/python tools/setup/app.py ~/projects/my-project
```

- **Safe by default:** `Check` is read-only, each install step waits for `y`, and existing project files are never overwritten.
- **Next step:** Open your project in your coding agent and run `/pm-setup`.
- **Full guide and manual path:** See [`docs/getting-started.md`](docs/getting-started.md).

## Status

- **Stage:** Alpha; expect breaking changes. New alpha releases will come quickly.
- **Platforms:** Tested end to end on Windows; Linux not tested yet.
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
