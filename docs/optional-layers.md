---
title: Optional layers
description: What each layer adds, what it needs and when to add it.
---

The core layer is enough to plan a task, do it and check it. These four layers add more. Each one is optional, and you can add one later without reinstalling the rest. New words are in the [glossary](glossary.md).

| Layer | What it adds | What it needs |
|---|---|---|
| [Map](#map-layer-optional) | Diagrams of your architecture that your agent can read and keep current | Node.js |
| [Swarm](#swarm-layer-optional) | Helper agents in terminal panes you can watch | Pi and Herdr |
| [EVREN](#evren-layer-optional) | Your own EVREN models, through a local bridge | An EVREN account |
| [Statechart](#statechart-layer-optional) | mise, which the `pm-statechart` skill uses to get Java and TLC: a flow with states checked and drawn, bug paths marked | Node.js (core) |

Tick a layer in the setup screen, or add `--map` / `--swarm` to the installer command. EVREN and Statechart have no installer flag: their steps come from the setup screen's check list.

## Map layer (optional)

[LikeC4](https://likec4.dev/tooling/cli/) turns a model of your architecture into diagrams you can browse: `npx likec4@1.60.0 start` in the project. The first map preview may download the pinned LikeC4 package; your assistant asks before that. Its [MCP server](https://likec4.dev/tooling/mcp/) (Model Context Protocol: a small server your agent can ask for data) lets your agent read that model, and the `pm-likec4-dsl` skill (LikeC4's own `likec4-dsl` skill, copied at v1.60.0) teaches it the syntax, and the `pm-map` skill teaches it how to draw a map that reads at a glance and opens in layers: short text on each box, detail in the box's panel, one shared set of colours for boxes and arrows; tick Map in the setup screen, or add `--map` to the installer command. If the project already has a `.mcp.json` (for example from an earlier core-only setup), the server is listed for `/pm-setup` to add rather than written into your file.

## Swarm layer (optional)

The swarm runs helper agents as workers you can watch: each one in its own [Herdr](https://herdr.dev) pane, started and checked by `.pm/swarm/pm_run.py`. You do not need it to start. Tick Swarm in the setup screen (it starts unticked), or add `--swarm` to the installer command. It needs:

- [Pi](https://github.com/earendil-works/pi), with the extensions `pi-mcp-adapter` (the project's MCP servers, such as Context7, for Pi workers) and `pi-web-access` (web search and pages). Pi finds the `pm-` skills in `.agents/skills/` once you trust the project when Pi asks; call them as `/skill:pm-setup` and so on.
  While Pi and the extensions install, npm may report "high severity vulnerabilities" and install-script warnings from their own dependencies; setup goes on.
  `pi-mcp-adapter` replaces Pi's built-in MCP: on its first start it turns the built-in off in your Pi user settings (`pi config` turns it back on), and it reads the project's `.mcp.json`, the file Claude Code reads too.
  The project's MCP servers start only after you allow them. The first time Pi opens the project, it asks once per server ("Allow project MCP server?"); choose Allow, because Enter means Don't allow. Pi remembers the answer for that project and its worktrees. Answer it once in `pi` in your project before the first pm_run worker, so no worker stops at the question.
- Herdr, from its own installer, which puts the newest release on your PATH and checks its SHA-256.

Two things no check can see, so the Done screen reminds you: start `herdr` once in a terminal and leave it running, and sign in to a model in Pi (`pi`, then `/login`; with a ChatGPT plan, choose OpenAI, then Sign in with ChatGPT). Set `PM_RUN_HERDR` only if `herdr` is not on your PATH.

On its first start Herdr shows a welcome, then an "agent integrations" screen that offers to install integrations for the agents it finds; pm_run does not need them, and `Esc` skips it. After Sign in with ChatGPT, Pi may pick a model a ChatGPT plan cannot use (`gpt-5.5`, error 400): type `/model`, choose `openai/gpt-6.1-sol` and press `Ctrl+S` to keep it for new sessions. pm_run workers are not affected, because each job names its model.

A worker in Claude Code starts without Claude Code's bundled skills (such as `/code-review`, which starts its own hidden helper); your own Claude Code setup is not changed. Which commands it may run without asking follows your Claude Code settings: read-only ones such as `git status` never ask. When a worker asks, pm_run writes `WAITING` and the Herdr tab to answer in.

## EVREN layer (optional)

[evren-bridge](https://github.com/Kscl1/evren-bridge) is a local bridge to the models of [EVREN](https://evren.ssyz.org.tr), for agents that speak OpenAI Chat Completions, such as Pi; it is not an official EVREN project. EVREN is a model service some people already pay for. Tick EVREN in the setup screen (it starts unticked) only if you have your own EVREN account. Setup follows the bridge's own README: it clones the repo to `~/evren-bridge` and installs its one dependency, `rich` (on Omarchy from pacman, because Arch's Python refuses `pip install`); start the bridge with the same `python`. The check reads the release tag of that clone, and an older clone is updated with `git pull`.

Setup never asks for your EVREN API key, and never reads it. Put it in place yourself as the Quick start of the [evren-bridge README](https://github.com/Kscl1/evren-bridge#quick-start) says (get one from [EVREN API keys](https://evren.ssyz.org.tr/api-keys)), run `python evren_bridge.py` in `~/evren-bridge` and leave it running, then add an OpenAI-compatible provider with base URL `http://127.0.0.1:8787/v1` in your agent; the bridge's README shows Pi's `models.json`. Nothing else depends on it: without the EVREN layer the other screens and the installer work the same, and deleting `~/evren-bridge` only makes its row missing while EVREN is ticked.

## Statechart layer (optional)

The `pm-statechart` skill checks a flow that moves between states, such as a sign-up, a payment or a server that starts and stops, and draws it as a Mermaid statechart with the shortest path to each state that breaks a rule marked. Your agent writes a small TLA+ model of the flow, the TLC model checker tries every path through it, and you read the chart. The skill is a copy of the [statechart skill](https://github.com/cursor/plugins/tree/main/pstack/skills/statechart) of [P-Stack](https://github.com/cursor/plugins/tree/main/pstack) (MIT, by Lauren Tan) with fixes that let it run on Windows; it comes with the core package in every project.

TLC is a Java program, so the skill needs Java and TLC. It gets both with mise, a tool installer, on its first run, which needs the network. The Statechart layer installs mise; tick it in the setup screen (it starts unticked). By hand: `winget install --id jdx.mise --exact --source winget` on Windows, `sudo pacman -S --needed mise` on Omarchy, or [mise's own guide](https://mise.jdx.dev/getting-started.html).

Type `/pm-statechart` when you want a flow checked. The skill runs with Node.js, which the core layer installs; on Windows it runs through the Git Bash that Claude Code uses. Some antivirus programs stop mise while it unpacks Java on the first run; let that one run finish, or install Java and TLC yourself and set `JAVA` and `TLA2TOOLS` to them. A model that passes is not proof that the code does the same: the skill asks the agent to replay each bug path against the real code.
