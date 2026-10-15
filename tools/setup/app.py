"""Setup TUI: check what is installed against bom.toml, choose the layers, then install step by step (DESIGN.md).

The checks, the status rules and the steps live in bom.py; this file only shows them and runs a step after the
user presses y on it.

usage: python tools/setup/app.py    (in the TUI's own virtual environment, see DESIGN.md)
"""

import shutil
import subprocess
import sys
from pathlib import Path

import bom
from rich.text import Text
from textual import work
from textual.app import App, ComposeResult, SuspendNotSupported
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
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
    "map": "Map: architecture diagrams of your project (optional; set up inside the project later)",
}
# Install screen: what each step state shows, and its level for the colour (bom.outcome names the states).
STATES = {
    "waiting": ("· waiting", "skip"),
    "done": ("✓ done", "good"),
    "not-found": ("! not found yet", "warn"),
    "unverified": ("! not verified", "warn"),
    "too-old": ("✗ still too old", "bad"),
    "failed": ("✗ failed", "bad"),
    "skipped": ("· skipped", "skip"),
}
FINISHED = {"done", "not-found", "unverified", "skipped"}  # nothing more this screen can do for these

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


def agent_message(layers):
    """What the user pastes into their coding agent when they hand the setup over (DESIGN.md)."""
    script = Path(bom.__file__).resolve()
    return (
        "Please finish the project-manager setup on this machine. "
        f'Run: python "{script}" --layers {",".join(layers)} '
        "It prints what is installed and a To do list with one command per step (add --json for JSON). "
        "Show me each command and run it only after I say yes; never add sudo to npm. "
        "Then run the check again until it exits 0, and tell me what is left."
    )


