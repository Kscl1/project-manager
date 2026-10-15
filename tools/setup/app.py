"""Setup TUI: check what is installed against bom.toml, choose the layers, then install step by step (DESIGN.md).

The checks, the status rules and the steps live in bom.py; this file only shows them and runs a step after the
user presses y on it.

usage: python tools/setup/app.py [project folder]    (in the TUI's own virtual environment, see DESIGN.md)
"""

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import quote

import bom
from rich.text import Text
from textual import work
from textual.app import App, ComposeResult, SuspendNotSupported
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, SelectionList, Static
from textual.widgets.selection_list import Selection
from textual.worker import get_current_worker

# A symbol and a theme colour per level (bom.LEVEL), so the status reads without colour too.
SYMBOLS = {"good": "✓", "warn": "!", "bad": "✗", "skip": "·"}
COLOURS = {"good": "success", "warn": "warning", "bad": "error", "skip": None}
LEGEND = "✓ ready   ! works, worth a look   ✗ needs action   · not checked yet"
WIDE = 100  # below this many columns the Path column is left out
PATH = bom.COLUMNS.index("Path")
STUCK = "Stuck? Press a to copy a message for your coding agent; it can finish the setup without this screen."
LAYER_TEXT = {
    "core": "Core: what every project needs",
    "map": "Map: architecture diagrams of your project (optional)",
}
# Install screen: what each step state shows, and its level for the colour (bom.outcome names the states).
STATES = {
    "waiting": ("waiting", "skip"),
    "done": ("done", "good"),
    "not-found": ("not found yet", "warn"),
    "unverified": ("not verified", "warn"),
    "too-old": ("still too old", "bad"),
    "failed": ("failed", "bad"),
    "skipped": ("skipped", "skip"),
    "merge": ("done, merge the rest", "warn"),
}
QUIET_S = 0.8  # after a step returns, y is ignored this long: keys queued while it ran must not run the next
PLAN_S = 30  # the installer's read-only plan; longer than this and the step is not run from here
FINISHED = {"done", "not-found", "unverified", "skipped", "merge"}  # nothing more this screen can do for these
NO_PROJECT = (
    "Your project's files are checked when setup starts with the project folder: "
    "python tools/setup/app.py <your project folder>"
)

CSS = """
Screen { align-horizontal: center; }
#body { width: 100%; max-width: 130; height: 1fr; padding: 0 1; }  /* scrolls on a short terminal */
DataTable { height: auto; max-height: 20; overflow-x: hidden; }  /* a long path is cut at the edge, no scrollbar */
SelectionList { height: auto; border: round $primary; padding: 0 1; }
.panel { height: auto; border: round $primary; padding: 0 1; margin-top: 1; }
.hint { height: auto; padding: 1 1 0 1; color: $text-muted; }
CheckTable > .datatable--cursor { background: $primary 30%; }  /* only c reads it: keep it quiet */
"""


class CheckTable(DataTable):
    """The Check table: a click on a Path cell copies the stored full path, not the clipped cell (DESIGN.md, Copying).

    DataTable stops the click once it has moved its cursor, so the click is read here, on the table itself.
    """

    def on_click(self, event):
        meta = event.style.meta
        if meta.get("column") == PATH and not meta.get("out_of_bounds"):
            self.app.copy_row_path(meta.get("row", -1))


def copy_message(text):
    """The app cannot tell whether the terminal accepted the copy (OSC 52), so the message always shows the text."""
    return f"Sent to the clipboard:\n{text}\nIf nothing was copied, select the text here instead."


def agent_message(layers, project=None):
    """What the user pastes into their coding agent when they hand the setup over (DESIGN.md)."""
    script = Path(bom.__file__).resolve()
    where = f' --project "{project}"' if project else ""
    return (
        "Please finish the project-manager setup on this machine. "
        f'Run: python "{script}" --layers {",".join(layers)}{where} '
        "It prints what is installed and a To do list with one command per step (add --json for JSON). "
        "Show me each command and run it only after I say yes; never add sudo to npm. "
        "Then run the check again until it exits 0, and tell me what is left."
        + (" After that, run /pm-setup in the project." if project else "")
    )


def next_lines(project):
    """The commands that open the project in Claude Code and start /pm-setup, for the Done screen and its c key."""
    return [f'cd "{project}"', "claude", "/pm-setup"]


