"""Tests for tools/setup/app.py, headless with a fake probe and runner. Skipped where Textual is not installed (CI)."""

import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools" / "setup"))

try:
    import app
except ImportError:
    app = None

ITEMS = [
    {"id": "a", "name": "A", "kind": "command", "layer": "core", "check": ["a"], "min": "1.0", "tested": "1.2",
     "install": {"all": "get a"}},
    {"id": "b", "name": "B", "kind": "command", "layer": "core", "check": ["b"], "min": "1.0", "tested": "1.2",
     "install": {"all": "get b"}},
    {"id": "c", "name": "C", "kind": "project-file", "layer": "core", "path": ".pm"},
]  # fmt: skip
MAP = {"id": "m", "name": "M", "kind": "command", "layer": "map", "check": ["m"], "min": "1.0", "tested": "1.0",
       "install": {"all": "get m"}}  # fmt: skip


@unittest.skipIf(app is None, "Textual is not installed; see tools/setup/DESIGN.md")
class CheckScreenTest(unittest.IsolatedAsyncioTestCase):
    async def test_table_shows_each_item(self):
        found = {"a": ("/bin/a", True, "1.3"), "b": (None, False, None)}
        setup = app.SetupApp(ITEMS, lambda check: found[check[0]])
        async with setup.run_test(size=(120, 35)) as pilot:
            await setup.workers.wait_for_complete()
            await pilot.pause()
            table = setup.query_one(app.DataTable)
            self.assertEqual(table.row_count, 3)
            self.assertEqual(
                [str(cell) for cell in table.get_row_at(0)], ["A", "1.3", "1.0", "1.2", "! not tested yet", "/bin/a"]
            )
            self.assertEqual(str(table.get_row_at(1)[4]), "✗ missing")
            self.assertEqual(str(table.get_row_at(2)[0]), "1 project item, set up later")
            self.assertEqual(str(table.get_row_at(2)[4]), "· not checked")
            summary = str(setup.query_one("#summary").content)
            self.assertIn("3 items: 1 not tested yet, 1 missing, 1 not checked", summary)
            self.assertIn("Next: install or update B (missing)", summary)

    async def test_path_column_only_when_wide(self):
        found = {"a": ("/bin/a", True, "1.1"), "b": ("/bin/b", True, "1.1")}
        setup = app.SetupApp(ITEMS, lambda check: found[check[0]])
        async with setup.run_test(size=(80, 24)) as pilot:
            await setup.workers.wait_for_complete()
            await pilot.pause()
            table = setup.query_one(app.DataTable)
            self.assertEqual(len(table.columns), 5)
            await pilot.resize_terminal(120, 35)
            await pilot.pause()
            self.assertEqual(len(table.columns), 6)
            self.assertEqual(str(table.get_row_at(0)[5]), "/bin/a")

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
            self.assertEqual(str(setup.query_one(app.DataTable).get_row_at(0)[4]), "✓ ok")

    async def test_r_and_enter_do_nothing_while_a_scan_runs(self):
        release = threading.Event()
        calls = []

        def slow(check):
            calls.append(check[0])
            release.wait(5)
            return None, False, None

        setup = app.SetupApp(ITEMS[:1], slow)
        async with setup.run_test() as pilot:
            await pilot.press("r", "r", "enter")
            self.assertIsInstance(setup.screen, app.Screen)
            self.assertNotIsInstance(setup.screen, app.ChooseScreen)
            release.set()
            await setup.workers.wait_for_complete()
            await pilot.pause()
            self.assertEqual(calls, ["a"])
            self.assertFalse(setup.scanning)

    async def test_c_and_a_click_copy_the_full_path(self):
        found = {"a": ("/a/very/long/folder/a", True, "1.1"), "b": ("/bin/b", True, "1.1")}
        setup = app.SetupApp(ITEMS, lambda check: found[check[0]])
        copied = []
        async with setup.run_test(size=(80, 24)) as pilot:
            setup.copy_to_clipboard = copied.append
            await setup.workers.wait_for_complete()
            await pilot.pause()
            await pilot.press("c")  # Path column hidden at 80 columns: the key still copies
            self.assertEqual(copied, ["/a/very/long/folder/a"])
            await pilot.resize_terminal(120, 35)
            await pilot.pause()
            table = setup.query_one(app.DataTable)
            x = sum(column.get_render_width(table) for column in table.ordered_columns[: app.PATH]) + 2
            await pilot.click(app.DataTable, offset=(x, 2))  # header is line 0, row B is line 2
            self.assertEqual(copied[-1], "/bin/b")

    async def test_a_copies_a_message_for_the_agent(self):
        found = {"a": ("/bin/a", True, "1.1"), "b": ("/bin/b", True, "1.1")}
        setup = app.SetupApp(ITEMS, lambda check: found[check[0]])
        copied = []
        async with setup.run_test() as pilot:
            setup.copy_to_clipboard = copied.append
            await setup.workers.wait_for_complete()
            await pilot.press("a")
            self.assertIn("bom.py", copied[0])
            self.assertIn("--layers core,map", copied[0])
            self.assertIn("only after I say yes", copied[0])


