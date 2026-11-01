---
title: Getting started
description: Install the work-system package in your project, then fit it with your agent.
---

project-manager keeps your tasks, decisions and working rules next to your code, so your coding agent plans and checks work the same way every session.

There are three ways in: let your **coding agent** do it ([Install with your agent](install-with-agent.md): paste one prompt, answer its questions), the **setup TUI**, a guided screen in your terminal, or **by hand**, working down the layers below. Every way ends with `/pm-setup` in your project, where your agent fits the package to the project with you.

## Before you start

You need an internet connection, **Python 3.11 or newer** and **Git**. The TUI cannot install the Python it runs on.

**Windows 11:** in PowerShell, install the [Python Install Manager](https://docs.python.org/3/using/windows.html) and [Git for Windows](https://git-scm.com/install/windows) with [WinGet](https://learn.microsoft.com/en-us/windows/package-manager/winget/), then open a new terminal and install Python itself with `py`:

```powershell
winget install --id Python.PythonInstallManager --exact --source winget
winget install --id Git.Git --exact --source winget
py install 3.13
```

The older installers (`Python.Python.3.11` and so on) can be stopped by Smart App Control with a "Bad Image" error (`0xc0e90002`); the Install Manager is not.

**Omarchy and other Arch-based systems:** both are usually there already; check with `python --version` and `git --version`. If not, use [pacman](https://man.archlinux.org/man/pacman.8.en):

```bash
sudo pacman -S --needed python git
```

Your project must be a Git repository. For a new project, create its folder and run `git init` in it. Commit or back up your work before setup.

## Run the setup TUI

In the folder that holds your project, clone project-manager **next to** it, not inside it, and give the TUI its own virtual environment (a folder that keeps its Python libraries apart from the rest of your system):

```bash
git clone --branch v0.1.0-alpha.6 https://github.com/Kscl1/project-manager.git
cd project-manager
python -m venv tools/setup/.venv
```

`--branch v0.1.0-alpha.6` installs the release, not the newest `main`. Git then reports a "detached HEAD": that is expected, it only means the clone sits on a release instead of a branch. Newer releases are listed on the [Releases](https://github.com/Kscl1/project-manager/releases) page.

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
| Choose | Core is always on; tick Map if you want diagrams, Swarm if you want visible worker agents, EVREN only if you have an EVREN account. Lists the steps this machine needs. | `Space` ticks, `Enter` continues, `Esc` goes back |
| Install | One step at a time. It shows the command first; the project step also shows the installer's plan. | `y` runs, `s` skips, `c` copies, `r` checks again |
| Done | What is ready, what is left, and how to open your project. | `o` opens Claude Desktop (Windows), `c` copies the commands |

Nothing is installed until you press `y` on a step. A version above the tested one means **not tested yet**, not broken. Setup never rewrites a file of yours; it only adds lines at the end of `.gitignore`, `.gitattributes` and `.ignore` (the last lets search tools such as ripgrep into the hidden `.pm/` folder). If your project already has its own `AGENTS.md`, git hooks, `.claude/settings.json` or `.mcp.json`, they are kept as they are and listed for `/pm-setup` to merge with you.

**Stuck? Press `a`.** It copies a message for your coding agent, which can finish the setup without the TUI. If copying does not work, select the text on screen. `python tools/setup/bom.py --project <folder>` prints the same check and the commands; it installs nothing.

After an installer finishes, read its output and press `Enter` to go back. If a program is still not found, open a new terminal and start setup again. On Linux, `sudo` asks for your password and shows nothing while you type it.

## Core layer

What every project needs. By hand, work down the table.

| Tool | What it is for, and how to install it |
|---|---|
| [Node.js](https://nodejs.org/en/download) | Runs the JavaScript tools below. Windows: `winget install --id OpenJS.NodeJS.LTS --exact --source winget`. Omarchy: `omarchy install dev-env node`. |
| [Backlog.md](https://github.com/MrLesk/Backlog.md) | Your tasks, as Markdown files in the project. `npm i -g backlog.md@1.55.3`. If npm says `EACCES`, follow [npm's guide](https://docs.npmjs.com/resolving-eacces-permissions-errors-when-installing-packages-globally); do not add `sudo`. |
| [Claude Code](https://code.claude.com/docs/en/setup) | Your coding agent. Windows PowerShell: `irm https://claude.ai/install.ps1 \| iex`. Linux: `curl -fsSL https://claude.ai/install.sh \| bash`. Both put `claude` in `.local\bin` (`~/.local/bin`) in your home folder; on Windows that folder is not added to PATH, so the TUI's step adds it to your user PATH for you (by hand: add `%USERPROFILE%\.local\bin`, then open a new terminal). Sign in when you first run `claude`. |
| The `.pm` package | Rules, decisions, checks and the `pm-` skills (`pm-setup`, `pm-grilling`, `pm-grill-me`, `pm-scratch`, `pm-feedback`). |
| Session hooks | Show your agent where work stopped when a session starts and after its memory is compacted. |
| [Context7](https://github.com/upstash/context7) | Gives your agent current library docs. No account needed; a free key only raises its rate limit. |

The last three come from one command, run from the project-manager folder. The TUI runs it for you:

```bash
python template/.pm/tools/pm_init.py ../my-project --check
python template/.pm/tools/pm_init.py ../my-project
```

`--check` prints everything it would write and writes nothing. If your project already has its own agent instructions, Backlog.md or git hooks, the installer stops; run it again with `--keep-existing` to install and keep yours. A second run changes nothing.

**Your language.** Add `--lang tr` (or another language code) and the agent talks to you and writes tasks, decisions, worklogs and commit messages in that language. Keys such as `Next:` and status names such as `Done` stay English, because the tools read them: `Next: İlk testi çalıştır`. The flag writes one `Language: tr` line in `AGENTS.md` and Claude Code's `language` setting in the project's `.claude/settings.json`, so it holds for everyone who opens the project (a settings file of your own is listed for `/pm-setup` instead); without it, `/pm-setup` asks once. To change it later, run `python .pm/tools/pm_init.py . --lang <code>` in the project; older records are not translated. When a task or decision still reads as English, `pm_check` prints an `Info:` line about it and passes.

## Optional layers

Map adds architecture diagrams your agent can keep current, Swarm runs helper agents in panes you can watch, and EVREN connects your own EVREN models through a local bridge. None of them is needed for a first task, and you can add one later.

[Map, Swarm and EVREN](optional-layers.md): what each one adds, what it needs and how to add it.

## After setup: /pm-setup

Open your project, not the project-manager folder, in Claude Code:

- **Windows:** press `o` on the Done screen, or open [Claude Desktop](https://code.claude.com/docs/en/desktop-quickstart), choose Code and select the project folder. Desktop is a separate install and its Code tab needs a paid Claude plan; the terminal works too. If Desktop asks you to sign in first, it forgets the project: sign in, then press `o` again.
- **Linux:** `cd ~/projects/my-project`, then `claude`.

Type `/pm-setup` and press Enter. If an install chat left a hand-over note (`.pm/local/handover.md`), your agent reads it first. It opens with three sentences on what `.pm` is and asks how you want the project-management side explained (below). Then it opens a setup Epic in Backlog (a parent task with its steps as children) and goes through what it finds, one thing at a time: your existing agent rules, git hooks, CI, tests, task lists, anything setup left for you to merge, the project's purpose (its charter) and the models you have. Nothing changes without your yes. It ends with one small real task from your project and a prompt for your next session.

Already have MCP servers, plugins, skills or apps? See [Make your own tools useful](own-tools.md). `/pm-setup` checks one at a time, keeps your existing setup and, with approval, adds a short “which tool when” rule plus a real smoke check.

How it explains: **short hint** (the default: one sentence the first time something new comes up, at most twice for the same thing), **try together** (it leaves the step to you and guides; you never type a command) or **off** (no explanations; it still asks before changing your files). The first real task is done together unless you choose off. Change it any time in chat: "stop teaching", "explain tasks", "I already know Backlog".

## Updating later

See [Upgrade and roll back](upgrading.md) for release-tag upgrades, separate tool/skill updates and keeping project records through a rollback.

## When something breaks

For a problem with the `.pm` package itself, run `/pm-feedback` in your project. It writes a diagnosis-only report and shows it to you; it opens an issue only on your yes, which needs GitHub's `gh` CLI signed in. If setup fails before the skills are installed, use the TUI's `a` key instead.

**Windows, Smart App Control.** Seen so far only in Windows Sandbox, not yet on a real PC: with Smart App Control on, `git` fails with a "Bad Image" error (`0xc0e90002`), because it blocks Git for Windows' unsigned DLLs. The Git installer still reports success but leaves Git without a credential helper, so `git clone` asks for a GitHub user name in the terminal instead of opening the sign-in window. Check with `git config --system credential.helper` (it should print `manager`). If it prints nothing, reinstall Git once, but only after `git --version` works again (that is, when Smart App Control no longer blocks Git): `winget install --id Git.Git --exact --source winget --force`. Smart App Control is a Windows security setting (Windows Security, App & browser control); decide yourself whether to turn it off.