def desktop_link(project):
    """Claude Desktop's documented link that opens a new Code session in a folder."""
    return "claude://code/new?folder=" + quote(str(project), safe="")


class SetupApp(App):
    TITLE = "project-manager setup"
    SUB_TITLE = "Check"
    BINDINGS = [
        Binding("enter", "choose", "Continue", priority=True),
        ("r", "recheck", "Check again"),
        ("c", "copy_path", "Copy path"),
        ("l", "layers", "Change layers"),
        ("a", "agent", "Ask agent"),
        ("q", "quit", "Quit"),
    ]
    ENABLE_COMMAND_PALETTE = False  # a few keys per screen: nothing to search for
    CSS = CSS

    def __init__(self, items=None, probe=bom.probe, runner=None, system=None, project=None, home=None):
        super().__init__()
        self.items = bom.load() if items is None else items
        self.probe = probe  # tests pass a fake one
        self.runner = runner or self.run_in_terminal  # tests pass a fake one
        self.system = system or bom.this_os()
        self.project = Path(project).resolve() if project else None
        self.home = home  # tests pass a folder; None is the user's home
        self.record = bom.read_record(self.project) if self.project else None
        self.layers = bom.LAYERS
        if self.record and self.record.get("layers"):  # a rerun starts from what was chosen last time
            self.layers = tuple(layer for layer in bom.LAYERS if layer == "core" or layer in self.record["layers"])
        self.similar = []
        self.scanning = False
        self.rows = []
        self.shown = []  # the index in self.rows of each table line; not-checked items share one line
        # Kept here, not queried: while Choose or Install is on top, a query would find their widgets.
        self.table = CheckTable(cursor_type="row", zebra_stripes=True)
        self.summary = Static(id="summary", classes="hint")

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="body"):
            yield self.table
            yield self.summary
        yield Footer()

    def on_mount(self):
        self.action_recheck()

    def on_resize(self, event):
        self.fill(event.size.width)  # show or hide the Path column; self.size is not updated yet here

    def check_action(self, action, parameters):
        """The Check screen's own keys work only while it is on top; Continue only once a scan has ended."""
        if action in ("recheck", "choose", "copy_path", "layers") and len(self.screen_stack) > 1:
            return False
        if action == "choose" and (self.scanning or not self.rows):
            return None  # shown greyed out
        if action == "layers":  # only where Enter skips Choose: a rerun with nothing left
            return not self.scanning and bool(self.rows) and self.nothing_left()
        return True

    def action_recheck(self):
        if self.scanning:  # one scan at a time; r does nothing until it ends
            return
        self.scanning = True
        self.rows = []
        self.fill()
        self.summary.update("Checking what is installed. Nothing is installed or changed.")
        self.refresh_bindings()
        self.check()

    @work(thread=True)
    def check(self):
        """Runs the version commands off the screen's thread, so the window opens at once."""
        rows = bom.check_all(self.items, self.probe, self.project)
        similar = bom.similar(self.items, bom.user_scan(self.home), self.layers)
        if not get_current_worker().is_cancelled:  # the app may have closed meanwhile
            self.call_from_thread(self.show, rows, similar)  # Textual is not thread-safe: update on its own thread

    def show(self, rows, similar=()):
        self.rows, self.similar = rows, list(similar)
        self.fill()
        level = bom.worst(rows)  # "worth a look" is still good news: only "needs action" turns the sentence red
        text = Text()
        if self.project:
            text.append(f"Project: {self.project}\n", "bold")
        if self.record:
            text.append(f"Set up here before on {self.record.get('date')} ({', '.join(self.layers)}).\n", "dim")
        text.append(bom.summary(rows), "bold")
        text.append("\n")
        text.append(bom.next_step(rows), self.colour("good" if level == "warn" else level) or "")
        if not self.project:
            text.append(f"\n{NO_PROJECT}", "dim")
        for line in self.similar:
            text.append(f"\nAlready on this machine: {line}", "dim")
        merge = bom.merge_list(self.project) if self.project else []
        if merge:
            text.append(f"\nKept as yours, for /pm-setup to merge with you: {bom.merge_names(merge)}.", "dim")
        enter = "finish, l to change the layers" if self.nothing_left() else "choose what to set up"
        text.append(f"\n\nPress Enter to {enter}. c or a click on a path copies it.\n")
        text.append(LEGEND, "dim")
        text.append(f"\n{STUCK}", "dim")
        self.summary.update(text)
        self.scanning = False
        self.refresh_bindings()

    def nothing_left(self):
        """A rerun with nothing to do and the same bom.toml: Enter goes straight to Done (the short screen)."""
        if not self.record or self.record.get("bom") != bom.bom_hash():
            return False
        steps, notes = bom.plan(self.items, self.rows, self.layers, self.system, self.project)
        return not steps and not notes

    def action_layers(self):
        self.push_screen(ChooseScreen())

    def fill(self, width=None):
        """Redraws the table from self.rows; the Path column only on a wide terminal."""
        table = self.table
        wide = (width or self.size.width) >= WIDE
        keep = table.cursor_row
        table.clear(columns=True)
        table.add_columns(*(bom.COLUMNS if wide else bom.COLUMNS[:PATH]))
        # A beginner reads nine "not checked" or nine "not in project" lines as nine problems, while one step (or
        # none) settles them all; each group gets one line that says so plainly.
        grouped = (bom.NOT_CHECKED, bom.NOT_IN_PROJECT)
        self.shown = [i for i, row in enumerate(self.rows) if row[4] not in grouped]
        for *cells, result, path in (self.rows[i] for i in self.shown):
            level = bom.LEVEL[result]
            status = Text(f"{SYMBOLS[level]} {result}", style=self.colour(level) or "")
            table.add_row(*cells, status, *([path] if wide else []))
        empty = Text("-", style="dim")
        for result, label, style in (
            (bom.NOT_IN_PROJECT, "{n} project file{s}, one step sets them up", self.colour("bad") or ""),
            (bom.NOT_CHECKED, "{n} project item{s}, set up later", "dim"),
        ):
            n = sum(1 for row in self.rows if row[4] == result)
            if n:
                name = Text(label.format(n=n, s="s" if n != 1 else ""), style="dim")
                status = Text(f"{SYMBOLS[bom.LEVEL[result]]} {result}", style=style)
                table.add_row(name, empty, empty, empty, status, *([empty] if wide else []))
        table.move_cursor(row=keep)

    def action_copy_path(self):
        """c copies the highlighted row's path; it works when the Path column is hidden on a narrow terminal too."""
        self.copy_row_path(self.table.cursor_row)

    def copy_row_path(self, line):
        """Copies the full path of a table line; the shared not-checked line has none."""
        if 0 <= line < len(self.shown) and self.rows[self.shown[line]][PATH] != "-":
            self.copy(self.rows[self.shown[line]][PATH])

    def action_agent(self):
        self.copy(agent_message(self.layers, self.project))

    def copy(self, text):
        self.copy_to_clipboard(text)
        self.notify(copy_message(text), timeout=8)

    def colour(self, level):
        """The current theme's colour for a level, or None for not checked."""
        return COLOURS[level] and getattr(self.current_theme, COLOURS[level])

    def action_choose(self):
        self.push_screen(DoneScreen() if self.nothing_left() else ChooseScreen())

    def run_in_terminal(self, step):
        """Steps the app aside, runs one step in the real terminal, waits for Enter. None: cannot."""
        command = step["command"]
        try:
            with self.suspend():
                print(f"\nproject-manager setup runs:\n\n    {command}\n", flush=True)
                if "sudo " in command:
                    print("It asks for your password. Nothing appears while you type it; press Enter at the end.\n")
                try:
                    code = subprocess.call(step["shell"])
                except KeyboardInterrupt:  # Ctrl+C reaches us as well as the installer
                    code = 130
                except OSError as error:  # the shell itself is missing
                    print(error)
                    code = 127
                verdict = "finished" if code == 0 else f"stopped with exit code {code}"
                try:
                    input(f"\nThe command {verdict}. Read the output above, then press Enter to go back to setup. ")
                except (KeyboardInterrupt, EOFError):
                    pass
                return code
        except SuspendNotSupported:
            return None


