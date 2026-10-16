# Setup TUI: design

A small terminal app a new user runs once before using `.pm`. It checks what is installed against what the product needs, shows the result in one table, offers the official install or upgrade for anything missing or too old, and installs `.pm` into the project with `pm_init`. Python + Textual; runs on Windows 11 and Linux (Arch-based Omarchy first).

The Check screen is read-only: it never installs, upgrades or downloads anything, and it never shows "ok" for something it did not check. Only the Install screen runs commands, each one after the user presses `y` on it.

## The bill of materials becomes `bom.toml`

`tools/setup/bom.toml` is the one machine-readable list of what the product needs. One `[[item]]` per tool:

```toml
[[item]]
id = "git"                          # stable key
name = "Git"
kind = "command"                    # command | project-file | manual
layer = "core"                      # core | map | swarm
check = ["git", "--version"]        # a command and its arguments, never a shell line
min = "2.54.0"                      # below this the TUI warns
tested = "2.54.0"                   # above this the TUI says "not tested yet"
install.windows = "winget install --id Git.Git --exact --source winget"
install.linux = "sudo pacman -S --needed git"
note = "Preinstalled on Omarchy."
```

- **command**: the TUI runs `check` and reads the version. `min` and `tested` are required. `npx` is refused, because it may download. For a check that lists packages (`pi list --no-approve` for the Pi extensions), `package` names the one to find (`npm:pi-web-access`). The listed name is only what Pi's settings ask for, so the version is read from the `package.json` in the folder printed under it: not listed is missing, listed without a readable `package.json` is "version unreadable", never ready. A package Pi marks `(filtered)` (its settings pick only some of its resources) is "version unreadable" too, because what it loads is unknown. `--no-approve` makes Pi list only the user's own packages, without a project's trust question: the check covers the user-level install the workers share, not a project's own `.pi/settings.json`.
- **project-file**: lives in the user's project at `path` (the `.pm` package, the hooks, `.mcp.json`, the `pm-` skills, with the upstream `ref` for copied skills). Checked only when setup is started with the project folder (`app.py <folder>`, `bom.py --project <folder>`); without one it is "not checked". `has` is text the file must hold: the hooks file must run `pm_board.py --resume`, `.mcp.json` must name the server.
- **manual**: nothing on the machine to check (LikeC4 runs through `npx` with a pinned version).

Unknown versions are left out, never written as "not set". Until an older version has been tried, `min` equals `tested`. `note` is text shown to the user: under its step on Install and in the plain To do list, or as the note when there is no command for this OS. `install.*` and `upgrade.*` are shown too, and run through the platform shell only after the user presses Enter on that step (see Running a step). `load()` stops with a plain message on a duplicate id, an unknown kind, a malformed version or `min` above `tested`.

`similar` lists names of skills, MCP servers or plugins that do the same job as the item (see Similar items).

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
| manual item, or project-file item without a project folder | not checked |
| project-file: the path is there (and holds `has`) | in project |
| project-file: the path is missing | not in project |
| project-file: the user's own file, without `has` | merge by hand |
| command not found | missing |
| non-zero exit, timeout or start error (no version is taken from its output) | check failed |
| exit 0, no version in the output | version unreadable |
| a version with a suffix, such as `3.15.0rc1` | cannot compare |
| below `min` | below minimum |
| from `min` up to `tested` | ok |
| above `tested` | not tested yet |

The version is the first word that starts like `3.11` or `3.11.9`. Git's `.windows.1` suffix is dropped; any other suffix makes the version uncomparable rather than guessing. Versions are compared number by number; `3.11` equals `3.11.0`. At or above the minimum the TUI never touches the user's install. One failing check gives one red row; the rest of the table still fills.

## Screens

