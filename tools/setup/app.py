"""Setup TUI, first slice: one read-only table of what is installed against bom.toml (DESIGN.md). Installs come later.

The checks and the status rules live in bom.py; this file only shows them.

usage: python tools/setup/app.py    (in the TUI's own virtual environment, see DESIGN.md)
"""

import sys

import bom
from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.widgets import DataTable, Footer, Header
from textual.worker import get_current_worker

COLOURS = {
    bom.OK: "green",
    bom.UNTESTED: "yellow",
    bom.CANNOT_COMPARE: "yellow",
    bom.UNREADABLE: "yellow",
    bom.NOT_CHECKED: "dim",
    bom.BELOW: "red",
    bom.FAILED: "red",
    bom.MISSING: "red",
}


class SetupApp(App):
    TITLE = "project-manager setup"
    BINDINGS = [("r", "recheck", "Check again"), ("q", "quit", "Quit")]

    def __init__(self, items=None, probe=bom.probe):
        super().__init__()
        self.items = bom.load() if items is None else items
        self.probe = probe  # tests pass a fake one
        self.scanning = False

    def compose(self) -> ComposeResult:
        yield Header()
        yield DataTable(cursor_type="row")
        yield Footer()

    def on_mount(self):
        self.query_one(DataTable).add_columns(*bom.COLUMNS)
        self.action_recheck()

    def action_recheck(self):
        if self.scanning:  # one scan at a time; r does nothing until it ends
            return
        self.scanning = True
        self.query_one(DataTable).clear()
        self.sub_title = "checking..."
        self.check()

    @work(thread=True)
    def check(self):
        """Runs the version commands off the screen's thread, so the window opens at once."""
        rows = bom.check_all(self.items, self.probe)
        if not get_current_worker().is_cancelled:  # the app may have closed meanwhile
            self.call_from_thread(self.show, rows)  # Textual is not thread-safe: update the table on its own thread

    def show(self, rows):
        table = self.query_one(DataTable)
        table.clear()
        for *cells, result, path in rows:
            table.add_row(*cells, Text(result, style=COLOURS[result]), path)
        self.sub_title = bom.summary(rows)
        self.scanning = False


if __name__ == "__main__":
    try:
        SetupApp().run()
    except ValueError as error:  # a bad bom.toml entry
        sys.exit(str(error))
