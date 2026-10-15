# Setup TUI: design (first slice)

A small terminal app a new user runs once before using `.pm`. It checks what is installed against what the product needs, shows the result in one table, and later offers the official install or upgrade for anything missing or too old. Python + Textual; runs on Windows 11 and Linux (Arch-based Omarchy first).

## The bill of materials becomes `bom.toml`

`tools/setup/bom.toml` is the one machine-readable list of what the product needs. One `[[item]]` per tool:

```toml
[[item]]
name = "Git"
layer = "core"                      # core | map (first trial); swarm comes later
check = ["git", "--version"]        # a command, never a shell line
min = "2.54.0"                      # below this the TUI warns
tested = "2.54.0"                   # above this the TUI says "not tested yet"
install.windows = "winget install Git.Git"
install.linux = "preinstalled on Omarchy"
```

TOML because people read and edit it, it allows comments, and Python 3.11 reads it with the standard library (`tomllib`). Install routes are stored now but not run in this slice. Until an older version has been tried, `min` equals `tested`.

## Data flow

```
bom.toml --load--> items --run check--> raw output --parse--> version --compare--> status --> table
```

- `bom.py` (standard library only, tested): `load()`, `installed_version()` runs the check command with a timeout, `parse_version()` takes the first `1.2.3` in the output (`git version 2.54.0.windows.1` -> `2.54.0`), `status()` compares.
- `app.py` (Textual, thin): one screen, one `DataTable`. Runs the checks in a background thread so the screen opens at once, then fills the rows. `q` quits, `r` runs the checks again.
- `python tools/setup/bom.py` prints the same table as plain text, without Textual.

## Status rules

| Installed version | Status |
|---|---|
| command not found | missing |
| found, but no version in the output | version unreadable |
| below `min` | below minimum |
| from `min` up to `tested` | ok |
| above `tested` | not tested yet |

Versions are compared number by number; a shorter version counts missing parts as 0 (`3.11` = `3.11.0`). At or above the minimum the TUI never touches the user's install.

## Screens

1. **Check** (this slice): the table, columns item, installed, minimum, tested, status.
2. **Choose** (later): core is fixed, map is optional; shows the install or upgrade command for each missing or too old item.
3. **Install** (later): shows each official command (winget, pacman, npm, official script) and runs it only after a yes.
4. **Done** (later): opens Claude Code Desktop on Windows, prints CLI steps on Linux.

On later runs only screen 1 appears, unless the project is new or the selection changed.

## Running it

```
python -m venv tools/setup/.venv
tools/setup/.venv/Scripts/python -m pip install -r tools/setup/requirements.txt    # Linux: tools/setup/.venv/bin/python
tools/setup/.venv/Scripts/python tools/setup/app.py
```

The TUI has its own virtual environment (ignored by git), because Arch blocks system-wide pip (PEP 668) and the user's Python stays untouched. It needs Python 3.11 or newer for `tomllib`. Tests: `python -m unittest discover -s tests`; the app tests skip where Textual is missing.

## Left for later, on purpose

- Installs and upgrades, each shown and confirmed.
- Project files: `.pm` package, shipped `pm-` skills, Context7 MCP in `.mcp.json`, the opener and compaction hooks; and listing the user's own skills with the same or a similar name as ours.
- The map layer: LikeC4 runs through `npx` with a pinned version, so nothing is installed to check yet.
- The swarm layer (Pi, Herdr, Pi extensions).
- `/pm-setup`, the in-chat integration of `.pm` into an existing project.
- A one-line bootstrap that makes the virtual environment for the user.
- Renovate watching `bom.toml`.
