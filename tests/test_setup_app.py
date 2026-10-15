"""Tests for tools/setup/app.py, headless with a fake probe. Skipped where Textual is not installed (CI today)."""

import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools" / "setup"))

try:
    import app
except ImportError:
    app = None

ITEMS = [
    {"name": "A", "kind": "command", "check": ["a"], "min": "1.0", "tested": "1.2"},
    {"name": "B", "kind": "command", "check": ["b"], "min": "1.0", "tested": "1.2"},
    {"name": "C", "kind": "project-file", "path": ".pm"},
]


@unittest.skipIf(app is None, "Textual is not installed; see tools/setup/DESIGN.md")
class SetupAppTest(unittest.IsolatedAsyncioTestCase):
    async def test_table_shows_each_item(self):
        found = {"a": ("/bin/a", True, "1.3"), "b": (None, False, None)}
        setup = app.SetupApp(ITEMS, lambda check: found[check[0]])
        async with setup.run_test() as pilot:
            await setup.workers.wait_for_complete()
            await pilot.pause()
            table = setup.query_one(app.DataTable)
            self.assertEqual(table.row_count, 3)
            self.assertEqual(
                [str(cell) for cell in table.get_row_at(0)], ["A", "1.3", "1.0", "1.2", "not tested yet", "/bin/a"]
            )
            self.assertEqual(str(table.get_row_at(1)[4]), "missing")
            self.assertEqual(str(table.get_row_at(2)[4]), "not checked")
            self.assertEqual(setup.sub_title, "3 items: 1 not tested yet, 1 missing, 1 not checked")

    async def test_check_again_reads_new_versions(self):
        found = {"a": (None, False, None), "b": (None, False, None)}
        setup = app.SetupApp(ITEMS, lambda check: found[check[0]])
        async with setup.run_test() as pilot:
            await setup.workers.wait_for_complete()
            await pilot.pause()
            found["a"] = ("/bin/a", True, "1.1")
            await pilot.press("r")
            await setup.workers.wait_for_complete()
            await pilot.pause()
            self.assertEqual(str(setup.query_one(app.DataTable).get_row_at(0)[4]), "ok")

    async def test_r_does_nothing_while_a_scan_runs(self):
        release = threading.Event()
        calls = []

        def slow(check):
            calls.append(check[0])
            release.wait(5)
            return None, False, None

        setup = app.SetupApp(ITEMS[:1], slow)
        async with setup.run_test() as pilot:
            await pilot.press("r", "r")
            release.set()
            await setup.workers.wait_for_complete()
            await pilot.pause()
            self.assertEqual(calls, ["a"])
            self.assertFalse(setup.scanning)


if __name__ == "__main__":
    unittest.main()
