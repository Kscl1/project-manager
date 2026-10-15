"""Setup TUI, first slice: one read-only table of what is installed against bom.toml (DESIGN.md). Installs come later.

The checks and the status rules live in bom.py; this file only shows them.

usage: python tools/setup/app.py    (in the TUI's own virtual environment, see DESIGN.md)
"""

import sys

import bom
from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.widgets import DataTable, Footer, Header, Static
from textual.worker import get_current_worker

# A symbol and a theme colour per level (bom.LEVEL), so the status reads without colour too.
SYMBOLS = {"good": "✓", "warn": "!", "bad": "✗", "skip": "·"}
COLOURS = {"good": "success", "warn": "warning", "bad": "error", "skip": None}
LEGEND = "✓ ready   ! works, worth a look   ✗ needs action   · not checked yet"
WIDE = 100  # below this many columns the Path column is left out


class SetupApp(App):
    TITLE = "project-manager setup"
    BINDINGS = [("r", "recheck", "Check again"), ("q", "quit", "Quit")]
    ENABLE_COMMAND_PALETTE = False  # one screen, two keys: nothing to search for
    CSS = """
    DataTable { height: auto; overflow-x: hidden; }  /* a long path is cut at the edge, no scrollbar */
    #summary { height: auto; padding: 1 2 0 2; }
    """

    def __init__(self, items=None, probe=bom.probe):
        super().__init__()
        self.items = bom.load() if items is None else items
        self.probe = probe  # tests pass a fake one
        self.scanning = False
        self.rows = []

    def compose(self) -> ComposeResult:
        yield Header()
        yield DataTable(cursor_type="none", zebra_stripes=True)
        yield Static(id="summary")
        yield Footer()

    def on_mount(self):
        self.action_recheck()

    def on_resize(self, event):
        self.fill(event.size.width)  # show or hide the Path column; self.size is not updated yet here

    def action_recheck(self):
        if self.scanning:  # one scan at a time; r does nothing until it ends
            return
        self.scanning = True
        self.rows = []
        self.fill()
        self.sub_title = "checking..."
        self.query_one("#summary", Static).update("Checking what is installed. Nothing is installed or changed.")
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
                (LEGEND, "dim"),
            )
        )
        self.sub_title = "read-only check, nothing was installed"
        self.scanning = False

    def fill(self, width=None):
        """Redraws the table from self.rows; the Path column only on a wide terminal."""
        table = self.query_one(DataTable)
        wide = (width or self.size.width) >= WIDE
        table.clear(columns=True)
        table.add_columns(*(bom.COLUMNS if wide else bom.COLUMNS[:-1]))
        for *cells, result, path in self.rows:
            level = bom.LEVEL[result]
            dim = "dim" if level == "skip" else ""
            status = Text(f"{SYMBOLS[level]} {result}", style=self.colour(level) or dim)
            row = [Text(cell, style=dim) for cell in cells] + [status]
            table.add_row(*row, *([Text(path, style=dim)] if wide else []))

    def colour(self, level):
        """The current theme's colour for a level, or None for not checked."""
        return COLOURS[level] and getattr(self.current_theme, COLOURS[level])


if __name__ == "__main__":
    try:
        SetupApp().run()
    except ValueError as error:  # a bad bom.toml entry
        sys.exit(str(error))