1. **Check**: the project folder, then the table, columns item, installed, minimum, tested, status, path; the next step under it. The items this screen does not check (LikeC4, and the project files when no folder was given) share one dim line at the end, because a beginner reads nine "not checked" lines as nine problems; `python tools/setup/bom.py` still lists them one by one. `c` copies the highlighted line's path, and so does a click on a Path cell (see Copying). Under the table: what the user already has that is similar (see Similar items), and on a rerun when it was set up before. `Enter` goes on to Choose once the scan has ended, or straight to Done on a rerun with nothing left (see The record).
2. **Choose**: the layers as a checklist (core ticked and locked; map ticked and swarm unticked on a first run, as last chosen on a rerun; space or a click ticks) and, under it, what this machine needs for the ticked layers: each step with its official command, then the notes. `Enter` goes on to Install; nothing runs yet. `Esc` goes back. When there is nothing to run it says so and `Enter` goes to Done.
3. **Install**: the steps in a list, the highlighted one's full command in a panel titled "Step 2 of 3: Node.js". `y` runs it, `s` skips it, `c` copies it, `r` checks its program again; arrows pick another step. `Enter` never runs a step: pressed twice on Choose, it must not start an installer. For 0.8 seconds after a step returns, `y` is ignored with a hint: a key pressed while the installer ran must not start the next step before the user has read it. `Esc` goes back to Choose, which plans again from the re-checked rows, so a step already done is not offered twice. Once every step is finished, the screen says what is still open and `Enter` goes to Done.
4. **Done**: what is ready for the chosen layers, what is still open, the notes (a note means "worth a look", never "ready") and what is left for `/pm-setup` to merge; then how to go on in the project: the terminal commands (`cd <project>`, `claude`, then `/pm-setup`; `c` copies them) and, on Windows, `o`, which opens Claude Desktop's documented link `claude://code/new?folder=<the project, URL-encoded>` (a new Code session in that folder). `Esc` goes back to Check and checks everything again. Done writes the record.

The subtitle names where the user is (`Check · Choose · Install · Done`), the footer shows only the keys that work at that moment (short labels, so they fit in 80 columns), and the body scrolls on a short terminal. Every screen ends with "Stuck? Press a to copy a message for your coding agent" (see the last section).

## Steps: what Choose and Install run

`bom.plan(items, rows, layers, os)` is a pure function in `bom.py`: from the check rows it returns one step per command item in a ticked layer whose status is **missing** or **below minimum**. A step holds the item, why it is needed, the command text for this OS, the program that runs it (`needs`: `winget`, `npm`, `pacman` after `sudo`, or the shell for a PowerShell line) and the argument list that runs it. The command is `upgrade.<os>` for an item below its minimum when the entry has one, else `install.<os>`, else `install.all`. Current winget may upgrade on `install` too, but an explicit `upgrade` line says what happens. An item without a command for this OS becomes a note ("no install command for windows" plus its `note`). An item that is installed but could not be verified (**check failed**, **version unreadable**, **cannot compare**) is a note too: reinstalling over it could hide the cause, and it is never counted as ready. Project files that are **not in project** become one last step, `pm_init` into the project (`init_step`), with `--keep-existing` and, when Map is ticked, `--map`. Before `y` the Install panel shows the installer's own plan (`pm_init --check`, read-only, in a worker with a 30-second limit), in a few lines: its changes counted ("copy 10 package folders, write 16 files, ...",
all inside the project folder) and, by name, every file of the user's that it keeps; `--check` on the copied command
lists every file. `y` runs the step only once that plan has arrived; without one it says so and `c` copies the command. `--keep-existing` is safe here because the user has read that plan; run by hand, `pm_init` stops on such files instead. A file of the user's that lacks our part (**merge by hand**) goes to the same step until the installer has listed it in `.pm/local/merge-by-hand.md`; from then on it is `/pm-setup`'s work, neither a step nor a note, and Check and Done name it on one line. The installer never rewrites such a file. After the step the project items are checked again: all there and nothing listed is done; anything listed is "done, merge the rest".

### Running a step

The command text is shown exactly as it will run, and runs only after the user presses `y` on it. Before that the app checks that the step's program is there (`npm` is missing until the Node.js step has run); if not, it says which step to finish first and runs nothing. The command runs through the platform shell, because the official installers are shell lines (`irm … | iex`, `curl … | bash`): `powershell -NoProfile -Command <text>` on Windows, `bash -c <text>` on Linux, as one argument list with no second shell around it. This replaces the first slice's rule "never handed to a shell": the text is still never built from user input or tool output; it comes only from `bom.toml`, which is reviewed like code.