@unittest.skipIf(app is None, "Textual is not installed; see tools/setup/DESIGN.md")
class ChooseAndInstallTest(unittest.IsolatedAsyncioTestCase):
    def make(self, items, found, codes=None):
        """An app whose runner records each command and, on success, makes its program found at version 1.1."""
        self.ran = []
        codes = codes or {}

        def runner(command):
            self.ran.append(command)
            code = codes.get(command, 0)
            if code == 0:
                found[command.split()[-1]] = ("/bin/x", True, "1.1")
            return code

        return app.SetupApp(items, lambda check: found[check[0]], runner=runner, system="linux")

    async def open_install(self, setup, pilot):
        await setup.workers.wait_for_complete()
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        self.assertIsInstance(setup.screen, app.ChooseScreen)
        await pilot.press("enter")
        await pilot.pause()
        self.assertIsInstance(setup.screen, app.InstallScreen)

    async def test_choose_lists_steps_and_map_can_be_unticked(self):
        found = {"a": ("/bin/a", True, "1.1"), "b": (None, False, None), "m": (None, False, None)}
        setup = self.make([*ITEMS, MAP], found)
        async with setup.run_test(size=(120, 35)) as pilot:
            await setup.workers.wait_for_complete()
            await pilot.press("enter")
            await pilot.pause()
            screen = setup.screen
            self.assertEqual([step["id"] for step in screen.steps], ["b", "m"])
            self.assertIn("get b", str(screen.query_one("#steps").content))
            screen.query_one(app.SelectionList).deselect("map")
            await pilot.pause()
            self.assertEqual([step["id"] for step in screen.steps], ["b"])
            self.assertEqual(setup.layers, ("core",))

    async def test_enter_never_runs_a_step_y_does(self):
        found = {"a": (None, False, None), "b": (None, False, None)}
        setup = self.make(ITEMS, found)
        with patch.object(app.shutil, "which", lambda name: f"/bin/{name}"):
            async with setup.run_test(size=(120, 35)) as pilot:
                await self.open_install(setup, pilot)
                await pilot.press("enter", "enter")
                self.assertEqual(self.ran, [])
                await pilot.press("y")
                await pilot.pause()
                screen = setup.screen
                self.assertEqual(self.ran, ["get a"])
                self.assertEqual(screen.states, ["done", "waiting"])
                self.assertEqual(screen.current, 1)  # moved on to the next open step
                screen.quiet_until = 0  # time passes; the user reads step 2
                await pilot.press("y")
                await pilot.pause()
                self.assertTrue(screen.finished)
                self.assertIn("2 of 2 done", str(screen.query_one("#install-hint").content))
                await pilot.press("enter")  # finished: Enter goes back and checks everything again
                await setup.workers.wait_for_complete()
                await pilot.pause()
                self.assertNotIsInstance(setup.screen, (app.ChooseScreen, app.InstallScreen))
                self.assertEqual(str(setup.query_one(app.DataTable).get_row_at(1)[4]), "✓ ok")

    async def test_resizing_on_install_leaves_its_table_alone(self):
        found = {"a": (None, False, None), "b": ("/bin/b", True, "1.1")}
        setup = self.make(ITEMS, found)
        async with setup.run_test(size=(120, 35)) as pilot:
            await self.open_install(setup, pilot)
            await pilot.resize_terminal(80, 24)
            await pilot.pause()
            table = setup.screen.query_one(app.DataTable)
            self.assertEqual(
                [str(column.label) for column in table.columns.values()], ["Step", "Program", "Why", "State"]
            )
            self.assertEqual(table.row_count, 1)
            self.assertEqual(len(setup.table.columns), 5)  # the Check table followed the new width

    async def test_keys_queued_while_a_step_ran_do_not_run_the_next(self):
        found = {"a": (None, False, None), "b": (None, False, None)}
        setup = self.make(ITEMS, found)
        with patch.object(app.shutil, "which", lambda name: f"/bin/{name}"):
            async with setup.run_test(size=(120, 35)) as pilot:
                await self.open_install(setup, pilot)
                await pilot.press("y", "y")  # the second y arrives as the first step returns
                await pilot.pause()
                self.assertEqual(self.ran, ["get a"])
                self.assertEqual(setup.screen.states, ["done", "waiting"])
                setup.screen.quiet_until = 0  # time passes; the user reads step 2 and presses y
                await pilot.press("y")
                await pilot.pause()
                self.assertEqual(self.ran, ["get a", "get b"])

    async def test_back_to_choose_plans_from_the_new_rows(self):
        found = {"a": (None, False, None), "b": (None, False, None)}
        setup = self.make(ITEMS, found)
        with patch.object(app.shutil, "which", lambda name: f"/bin/{name}"):
            async with setup.run_test(size=(120, 35)) as pilot:
                await self.open_install(setup, pilot)
                await pilot.press("y")
                await pilot.pause()
                await pilot.press("escape")
                await pilot.pause()
                self.assertIsInstance(setup.screen, app.ChooseScreen)
                self.assertEqual([step["id"] for step in setup.screen.steps], ["b"])
                self.assertEqual(str(setup.table.get_row_at(0)[4]), "✓ ok")

    async def test_short_terminal_scrolls_to_the_command(self):
        found = {"a": (None, False, None), "b": (None, False, None)}
        setup = self.make(ITEMS, found)
        async with setup.run_test(size=(80, 12)) as pilot:
            await self.open_install(setup, pilot)
            body = setup.screen.query_one("#body")
            self.assertIsInstance(body, app.VerticalScroll)
            self.assertGreater(body.max_scroll_y, 0)

    async def test_a_failed_step_stays_and_can_be_skipped(self):
        found = {"a": (None, False, None), "b": ("/bin/b", True, "1.1")}
        setup = self.make(ITEMS, found, codes={"get a": 3})
        with patch.object(app.shutil, "which", lambda name: f"/bin/{name}"):
            async with setup.run_test(size=(120, 35)) as pilot:
                await self.open_install(setup, pilot)
                await pilot.press("y")
                await pilot.pause()
                screen = setup.screen
                self.assertEqual(screen.states, ["failed"])
                self.assertIn("exit code 3", str(screen.query_one("#command").content))
                await pilot.press("s")
                await pilot.pause()
                self.assertTrue(screen.finished)
                self.assertIn("Still open: A (skipped)", str(screen.query_one("#install-hint").content))

    async def test_exit_0_but_not_found_is_not_done(self):
        found = {"a": (None, False, None), "b": ("/bin/b", True, "1.1")}
        setup = app.SetupApp(ITEMS, lambda check: found[check[0]], runner=lambda command: 0, system="linux")
        with patch.object(app.shutil, "which", lambda name: f"/bin/{name}"):
            async with setup.run_test(size=(120, 35)) as pilot:
                await self.open_install(setup, pilot)
                await pilot.press("y")
                await pilot.pause()
                self.assertEqual(setup.screen.states, ["not-found"])
                self.assertIn("not found yet", str(setup.screen.query_one("#command").content))

    async def test_missing_installer_program_is_not_run(self):
        found = {"a": (None, False, None), "b": ("/bin/b", True, "1.1")}
        setup = self.make(ITEMS, found)
        with patch.object(app.shutil, "which", lambda name: None):
            async with setup.run_test(size=(120, 35)) as pilot:
                await self.open_install(setup, pilot)
                await pilot.press("y")
                await pilot.pause()
                self.assertEqual(self.ran, [])
                self.assertEqual(setup.screen.states, ["waiting"])
                self.assertIn("this step needs get", str(setup.screen.query_one("#command").content))

    async def test_terminal_that_cannot_hand_over_copies_and_r_rechecks(self):
        found = {"a": (None, False, None), "b": ("/bin/b", True, "1.1")}
        setup = app.SetupApp(ITEMS, lambda check: found[check[0]], runner=lambda command: None, system="linux")
        copied = []
        with patch.object(app.shutil, "which", lambda name: f"/bin/{name}"):
            async with setup.run_test(size=(120, 35)) as pilot:
                setup.copy_to_clipboard = copied.append
                await self.open_install(setup, pilot)
                await pilot.press("y")
                await pilot.pause()
                self.assertEqual(copied, ["get a"])
                self.assertEqual(setup.screen.states, ["waiting"])
                found["a"] = ("/bin/a", True, "1.1")  # the user ran it in another terminal
                await pilot.press("r")
                await pilot.pause()
                self.assertEqual(setup.screen.states, ["done"])


if __name__ == "__main__":
    unittest.main()
