"""Tests for tools/setup/app.py, headless with a fake probe. Skipped where Textual is not installed (CI today)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools" / "setup"))

try:
    import app
except ImportError:
    app = None

ITEMS = [
    {"name": "A", "check": ["a"], "min": "1.0", "tested": "1.2"},
    {"name": "B", "check": ["b"], "min": "1.0", "tested": "1.2"},
]


@unittest.skipIf(app is None, "Textual is not installed; see tools/setup/DESIGN.md")
class SetupAppTest(unittest.IsolatedAsyncioTestCase):
    async def test_table_shows_each_item(self):
        found = {"a": (True, "1.3"), "b": (False, None)}
        setup = app.SetupApp(ITEMS, lambda check: found[check[0]])
        async with setup.run_test() as pilot:
            await setup.workers.wait_for_complete()
            await pilot.pause()
            table = setup.query_one(app.DataTable)
            self.assertEqual(table.row_count, 2)
            self.assertEqual(table.get_row_at(0)[:4], ["A", "1.3", "1.0", "1.2"])
            self.assertEqual(str(table.get_row_at(0)[4]), "not tested yet")
            self.assertEqual(str(table.get_row_at(1)[4]), "missing")
            self.assertEqual(setup.sub_title, "2 checked: 1 not tested yet, 1 missing")

    async def test_check_again_reads_new_versions(self):
        found = {"a": (False, None), "b": (False, None)}
        setup = app.SetupApp(ITEMS, lambda check: found[check[0]])
        async with setup.run_test() as pilot:
            await setup.workers.wait_for_complete()
            found["a"] = (True, "1.1")
            await pilot.press("r")
            await setup.workers.wait_for_complete()
            await pilot.pause()
            self.assertEqual(str(setup.query_one(app.DataTable).get_row_at(0)[4]), "ok")


if __name__ == "__main__":
    unittest.main()
