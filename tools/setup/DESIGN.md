# Setup TUI: design (first slice)

A small terminal app a new user runs once before using `.pm`. It checks what is installed against what the product needs, shows the result in one table, and later offers the official install or upgrade for anything missing or too old. Python + Textual; runs on Windows 11 and Linux (Arch-based Omarchy first).

This slice is a read-only check. It never installs, upgrades or downloads anything, and it never shows "ok" for something it did not check.

## The bill of materials becomes `bom.toml`

`tools/setup/bom.toml` is the one machine-readable list of what the product needs. One `[[item]]` per tool:

```toml
[[item]]
id = "git"                          # stable key
name = "Git"
kind = "command"                    # command | project-file | manual
layer = "core"                      # core | map (first trial); swarm comes later
check = ["git", "--version"]        # a command and its arguments, never a shell line
min = "2.54.0"                      # below this the TUI warns
tested = "2.54.0"                   # above this the TUI says "not tested yet"
install.windows = "winget install --id Git.Git --exact --source winget"
install.linux = "sudo pacman -S --needed git"
note = "Preinstalled on Omarchy."
```

- **command**: the TUI runs `check` and reads the version. `min` and `tested` are required. `npx` is refused, because it may download.
- **project-file**: lives in the user's project at `path` (the `.pm` package, the hooks, `.mcp.json`, the `pm-` skills, with the upstream `ref` for copied skills). Shown as "not checked" in this slice.
- **manual**: nothing on the machine to check (LikeC4 runs through `npx` with a pinned version).

Unknown versions are left out, never written as "not set". Until an older version has been tried, `min` equals `tested`. `install.*` and `note` are text shown to the user, never handed to a shell. `load()` stops with a plain message on a duplicate id, an unknown kind, a malformed version or `min` above `tested`.

TOML because people read and edit it, it allows comments, and Python 3.11 reads it with the standard library (`tomllib`).

## Data flow

```
bom.toml --load--> items --probe--> path, exit, output --parse--> version --compare--> status --> table
```

- `bom.py` (standard library only, tested): `load()`; `probe()` resolves the executable (`shutil.which`, which also finds npm's `.cmd` shims on Windows; for Python the interpreter running the TUI, `sys.executable`), runs the check with a 15-second timeout and keeps the path; `parse_version()`; `status()`.
- `app.py` (Textual, thin): one screen, one `DataTable`. The checks run in a thread worker so the screen opens at once; the worker hands the rows back with `call_from_thread`, because Textual is not thread-safe. While a scan runs, `r` does nothing. `q` quits. Under the table: the counts, one next-step sentence (`next_step()`, from the worst status) and a legend. Each status has a symbol as well as the theme's colour, so it reads without colour; not-checked rows are dimmed. The Path column shows from 100 columns up, so 80 columns fit without scrolling.
- `python tools/setup/bom.py` prints the same table and next step as plain text, without Textual.

## Status rules

| What the check found | Status |
|---|---|
| project-file or manual item | not checked |
| command not found | missing |
| non-zero exit, timeout or start error (no version is taken from its output) | check failed |
| exit 0, no version in the output | version unreadable |
| a version with a suffix, such as `3.15.0rc1` | cannot compare |
| below `min` | below minimum |
| from `min` up to `tested` | ok |
| above `tested` | not tested yet |

The version is the first word that starts like `3.11` or `3.11.9`. Git's `.windows.1` suffix is dropped; any other suffix makes the version uncomparable rather than guessing. Versions are compared number by number; `3.11` equals `3.11.0`. At or above the minimum the TUI never touches the user's install. One failing check gives one red row; the rest of the table still fills.

## Screens

1. **Check** (this slice): the table, columns item, installed, minimum, tested, status, path; the next step under it.
2. **Choose** (later): core is fixed, map is optional; shows the install or upgrade command for each missing or too old item.
3. **Install** (later): shows each official command (winget, pacman, npm, official script) and runs it only after a yes.
4. **Done** (later): opens Claude Code Desktop on Windows, prints CLI steps on Linux.

## Running it

A supported Python (3.11 or newer, for `tomllib`) must already exist; the TUI cannot install the Python it runs on. Without one, install it by hand first: Windows `winget install --id Python.Python.3.11 --exact --source winget`, Arch `sudo pacman -S --needed python`.

```
python -m venv tools/setup/.venv
tools/setup/.venv/Scripts/python -m pip install -r tools/setup/requirements.txt    # Linux: tools/setup/.venv/bin/python
tools/setup/.venv/Scripts/python tools/setup/app.py
```

The TUI has its own virtual environment (ignored by git), so the user's Python stays untouched. This also avoids PEP 668: a distribution that marks its Python as externally managed (Arch does) refuses system-wide `pip install`; whether it does depends on that marker file, not on Linux as such. Tests: `python -m unittest discover -s tests`; the app tests skip where Textual is missing.

## Left for later, on purpose

- Installs and upgrades, each shown and confirmed; offering the official upgrade for an item below its minimum.
- Checking project files: the `.pm` package, the hooks, `.mcp.json`, the `pm-` skills; and listing the user's own skills with the same or a similar name as ours (explicit name mappings first, no fuzzy matching engine).
- A record of the user's selection, so later runs show only the check screen unless the project is new or the selection changed.
- The swarm layer (Pi, Herdr, Pi extensions).
- `/pm-setup`, the in-chat integration of `.pm` into an existing project. The teaching mode is chosen at its end, in chat, not in the TUI.
- A one-line bootstrap that makes the virtual environment for the user, and a run on a clean machine.
- Renovate watching `bom.toml`.