class SetupApp(App):
    TITLE = "project-manager setup"
    SUB_TITLE = "Check"
    BINDINGS = [
        Binding("enter", "choose", "Continue", priority=True),
        ("r", "recheck", "Check again"),
        ("c", "copy_path", "Copy path"),
        ("a", "agent", "Ask agent"),
        ("q", "quit", "Quit"),
    ]
    ENABLE_COMMAND_PALETTE = False  # a few keys per screen: nothing to search for
    CSS = CSS

    def __init__(self, items=None, probe=bom.probe, runner=None, system=None):
        super().__init__()
        self.items = bom.load() if items is None else items
        self.probe = probe  # tests pass a fake one
        self.runner = runner or self.run_in_terminal  # tests pass a fake one
        self.system = system or bom.this_os()
        self.layers = bom.LAYERS
        self.scanning = False
        self.rows = []
        self.shown = []  # the index in self.rows of each table line; not-checked items share one line

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="body"):
            yield CheckTable(cursor_type="row", zebra_stripes=True)
            yield Static(id="summary", classes="hint")
        yield Footer()

    def on_mount(self):
        self.action_recheck()

    def on_resize(self, event):
        self.fill(event.size.width)  # show or hide the Path column; self.size is not updated yet here

    def check_action(self, action, parameters):
        """The Check screen's own keys work only while it is on top; Continue only once a scan has ended."""
        if action in ("recheck", "choose", "copy_path") and len(self.screen_stack) > 1:
            return False
        if action == "choose" and (self.scanning or not self.rows):
            return None  # shown greyed out
        return True

    def action_recheck(self):
        if self.scanning:  # one scan at a time; r does nothing until it ends
            return
        self.scanning = True
        self.rows = []
        self.fill()
        self.query_one("#summary", Static).update("Checking what is installed. Nothing is installed or changed.")
        self.refresh_bindings()
        self.check()

    @work(thread=True)
    def check(self):
        """Runs the version commands off the screen's thread, so the window opens at once."""
        rows = bom.check_all(self.items, self.probe)
        if not get_current_worker().is_cancelled:  # the app may have closed meanwhile
            self.call_from_thread(self.show, rows)  # Textual is not thread-safe: update the table on its own thread

    def show(self, rows):
        self.rows = rows
        self.fill()
        level = bom.worst(rows)  # "worth a look" is still good news: only "needs action" turns the sentence red
        self.query_one("#summary", Static).update(
            Text.assemble(
                (bom.summary(rows), "bold"),
                "\n",
                (bom.next_step(rows), self.colour("good" if level == "warn" else level) or ""),
                "\n\n",
                "Press Enter to choose what to set up. c or a click on a path copies it.\n",
                (LEGEND, "dim"),
                "\n",
                (STUCK, "dim"),
            )
        )
        self.scanning = False
        self.refresh_bindings()

    def fill(self, width=None):
        """Redraws the table from self.rows; the Path column only on a wide terminal."""
        table = self.query_one(DataTable)
        wide = (width or self.size.width) >= WIDE
        keep = table.cursor_row
        table.clear(columns=True)
        table.add_columns(*(bom.COLUMNS if wide else bom.COLUMNS[:PATH]))
        self.shown = [i for i, row in enumerate(self.rows) if row[4] != bom.NOT_CHECKED]
        for *cells, result, path in (self.rows[i] for i in self.shown):
            level = bom.LEVEL[result]
            status = Text(f"{SYMBOLS[level]} {result}", style=self.colour(level) or "")
            table.add_row(*cells, status, *([path] if wide else []))
        later = len(self.rows) - len(self.shown)
        if later:  # a beginner reads nine "not checked" lines as nine problems; one dim line says it plainly
            name = Text(f"{later} project item{'s' if later != 1 else ''}, set up later", style="dim")
            empty = Text("-", style="dim")
            status = Text(f"· {bom.NOT_CHECKED}", style="dim")
            table.add_row(name, empty, empty, empty, status, *([empty] if wide else []))
        table.move_cursor(row=keep)

    def action_copy_path(self):
        """c copies the highlighted row's path; it works when the Path column is hidden on a narrow terminal too."""
        self.copy_row_path(self.query_one(DataTable).cursor_row)

    def copy_row_path(self, line):
        """Copies the full path of a table line; the shared not-checked line has none."""
        if 0 <= line < len(self.shown) and self.rows[self.shown[line]][PATH] != "-":
            self.copy(self.rows[self.shown[line]][PATH])

    def action_agent(self):
        self.copy(agent_message(self.layers))

    def copy(self, text):
        self.copy_to_clipboard(text)
        self.notify(copy_message(text), timeout=8)

    def colour(self, level):
        """The current theme's colour for a level, or None for not checked."""
        return COLOURS[level] and getattr(self.current_theme, COLOURS[level])

    def action_choose(self):
        self.push_screen(ChooseScreen())

    def run_in_terminal(self, command):
        """Steps the app aside, runs one bom.toml command in the real terminal, waits for Enter. None: cannot."""
        try:
            with self.suspend():
                print(f"\nproject-manager setup runs:\n\n    {command}\n", flush=True)
                if "sudo " in command:
                    print("It asks for your password. Nothing appears while you type it; press Enter at the end.\n")
                try:
                    code = subprocess.call(bom.shell_args(command, self.system))
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
        Binding("enter", "install", "Review the steps", priority=True),
        ("escape", "app.pop_screen", "Back"),
    ]

    def __init__(self):
        super().__init__()
        self.steps = []

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="body"):
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

    def on_selection_list_selected_changed(self):
        selected = self.query_one(SelectionList).selected
        self.app.layers = tuple(layer for layer in bom.LAYERS if layer == "core" or layer in selected)
        self.update_steps()

    def update_steps(self):
        self.steps, notes = bom.plan(self.app.items, self.app.rows, self.app.layers, self.app.system)
        text = Text()
        for number, step in enumerate(self.steps, 1):
            text.append(f"{number}. {step['name']}", "bold")
            text.append(f"  {step['why']}\n", "dim")
            text.append(f"   {step['command']}\n")
        if not self.steps:
            text.append(
                "Nothing can be installed automatically; see the notes." if notes else "Every program is ready."
            )
            text.append(
                "\nThe project files (.pm, hooks, skills) are set up inside your project in the next step.", "dim"
            )
        for note in notes:
            text.append(f"\nNote: {note}", "dim")
        self.query_one("#steps", Static).update(text)
        if self.steps:
            hint = f"Press Enter to review these {len(self.steps)} steps. Nothing runs yet."
        else:
            hint = "Press Esc to go back or q to quit."
        self.query_one("#choose-hint", Static).update(f"{hint}\n{STUCK}")
        self.refresh_bindings()

    def check_action(self, action, parameters):
        return None if action == "install" and not self.steps else True

    def action_install(self):
        self.app.push_screen(InstallScreen(self.steps))


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

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="body"):
            yield DataTable(cursor_type="row", zebra_stripes=True)
            yield Static(id="command", classes="panel")
            yield Static(id="install-hint", classes="hint")
        yield Footer()

    def on_mount(self):
        self.query_one(DataTable).add_columns("Step", "Program", "Why", "State")
        self.redraw()
        self.query_one(DataTable).focus()

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
            table.add_row(str(number), step["name"], step["why"], Text(label, style=self.app.colour(level) or "dim"))
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
            f"{step['name']} ({STATES[state][0][2:]})"
            for step, state in zip(self.steps, self.states)
            if state != "done"
        ]
        done = self.states.count("done")
        text = f"All steps are finished: {done} of {len(self.steps)} done."
        if left:
            text += f" Still open: {', '.join(left)}."
        return text + " Press Enter to check everything again."

    def action_run(self):
        index = self.current
        step = self.steps[index]
        if self.states[index] == "done":
            self.app.notify(f"{step['name']} is already done.")
            return
        if not shutil.which(step["needs"]):  # e.g. npm before the Node.js step has run
            self.messages[index] = (
                f"this step needs {step['needs']}, which is not found. "
                "Finish the step that installs it first, or open a new terminal and run setup again."
            )
            self.redraw()
            return
        code = self.app.runner(step["command"])
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
        bom.refresh_path()
        item = next(item for item in self.app.items if item["id"] == self.steps[index]["id"])
        self.states[index], self.messages[index] = bom.outcome(code, bom.check_one(item, self.app.probe))
        self.advance(index)

    def action_skip(self):
        index = self.current
        if self.states[index] != "done":
            self.states[index], self.messages[index] = "skipped", "skipped; run setup again to do it later."
        self.advance(index)

    def action_copy(self):
        self.app.copy(self.steps[self.current]["command"])

    def action_finish(self):
        self.app.pop_screen()
        self.app.pop_screen()
        self.app.action_recheck()

    def advance(self, index):
        """After a finished step, move to the next one not finished; after a failure, stay on it."""
        if self.states[index] in FINISHED:
            open_steps = [i for i, state in enumerate(self.states) if state not in FINISHED]
            if open_steps:
                self.query_one(DataTable).move_cursor(row=next((i for i in open_steps if i > index), open_steps[0]))
        self.redraw()


if __name__ == "__main__":
    try:
        SetupApp().run()
    except ValueError as error:  # a bad bom.toml entry
        sys.exit(str(error))