class ChooseScreen(Screen):
    """The layers as a checklist and the steps this machine needs for them (DESIGN.md, Choose)."""

    SUB_TITLE = "Check · Choose"
    BINDINGS = [
        Binding("enter", "install", "Continue", priority=True),
        ("escape", "app.pop_screen", "Back"),
    ]

    def __init__(self):
        super().__init__()
        self.steps = []

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="body"):
            yield Static("Choose what to set up. Space or a click ticks a layer; core is always on.", classes="hint")
            yield SelectionList(
                *(
                    Selection(LAYER_TEXT[layer], layer, layer in self.app.layers, disabled=layer == "core")
                    for layer in bom.LAYERS
                )
            )
            yield Static(id="steps", classes="panel")
            yield Static(id="choose-hint", classes="hint")
        yield Footer()

    def on_mount(self):
        self.query_one("#steps").border_title = "What this machine needs"
        self.query_one(SelectionList).focus()
        self.update_steps()

    def on_screen_resume(self):
        """Back from Install: its re-checks changed the rows, so plan again."""
        self.update_steps()

    def on_selection_list_selected_changed(self):
        selected = self.query_one(SelectionList).selected
        self.app.layers = tuple(layer for layer in bom.LAYERS if layer == "core" or layer in selected)
        self.update_steps()

    def update_steps(self):
        app = self.app
        self.steps, notes = bom.plan(app.items, app.rows, app.layers, app.system, app.project)
        text = Text()
        for number, step in enumerate(self.steps, 1):
            text.append(f"{number}. {step['name']}", "bold")
            text.append(f"  {step['why']}\n", "dim")
            text.append(f"   {step['command']}\n")
        if not self.steps:
            text.append("Nothing can be installed automatically; see the notes." if notes else "Everything is ready.")
        if not app.project:
            text.append(f"\n{NO_PROJECT}", "dim")
        for note in notes:
            text.append(f"\nNote: {note}", "dim")
        self.query_one("#steps", Static).update(text)
        if self.steps:
            count = "this step" if len(self.steps) == 1 else f"these {len(self.steps)} steps one by one"
            hint = f"Press Enter to review {count}. Nothing runs yet."
        else:
            hint = "Press Enter to finish, Esc to go back."
        self.query_one("#choose-hint", Static).update(f"{hint}\n{STUCK}")
        self.refresh_bindings()

    def action_install(self):
        self.app.push_screen(InstallScreen(self.steps) if self.steps else DoneScreen())