While the step runs the app steps aside (Textual's `App.suspend`, supported on Windows and Unix), so the real terminal shows the installer's output and takes a `sudo` password; for a `sudo` line it first says that nothing appears while the password is typed. `Ctrl+C` stops the installer and comes back to the app as a failure (exit code 130). After the command ends the terminal says whether it finished and waits for `Enter`, so the user can read the output before the app comes back. Then the app re-checks that one item and stores the new row for Choose and Check. An exit code of 0 alone proves nothing; only the re-check does:

| Exit code | Re-check | Step shows |
|---|---|---|
| 0 | ok or not tested yet | ✓ done |
| 0 | still missing | ! not found yet: open a new terminal and run setup again; if it is still missing there, the command did not install it (the item's note says where an installer puts it, e.g. `~/.local/bin`) |
| 0 | still below minimum | ✗ still too old |
| 0 | check failed, unreadable or cannot compare | ! not verified |
| not 0 | any | ✗ failed, with the exit code; `y` tries again, `c` copies, `s` skips |

Done, not found yet, not verified and skipped count as finished: nothing more this screen can do for them. On Windows the app adds the registry's `Path` entries (machine and user, standard library `winreg`) after the current ones before the re-check, so a winget install is usually found at once while the virtual environment stays first. Where the app cannot step aside (`SuspendNotSupported`), it runs nothing: it copies the command, asks the user to run it in another terminal, then press `r`.

## Similar items

The user may already have a skill, MCP server or plugin that does the job of one of ours (Context7 as a plugin, a `grill-me` skill). The scan reads only names: skill folders in `~/.claude/skills` and `~/.agents/skills`, the keys of `mcpServers` in `~/.claude.json` and of `plugins` in `~/.claude/plugins/installed_plugins.json`; never a server's command, headers or keys. A name matches an item's `similar` name exactly or as its prefix (`context7-mcp`), with no fuzzy matching. Each match is one information line ("Both stay; /pm-setup asks which to use."); it never blocks and never removes anything.

## The record

Done writes `<project>/.pm/local/setup.json` (git-ignored, only once `.pm/` exists): the project-manager folder, the chosen layers, a hash of `bom.toml`, the date and the similar items. A rerun starts from those layers; when nothing is left to do (no step, no note) and `bom.toml` is unchanged, `Enter` on Check goes straight to Done, and `l` opens Choose to change the layers. `/pm-setup` reads it for the source folder and the layers, and `.pm/local/merge-by-hand.md`, which `pm_init` keeps, for what is left to merge.

## Copying

`App.copy_to_clipboard` sends the text through the terminal (OSC 52; Windows Terminal and most Linux terminals accept it, some older consoles ignore it silently). The app cannot tell whether it worked, so the message always shows the full text: "Sent to the clipboard: <text>. If nothing was copied, select the text here instead." It copies the stored full path, never the clipped cell.

## When the user hands it to an agent

The user may give up and ask their coding agent instead; the agent should not have to drive a TUI. `a` on any screen copies a short message for the agent: run `python <full path>/tools/setup/bom.py --layers <the ticked layers> --project <the folder>`, show the user each command and run it only after they say yes, never add `sudo` to npm, run the check again until it exits 0.

`python tools/setup/bom.py` (no Textual) prints the full table (every item on its own line), then a `To do` list with each step's command for this OS, then the notes. `--layers core` limits it to core (default: core and map, as the TUI starts). `--json` prints one JSON object: `os`, `layers`, `items` (id, layer, name, installed, minimum, tested, status, path), `steps` (id, name, why, command, needs, shell, check; the installer step also `ids` and `preview`), `notes` and `similar`; stdout holds only that object. Exit code 0 when every program the layers need is ready, 1 when steps or notes are left, 2 on a bad `bom.toml` or argument. A failed check's error output is not in the JSON: the note names the check command, and the agent can run it.

## Running it

A supported Python (3.11 or newer, for `tomllib`) must already exist; the TUI cannot install the Python it runs on. Without one, install it by hand first: Windows `winget install --id Python.Python.3.11 --exact --source winget`, Arch `sudo pacman -S --needed python`.

```
python -m venv tools/setup/.venv
tools/setup/.venv/Scripts/python -m pip install -r tools/setup/requirements.txt    # Linux: tools/setup/.venv/bin/python
tools/setup/.venv/Scripts/python tools/setup/app.py <your project folder>
```

The TUI has its own virtual environment (ignored by git), so the user's Python stays untouched. This also avoids PEP 668: a distribution that marks its Python as externally managed (Arch does) refuses system-wide `pip install`; whether it does depends on that marker file, not on Linux as such. Tests: `python -m unittest discover -s tests`; the app tests skip where Textual is missing.

## Layers that are not chosen

Every item is checked, but Check counts and shows only the ticked layers: an optional layer nobody chose must not
make the table look broken (`bom.chosen`). One dim line says which layers are not chosen; ticking one on Choose
redraws Check under it. The swarm starts unticked (`DEFAULT_LAYERS`), because it needs Pi, Herdr and a model login.
`bom.AFTER` holds what a layer still needs once every step is done and no check can see (swarm: start `herdr` once,
sign in to a model in Pi); Done and the plain output say it on a "Then:" line. Herdr comes from its own installer,
which installs the newest release and checks its SHA-256, so it often shows as not tested yet, like Claude Code.

## Left for later, on purpose

- A one-line bootstrap that makes the virtual environment for the user, and a run on a clean machine.
- Renovate watching `bom.toml`.
