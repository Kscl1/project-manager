# project-manager

Used ChatGPT or Gemini on your phone? You already know how to ask for help in plain words. Here the same words work, and the assistant can also read and change the files in the project folder you open. project-manager helps it keep the work notes for the next chat.

You do not have to learn a new tool: it uses files and programs you already have. It is not another AI model or a website you visit. Your application keeps its own folders, and every record is a file you can open in an editor or review in Git.

**Only used AI on your phone?** [Start here](docs/first-time.md) · [Türkçe](docs/tr/index.md)

![Four panels: you ask for a small change; the assistant shows its plan, you approve, it changes the file and runs the check; the notes are saved in .pm/ in your project; next time a new chat reads the notes, checks the files and names the next step.](public/next-chat.svg)

**The new chat reads saved files, not the old assistant's mind.** In words: you ask for a small change; after your yes the assistant updates the project and writes a work note in `.pm/`; you close the chat; in a new chat you open the same folder and say "continue"; the assistant reads the notes, checks the files and names the next action.

**The project's notebook.** Think of `.pm/` as the project's notebook. The assistant writes the job list, the reasons for choices and where you stopped there, as plain text files you can open. It is not the AI's memory, and it does not keep every word of a chat: the assistant reads the notes and checks the files each time.

## What you need

- **A coding agent:** a chat window that can read and change your project, such as [Claude Code](https://code.claude.com). Do you not have one yet? Install it first, then come back.
- **A project folder:** the folder that holds your code. If it is not a Git repository yet, the agent offers to turn it into one during setup (a Git repository is a folder whose history Git keeps).
- **About 15 minutes.** The agent path below needs no terminal skills; the other two ways ask you to type commands.

You need five programs. The installer checks them and names what is missing. The badges show each program's minimum version; the installer itself pins a tested version, a little newer, and tells you when yours differs.

[![Status: alpha](https://img.shields.io/badge/status-alpha-orange)](#status)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![Git 2.54.0+](https://img.shields.io/badge/Git-2.54.0%2B-F05032?logo=git&logoColor=white)
![Node.js 24.14.0+](https://img.shields.io/badge/Node.js-24.14.0%2B-5FA04E?logo=nodedotjs&logoColor=white)
[![Backlog.md 1.52.0+](https://img.shields.io/badge/Backlog.md-1.52.0%2B-000000?logo=markdown&logoColor=white)](https://github.com/MrLesk/Backlog.md)
[![Claude Code 2.1.296+](https://img.shields.io/badge/Claude_Code-2.1.296%2B-D97757?logo=claude&logoColor=white)](https://code.claude.com)

## Install

Open your project folder in a coding agent: in Claude Desktop, click **Code** and choose the folder; in a terminal, run `cd "<your project folder>"`, then `claude`. The only command you type yourself is `/pm-setup`, in that agent's chat box after the install (Pi: `/skill:pm-setup`, Codex: `$pm-setup`).

Paste this into the chat box:

```text
Install project-manager into my project. Read all of https://raw.githubusercontent.com/Kscl1/project-manager/main/docs/install-with-agent.md, follow it step by step, ask me before every change, and stop where it says to stop.
```

Do you work in Turkish? Paste this one instead; it points the agent at the Turkish page:

```text
project-manager'ı projeme kur. https://raw.githubusercontent.com/Kscl1/project-manager/main/docs/tr/install-with-agent.md sayfasının tamamını oku, adım adım izle, her değişiklikten önce bana sor ve sayfanın dur dediği yerde dur.
```

The agent asks which project and which optional parts you want, checks your machine, keeps its changes on a separate branch so you can undo them, and writes a short note for the next chat. This setup asks before changing your files; your assistant's own permission settings matter too. The AI can make mistakes; check what it did. Then you open the project again in a new chat and type `/pm-setup`.

The steps your agent follows: [Install with your agent](docs/install-with-agent.md) ([Türkçe](docs/tr/install-with-agent.md)).

[Getting started](docs/getting-started.md) · [Package guide](template/README.md) · [Principles](template/.pm/principles.md)

## After setup, just say

Once `/pm-setup` has made your first real task, you do not need commands to run the work:

- `continue`: your agent says where you stopped and what is next.
- `what next?`: it names the next task and why.
- `show the board`: the task board opens.
- `explain <word>`: a plain explanation, and nothing changes.

Words such as task, Epic, commit or MCP server are in the [glossary](docs/glossary.md).

## Other ways

### The setup screen

A text menu in your terminal. It checks each program, lets you tick optional parts and runs one step at a time.

You need **Python 3.11+** and **Git** in a Git repository. Clone project-manager **next to** your project, not inside it, and start the screen:

```bash
git clone --branch v0.1.0-alpha.6 https://github.com/Kscl1/project-manager.git
cd project-manager
python -m venv tools/setup/.venv
```

The last line makes a private folder for this tool's Python libraries.

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
| **Map**   | On by default      | LikeC4 CLI (`npx likec4@1.60.0 start`), LikeC4 MCP server, `pm-likec4-dsl` skill.                               |
| **Swarm** | Off by default     | Pi, Herdr, and the swarm runner for visible worker panes and evidence checks.                                       |
| **EVREN** | Off by default, only if you have an EVREN account | evren-bridge, a local bridge to your own EVREN models for Pi. EVREN is a model service some people already pay for ([details](docs/optional-layers.md#evren-layer-optional)). |

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