class InstallScreen(Screen):
    """The steps one at a time: show the command, run it on y, re-check the item (DESIGN.md, Running a step)."""

    SUB_TITLE = "Check · Choose · Install"
    BINDINGS = [
        ("y", "run", "Run"),
        ("s", "skip", "Skip"),
        ("c", "copy", "Copy"),
        ("r", "recheck_step", "Recheck"),
        Binding("enter", "finish", "Finish", priority=True),
        ("escape", "app.pop_screen", "Back"),
    ]

    def __init__(self, steps):
        super().__init__()
        self.steps = steps
        self.states = ["waiting"] * len(steps)
        self.messages = [""] * len(steps)
        self.previews = {}  # step index: (usable, text) from the installer's --check; missing while it runs
        self.quiet_until = 0.0

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="body"):
            yield DataTable(cursor_type="row", zebra_stripes=True)
            yield Static(id="command", classes="panel")
            yield Static(id="install-hint", classes="hint")
        yield Footer()

    def on_mount(self):
        self.query_one(DataTable).add_columns("Step", "Program", "Why", "State")
        self.redraw()
        self.query_one(DataTable).focus()
        for index, step in enumerate(self.steps):
            if step.get("preview"):
                self.ask_plan(index, step["preview"])

    @work(thread=True)
    def ask_plan(self, index, command):
        """The installer's own plan for this project (--check, read-only), off the screen's thread."""
        try:
            done = subprocess.run(
                command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=PLAN_S
            )
            # 0: nothing in the way; 3: the project's own files, which the step keeps (--keep-existing)
            result = done.returncode in (0, 3), (done.stdout + done.stderr).strip()
        except (OSError, subprocess.SubprocessError) as error:
            result = False, f"the installer did not answer ({error})."
        if not get_current_worker().is_cancelled:
            self.app.call_from_thread(self.got_plan, index, result)

    def got_plan(self, index, result):
        self.previews[index] = result
        self.show_current()

    @property
    def current(self):
        return self.query_one(DataTable).cursor_row

    @property
    def finished(self):
        return all(state in FINISHED for state in self.states)

    def check_action(self, action, parameters):
        """Enter only finishes once every step is finished; y, s and r only while one is left (others hidden)."""
        if action == "finish":
            return self.finished
        if action in ("run", "skip", "recheck_step"):
            return not self.finished
        return True

    def redraw(self):
        table = self.query_one(DataTable)
        keep = table.cursor_row
        table.clear()
        for number, (step, state) in enumerate(zip(self.steps, self.states), 1):
            label, level = STATES[state]
            state_cell = Text(f"{SYMBOLS[level]} {label}", style=self.app.colour(level) or "dim")
            table.add_row(str(number), step["name"], step["why"], state_cell)
        table.move_cursor(row=keep)
        self.show_current()
        self.refresh_bindings()

    def on_data_table_row_highlighted(self):
        self.show_current()

    def show_current(self):
        index = self.current
        step, state, message = self.steps[index], self.states[index], self.messages[index]
        panel = self.query_one("#command", Static)
        panel.border_title = f"Step {index + 1} of {len(self.steps)}: {step['name']}"
        text = Text(step["command"], "bold")
        if step.get("preview") and state not in FINISHED:
            usable, plan = self.previews.get(index, (False, "asking the installer for its plan..."))
            text.append(f"\n\nWhat it will do (nothing is written yet):\n{plan}", "dim")
            if index in self.previews and not usable:
                text.append("\n\nWithout its plan this step does not run here; c copies the command.", "bold")
        if message:
            text.append(f"\n\n{message}", self.app.colour(STATES[state][1]) or "")
        panel.update(text)
        if self.finished:
            hint = self.final_words()
        else:
            hint = "y runs this step here, s skips it, c copies it, ↑↓ pick another step. Nothing runs without y."
        self.query_one("#install-hint", Static).update(f"{hint}\n{STUCK}")

    def final_words(self):
        """What happened, and what is still left, once every step is finished."""
        left = [
            f"{step['name']} ({STATES[state][0]})" for step, state in zip(self.steps, self.states) if state != "done"
        ]
        done = self.states.count("done")
        text = f"All steps are finished: {done} of {len(self.steps)} done."
        if left:
            text += f" Still open: {', '.join(left)}."
        return text + " Press Enter to finish."

    def action_run(self):
        index = self.current
        step = self.steps[index]
        if time.monotonic() < self.quiet_until:  # a key pressed while the last step ran
            self.app.notify(f"Read step {index + 1} first, then press y to run it.")
            return
        if self.states[index] == "done":
            self.app.notify(f"{step['name']} is already done.")
            return
        if step.get("preview") and not self.previews.get(index, (False, ""))[0]:  # the user reads the plan first
            self.app.notify("Wait for the installer's plan above; it runs only after you have seen it.")
            return
        if not shutil.which(step["needs"]):  # e.g. npm before the Node.js step has run
            self.messages[index] = (
                f"this step needs {step['needs']}, which is not found. "
                "Finish the step that installs it first, or open a new terminal and run setup again."
            )
            self.redraw()
            return
        code = self.app.runner(step)
        self.quiet_until = time.monotonic() + QUIET_S
        if code is None:  # the terminal cannot hand over: the user runs it elsewhere
            self.app.copy(step["command"])
            self.messages[index] = (
                "this terminal cannot hand over. Run the copied command in another terminal, then press r."
            )
            self.redraw()
            return
        self.settle(index, code)

    def action_recheck_step(self):
        """r: re-check the highlighted step's program, e.g. after running its command in another terminal."""
        self.settle(self.current, None)

    def settle(self, index, code):
        """Re-checks the step's program and stores the new row, so Choose and Check do not plan it again."""
        bom.refresh_path()
        app, step = self.app, self.steps[index]
        rows = []
        for at, item in enumerate(app.items):
            if item["id"] in step.get("ids", [step["id"]]):
                app.rows[at] = bom.check_one(item, app.probe, app.project)
                rows.append(app.rows[at])
        app.fill()
        if "ids" in step:  # the installer step sets up several project items
            self.states[index], self.messages[index] = bom.project_outcome(code, rows, bom.merge_list(app.project))
        else:
            self.states[index], self.messages[index] = bom.outcome(code, rows[0])
        self.advance(index)

    def action_skip(self):
        index = self.current
        if self.states[index] != "done":
            self.states[index], self.messages[index] = "skipped", "skipped; run setup again to do it later."
        self.advance(index)

    def action_copy(self):
        self.app.copy(self.steps[self.current]["command"])

    def action_finish(self):
        self.app.switch_screen(DoneScreen())

    def advance(self, index):
        """After a finished step, move to the next one not finished; after a failure, stay on it."""
        if self.states[index] in FINISHED:
            open_steps = [i for i, state in enumerate(self.states) if state not in FINISHED]
            if open_steps:
                self.query_one(DataTable).move_cursor(row=next((i for i in open_steps if i > index), open_steps[0]))
        self.redraw()


