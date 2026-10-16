# Getting started

project-manager keeps your tasks, decisions and working rules next to your code, so your coding agent plans and checks work the same way every session.

There are two ways in: the **setup TUI** (recommended), a guided screen in your terminal, or **by hand**, working down the layers below. Either way, you finish by running `/pm-setup` in your project, where your agent fits the package to the project with you.

## Before you start

You need an internet connection, **Python 3.11 or newer** and **Git**. The TUI cannot install the Python it runs on.

**Windows 11:** in PowerShell, install [Python](https://www.python.org/downloads/windows/) and [Git for Windows](https://git-scm.com/install/windows) with [WinGet](https://learn.microsoft.com/en-us/windows/package-manager/winget/), then open a new terminal:

```powershell
winget install --id Python.Python.3.11 --exact --source winget
winget install --id Git.Git --exact --source winget
```

**Omarchy and other Arch-based systems:** both are usually there already; check with `python --version` and `git --version`. If not, use [pacman](https://man.archlinux.org/man/pacman.8.en):

```bash
sudo pacman -S --needed python git
```

Your project must be a Git repository. For a new project, create its folder and run `git init` in it. Commit or back up your work before setup.

## Run the setup TUI

In the folder that holds your project, clone project-manager **next to** it, not inside it, and give the TUI its own virtual environment (a folder that keeps its Python libraries apart from the rest of your system):

```bash
git clone https://github.com/Kscl1/project-manager.git
cd project-manager
python -m venv tools/setup/.venv
```

Then install its libraries and start it with your project folder.

Windows PowerShell:

```powershell
tools/setup/.venv/Scripts/python -m pip install -r tools/setup/requirements.txt
tools/setup/.venv/Scripts/python tools/setup/app.py "C:/projects/my-project"
```

Omarchy:

```bash
tools/setup/.venv/bin/python -m pip install -r tools/setup/requirements.txt
tools/setup/.venv/bin/python tools/setup/app.py ~/projects/my-project
```

| Screen | What happens | Keys |
|---|---|---|
| Check | Shows each program and project file: installed, minimum and tested version. Nothing changes here. On a rerun with nothing left, `Enter` goes straight to Done. | `Enter` continues, `r` checks again, `c` copies a path, `l` changes the layers on a rerun |
| Choose | Core is always on; tick Map if you want diagrams, Swarm if you want visible worker agents. Lists the steps this machine needs. | `Space` ticks, `Enter` continues, `Esc` goes back |
| Install | One step at a time. It shows the command first; the project step also shows the installer's plan. | `y` runs, `s` skips, `c` copies, `r` checks again |
| Done | What is ready, what is left, and how to open your project. | `o` opens Claude Desktop (Windows), `c` copies the commands |

Nothing is installed until you press `y` on a step. A version above the tested one means **not tested yet**, not broken. Setup never rewrites a file of yours; it only adds lines at the end of `.gitignore` and `.gitattributes`. If your project already has its own `AGENTS.md`, git hooks, `.claude/settings.json` or `.mcp.json`, they are kept as they are and listed for `/pm-setup` to merge with you.

**Stuck? Press `a`.** It copies a message for your coding agent, which can finish the setup without the TUI. If copying does not work, select the text on screen. `python tools/setup/bom.py --project <folder>` prints the same check and the commands; it installs nothing.

After an installer finishes, read its output and press `Enter` to go back. If a program is still not found, open a new terminal and start setup again. On Linux, `sudo` asks for your password and shows nothing while you type it.

## Core layer

What every project needs. By hand, work down the table.

| Tool | What it is for, and how to install it |
|---|---|
| [Node.js](https://nodejs.org/en/download) | Runs the JavaScript tools below. Windows: `winget install --id OpenJS.NodeJS.LTS --exact --source winget`. Omarchy: `omarchy install dev-env node`. |
| [Backlog.md](https://github.com/MrLesk/Backlog.md) | Your tasks, as Markdown files in the project. `npm i -g backlog.md@1.52.0`. If npm says `EACCES`, follow [npm's guide](https://docs.npmjs.com/resolving-eacces-permissions-errors-when-installing-packages-globally); do not add `sudo`. |
| [Claude Code](https://code.claude.com/docs/en/setup) | Your coding agent. Windows PowerShell: `irm https://claude.ai/install.ps1 \| iex`. Linux: `curl -fsSL https://claude.ai/install.sh \| bash`. Sign in when you first run `claude`. |
| The `.pm` package | Rules, decisions, checks and the `pm-` skills (`pm-setup`, `pm-grilling`, `pm-grill-me`, `pm-scratch`, `pm-feedback`). |
| Session hooks | Show your agent where work stopped when a session starts and after its memory is compacted. |
| [Context7](https://github.com/upstash/context7) | Gives your agent current library docs. No account needed; a free key only raises its rate limit. |

The last three come from one command, run from the project-manager folder. The TUI runs it for you:

```bash
python template/.pm/tools/pm_init.py ../my-project --check
python template/.pm/tools/pm_init.py ../my-project
```

`--check` prints everything it would write and writes nothing. If your project already has its own agent instructions, Backlog.md or git hooks, the installer stops; run it again with `--keep-existing` to install and keep yours. A second run changes nothing.

## Map layer (optional)

[LikeC4](https://likec4.dev/tooling/cli/) turns a model of your architecture into diagrams you can browse: `npx likec4@1.59.4 start` in the project. Its [MCP server](https://likec4.dev/tooling/mcp/) lets your agent read that model, and the `pm-likec4-dsl` skill (LikeC4's own `likec4-dsl` skill, copied at v1.59.4) teaches it the syntax; tick Map in the TUI, or add `--map` to the installer command. If the project already has a `.mcp.json` (for example from an earlier core-only setup), the server is listed for `/pm-setup` to add rather than written into your file.

## Swarm layer (optional)

The swarm runs helper agents as workers you can watch: each one in its own [Herdr](https://herdr.dev) pane, started and checked by `.pm/swarm/pm_run.py`. You do not need it to start. Tick Swarm in the TUI (it starts unticked), or add `--swarm` to the installer command. It needs:

- [Pi](https://github.com/earendil-works/pi), with the extensions `pi-mcp-adapter` (the project's MCP servers, such as Context7, for Pi workers) and `pi-web-access` (web search and pages). Pi finds the `pm-` skills in `.agents/skills/` once you trust the project when Pi asks; call them as `/skill:pm-setup` and so on.
- Herdr, from its own installer, which puts the newest release on your PATH and checks its SHA-256.

Two things no check can see, so the Done screen reminds you: start `herdr` once in a terminal and leave it running, and sign in to a model in Pi (`pi`, then `/login`). Set `PM_RUN_HERDR` only if `herdr` is not on your PATH.

A worker in Claude Code starts without Claude Code's bundled skills (such as `/code-review`, which starts its own hidden helper); your own Claude Code setup is not changed. Which commands it may run without asking follows your Claude Code settings: read-only ones such as `git status` never ask. When a worker asks, pm_run writes `WAITING` and the Herdr tab to answer in.

## After setup: /pm-setup

Open your project, not the project-manager folder, in Claude Code:

- **Windows:** press `o` on the Done screen, or open [Claude Desktop](https://code.claude.com/docs/en/desktop-quickstart), choose Code and select the project folder. Desktop is a separate install and its Code tab needs a paid Claude plan; the terminal works too.
- **Linux:** `cd ~/projects/my-project`, then `claude`.

Type `/pm-setup` and press Enter. Your agent opens a setup Epic in Backlog (a parent task with one child per question) and asks about one thing at a time: your existing agent rules, git hooks, CI, tests, task lists, anything setup left for you to merge, the project's purpose (its charter) and the models you have. Nothing changes without your yes.

At the end it asks how you want the tools explained: **short hints** (the default), **try together**, or **off**. Change it any time in chat ("stop teaching", "I already know Backlog").

## When something breaks

For a problem with the `.pm` package itself, run `/pm-feedback` in your project. It writes a diagnosis-only report and shows it to you; it opens an issue only on your yes, which needs GitHub's `gh` CLI signed in. If setup fails before the skills are installed, use the TUI's `a` key instead.
