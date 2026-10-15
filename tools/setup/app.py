"""Setup TUI, first slice: one table of what is installed against bom.toml (DESIGN.md). Installs come later.

The checks and the status rules live in bom.py; this file only shows them.

usage: python tools/setup/app.py    (in the TUI's own virtual environment, see DESIGN.md)
"""

import bom
from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.widgets import DataTable, Footer, Header

COLOURS = {bom.OK: "green", bom.UNTESTED: "yellow", bom.UNREADABLE: "yellow", bom.BELOW: "red", bom.MISSING: "red"}


class SetupApp(App):
    TITLE = "project-manager setup"
    BINDINGS = [("r", "recheck", "Check again"), ("q", "quit", "Quit")]

    def __init__(self, items=None, probe=bom.installed_version):
        super().__init__()
        self.items = bom.load() if items is None else items
        self.probe = probe  # tests pass a fake one

    def compose(self) -> ComposeResult:
        yield Header()
        yield DataTable(cursor_type="row")
        yield Footer()

    def on_mount(self):
        self.query_one(DataTable).add_columns(*bom.COLUMNS)
        self.action_recheck()

    def action_recheck(self):
        self.query_one(DataTable).clear()
        self.sub_title = "checking..."
        self.check()

    @work(thread=True, exclusive=True)
    def check(self):
        """Runs the version commands off the screen's thread, so the window opens at once."""
        rows = bom.check_all(self.items, self.probe)
        self.call_from_thread(self.show, rows)

    def show(self, rows):
        table = self.query_one(DataTable)
        table.clear()
        for *cells, result in rows:
            table.add_row(*cells, Text(result, style=COLOURS[result]))
        self.sub_title = bom.summary(rows)


if __name__ == "__main__":
    SetupApp().run()