class DoneScreen(Screen):
    """What is ready, what is left, and how to go on in the project with /pm-setup (DESIGN.md, Done)."""

    SUB_TITLE = "Check · Choose · Install · Done"
    BINDINGS = [
        ("o", "open_desktop", "Open in Claude Desktop"),
        ("c", "copy_next", "Copy commands"),
        ("escape", "back", "Check again"),
        ("q", "app.quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="body"):
            yield Static(id="done", classes="panel")
            yield Static(id="next", classes="panel")
            yield Static(id="done-hint", classes="hint")
        yield Footer()

    def on_mount(self):
        app = self.app
        steps, notes = bom.plan(app.items, app.rows, app.layers, app.system, app.project)
        saved = app.project and bom.write_record(app.project, app.layers, app.similar, time.strftime("%Y-%m-%d"))
        done = self.query_one("#done", Static)
        done.border_title = "Setup"
        text = Text()
        if steps:
            text.append(f"Still open ({', '.join(app.layers)}): ", app.colour("bad") or "")
            text.append(", ".join(step["name"] for step in steps))
            text.append("\nRun setup again to do them, or press a for your coding agent.", "dim")
        elif notes:
            text.append("Installed, but worth a look first:", app.colour("warn") or "")
        else:
            text.append(f"✓ Everything for {', '.join(app.layers)} is ready.", app.colour("good") or "")
        for note in notes:
            text.append(f"\nNote: {note}", "dim")
        merge = bom.merge_list(app.project) if app.project else []
        if merge:
            text.append(f"\nKept as yours, for /pm-setup to merge with you: {bom.merge_names(merge)}.")
        for line in app.similar:
            text.append(f"\nAlready on this machine: {line}", "dim")
        if saved:
            text.append(f"\nSaved what was chosen in {app.project / bom.RECORD}; a rerun starts from it.", "dim")
        done.update(text)

        nxt = self.query_one("#next", Static)
        nxt.border_title = "Next: fit .pm to your project"
        if not app.project:
            nxt.update(f"{NO_PROJECT}\nThen run /pm-setup in your coding agent, inside the project.")
        else:
            lines = next_lines(app.project)
            text = Text("In a terminal:\n")
            for line in lines[:2]:
                text.append(f"    {line}\n", "bold")
            text.append("then type ")
            text.append(lines[2], "bold")
            text.append(
                " and press Enter. It asks about your project one question at a time; nothing changes without your yes."
            )
            if app.system == "windows":
                text.append(
                    "\n\nOr press o: Claude Desktop opens a new Code session in the project; type /pm-setup there.", ""
                )
            nxt.update(text)
        keys = "o opens Claude Desktop, " if self.can_open() else ""
        self.query_one("#done-hint", Static).update(f"{keys}c copies the commands, Esc checks again, q quits.\n{STUCK}")

    def can_open(self):
        return self.app.project is not None and self.app.system == "windows"

    def check_action(self, action, parameters):
        if action == "open_desktop":
            return self.can_open()
        if action == "copy_next":
            return self.app.project is not None
        return True

    def action_open_desktop(self):
        try:
            os.startfile(desktop_link(self.app.project))  # Windows only: the link opens Claude Desktop
            self.app.notify("Opening Claude Desktop. If nothing opens, use the terminal commands instead.")
        except OSError as error:
            self.app.notify(f"Claude Desktop did not open ({error}); use the terminal commands.", severity="warning")

    def action_copy_next(self):
        self.app.copy("\n".join(next_lines(self.app.project)))

    def action_back(self):
        while len(self.app.screen_stack) > 1:
            self.app.pop_screen()
        self.app.action_recheck()


if __name__ == "__main__":
    folder = sys.argv[1] if len(sys.argv) > 1 else None
    if folder and not Path(folder).is_dir():
        sys.exit(f"{folder} is not a folder. Start setup with your project folder, or with none.")
    try:
        SetupApp(project=folder).run()
    except ValueError as error:  # a bad bom.toml entry
        sys.exit(str(error))
